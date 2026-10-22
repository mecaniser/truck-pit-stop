"""Lazy, tenant-scoped CallRail media. No persistence, retries or cache; one restricted signed-object hop."""
from __future__ import annotations
import asyncio
import io
import json
import logging
from contextvars import ContextVar
import re
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit, parse_qsl

import httpx
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from app.db.models.callrail import CallRailConversation, CallRailMessageAlias
from app.db.models.sms_message import SMSMessage, SMSMessageDirection
from app.services import callrail_service as cr

HEADERS = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'}
JSON_LIMIT = 2 * 1024 * 1024
INPUT_LIMIT = 5 * 1024 * 1024
OUTPUT_LIMIT = 10 * 1024 * 1024
TIMEOUT = httpx.Timeout(connect=4, read=8, write=4, pool=3)
# httpx logs URLs at INFO; httpcore traces response headers (including Location)
# at DEBUG. Filters belong to emitting loggers, since parent logger filters do
# not run for propagated child records. ContextVar isolation preserves other
# concurrent requests and their trace levels.
_PRIVATE_REQUEST = ContextVar('callrail_private_media_request', default=False)


class _PrivateRequestFilter(logging.Filter):
    def filter(self, record):
        return not _PRIVATE_REQUEST.get()


for _logger_name in ('httpx', 'httpcore.connection', 'httpcore.http11', 'httpcore.http2',
                     'httpcore.proxy', 'httpcore.socks'):
    logging.getLogger(_logger_name).addFilter(_PrivateRequestFilter())
_ERRORS = {'attachment_not_found': (404, 'Attachment not found.'), 'attachment_unsupported': (422, 'This image format is unavailable.'), 'attachment_too_large': (413, 'This image is too large.'), 'attachment_unavailable': (502, 'Attachment is unavailable. Try again later.'), 'attachment_timeout': (504, 'Attachment request timed out.')}


def fail(code):
    status, message = _ERRORS[code]
    raise HTTPException(status, detail={'code': code, 'message': message}, headers=HEADERS)


def candidate(message):
    return bool(message.provider == 'callrail' and message.direction == SMSMessageDirection.INBOUND
        and isinstance(message.body, str) and message.body.endswith(cr.ATTACHMENT_NOTICE)
        and message.callrail_binding_id and message.provider_account_id
        and message.provider_conversation_id and message.provider_message_id)


@dataclass(frozen=True)
class Context:
    message: SMSMessage
    account: str
    conversation: str
    company: str
    contact: str
    credential: str
    aliases: frozenset[str]


async def context_for(db, tenant_id, thread, message_id):
    message = await db.scalar(select(SMSMessage).where(SMSMessage.id == message_id,
        SMSMessage.tenant_id == tenant_id, SMSMessage.thread_id == thread.id, SMSMessage.deleted_at.is_(None)))
    if not message or not candidate(message):
        fail('attachment_not_found')
    mapping = await db.scalar(select(CallRailConversation).where(CallRailConversation.tenant_id == tenant_id,
        CallRailConversation.thread_id == thread.id, CallRailConversation.binding_id == message.callrail_binding_id,
        CallRailConversation.deleted_at.is_(None)))
    if not mapping or mapping.provider_conversation_id != message.provider_conversation_id:
        fail('attachment_not_found')
    try:
        bound = await cr._context_for_mapping(db, mapping, allow_opt_out=True)
    except HTTPException:
        fail('attachment_not_found')
    if (bound.account_id != message.provider_account_id or message.customer_id != mapping.customer_id
        or message.from_number != bound.customer_phone or message.to_number != bound.sender_phone
        or not re.fullmatch(r'[A-Za-z0-9]{1,64}', bound.account_id)
        or not re.fullmatch(r'[A-Za-z0-9]{1,80}', message.provider_conversation_id)):
        fail('attachment_not_found')
    aliases = frozenset(await db.scalars(select(CallRailMessageAlias.alias).where(
        CallRailMessageAlias.message_id == message.id, CallRailMessageAlias.tenant_id == tenant_id,
        CallRailMessageAlias.account_id == bound.account_id, CallRailMessageAlias.deleted_at.is_(None))))
    aliases = frozenset(a for a in aliases if re.fullmatch(r'(?:id:[1-9][0-9]*|resource:SCI[A-Za-z0-9]{1,77})', a))
    if not aliases or not ({f'id:{message.provider_message_id}', f'resource:{message.provider_message_id}'} & aliases):
        fail('attachment_not_found')
    return Context(message, bound.account_id, message.provider_conversation_id, bound.company_id,
                   bound.customer_phone, bound.credential_ref, aliases)


def media_url(url, context, index, *, require_resource=True):
    if not isinstance(url, str) or len(url) > 4096:
        fail('attachment_unavailable')
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'api.callrail.com' or parsed.query or parsed.fragment
            or '%' in parsed.path or '\\' in url):
            fail('attachment_unavailable')
        match = re.fullmatch(r'/v3/a/([A-Za-z0-9]{1,64})/text-messages/(SCI[A-Za-z0-9]{1,77})/media/([0-9])', parsed.path)
        if not match or match[1] != context.account or int(match[3]) != index:
            fail('attachment_unavailable')
        resources = {a.removeprefix('resource:') for a in context.aliases if a.startswith('resource:')}
        if require_resource and resources and resources != {match[2]}:
            fail('attachment_unavailable')
        return match[2]
    except ValueError:
        fail('attachment_unavailable')


async def _read_response(response, limit, *, media=False):
    if response.status_code != 200:
        fail('attachment_unavailable')
    # Negotiate unencoded bodies and reject encoding before httpx can expand
    # a compressed bomb in its decoder. Both JSON and pixels stay bounded.
    if response.headers.get('content-encoding', 'identity').strip().lower() not in {'', 'identity'}:
        fail('attachment_unavailable')
    declared = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    if media and declared not in {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}:
        fail('attachment_unsupported')
    if not media and declared != 'application/json':
        fail('attachment_unavailable')
    length = response.headers.get('content-length')
    if length and (not length.isascii() or not length.isdigit() or len(length) > 10 or int(length) > limit):
        fail('attachment_too_large' if media else 'attachment_unavailable')
    data = bytearray()
    async for chunk in response.aiter_bytes():
        if len(data) + len(chunk) > limit:
            fail('attachment_too_large' if media else 'attachment_unavailable')
        data.extend(chunk)
    return bytes(data), declared


async def bounded_get(client, url, headers, limit, *, media=False):
    async with client.stream('GET', url, headers=headers) as response:
        return await _read_response(response, limit, media=media)


_OBJECT_HOST = 'calltrk-mms-media-prod1.s3.amazonaws.com'
_SIGNED_KEYS = frozenset({'X-Amz-Algorithm', 'X-Amz-Credential', 'X-Amz-Date', 'X-Amz-Expires',
    'X-Amz-Security-Token', 'X-Amz-Signature', 'X-Amz-SignedHeaders',
    'response-content-disposition', 'response-content-type'})
_RASTER_TYPES = frozenset({'image/jpeg', 'image/png', 'image/webp', 'image/gif'})


def signed_object_url(locator, *, now=None):
    """Validate an authenticated provider Location; never rebuild its signature."""
    if (not isinstance(locator, str) or not locator or len(locator) > 16384
        or not locator.startswith('https://') or '\\' in locator
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in locator)
        or re.search(r'%(?![0-9A-Fa-f]{2})', locator)):
        fail('attachment_unavailable')
    try:
        parsed = urlsplit(locator)
        if (parsed.scheme != 'https' or parsed.netloc != _OBJECT_HOST or parsed.fragment
            or len(parsed.path) > 1024 or len(parsed.query) > 12288
            or not re.fullmatch(r'/[A-Za-z0-9_-][A-Za-z0-9_.-]*', parsed.path)
            or '..' in parsed.path):
            fail('attachment_unavailable')
        # Keys themselves must be literal observed SigV4 names. Values are decoded
        # exactly once for validation; the original locator is used unchanged.
        parts = parsed.query.split('&')
        if len(parts) != len(_SIGNED_KEYS) or any(part.split('=', 1)[0] not in _SIGNED_KEYS for part in parts):
            fail('attachment_unavailable')
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True,
                          encoding='utf-8', errors='strict', max_num_fields=9)
        values = dict(pairs)
        if (len(values) != len(pairs) or values.keys() != _SIGNED_KEYS
            or any(not value or any(ord(c) < 32 or ord(c) == 127 for c in value) for value in values.values())):
            fail('attachment_unavailable')
        if (values['X-Amz-Algorithm'] != 'AWS4-HMAC-SHA256'
            or not re.fullmatch(r'[0-9a-f]{64}', values['X-Amz-Signature'])
            or values['X-Amz-SignedHeaders'] != 'host'
            or len(values['X-Amz-Credential']) > 512 or len(values['X-Amz-Security-Token']) > 8192
            or len(values['response-content-disposition']) > 1024
            or values['response-content-type'] not in _RASTER_TYPES):
            fail('attachment_unavailable')
        scope = re.fullmatch(r'([A-Za-z0-9_-]+)/([0-9]{8})/([A-Za-z0-9_-]+)/s3/aws4_request', values['X-Amz-Credential'])
        date = values['X-Amz-Date']
        expiry = values['X-Amz-Expires']
        if (not scope or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z', date)
            or scope[2] != date[:8] or not re.fullmatch(r'[0-9]{1,3}', expiry)
            or not 1 <= int(expiry) <= 300):
            fail('attachment_unavailable')
        signed_at = datetime.strptime(date, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if signed_at > current + timedelta(seconds=60) or signed_at + timedelta(seconds=int(expiry)) <= current:
            fail('attachment_unavailable')
    except (ValueError, UnicodeDecodeError):
        fail('attachment_unavailable')
    return locator


async def media_get(client, url, headers):
    # Only callers that already resolved tenant/message identity and validated
    # this exact CallRail URL may enter the restricted redirect path.
    locator = None
    async with client.stream('GET', url, headers=headers) as response:
        if response.status_code != 302:
            return await _read_response(response, INPUT_LIMIT, media=True)
        locations = response.headers.get_list('location')
        if len(locations) != 1:
            fail('attachment_unavailable')
        locator = signed_object_url(locations[0])
    # The authenticated 302 response is closed before this separate client exists.
    # Its fresh cookie jar/auth and trust_env=False prevent cross-origin secrets.
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as object_client:
        object_client.headers.clear()
        return await bounded_get(object_client, locator,
            {'Accept': 'image/jpeg, image/png, image/webp, image/gif', 'Accept-Encoding': 'identity'},
            INPUT_LIMIT, media=True)


def _identity(item, context):
    aliases = set()
    identifier = item.get('id')
    if isinstance(identifier, int) and not isinstance(identifier, bool) and identifier > 0:
        aliases.add(f'id:{identifier}')
    if isinstance(identifier, str) and re.fullmatch(r'SCI[A-Za-z0-9]{1,77}', identifier):
        aliases.add(f'resource:{identifier}')
    resource = item.get('resource_id')
    if isinstance(resource, str) and re.fullmatch(r'SCI[A-Za-z0-9]{1,77}', resource):
        aliases.add(f'resource:{resource}')
    urls = item.get('media_urls', [])
    if not isinstance(urls, list) or len(urls) > 10:
        fail('attachment_unavailable')
    # Validate every locator before either exposing slots or using a resource alias.
    for index, url in enumerate(urls):
        sci = media_url(url, context, index, require_resource=False)
        if f'resource:{sci}' in context.aliases:
            aliases.add(f'resource:{sci}')
    if not aliases.intersection(context.aliases):
        return None
    for index, url in enumerate(urls):
        media_url(url, context, index)
    # Any additional conflicting numeric/resource identity fails closed.
    for prefix in ('id:', 'resource:'):
        stored = {a for a in context.aliases if a.startswith(prefix)}
        offered = {a for a in aliases if a.startswith(prefix)}
        if stored and offered and stored != offered:
            fail('attachment_not_found')
    try:
        timestamp = cr._date(item.get('created_at'))
        original = context.message.created_at
        original = original.replace(tzinfo=timezone.utc) if original.tzinfo is None else original
    except (ValueError, TypeError, AttributeError):
        fail('attachment_not_found')
    caption = context.message.body[:-len(cr.ATTACHMENT_NOTICE)]
    if caption.endswith('\n\n'):
        caption = caption[:-2]
    if (item.get('direction') != 'incoming' or timestamp != original or (item.get('content') or '') != caption
        or not isinstance(item.get('message_type', item.get('type', 'sms')), str)
        or item.get('message_type', item.get('type', 'sms')).lower() not in {'sms', 'mms'}):
        fail('attachment_not_found')
    return urls


async def discover(client, context, headers):
    found = None
    expected_total = None
    for page in range(1, 11):
        url = f'https://api.callrail.com/v3/a/{context.account}/text-messages/{context.conversation}.json?page={page}&per_page=100'
        raw, _ = await bounded_get(client, url, headers, JSON_LIMIT)
        try:
            record = json.loads(raw)
        except (ValueError, UnicodeDecodeError, RecursionError):
            fail('attachment_unavailable')
        if (not isinstance(record, dict) or record.get('id') != context.conversation
            or record.get('company_id') != context.company or cr._phone(record.get('customer_phone_number')) != context.contact):
            fail('attachment_not_found')
        messages = record.get('messages')
        if not isinstance(messages, list) or len(messages) > 100 or any(not isinstance(i, dict) for i in messages):
            fail('attachment_unavailable')
        for item in messages:
            matched = _identity(item, context)
            if matched is not None:
                if found is not None:
                    fail('attachment_not_found')
                found = matched
        total = record.get('total_pages', 1)
        actual = record.get('page', page)
        if (type(total) is not int or not 1 <= total <= 10 or type(actual) is not int or actual != page
            or (expected_total is not None and total != expected_total)
            or ('per_page' in record and (type(record['per_page']) is not int or record['per_page'] != 100))):
            fail('attachment_unavailable')
        expected_total = total
        if page == total:
            if found is None:
                fail('attachment_not_found')
            return found
    fail('attachment_unavailable')


class _BoundedOutput(io.BytesIO):
    def write(self, data):
        if self.tell() + len(data) > OUTPUT_LIMIT:
            fail('attachment_too_large')
        return super().write(data)


def decode_raster(data, declared):
    expected = {'image/jpeg': {'JPEG', 'MPO'}, 'image/png': {'PNG'},
                'image/webp': {'WEBP'}, 'image/gif': {'GIF'}}
    if len(data) > INPUT_LIMIT:
        fail('attachment_too_large')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            # Pillow otherwise downgrades a broken MPF container to plain JPEG.
            # Fail closed instead of silently accepting malformed MPO metadata.
            warnings.filterwarnings('error', message=r'Image appears to be a malformed MPO file.*', category=UserWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in expected.get(declared, set()):
                    fail('attachment_unsupported')
                # MPO is a JPEG container, not an attachment gallery. Only the
                # primary picture is sought, validated, loaded and copied.
                source.seek(0)
                width, height = source.size
                if width > 8192 or height > 8192 or width * height > 25_000_000:
                    fail('attachment_too_large')
                source.load()
                # Fresh pixels remove metadata, extra frames and trailing bytes.
                oriented = ImageOps.exif_transpose(source)
                mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
                converted = oriented.convert(mode)
                clean = Image.new(mode, converted.size)
                clean.paste(converted)
                output = _BoundedOutput()
                # Lossless output avoids a second lossy/native JPEG codec pass.
                # Bounds apply during encoding; larger photographs fail closed.
                clean.save(output, format='PNG')
                if output.tell() > OUTPUT_LIMIT:
                    fail('attachment_too_large')
                return output.getvalue(), 'image/png'
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        fail('attachment_too_large')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, UserWarning, AssertionError):
        fail('attachment_unsupported')


async def retrieve(context, index=None):
    if index is not None and not 0 <= index <= 9:
        fail('attachment_not_found')
    token = _PRIVATE_REQUEST.set(True)
    try:
        async with asyncio.timeout(20):
            try:
                key = cr.secret(context.credential)
            except HTTPException:
                fail('attachment_unavailable')
            headers = {'Authorization': f'Token token="{key}"', 'Request-From': 'dieselbridge', 'Accept-Encoding': 'identity'}
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
                urls = await discover(client, context, headers)
                if index is None:
                    return {'items': [{'index': i, 'kind': 'image'} for i in range(len(urls))]}
                if index >= len(urls):
                    fail('attachment_not_found')
                data, declared = await media_get(client, urls[index], headers)
                return await asyncio.to_thread(decode_raster, data, declared)
    except (TimeoutError, httpx.TimeoutException):
        fail('attachment_timeout')
    except httpx.HTTPError:
        fail('attachment_unavailable')
    finally:
        _PRIVATE_REQUEST.reset(token)
