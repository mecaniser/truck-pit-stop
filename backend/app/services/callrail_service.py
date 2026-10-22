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
from sqlalchemy import select, or_
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
    customer_id: UUID | None
    account_id: str
    company_id: str
    tracker_id: str
    sender_phone: str
    customer_phone: str
    credential_ref: str


async def resolve_for_thread(db, tenant_id, thread_id, *, allow_opt_out=False):
    mapping = await db.scalar(select(CallRailConversation).where(
        CallRailConversation.thread_id == thread_id, CallRailConversation.tenant_id == tenant_id,
        CallRailConversation.deleted_at.is_(None), CallRailConversation.selected_for_sending.is_(True)))
    if not mapping:
        return None
    return await _context_for_mapping(db, mapping, allow_opt_out=allow_opt_out)


async def _context_for_mapping(db, mapping, *, allow_opt_out=False):
    tenant_id, thread_id = mapping.tenant_id, mapping.thread_id
    binding = await db.get(CallRailNumberBinding, mapping.binding_id, populate_existing=True)
    thread = await db.get(MessageThread, thread_id, populate_existing=True)
    customer = await db.get(Customer, mapping.customer_id, populate_existing=True) if mapping.customer_id else None
    tenant = await db.get(Tenant, tenant_id, populate_existing=True)
    if not binding or not binding.enabled or binding.deleted_at is not None:
        deny('callrail_binding_disabled')
    if (binding.tenant_id != tenant_id or not thread or thread.tenant_id != tenant_id
        or thread.deleted_at is not None or thread.customer_id != mapping.customer_id
        or not tenant or not tenant.is_active or tenant.deleted_at is not None or not tenant.messaging_enabled):
        deny('callrail_binding_changed')
    if thread.thread_kind == 'inquiry':
        if (thread.customer_id is not None or mapping.customer_id is not None
            or thread.inquiry_binding_id != binding.id or _phone(thread.customer_phone) != mapping.customer_phone
            or not re.fullmatch(r'\+1\d{10}', mapping.customer_phone)):
            deny('callrail_binding_changed')
        opted_out = thread.inquiry_opted_out
    elif thread.thread_kind == 'customer':
        if (not customer or customer.tenant_id != tenant_id or customer.deleted_at is not None
            or thread.inquiry_binding_id is not None):
            deny('callrail_binding_changed')
        if (_phone(customer.phone) != mapping.customer_phone
            or (thread.customer_phone and _phone(thread.customer_phone) != mapping.customer_phone)):
            deny('callrail_contact_changed')
        opted_out = customer.sms_opt_out
    else:
        deny('callrail_binding_changed')
    if opted_out and not allow_opt_out:
        deny('recipient_opted_out')
    return CallRailContext(binding.id, tenant_id, thread_id, mapping.customer_id,
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
    if response.status_code not in {200, 201}:
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


ATTACHMENT_NOTICE = '[Attachment received in CallRail. Open CallRail to view.]'


def _event_content(payload, *, inbound):
    """Persist a visible receipt, never an expiring provider media URL."""
    kind = payload.get('message_type', 'sms')
    content = payload.get('content')
    media = payload.get('media_urls')
    if (not isinstance(kind, str) or kind.lower() not in {'sms', 'mms'}
        or (media is not None and (not isinstance(media, list) or len(media) > 10
            or any(not isinstance(item, str) or not item or len(item) > 4096 for item in media)))):
        return None
    attachment = kind.lower() == 'mms' or bool(media)
    if not attachment:
        return (content, content) if isinstance(content, str) and len(content) <= 10000 else None
    if not inbound or (content is not None and not isinstance(content, str)):
        return None
    caption = content or ''
    if len(caption) > 10000:
        return None
    return ((caption + '\n\n' if caption else '') + ATTACHMENT_NOTICE, caption)


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
    conversation_id = payload.get('conversation_id')
    if (not isinstance(conversation_id, str) or not re.fullmatch(r'[A-Za-z0-9]{1,80}', conversation_id)):
        return await _quarantine(db, binding, payload, 'conversation_mismatch')
    try:
        timestamp = _date(payload.get('timestamp'))
    except (ValueError, TypeError):
        return await _quarantine(db, binding, payload, 'invalid_timestamp')
    if not historical and abs(datetime.now(timezone.utc) - timestamp) > timedelta(days=7):
        return await _quarantine(db, binding, payload, 'stale_timestamp')
    normalized = _event_content(payload, inbound=inbound)
    if normalized is None:
        return await _quarantine(db, binding, payload, 'unsupported_message')
    content, opt_out_content = normalized
    aliases = []
    numeric = payload.get('id')
    if isinstance(numeric, int) and not isinstance(numeric, bool) and numeric > 0:
        aliases.append(f'id:{numeric}')
    resource = payload.get('resource_id')
    if historical and not resource and isinstance(numeric, str) and numeric.startswith('SCI'):
        resource = numeric
    if isinstance(resource, str) and re.fullmatch(r'SCI[A-Za-z0-9]{1,77}', resource):
        aliases.append(f'resource:{resource}')
    if not aliases or (not historical and not any(alias.startswith('resource:') for alias in aliases)):
        return await _quarantine(db, binding, payload, 'missing_message_identity')
    existing_aliases = (await db.scalars(select(CallRailMessageAlias).where(
        CallRailMessageAlias.account_id == binding.account_id, CallRailMessageAlias.alias.in_(aliases)))).all()
    if not re.fullmatch(r'\+1\d{10}', contact_phone or ''):
        return await _quarantine(db, binding, payload, 'invalid_contact_phone')
    mapping = await db.scalar(select(CallRailConversation).where(
        CallRailConversation.binding_id == binding.id, CallRailConversation.tenant_id == binding.tenant_id,
        CallRailConversation.customer_phone == contact_phone))
    if mapping and mapping.deleted_at is not None:
        return await _quarantine(db, binding, payload, 'contact_changed')
    if not mapping:
        tenant = await db.get(Tenant, binding.tenant_id)
        if (not inbound or historical or not binding.accept_new_inquiries):
            return await _quarantine(db, binding, payload, 'unmapped_contact')
        if not tenant or not tenant.is_active or tenant.deleted_at is not None or not tenant.messaging_enabled:
            return await _quarantine(db, binding, payload, 'tenant_inactive')
        if existing_aliases:
            return await _quarantine(db, binding, payload, 'identity_conflict')
        inquiry = MessageThread(tenant_id=binding.tenant_id, thread_kind='inquiry', customer_id=None,
            inquiry_binding_id=binding.id, customer_phone=contact_phone, inquiry_opted_out=False)
        db.add(inquiry)
        await db.flush()
        mapping = CallRailConversation(tenant_id=binding.tenant_id, thread_id=inquiry.id, customer_id=None,
            binding_id=binding.id, customer_phone=contact_phone, selected_for_sending=True)
        db.add(mapping)
        await db.flush()
    try:
        context = await _context_for_mapping(db, mapping, allow_opt_out=True)
    except HTTPException:
        return await _quarantine(db, binding, payload, 'contact_changed')
    if not context or context.binding_id != binding.id:
        return await _quarantine(db, binding, payload, 'binding_changed')
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
            body=content, from_number=sender, to_number=recipient, created_at=timestamp,
            provider='callrail', callrail_binding_id=binding.id, provider_account_id=binding.account_id)
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
        if opt_out_content.strip().upper() in {'STOP', 'CANCEL', 'UNSUBSCRIBE', 'QUIT', 'END'}:
            if thread.thread_kind == 'inquiry':
                thread.inquiry_opted_out = True
            else:
                customer = await db.get(Customer, mapping.customer_id)
                customer.sms_opt_out = True
                customer.sms_opted_out_at = timestamp
                customer.sms_opt_out_source = 'callrail_inbound'
    await db.flush()
    return {'status': 'duplicate' if replayed else 'received', 'message_id': str(message.id)}


async def import_conversation(db, binding_id, thread_id, record, *, verified_message_ids=frozenset()):
    """Import only receipts with proven sender provenance.

    API conversation-level current_tracking_number does not identify historical
    message senders. New rows require an explicit operator-verified ID allowlist;
    existing aliases may be reconciled without re-attributing prior history.
    This helper is server/operator-only, never accepts client-provided allowlists.
    """
    binding = await db.scalar(select(CallRailNumberBinding).where(CallRailNumberBinding.id == binding_id)
                              .with_for_update().execution_options(populate_existing=True))
    if not binding:
        raise HTTPException(404, 'Unknown CallRail binding')
    route = await db.scalar(select(CallRailConversation).where(CallRailConversation.tenant_id == binding.tenant_id,
        CallRailConversation.thread_id == thread_id, CallRailConversation.binding_id == binding_id,
        CallRailConversation.deleted_at.is_(None)))
    context = await _context_for_mapping(db, route, allow_opt_out=True) if route else None
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
            timestamp=item.get('created_at'), message_type=item.get('message_type', item.get('type', 'sms')))
        identifier = item.get('id')
        aliases = []
        if isinstance(identifier, int) and not isinstance(identifier, bool) and identifier > 0:
            aliases.append(f'id:{identifier}')
        if isinstance(identifier, str) and re.fullmatch(r'SCI[A-Za-z0-9]{1,77}', identifier):
            aliases.append(f'resource:{identifier}')
        resource = item.get('resource_id')
        if isinstance(resource, str) and re.fullmatch(r'SCI[A-Za-z0-9]{1,77}', resource):
            aliases.append(f'resource:{resource}')
        known = await db.scalar(select(CallRailMessageAlias.id).where(
            CallRailMessageAlias.account_id == binding.account_id, CallRailMessageAlias.tenant_id == binding.tenant_id,
            CallRailMessageAlias.alias.in_(aliases))) if aliases else None
        verified = isinstance(identifier, (int, str)) and not isinstance(identifier, bool) and identifier in verified_message_ids
        if not known and not verified:
            results.append(await _quarantine(db, binding, payload, 'historical_sender_unproven'))
            continue
        results.append(await apply_event(db, binding_id, payload, 'received' if incoming else 'sent', historical=True,
                                        failed=item.get('status') in {'error', 'failed'}))
    return results


async def sender_context(db, tenant, thread):
    from app.services import automatic_sms_route as automatic
    customer = await db.get(Customer, thread.customer_id) if thread.customer_id else None
    recipient = _phone(thread.customer_phone if thread.thread_kind == 'inquiry' else customer.phone if customer else '')
    try:
        return (await automatic.resolve(db, tenant, thread, recipient)).context()
    except HTTPException as exc:
        return dict(sms_provider=None, sender_number='', selected_sender_id=None,
                    sender_selection_allowed=False, sender_mode='unavailable', sender_route_reason=exc.detail['code'])


async def lock_sender_bindings(db, tenant_id):
    """Lock before the thread, matching the callback binding -> thread lock order."""
    return (await db.scalars(select(CallRailNumberBinding).where(
        CallRailNumberBinding.tenant_id == tenant_id).order_by(CallRailNumberBinding.id).with_for_update()
        .execution_options(populate_existing=True))).all()


async def set_sender(db, tenant, thread, binding_id):
    """Caller holds tenant binding locks and thread lock; never sends or changes history."""
    from app.db.models.automated_sms import AutomatedSMSOperation
    if thread.thread_kind == 'inquiry':
        if binding_id == thread.inquiry_binding_id:
            await resolve_for_thread(db, tenant.id, thread.id, allow_opt_out=True)
            return False
        deny('inquiry_sender_locked')
    if thread.thread_kind != 'customer':
        deny('callrail_binding_changed')
    mapping = await db.scalar(select(CallRailConversation).where(CallRailConversation.thread_id == thread.id,
        CallRailConversation.tenant_id == tenant.id, CallRailConversation.deleted_at.is_(None),
        CallRailConversation.selected_for_sending.is_(True)))
    if binding_id is None and (not mapping or mapping.deleted_at is not None):
        return False
    binding = None
    if binding_id is not None:
        binding = await db.scalar(select(CallRailNumberBinding).where(CallRailNumberBinding.id == binding_id,
            CallRailNumberBinding.tenant_id == tenant.id))
        if not binding:
            raise HTTPException(404, detail={'code': 'not_found', 'message': 'Sender not found.'})
        if not binding.enabled or binding.deleted_at is not None:
            deny('callrail_binding_disabled')
        if mapping and mapping.deleted_at is None and mapping.binding_id == binding_id:
            return False
    customer = await db.scalar(select(Customer).where(Customer.id == thread.customer_id, Customer.tenant_id == tenant.id,
        Customer.deleted_at.is_(None)))
    phone = _phone(customer.phone) if customer else ''
    if (not re.fullmatch(r'\+1\d{10}', phone) or (thread.customer_phone and _phone(thread.customer_phone) != phone)
        or (mapping and mapping.customer_phone != phone)):
        deny('callrail_contact_changed')
    if await db.scalar(select(SMSSendOperation.id).where(SMSSendOperation.tenant_id == tenant.id,
        or_(SMSSendOperation.thread_id == thread.id, SMSSendOperation.to_number == phone),
        SMSSendOperation.state.in_(['pending', 'dispatching', 'unknown'])).limit(1)):
        deny('ambiguous_outcome')
    if await db.scalar(select(AutomatedSMSOperation.id).where(AutomatedSMSOperation.tenant_id == tenant.id,
        AutomatedSMSOperation.to_number == phone, AutomatedSMSOperation.state.in_(['pending', 'dispatching', 'unknown'])).limit(1)):
        deny('ambiguous_outcome')
    if binding is None:
        mapping.selected_for_sending = False
        await db.flush()
        return True
    conflict = await db.scalar(select(CallRailConversation.id).where(CallRailConversation.binding_id == binding.id,
        CallRailConversation.customer_phone == phone, CallRailConversation.thread_id != thread.id))
    if conflict:
        deny('callrail_phone_conflict')
    if mapping:
        mapping.selected_for_sending = False
        await db.flush()  # Release the partial unique selection before selecting another route.
    target = await db.scalar(select(CallRailConversation).where(CallRailConversation.tenant_id == tenant.id,
        CallRailConversation.thread_id == thread.id, CallRailConversation.binding_id == binding.id))
    if target:
        if target.customer_id != customer.id or target.customer_phone != phone or target.deleted_at is not None:
            deny('callrail_contact_changed')
        target.selected_for_sending = True
    else:
        db.add(CallRailConversation(tenant_id=tenant.id, thread_id=thread.id, customer_id=customer.id,
            binding_id=binding.id, customer_phone=phone, selected_for_sending=True))
    await db.flush()
    return True
