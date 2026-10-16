"""Shared inbox persistence. Only pending intents may cross the provider boundary."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from fastapi import HTTPException
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.exc import SQLAlchemyError
from twilio.base.exceptions import TwilioRestException
from app.db.models.communication import ConversationWorkflow, ConversationReadWatermark, SMSSendOperation
from app.db.models.automated_sms import AutomatedSMSOperation
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.sms_message import SMSMessage, SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.messaging_service import _normalize_for_twilio, _get_twilio_client, _status_callback_url, enforce_tenant_send_rate_limit

STAFF_ROLES = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST, UserRole.MECHANIC}
DISPATCH_TIMEOUT = timedelta(minutes=5)  # Provider I/O is bounded to 30 seconds.


def fail(code, message, status=409):
    raise HTTPException(status, detail={'code': code, 'message': message})


def permitted(user):
    return user and user.is_active and user.deleted_at is None and (user.role in STAFF_ROLES or user.can_access_messaging)


class LiveSMSSender:
    mode = 'live'
    @property
    def ready(self):
        return _get_twilio_client() is not None

    async def send(self, *, body, from_number, to_number, status_callback):
        client = _get_twilio_client()
        if client is None:
            raise RuntimeError('SMS provider unavailable')
        payload = {'body': body, 'from_': from_number, 'to': to_number}
        if status_callback:
            payload['status_callback'] = status_callback
        result = await asyncio.wait_for(asyncio.to_thread(client.messages.create, **payload), timeout=30)
        return {'sid': result.sid, 'status': result.status}


def get_sms_sender():
    return LiveSMSSender()


async def authorize(db, user):
    if not permitted(user) or not user.tenant_id:
        fail('forbidden', 'Messaging access is required.', 403)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == user.tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True)))
    if not tenant or not tenant.messaging_enabled:
        fail('forbidden', 'Messaging is disabled for this shop.', 403)
    return tenant


async def thread_for(db, tenant_id, thread_id, *, lock=False):
    query = select(MessageThread).where(MessageThread.id == thread_id, MessageThread.tenant_id == tenant_id, MessageThread.deleted_at.is_(None), select(Customer.id).where(Customer.id == MessageThread.customer_id, Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None)).exists())
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    thread = await db.scalar(query)
    if not thread:
        fail('not_found', 'Conversation not found.', 404)
    return thread


async def workflow(db, thread):
    # Thread row lock serializes all mutations; GET never creates metadata.
    row = await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.tenant_id == thread.tenant_id, ConversationWorkflow.thread_id == thread.id))
    if row is None:
        row = ConversationWorkflow(tenant_id=thread.tenant_id, thread_id=thread.id, status='open', version=1)
        db.add(row)
        await db.flush()
    return row


async def send_policy(db, tenant, thread, sender, *, ignore_operation=None):
    customer = await db.scalar(select(Customer).where(Customer.id == thread.customer_id, Customer.tenant_id == tenant.id, Customer.deleted_at.is_(None)))
    phone = _normalize_for_twilio(customer.phone or '') if customer else ''
    from_number = _normalize_for_twilio(tenant.sms_phone_number or '')
    account_id = uuid5(NAMESPACE_URL, f'dieselbridge:sms-account:{tenant.id}:{from_number}')
    identity_id = uuid5(NAMESPACE_URL, f'dieselbridge:sms-identity:{tenant.id}:{thread.id}:{phone}')
    reason = None
    if not tenant.sms_enabled or not re.fullmatch(r'\+[1-9]\d{7,14}', from_number) or not getattr(sender, 'ready', True):
        reason = 'not_connected'
    elif not customer or customer.sms_opt_out:
        reason = 'opted_out' if customer else 'identity_unverified'
    elif not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
        reason = 'identity_unverified'
    else:
        others = (await db.execute(select(Customer.phone).where(Customer.tenant_id == tenant.id, Customer.id != customer.id, Customer.deleted_at.is_(None), Customer.phone.is_not(None)))).scalars().all()
        remote_rows = (await db.execute(select(SMSMessage.direction, SMSMessage.from_number, SMSMessage.to_number).where(SMSMessage.tenant_id == tenant.id, SMSMessage.thread_id == thread.id, SMSMessage.deleted_at.is_(None)))).all()
        remotes = {_normalize_for_twilio(f if d == SMSMessageDirection.INBOUND else t) for d, f, t in remote_rows if (f if d == SMSMessageDirection.INBOUND else t)}
        if any(_normalize_for_twilio(p) == phone for p in others) or len(remotes) > 1 or (remotes and phone not in remotes):
            reason = 'identity_unverified'
    held = select(SMSSendOperation.id).where(SMSSendOperation.tenant_id == tenant.id, SMSSendOperation.thread_id == thread.id, SMSSendOperation.state.in_(['unknown', 'dispatching']))
    if ignore_operation:
        held = held.where(SMSSendOperation.id != ignore_operation)
    if await db.scalar(held.limit(1)):
        reason = 'ambiguous_outcome'
    if await db.scalar(select(AutomatedSMSOperation.id).where(AutomatedSMSOperation.tenant_id == tenant.id, AutomatedSMSOperation.to_number == phone, AutomatedSMSOperation.state.in_(['unknown', 'dispatching'])).limit(1)):
        reason = 'ambiguous_outcome'
    return {'can_send': reason is None, 'reason': reason}, account_id, identity_id, from_number, phone, customer


def cursor_encode(binding, dt, row_id):
    return base64.urlsafe_b64encode(json.dumps([binding, dt.isoformat(), str(row_id)]).encode()).decode()


def cursor_decode(cursor, binding):
    if not cursor:
        return None
    try:
        actual, dt, row_id = json.loads(base64.urlsafe_b64decode(cursor))
        parsed = datetime.fromisoformat(dt)
        if actual != binding or parsed.tzinfo is None:
            raise ValueError()
        return parsed, UUID(row_id)
    except Exception:
        fail('invalid_cursor', 'Invalid pagination cursor.', 400)


async def unread_count(db, thread, user_id):
    mark = await db.scalar(select(ConversationReadWatermark).where(ConversationReadWatermark.tenant_id == thread.tenant_id, ConversationReadWatermark.thread_id == thread.id, ConversationReadWatermark.user_id == user_id))
    query = select(func.count()).select_from(SMSMessage).where(SMSMessage.tenant_id == thread.tenant_id, SMSMessage.thread_id == thread.id, SMSMessage.deleted_at.is_(None), SMSMessage.direction == SMSMessageDirection.INBOUND)
    if mark:
        query = query.where(or_(SMSMessage.created_at > mark.through_created_at, and_(SMSMessage.created_at == mark.through_created_at, SMSMessage.id > mark.through_message_id)))
    return await db.scalar(query)


async def message_json(db, message):
    operation = await db.scalar(select(SMSSendOperation).where(SMSSendOperation.tenant_id == message.tenant_id, SMSSendOperation.message_id == message.id))
    if operation is None and message.source == SMSMessageSource.AUTOMATED:
        operation = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.tenant_id == message.tenant_id, AutomatedSMSOperation.message_id == message.id))
    delivery = message.delivery_status.value
    if message.direction == SMSMessageDirection.INBOUND:
        delivery = 'received'
    elif operation and operation.state in ('unknown', 'dispatching'):
        delivery = 'unknown' if operation.state == 'unknown' else 'pending'
    return dict(id=message.id, conversation_id=message.thread_id, channel='sms', direction=message.direction.value, source={'inbound': 'customer', 'manual': 'staff', 'automated': 'automation'}[message.source.value], body=message.body, created_at=message.created_at, delivery_status=delivery, error_code=message.error_code, send_operation_id=operation.id if operation else None)


async def conversation_json(db, tenant, user, thread, sender):
    policy, account, identity, _, phone, customer = await send_policy(db, tenant, thread, sender)
    wf = await db.scalar(select(ConversationWorkflow).where(ConversationWorkflow.tenant_id == tenant.id, ConversationWorkflow.thread_id == thread.id))
    return dict(id=thread.id, tenant_id=tenant.id, customer_id=thread.customer_id, customer_name=f'{customer.first_name} {customer.last_name}' if customer else 'Unavailable customer', company=customer.company_name if customer else None, channel='sms', channel_account_id=account, contact_identity_id=identity, identity_label=phone, status=wf.status if wf else 'open', assignee_id=wf.assignee_id if wf else None, unread_count=await unread_count(db, thread, user.id), last_message_at=thread.last_message_at or thread.created_at, preview=thread.last_message_preview or '', version=wf.version if wf else 1, messages=[], send_policy=policy, context={})


async def operation_json(db, op, replayed=False):
    sms = await db.scalar(select(SMSMessage).where(SMSMessage.id == op.message_id, SMSMessage.tenant_id == op.tenant_id))
    delivery = 'unknown' if op.state == 'unknown' else sms.delivery_status.value
    return dict(id=op.id, conversation_id=op.thread_id, message_id=op.message_id, state=op.state, delivery_status=delivery, replayed=replayed, can_retry=False, reconciliation_state=op.reconciliation_state)


async def create_operation(db, user, tenant, thread_id, body, key, sender):
    canonical = body.body.strip()
    digest = hashlib.sha256(json.dumps([str(tenant.id), str(thread_id), str(body.channel_account_id), str(body.contact_identity_id), canonical], separators=(',', ':')).encode()).hexdigest()
    # Serialize same tenant/key even when conflicting callers target different conversations.
    from sqlalchemy import text
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int.from_bytes(hashlib.sha256(f'{tenant.id}:{key}'.encode()).digest()[:8], 'big', signed=True)})
    old = await db.scalar(select(SMSSendOperation).where(SMSSendOperation.tenant_id == tenant.id, SMSSendOperation.idempotency_key == key))
    if old:
        await thread_for(db, tenant.id, old.thread_id)
        if old.payload_hash != digest:
            fail('idempotency_conflict', 'This send key belongs to a different message.')
        return old, True
    thread = await thread_for(db, tenant.id, thread_id, lock=True)
    wf = await workflow(db, thread)
    if wf.version != body.expected_version:
        fail('stale_version', 'Conversation changed. Refresh and try again.')
    policy, account, identity, from_number, phone, _ = await send_policy(db, tenant, thread, sender)
    if account != body.channel_account_id or identity != body.contact_identity_id:
        fail('identity_unverified', 'Recipient or sender changed. Refresh before sending.')
    if not policy['can_send']:
        fail(policy['reason'], 'This conversation cannot send messages right now.')
    if not await enforce_tenant_send_rate_limit(tenant.id, limit=30, window_seconds=60):
        raise HTTPException(429, detail={'code': 'rate_limited', 'message': 'SMS send rate limit exceeded.'}, headers={'Retry-After': '60'})
    now = datetime.now(timezone.utc)
    sms = SMSMessage(id=uuid4(), tenant_id=tenant.id, thread_id=thread.id, customer_id=thread.customer_id, created_by_user_id=user.id, direction=SMSMessageDirection.OUTBOUND, source=SMSMessageSource.MANUAL, body=canonical, from_number=from_number, to_number=phone, delivery_status=SMSDeliveryStatus.PENDING, created_at=now)
    db.add(sms)
    await db.flush()
    op = SMSSendOperation(id=uuid4(), tenant_id=tenant.id, thread_id=thread.id, message_id=sms.id, actor_id=user.id, idempotency_key=key, payload_hash=digest, channel_account_id=account, contact_identity_id=identity, from_number=from_number, to_number=phone, body=canonical, state='pending', attempt_count=0, reconciliation_state='none')
    db.add(op)
    thread.last_message_at = now
    thread.last_message_preview = canonical[:240]
    wf.version += 1
    await db.commit()
    return op, False


async def dispatch_operation(db, operation_id, sender):
    op = await db.scalar(select(SMSSendOperation).where(SMSSendOperation.id == operation_id).with_for_update().execution_options(populate_existing=True))
    if not op or op.state != 'pending':
        await db.rollback()
        return
    tenant = await db.scalar(select(Tenant).where(Tenant.id == op.tenant_id))
    actor = await db.scalar(select(User).where(User.id == op.actor_id, User.tenant_id == op.tenant_id))
    try:
        thread = await thread_for(db, op.tenant_id, op.thread_id, lock=True)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        op.state = 'rejected'
        op.error_code = 'conversation_unavailable'
        sms = await db.scalar(select(SMSMessage).where(SMSMessage.id == op.message_id, SMSMessage.tenant_id == op.tenant_id))
        if sms:
            sms.delivery_status = SMSDeliveryStatus.FAILED
            sms.error_code = op.error_code
        await db.commit()
        return
    policy, account, identity, from_number, phone, _ = await send_policy(db, tenant, thread, sender, ignore_operation=op.id)
    if not tenant.is_active or tenant.deleted_at or not tenant.messaging_enabled or not permitted(actor) or not policy['can_send'] or (account, identity, from_number, phone) != (op.channel_account_id, op.contact_identity_id, op.from_number, op.to_number):
        op.state = 'rejected'
        op.error_code = policy['reason'] or 'access_changed'
        sms = await db.scalar(select(SMSMessage).where(SMSMessage.id == op.message_id, SMSMessage.tenant_id == op.tenant_id))
        sms.delivery_status = SMSDeliveryStatus.FAILED
        sms.error_code = op.error_code
        await db.commit()
        return
    op.state = 'dispatching'
    op.attempt_count = 1
    op.dispatch_started_at = datetime.now(timezone.utc)
    payload = dict(body=op.body, from_number=op.from_number, to_number=op.to_number, status_callback=_status_callback_url())
    await db.commit()  # Never hold a database transaction across provider I/O.
    outcome, error = None, None
    try:
        outcome = await asyncio.wait_for(sender.send(**payload), timeout=35)
        if not outcome or not outcome.get('sid'):
            raise ValueError('Provider returned no receipt')
    except TwilioRestException as exc:
        error = ('rejected', str(exc.code or 'provider_rejected')) if 400 <= exc.status < 500 and exc.status not in (408, 429) else ('unknown', 'provider_outcome_unknown')
    except Exception:
        error = ('unknown', 'provider_outcome_unknown')
    op = await db.scalar(select(SMSSendOperation).where(SMSSendOperation.id == operation_id).with_for_update().execution_options(populate_existing=True))
    sms = await db.scalar(select(SMSMessage).where(SMSMessage.id == op.message_id, SMSMessage.tenant_id == op.tenant_id).with_for_update())
    if error:
        op.state, op.error_code = error
        op.reconciliation_state = 'required' if op.state == 'unknown' else 'none'
        if op.state == 'rejected':
            sms.delivery_status = SMSDeliveryStatus.FAILED
            sms.error_code = op.error_code
            sms.failed_at = datetime.now(timezone.utc)
        if op.error_code == '21610':
            customer = await db.scalar(select(Customer).where(Customer.id == sms.customer_id, Customer.tenant_id == op.tenant_id).with_for_update())
            customer.sms_opt_out = True
            customer.sms_opted_out_at = customer.sms_opted_out_at or datetime.now(timezone.utc)
            customer.sms_opt_out_source = 'twilio'
    else:
        op.state = 'accepted'
        op.reconciliation_state = 'none'
        sms.twilio_message_sid = outcome['sid']
        # Acceptance is not delivery: callbacks are authoritative for terminal state.
        sms.delivery_status = SMSDeliveryStatus.QUEUED
    await db.commit()


async def process_pending_operations(db, sender, limit=50, *, tenant_id=None):
    scope = [SMSSendOperation.tenant_id == tenant_id] if tenant_id else []
    stale = (await db.execute(select(SMSSendOperation).where(*scope, SMSSendOperation.state == 'dispatching', SMSSendOperation.dispatch_started_at < datetime.now(timezone.utc) - DISPATCH_TIMEOUT).with_for_update(skip_locked=True).limit(limit))).scalars().all()
    counts = dict(examined=0, accepted=0, rejected=0, unknown=len(stale), skipped=0, errors=0)
    for op in stale:
        op.state = 'unknown'
        op.reconciliation_state = 'required'
    await db.commit()
    ids = (await db.execute(select(SMSSendOperation.id).where(*scope, SMSSendOperation.state == 'pending').order_by(SMSSendOperation.created_at).limit(limit))).scalars().all()
    await db.rollback()
    for operation_id in ids:
        counts['examined'] += 1
        try:
            await dispatch_operation(db, operation_id, sender)
            state = await db.scalar(select(SMSSendOperation.state).where(SMSSendOperation.id == operation_id))
            await db.rollback()
            counts[state if state in ('accepted', 'rejected', 'unknown') else 'skipped'] += 1
        except SQLAlchemyError:
            await db.rollback()
            raise  # Infrastructure failures must not alter dispatch eligibility.
        except Exception:
            await db.rollback()
            await db.execute(update(SMSSendOperation).where(SMSSendOperation.id == operation_id, SMSSendOperation.state.in_(['pending', 'dispatching'])).values(state='unknown', reconciliation_state='required', error_code='internal_recovery_error'))
            await db.commit()
            counts['errors'] += 1
            # Persist a hold so a malformed row cannot starve later batches.
            # Never retry automatically when its dispatch outcome is uncertain.
    if counts['errors']:
        raise RuntimeError(f"Manual SMS recovery failed for {counts['errors']} operations")
    return counts
