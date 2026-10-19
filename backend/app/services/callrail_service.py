"""Manual P2P CallRail adapter. No retries, discovery, forwarding or automation writes."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from uuid import UUID
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from app.db.models.callrail import CallRailNumberBinding, CallRailConversation, CallRailMessageAlias, CallRailQuarantine
from app.db.models.communication import ConversationWorkflow, SMSSendOperation
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.tenant import Tenant
from app.db.models.sms_message import SMSMessage, SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
from app.services.messaging_service import _normalize_for_twilio


def deny(code):
    raise HTTPException(409, detail={'code': code, 'message': 'CallRail sending requires a verified conversation binding.'})


def secret(reference):
    """Only dedicated env names may resolve credentials; never arbitrary process vars."""
    if not re.fullmatch(r'CALLRAIL_[A-Z0-9_]{1,110}', reference or ''):
        deny('callrail_credentials_unavailable')
    value = os.getenv(reference, '')
    if not value or '\n' in value or '\r' in value or '"' in value:
        deny('callrail_credentials_unavailable')
    return value


def valid_signature(raw, signature, signing_key):
    expected = base64.b64encode(hmac.new(signing_key.encode(), raw, hashlib.sha1).digest()).decode()
    return isinstance(signature, str) and signature.isascii() and hmac.compare_digest(expected, signature)


def _phone(value):
    return _normalize_for_twilio(value) if isinstance(value, str) else ""


@dataclass(frozen=True)
class CallRailContext:
    binding_id: UUID
    tenant_id: UUID
    thread_id: UUID
    customer_id: UUID
    account_id: str
    company_id: str
    tracker_id: str
    sender_phone: str
    customer_phone: str
    credential_ref: str


async def resolve_for_thread(db, tenant_id, thread_id, *, allow_opt_out=False):
    mapping = await db.scalar(select(CallRailConversation).where(
        CallRailConversation.thread_id == thread_id, CallRailConversation.tenant_id == tenant_id,
        CallRailConversation.deleted_at.is_(None)))
    if not mapping:
        return None
    binding = await db.get(CallRailNumberBinding, mapping.binding_id)
    thread = await db.get(MessageThread, thread_id)
    customer = await db.get(Customer, mapping.customer_id)
    tenant = await db.get(Tenant, tenant_id)
    if not binding or not binding.enabled or binding.deleted_at is not None:
        deny('callrail_binding_disabled')
    if (binding.tenant_id != tenant_id or not thread or thread.tenant_id != tenant_id
        or thread.deleted_at is not None or thread.customer_id != mapping.customer_id
        or not customer or customer.tenant_id != tenant_id or customer.deleted_at is not None
        or not tenant or not tenant.is_active or tenant.deleted_at is not None):
        deny('callrail_binding_changed')
    if (_phone(customer.phone) != mapping.customer_phone
        or (thread.customer_phone and _phone(thread.customer_phone) != mapping.customer_phone)):
        deny('callrail_contact_changed')
    if customer.sms_opt_out and not allow_opt_out:
        deny('recipient_opted_out')
    return CallRailContext(binding.id, tenant_id, thread_id, customer.id,
                           binding.account_id, binding.company_id, binding.tracker_id,
                           binding.sender_phone, mapping.customer_phone, binding.credential_ref)


def _current_tracker(record):
    # CallRail documents JSON null as "initial_tracker_id is the current tracker".
    # A present but different/malformed current identifier must never fall back.
    current = record.get('current_tracker_id')
    return record.get('initial_tracker_id') if current is None else current


async def send(context, body, to, *, source="manual"):
    """One HTTP attempt only. Caller durably claims an intent before invoking."""
    if source != 'manual':
        deny('callrail_manual_only')
    if not isinstance(body, str) or not body.strip() or len(body) > 140:
        deny('callrail_body_length')
    if _phone(to) != context.customer_phone:
        deny('callrail_contact_changed')
    if not re.fullmatch(r'[A-Za-z0-9]+', context.account_id):
        deny('callrail_binding_changed')
    headers = {'Authorization': f'Token token="{secret(context.credential_ref)}"', 'Request-From': 'dieselbridge'}
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
        response = await client.post(f'https://api.callrail.com/v3/a/{context.account_id}/text-messages.json',
            headers=headers, json={'company_id': context.company_id, 'tracking_number': context.sender_phone,
                                  'customer_phone_number': to, 'content': body})
    # Do not include provider response bodies in raised errors; they may contain PII.
    if response.status_code >= 400:
        # Explicit client rejection is definitive; 5xx/transport are unknown outcomes.
        if 400 <= response.status_code < 500 and response.status_code not in {408, 429}:
            raise CallRailRejected(str(response.status_code))
        raise RuntimeError('CallRail outcome unknown')
    if response.status_code != 201:
        raise RuntimeError('CallRail outcome unknown')
    result = response.json()
    identifier = result.get('id')
    if (not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9]{1,80}', identifier)
        or result.get('company_id') != context.company_id
        or _phone(result.get('customer_phone_number')) != context.customer_phone
        or _phone(result.get('current_tracking_number')) != context.sender_phone
        or _current_tracker(result) != context.tracker_id):
        raise RuntimeError('CallRail outcome requires reconciliation')
    return {'conversation_id': identifier}


class CallRailRejected(Exception):
    pass


def _date(value):
    if not isinstance(value, str):
        raise ValueError('invalid timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp missing zone')
    return result.astimezone(timezone.utc)


async def _quarantine(db, binding, payload, reason):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    existing = await db.scalar(select(CallRailQuarantine.id).where(
        CallRailQuarantine.binding_id == binding.id, CallRailQuarantine.event_hash == digest))
    if not existing:
        # Drop ephemeral media/auth URLs and unrelated attribution data.
        safe = {k: payload[k] for k in ('id', 'resource_id', 'source_number', 'destination_number', 'content',
            'message_type', 'timestamp', 'conversation_id', 'company_resource_id') if k in payload}
        db.add(CallRailQuarantine(tenant_id=binding.tenant_id, binding_id=binding.id,
                                 event_hash=digest, reason=reason, payload=safe))
    await db.flush()
    return {'status': 'quarantined', 'reason': reason}


async def apply_event(db, binding_id, payload, event_kind, *, historical=False, failed=False):
    """Caller validates signature before parsing. Serial binding lock makes replay safe."""
    binding = await db.scalar(select(CallRailNumberBinding).where(CallRailNumberBinding.id == binding_id)
                              .with_for_update().execution_options(populate_existing=True))
    if not binding:
        raise HTTPException(404, 'Unknown CallRail binding')
    if event_kind not in {'received', 'sent'} or not isinstance(payload, dict):
        raise HTTPException(422, 'Invalid CallRail event')
    if not binding.enabled or binding.deleted_at is not None:
        return await _quarantine(db, binding, payload, 'binding_disabled')
    if payload.get('company_resource_id') != binding.company_id:
        return await _quarantine(db, binding, payload, 'company_mismatch')
    inbound = event_kind == 'received'
    sender = _phone(payload.get('source_number'))
    recipient = _phone(payload.get('destination_number'))
    if (recipient if inbound else sender) != binding.sender_phone:
        return await _quarantine(db, binding, payload, 'sender_mismatch')
    contact_phone = sender if inbound else recipient
    mapping = await db.scalar(select(CallRailConversation).where(
        CallRailConversation.binding_id == binding.id, CallRailConversation.tenant_id == binding.tenant_id,
        CallRailConversation.customer_phone == contact_phone, CallRailConversation.deleted_at.is_(None)))
    if not mapping:
        return await _quarantine(db, binding, payload, 'unmapped_contact')
    try:
        context = await resolve_for_thread(db, binding.tenant_id, mapping.thread_id, allow_opt_out=True)
    except HTTPException:
        return await _quarantine(db, binding, payload, 'contact_changed')
    if not context or context.binding_id != binding.id:
        return await _quarantine(db, binding, payload, 'binding_changed')
    conversation_id = payload.get('conversation_id')
    if (not isinstance(conversation_id, str) or not re.fullmatch(r'[A-Za-z0-9]{1,80}', conversation_id)):
        return await _quarantine(db, binding, payload, 'conversation_mismatch')
    try:
        timestamp = _date(payload.get('timestamp'))
    except (ValueError, TypeError):
        return await _quarantine(db, binding, payload, 'invalid_timestamp')
    if not historical and abs(datetime.now(timezone.utc) - timestamp) > timedelta(days=7):
        return await _quarantine(db, binding, payload, 'stale_timestamp')
    content = payload.get('content')
    if (not isinstance(content, str) or len(content) > 10000 or not isinstance(payload.get('message_type', 'sms'), str)
        or payload.get('message_type', 'sms').lower() != 'sms'
        or payload.get('media_urls')):
        return await _quarantine(db, binding, payload, 'unsupported_message')
    aliases = []
    numeric = payload.get('id')
    if isinstance(numeric, int) and not isinstance(numeric, bool) and numeric > 0:
        aliases.append(f'id:{numeric}')
    resource = payload.get('resource_id')
    if isinstance(resource, str) and re.fullmatch(r'SCI[A-Za-z0-9]{1,77}', resource):
        aliases.append(f'resource:{resource}')
    if not aliases or (not historical and len(aliases) != 2):
        return await _quarantine(db, binding, payload, 'missing_message_identity')
    existing_aliases = (await db.scalars(select(CallRailMessageAlias).where(
        CallRailMessageAlias.account_id == binding.account_id, CallRailMessageAlias.alias.in_(aliases)))).all()
    if len({row.message_id for row in existing_aliases}) > 1:
        return await _quarantine(db, binding, payload, 'identity_conflict')
    message = await db.get(SMSMessage, existing_aliases[0].message_id) if existing_aliases else None
    if message and (message.tenant_id != binding.tenant_id or message.thread_id != mapping.thread_id
                    or message.body != content or message.from_number != sender or message.to_number != recipient
                    or message.direction.value != ('inbound' if inbound else 'outbound')):
        return await _quarantine(db, binding, payload, 'identity_conflict')
    thread = await db.scalar(select(MessageThread).where(MessageThread.id == mapping.thread_id).with_for_update())
    replayed = message is not None
    if not message and not inbound:
        plausible = (await db.scalars(select(SMSSendOperation).where(
            SMSSendOperation.tenant_id == binding.tenant_id, SMSSendOperation.thread_id == mapping.thread_id,
            SMSSendOperation.callrail_binding_id == binding.id, SMSSendOperation.provider == 'callrail',
            SMSSendOperation.to_number == contact_phone, SMSSendOperation.from_number == binding.sender_phone,
            SMSSendOperation.state.in_(['dispatching', 'accepted', 'unknown']),
            SMSSendOperation.provider_message_id.is_(None)).with_for_update())).all()
        def body_matches(operation):
            canonical = operation.body
            return content == canonical or content.split() == (canonical + ' Reply STOP to opt out.').split()
        candidates = [operation for operation in plausible if body_matches(operation)
            and operation.dispatch_started_at is not None
            and timestamp - timedelta(minutes=5) <= operation.dispatch_started_at <= timestamp + timedelta(seconds=30)]
        if len(candidates) > 1:
            return await _quarantine(db, binding, payload, 'ambiguous_send_receipt')
        if plausible and not candidates:
            return await _quarantine(db, binding, payload, 'unmatched_send_receipt')
        if candidates:
            operation = candidates[0]
            message = await db.get(SMSMessage, operation.message_id)
            message.body = content
            operation.provider_message_id = resource or str(numeric)
            operation.provider_conversation_id = conversation_id
            operation.state = 'accepted'
            operation.reconciliation_state = 'matched'
    if not message:
        message = SMSMessage(tenant_id=binding.tenant_id, thread_id=mapping.thread_id, customer_id=mapping.customer_id,
            direction=SMSMessageDirection.INBOUND if inbound else SMSMessageDirection.OUTBOUND,
            source=SMSMessageSource.INBOUND if inbound else SMSMessageSource.MANUAL,
            body=content, from_number=sender, to_number=recipient, created_at=timestamp)
        db.add(message)
    message.provider = 'callrail'
    message.provider_account_id = binding.account_id
    message.callrail_binding_id = binding.id
    message.provider_message_id = resource or message.provider_message_id or str(numeric)
    message.provider_conversation_id = conversation_id
    if replayed and failed and message.delivery_status == SMSDeliveryStatus.SENT:
        message.delivery_status = SMSDeliveryStatus.FAILED
        message.failed_at = timestamp
    if not replayed:
        message.delivery_status = SMSDeliveryStatus.DELIVERED if inbound else (SMSDeliveryStatus.FAILED if failed else SMSDeliveryStatus.SENT)
        message.sent_at = timestamp
        if inbound:
            message.delivered_at = timestamp
        elif failed:
            message.failed_at = timestamp
    await db.flush()
    for alias in aliases:
        if not any(row.alias == alias for row in existing_aliases):
            db.add(CallRailMessageAlias(tenant_id=binding.tenant_id, account_id=binding.account_id, alias=alias, message_id=message.id))
    mapping.provider_conversation_id = conversation_id
    latest = thread.last_message_at
    if latest and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    if not latest or timestamp >= latest:
        thread.last_message_at = timestamp
        thread.last_message_preview = content[:160]
    if inbound and not replayed:
        thread.unread_count_staff = (thread.unread_count_staff or 0) + 1
        workflow = await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.thread_id == thread.id))
        if workflow:
            workflow.status = 'open'
            workflow.version += 1
        else:
            db.add(ConversationWorkflow(tenant_id=binding.tenant_id, thread_id=thread.id, status='open', version=2))
        if content.strip().upper() in {'STOP', 'CANCEL', 'UNSUBSCRIBE', 'QUIT', 'END'}:
            customer = await db.get(Customer, mapping.customer_id)
            customer.sms_opt_out = True
            customer.sms_opted_out_at = timestamp
            customer.sms_opt_out_source = 'callrail_inbound'
    await db.flush()
    return {'status': 'duplicate' if replayed else 'received', 'message_id': str(message.id)}


async def import_conversation(db, binding_id, thread_id, record):
    """Import an authenticated API response for one explicitly mapped conversation."""
    binding = await db.get(CallRailNumberBinding, binding_id)
    if not binding:
        raise HTTPException(404, 'Unknown CallRail binding')
    context = await resolve_for_thread(db, binding.tenant_id, thread_id, allow_opt_out=True)
    if (not context or context.binding_id != binding_id or record.get('company_id') != context.company_id
        or _current_tracker(record) != context.tracker_id
        or _phone(record.get('current_tracking_number')) != context.sender_phone
        or _phone(record.get('customer_phone_number')) != context.customer_phone):
        deny('callrail_import_scope_mismatch')
    results = []
    for item in record.get('messages', []):
        direction = item.get('direction')
        if direction not in {'incoming', 'outgoing'}:
            deny('callrail_import_invalid')
        incoming = direction == 'incoming'
        payload = dict(item, company_resource_id=context.company_id, conversation_id=record.get('id'),
            source_number=context.customer_phone if incoming else context.sender_phone,
            destination_number=context.sender_phone if incoming else context.customer_phone,
            timestamp=item.get('created_at'), message_type=item.get('type', 'sms'))
        results.append(await apply_event(db, binding_id, payload, 'received' if incoming else 'sent', historical=True,
                                        failed=item.get('status') in {'error', 'failed'}))
    return results
