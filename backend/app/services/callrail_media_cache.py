"""Durable encrypted media reuse. Cached identities contain no provider URLs."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.models.callrail import CallRailMediaCache
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage
from app.db.session import AsyncSessionLocal
from app.services import callrail_media as media


def _ring():
    try:
        active = settings.CALLRAIL_MEDIA_ACTIVE_KEY_VERSION
        keys = json.loads(settings.CALLRAIL_MEDIA_ENCRYPTION_KEYS)
        if not isinstance(keys, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', active):
            raise ValueError()
        if any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', name) for name in keys):
            raise ValueError()
        ring = {name: Fernet(key.encode()) for name, key in keys.items()}
        if active not in ring:
            raise ValueError()
        return active, ring
    except (ValueError, TypeError, AttributeError):
        media.fail('attachment_unavailable')


def fingerprint(context):
    message = context.message
    fields = [str(message.tenant_id), str(message.thread_id), str(message.id),
        str(message.callrail_binding_id), context.account, context.company, context.conversation,
        context.contact, context.credential, message.from_number, message.to_number,
        message.provider_message_id, message.body, message.created_at.isoformat(), sorted(context.aliases)]
    return hashlib.sha256(json.dumps(fields, separators=(',', ':')).encode()).hexdigest()


def _seal(payload, tenant_id, message_id, slot, digest):
    active, ring = _ring()
    data = json.dumps({'scope': [str(tenant_id), str(message_id), slot, digest], 'payload': payload},
                      separators=(',', ':')).encode()
    return active + ':' + ring[active].encrypt(data).decode()


def _open(row, digest):
    _active, ring = _ring()
    try:
        version, ciphertext = row.encrypted_payload.split(':', 1)
        value = json.loads(ring[version].decrypt(ciphertext.encode()))
        if value['scope'] != [str(row.tenant_id), str(row.message_id), row.slot, digest]:
            raise ValueError()
        return value['payload']
    except (ValueError, KeyError, TypeError, AttributeError, InvalidToken):
        # Corruption or unavailable old key must never create a paid refetch loop.
        media.fail('attachment_unavailable')


async def retrieve_cached(original, index=None):
    try:
        async with asyncio.timeout(20):
            return await _retrieve_cached(original, index)
    except TimeoutError:
        media.fail('attachment_timeout')


async def _retrieve_cached(original, index=None):
    if index is not None and (type(index) is not int or not 0 <= index <= 9):
        media.fail('attachment_not_found')
    _ring()  # Fail before spending if encrypted persistence is unavailable.
    failure = None
    async with AsyncSessionLocal() as db:
        async with db.begin():
            # Lock an existing tenant-scoped parent, so even the first concurrent
            # cache miss has one owner across processes. Re-read access after wait.
            message = await db.scalar(select(SMSMessage).where(
                SMSMessage.id == original.message.id,
                SMSMessage.tenant_id == original.message.tenant_id,
                SMSMessage.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
            if not message:
                media.fail('attachment_not_found')
            thread = await db.scalar(select(MessageThread).where(MessageThread.id == message.thread_id,
                MessageThread.tenant_id == message.tenant_id, MessageThread.deleted_at.is_(None))
                .execution_options(populate_existing=True))
            if not thread:
                media.fail('attachment_not_found')
            context = await media.context_for(db, message.tenant_id, thread, message.id)
            digest = fingerprint(context)
            now = datetime.now(UTC)
            rows = list(await db.scalars(select(CallRailMediaCache).where(
                CallRailMediaCache.tenant_id == message.tenant_id,
                CallRailMediaCache.message_id == message.id)))
            valid = {}
            for row in rows:
                expiry = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
                if expiry <= now or row.fingerprint != digest or row.deleted_at is not None:
                    await db.delete(row)
                else:
                    valid[row.slot] = row
            await db.flush()

            def store(slot, payload, expiry):
                row = CallRailMediaCache(tenant_id=message.tenant_id, message_id=message.id, slot=slot,
                    fingerprint=digest, encrypted_payload=_seal(payload, message.tenant_id, message.id, slot, digest),
                    expires_at=expiry)
                db.add(row)
                return row

            manifest = valid.get(-1)
            if manifest:
                resources = _open(manifest, digest)
                if (not isinstance(resources, list) or len(resources) > 10
                    or any(not isinstance(resource, str) or not re.fullmatch(r'SCI[A-Za-z0-9]{1,77}', resource)
                           for resource in resources)):
                    media.fail('attachment_unavailable')
            else:
                urls = await media.retrieve(context, return_urls=True)
                resources = [media.media_url(url, context, i) for i, url in enumerate(urls)]
                manifest = store(-1, resources, now + timedelta(days=30))
            if index is None:
                result = {'items': [{'index': i, 'kind': 'image'} for i in range(len(resources))]}
            else:
                if index >= len(resources):
                    media.fail('attachment_not_found')
                image = valid.get(index)
                if image:
                    try:
                        payload = _open(image, digest)
                        data = base64.b64decode(payload['data'], validate=True)
                        if (payload['content_type'] != 'image/png' or payload['size'] != len(data)
                            or payload['sha256'] != hashlib.sha256(data).hexdigest()):
                            raise ValueError()
                    except (ValueError, TypeError, KeyError):
                        media.fail('attachment_unavailable')
                    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) > media.OUTPUT_LIMIT:
                        media.fail('attachment_unavailable')
                    result = data, 'image/png'
                else:
                    urls = [f'https://api.callrail.com/v3/a/{context.account}/text-messages/{resource}/media/{i}'
                            for i, resource in enumerate(resources)]
                    for i, url in enumerate(urls):
                        media.media_url(url, context, i)
                    try:
                        data, kind = await media.retrieve(context, index, urls=urls)
                    except HTTPException as exc:
                        # Preserve already validated discovery even when an image
                        # is unsupported, the provider is down, or budget is spent.
                        failure, result = exc, None
                    else:
                        store(index, {'data': base64.b64encode(data).decode(), 'size': len(data),
                            'content_type': kind, 'sha256': hashlib.sha256(data).hexdigest()}, manifest.expires_at)
                        result = data, kind
            # A binding/contact may be revoked while upstream/decode was in flight.
            current = await media.context_for(db, message.tenant_id, thread, message.id)
            if fingerprint(current) != digest:
                media.fail('attachment_not_found')
            # Commit durable encrypted bytes before returning to the HTTP route.
        if failure:
            raise failure
        return result


async def purge_expired(db, *, now=None):
    """Local-only retention job; no upstream I/O or cache refresh."""
    await db.execute(delete(CallRailMediaCache).where(CallRailMediaCache.expires_at <= (now or datetime.now(UTC))))
