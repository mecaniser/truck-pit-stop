"""Transactional automation outbox. Only committed pending intents can be claimed."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from twilio.base.exceptions import TwilioRestException

from app.db.models.automated_sms import AutomatedSMSOperation
from app.db.models.communication import SMSSendOperation
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.notification import Notification, NotificationType, NotificationStatus
from app.db.models.sms_message import SMSMessage, SMSMessageDirection, SMSMessageSource, SMSDeliveryStatus
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services.messaging_service import _normalize_for_twilio, _get_or_create_thread, _status_callback_url

CUSTOMER_TEMPLATES = {'work_started_sms', 'work_complete_sms', 'ready_pickup_sms', 'quote_sent_sms', 'invoice_reminder_sms'}
STAFF_TEMPLATES = {'job_assigned_sms', 'quote_declined_shop', 'mechanic_idle_alert_sms', 'pending_zelle_staff_submit_sms', 'pending_zelle_staff_reminder_sms'}
STAFF_ROLES = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST, UserRole.MECHANIC}
DISPATCH_TIMEOUT = timedelta(minutes=5)
FINANCIAL_TEMPLATES = {'invoice_reminder_sms', 'pending_zelle_staff_submit_sms', 'pending_zelle_staff_reminder_sms'}


def digest(values):
    return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()


def fail(code, message, status=409):
    raise HTTPException(status, detail={'code': code, 'message': message})


def valid_phone(phone):
    return bool(re.fullmatch(r'\+[1-9]\d{7,14}', phone or ''))


async def financial_snapshot(db, tenant_id, domain_event_id):
    """Hash debt evidence without storing provider credentials or parsing SMS copy."""
    from app.db.models.invoice import Invoice
    from app.db.models.payment import Payment
    from app.db.models.invoice_settlement import InvoiceSettlement
    try:
        prefix, identifier, _ = domain_event_id.split(':', 2)
        invoice_id = UUID(identifier)
    except (ValueError, TypeError):
        fail('invalid_domain_event', 'Financial SMS requires an invoice event.', 422)
    if prefix != 'invoice':
        fail('invalid_domain_event', 'Financial SMS requires an invoice event.', 422)
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id))
    if not invoice:
        fail('not_found', 'Invoice not found.', 404)
    payments = (await db.execute(select(Payment.id, Payment.amount, Payment.status, Payment.deleted_at).where(Payment.invoice_id == invoice_id, Payment.tenant_id == tenant_id).order_by(Payment.id))).all()
    settlements = (await db.execute(select(InvoiceSettlement.id, InvoiceSettlement.principal_total, InvoiceSettlement.confirmed_principal, InvoiceSettlement.active_pending_principal, InvoiceSettlement.unapplied_credit, InvoiceSettlement.refund_pending, InvoiceSettlement.version).where(InvoiceSettlement.invoice_id == invoice_id, InvoiceSettlement.tenant_id == tenant_id).order_by(InvoiceSettlement.id))).all()
    return digest([format(Decimal(invoice.total_amount), '.2f'), [[str(v) for v in row] for row in payments], [[str(v) for v in row] for row in settlements]])


async def enqueue_automated_sms(db, *, tenant_id, domain_event_id, template_name,
                               template_version='1', to, body, customer_id=None,
                               recipient_user_id=None, recipient_tenant_contact=False):
    """Flush intent with the caller's domain transaction; caller owns commit/rollback."""
    if not isinstance(domain_event_id, str) or not domain_event_id.strip() or len(domain_event_id) > 512:
        fail('missing_event_identity', 'A stable domain event identity is required.', 422)
    if not isinstance(template_version, str) or not template_version or len(template_version) > 32:
        fail('invalid_template', 'Invalid template version.', 422)
    if sum(bool(x) for x in (customer_id, recipient_user_id, recipient_tenant_contact)) != 1:
        fail('identity_unverified', 'Exactly one explicit recipient identity is required.', 422)
    tenant_id = UUID(str(tenant_id))
    kind = 'customer' if customer_id else 'user' if recipient_user_id else 'tenant_contact'
    recipient_id = UUID(str(customer_id or recipient_user_id or tenant_id))
    if template_name not in (CUSTOMER_TEMPLATES if kind == 'customer' else STAFF_TEMPLATES):
        fail('unsupported_template', 'Unsupported automated SMS template.', 422)
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        fail('not_found', 'Tenant not found.', 404)
    financial_hash = None
    if template_name in FINANCIAL_TEMPLATES:
        from app.services.financial_transaction_lock import lock_tenant_financials
        await lock_tenant_financials(db, tenant_id)
        financial_hash = await financial_snapshot(db, tenant_id, domain_event_id)
    customer = None
    if kind == 'customer':
        # Serialize thread creation as well as consent-sensitive customer state.
        customer = await db.scalar(select(Customer).where(Customer.id == recipient_id, Customer.tenant_id == tenant_id, Customer.deleted_at.is_(None)).with_for_update())
        if not customer:
            fail('not_found', 'Recipient not found.', 404)
    elif kind == 'user':
        user = await db.scalar(select(User).where(User.id == recipient_id, User.tenant_id == tenant_id, User.deleted_at.is_(None)))
        if not user:
            fail('not_found', 'Recipient not found.', 404)
    canonical = body.strip()
    if not canonical or len(canonical) > 1600:
        fail('invalid_body', 'SMS body must contain 1 to 1600 characters.', 422)
    from_number = _normalize_for_twilio(tenant.sms_phone_number or '')
    to_number = _normalize_for_twilio(to or '')
    key = digest([str(tenant_id), domain_event_id, template_name, template_version, kind, str(recipient_id)])
    payload_hash = digest([from_number, to_number, canonical] + ([financial_hash] if financial_hash else []))
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int.from_bytes(bytes.fromhex(key)[:8], 'big', signed=True)})
    old = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.tenant_id == tenant_id, AutomatedSMSOperation.event_key == key))
    if old:
        if old.payload_hash != payload_hash:
            fail('idempotency_conflict', 'This event already has a different immutable SMS payload.')
        return old
    current_phone = customer.phone if customer else user.phone if kind == 'user' else tenant.phone
    if not valid_phone(to_number) or _normalize_for_twilio(current_phone or '') != to_number:
        fail('identity_unverified', 'Recipient does not match its current verified identity.')
    notification = Notification(id=uuid4(), tenant_id=tenant_id, type=NotificationType.SMS, status=NotificationStatus.PENDING, recipient_phone=to_number, body=canonical, template_name=template_name)
    db.add(notification)
    message = None
    if customer:
        thread = await _get_or_create_thread(db, tenant_id, customer)
        message = SMSMessage(id=uuid4(), tenant_id=tenant_id, thread_id=thread.id, customer_id=customer.id, direction=SMSMessageDirection.OUTBOUND, source=SMSMessageSource.AUTOMATED, body=canonical, from_number=from_number, to_number=to_number, delivery_status=SMSDeliveryStatus.PENDING)
        db.add(message)
        thread.last_message_at = datetime.now(timezone.utc)
        thread.last_message_preview = canonical[:240]
    await db.flush()
    operation = AutomatedSMSOperation(id=uuid4(), tenant_id=tenant_id, event_key=key, domain_event_id=domain_event_id, template_name=template_name, template_version=template_version, recipient_kind=kind, recipient_id=recipient_id, from_number=from_number, to_number=to_number, body=canonical, payload_hash=payload_hash, notification_id=notification.id, message_id=message.id if message else None, state='pending', attempt_count=0, reconciliation_state='none', delivery_status='pending')
    db.add(operation)
    await db.flush()
    return operation


async def domain_eligibility(db, op, tenant):
    """Do not deliver queued operational alerts after their premise has changed."""
    from app.db.models.invoice import Invoice, InvoiceStatus
    from app.db.models.repair_order import RepairOrder, RepairOrderStatus
    from app.db.models.mechanic_time import MechanicIdleAlertStreak
    try:
        if op.template_name in FINANCIAL_TEMPLATES:
            from app.services.financial_transaction_lock import lock_tenant_financials
            from app.services.invoice_settlement_service import SettlementDomainError
            try:
                await lock_tenant_financials(db, op.tenant_id)
            except SettlementDomainError as exc:
                if exc.code == 'invoice_busy':
                    return 'defer_financial_busy'
                raise
            prefix, invoice_id, event = op.domain_event_id.split(':', 2)
            if prefix != 'invoice':
                return 'invalid_domain_event'
            invoice = await db.scalar(select(Invoice).where(Invoice.id == UUID(invoice_id), Invoice.tenant_id == op.tenant_id).execution_options(populate_existing=True))
            if not invoice or invoice.deleted_at or invoice.voided_at or invoice.status in {InvoiceStatus.PAID, InvoiceStatus.CANCELLED}:
                return 'domain_event_obsolete'
            order = await db.scalar(select(RepairOrder).where(RepairOrder.id == invoice.repair_order_id, RepairOrder.tenant_id == op.tenant_id).execution_options(populate_existing=True))
            if not order or order.deleted_at or order.status == RepairOrderStatus.CANCELLED:
                return 'domain_event_obsolete'
            current_hash = await financial_snapshot(db, op.tenant_id, op.domain_event_id)
            if op.payload_hash != digest([op.from_number, op.to_number, op.body, current_hash]):
                return 'financial_state_changed'
            if op.template_name == 'invoice_reminder_sms':
                if not event.startswith('reminder:'):
                    return 'invalid_domain_event'
                from app.db.models.payment import Payment, PaymentStatus
                from app.db.models.invoice_settlement import InvoiceSettlement
                if await db.scalar(select(Payment.id).where(Payment.tenant_id == op.tenant_id, Payment.invoice_id == invoice.id, Payment.status.in_([PaymentStatus.COMPLETED, PaymentStatus.REFUNDED]), Payment.deleted_at.is_(None)).limit(1)) or await db.scalar(select(InvoiceSettlement.id).where(InvoiceSettlement.tenant_id == op.tenant_id, InvoiceSettlement.invoice_id == invoice.id, InvoiceSettlement.confirmed_principal > 0).limit(1)):
                    return 'financial_balance_review_required'
                ordinal = int(event.removeprefix('reminder:'))
                if invoice.status not in {InvoiceStatus.SENT, InvoiceStatus.OVERDUE} or ordinal < 1 or invoice.reminder_count < ordinal or invoice.zelle_pending_submitted_at or not tenant.invoice_reminders_enabled or order.customer_id != op.recipient_id or invoice.is_internal:
                    return 'domain_event_obsolete'
            else:
                if not invoice.zelle_pending_submitted_at:
                    return 'domain_event_obsolete'
                expected = 'zelle-submitted:' + invoice.zelle_pending_submitted_at.isoformat()
                if op.template_name == 'pending_zelle_staff_reminder_sms':
                    event, stage = event.rsplit(':reminder:', 1)
                    if stage not in {'24', '48'}:
                        return 'invalid_domain_event'
                if event != expected:
                    return 'domain_event_obsolete'
        elif op.template_name == 'job_assigned_sms':
            prefix, order_id, event = op.domain_event_id.split(':', 2)
            if prefix != 'repair-order':
                return 'invalid_domain_event'
            order = await db.scalar(select(RepairOrder).where(RepairOrder.id == UUID(order_id), RepairOrder.tenant_id == op.tenant_id).execution_options(populate_existing=True))
            expected = f'assigned:{order.assigned_at.isoformat()}:{order.assigned_mechanic_id}' if order and order.assigned_at else None
            if not order or order.deleted_at or order.status == RepairOrderStatus.CANCELLED or order.assigned_mechanic_id != op.recipient_id or event != expected:
                return 'domain_event_obsolete'
        elif op.template_name == 'mechanic_idle_alert_sms':
            prefix, streak_id = op.domain_event_id.split(':', 1)
            if prefix != 'mechanic-idle-streak':
                return 'invalid_domain_event'
            streak = await db.scalar(select(MechanicIdleAlertStreak).where(MechanicIdleAlertStreak.id == UUID(streak_id), MechanicIdleAlertStreak.tenant_id == op.tenant_id).execution_options(populate_existing=True))
            if not streak or streak.deleted_at or not streak.is_active or streak.resolved_at:
                return 'domain_event_obsolete'
    except (ValueError, TypeError):
        return 'invalid_domain_event'
    return None


async def eligibility(db, op, sender):
    tenant = await db.scalar(select(Tenant).where(Tenant.id == op.tenant_id).execution_options(populate_existing=True))
    if not tenant or not tenant.is_active or tenant.deleted_at or not tenant.sms_enabled or not tenant.messaging_enabled:
        return 'tenant_disabled'
    domain_reason = await domain_eligibility(db, op, tenant)
    if domain_reason:
        return domain_reason
    if not getattr(sender, 'ready', True):
        return 'provider_unavailable'
    if not valid_phone(op.from_number) or _normalize_for_twilio(tenant.sms_phone_number or '') != op.from_number:
        return 'sender_changed'
    if not valid_phone(op.to_number):
        return 'identity_unverified'
    templates = CUSTOMER_TEMPLATES if op.recipient_kind == 'customer' else STAFF_TEMPLATES
    if op.template_name not in templates:
        return 'unsupported_template'
    if op.recipient_kind == 'customer':
        customer = await db.scalar(select(Customer).where(Customer.id == op.recipient_id, Customer.tenant_id == op.tenant_id, Customer.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
        if not customer or _normalize_for_twilio(customer.phone or '') != op.to_number:
            return 'identity_changed'
        if customer.sms_opt_out:
            return 'opted_out'
        others = (await db.execute(select(Customer.phone).where(Customer.tenant_id == op.tenant_id, Customer.id != customer.id, Customer.deleted_at.is_(None), Customer.phone.is_not(None)))).scalars().all()
        if any(_normalize_for_twilio(phone) == op.to_number for phone in others):
            return 'identity_unverified'
        sms = await db.scalar(select(SMSMessage).where(SMSMessage.id == op.message_id, SMSMessage.tenant_id == op.tenant_id, SMSMessage.deleted_at.is_(None)))
        thread = await db.scalar(select(MessageThread).where(MessageThread.id == sms.thread_id, MessageThread.tenant_id == op.tenant_id, MessageThread.customer_id == op.recipient_id, MessageThread.deleted_at.is_(None))) if sms else None
        if not thread:
            return 'conversation_unavailable'
        remotes = (await db.execute(select(SMSMessage.direction, SMSMessage.from_number, SMSMessage.to_number).where(SMSMessage.thread_id == thread.id, SMSMessage.tenant_id == op.tenant_id, SMSMessage.deleted_at.is_(None)))).all()
        if any(_normalize_for_twilio(f if d == SMSMessageDirection.INBOUND else t) != op.to_number for d, f, t in remotes):
            return 'identity_unverified'
        if await db.scalar(select(SMSSendOperation.id).where(SMSSendOperation.tenant_id == op.tenant_id, SMSSendOperation.thread_id == thread.id, SMSSendOperation.state.in_(['unknown', 'dispatching'])).limit(1)):
            return 'ambiguous_outcome'
    elif op.recipient_kind == 'user':
        user = await db.scalar(select(User).where(User.id == op.recipient_id, User.tenant_id == op.tenant_id).execution_options(populate_existing=True))
        if not user or not user.is_active or user.deleted_at or user.role not in STAFF_ROLES or _normalize_for_twilio(user.phone or '') != op.to_number:
            return 'recipient_unavailable'
    elif op.recipient_kind == 'tenant_contact':
        if op.recipient_id != tenant.id or _normalize_for_twilio(tenant.phone or '') != op.to_number:
            return 'recipient_unavailable'
    else:
        return 'identity_unverified'
    if await db.scalar(select(AutomatedSMSOperation.id).where(AutomatedSMSOperation.tenant_id == op.tenant_id, AutomatedSMSOperation.to_number == op.to_number, AutomatedSMSOperation.id != op.id, AutomatedSMSOperation.state.in_(['unknown', 'dispatching'])).limit(1)):
        return 'ambiguous_outcome'
    return None


async def project(db, op):
    notification = await db.scalar(select(Notification).where(Notification.id == op.notification_id, Notification.tenant_id == op.tenant_id))
    sms = await db.scalar(select(SMSMessage).where(SMSMessage.id == op.message_id, SMSMessage.tenant_id == op.tenant_id)) if op.message_id else None
    now = datetime.now(timezone.utc)
    if op.state == 'rejected':
        notification.status = NotificationStatus.FAILED
        notification.error_message = op.error_code
        op.delivery_status = 'failed'
        if sms:
            sms.delivery_status = SMSDeliveryStatus.FAILED
            sms.error_code = op.error_code
            sms.failed_at = now
    elif op.state == 'accepted':
        notification.external_id = op.provider_message_sid
        notification.status = NotificationStatus.SENT
        notification.sent_at = notification.sent_at or now
        if sms:
            sms.twilio_message_sid = op.provider_message_sid
            sms.delivery_status = SMSDeliveryStatus.QUEUED
    # Unknown stays pending on legacy Notification/SMS enums; inbox reads operation.


async def dispatch_automated_operation(db, operation_id, sender):
    op = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.id == operation_id).with_for_update().execution_options(populate_existing=True))
    if not op or op.state != 'pending':
        await db.rollback()
        return 'skipped'
    reason = await eligibility(db, op, sender)
    if reason == 'defer_financial_busy':
        await db.rollback()
        return 'skipped'
    if reason:
        op.state, op.error_code = 'rejected', reason
        await project(db, op)
        await db.commit()
        return 'rejected'
    op.state = 'dispatching'
    op.attempt_count = 1
    op.dispatch_started_at = datetime.now(timezone.utc)
    payload = dict(body=op.body, from_number=op.from_number, to_number=op.to_number, status_callback=_status_callback_url())
    await db.commit()
    outcome, error = None, None
    try:
        outcome = await asyncio.wait_for(sender.send(**payload), timeout=35)
        if not outcome or not outcome.get('sid'):
            raise ValueError('Missing provider receipt')
    except TwilioRestException as exc:
        error = ('rejected', str(exc.code or 'provider_rejected')) if 400 <= exc.status < 500 and exc.status not in (408, 429) else ('unknown', 'provider_outcome_unknown')
    except Exception:
        error = ('unknown', 'provider_outcome_unknown')
    op = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.id == operation_id).with_for_update().execution_options(populate_existing=True))
    if error:
        op.state, op.error_code = error
        op.reconciliation_state = 'required' if op.state == 'unknown' else 'none'
        if op.error_code == '21610' and op.recipient_kind == 'customer':
            customer = await db.scalar(select(Customer).where(Customer.id == op.recipient_id, Customer.tenant_id == op.tenant_id).with_for_update().execution_options(populate_existing=True))
            if customer:
                customer.sms_opt_out = True
                customer.sms_opted_out_at = customer.sms_opted_out_at or datetime.now(timezone.utc)
                customer.sms_opt_out_source = 'twilio'
    else:
        op.state = 'accepted'
        op.provider_message_sid = outcome['sid']
        op.delivery_status = 'queued'
        op.reconciliation_state = 'none'
    await project(db, op)
    await db.commit()
    return op.state


async def process_pending_automated_operations(db, sender, limit=50, *, tenant_id=None):
    """Bounded recovery; failures are isolated per row and surfaced to scheduler."""
    limit = max(1, min(int(limit), 100))
    scope = [AutomatedSMSOperation.tenant_id == tenant_id] if tenant_id else []
    stale = (await db.execute(select(AutomatedSMSOperation).where(*scope, AutomatedSMSOperation.state == 'dispatching', AutomatedSMSOperation.dispatch_started_at < datetime.now(timezone.utc) - DISPATCH_TIMEOUT).with_for_update(skip_locked=True).limit(limit))).scalars().all()
    counts = dict(examined=0, accepted=0, rejected=0, unknown=len(stale), skipped=0, errors=0)
    for op in stale:
        op.state, op.reconciliation_state = 'unknown', 'required'
        op.error_code = 'dispatch_outcome_unknown'
    await db.commit()
    ids = (await db.execute(select(AutomatedSMSOperation.id).where(*scope, AutomatedSMSOperation.state == 'pending').order_by(AutomatedSMSOperation.created_at, AutomatedSMSOperation.id).limit(limit))).scalars().all()
    await db.rollback()
    for operation_id in ids:
        counts['examined'] += 1
        try:
            state = await dispatch_automated_operation(db, operation_id, sender)
            counts[state] += 1
        except SQLAlchemyError:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            # Quarantine broken rows so a full first batch cannot starve all later
            # work. Never reset a possibly dispatched row back to pending.
            broken = await db.scalar(select(AutomatedSMSOperation).where(AutomatedSMSOperation.id == operation_id).with_for_update().execution_options(populate_existing=True))
            if broken and broken.state in ('pending', 'dispatching'):
                broken.state = 'unknown'
                broken.reconciliation_state = 'required'
                broken.error_code = 'internal_recovery_error'
            await db.commit()
            counts['errors'] += 1
    if counts['errors']:
        raise RuntimeError(f"Automated SMS recovery failed for {counts['errors']} operations")
    return counts


async def apply_automated_callback(db, *, message_sid, message_status, error_code=None):
    """Project exact-SID receipts, including staff Notification-only deliveries."""
    op = (await db.execute(select(AutomatedSMSOperation).where(AutomatedSMSOperation.provider_message_sid == message_sid).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not op:
        return
    status = {'sending': 'sent', 'canceled': 'failed'}.get(message_status, message_status)
    terminal = {'delivered', 'failed', 'undelivered'}
    advances = status in {'queued', 'sent', *terminal} and (op.delivery_status == 'pending' or op.delivery_status == 'queued' and status != 'queued' or op.delivery_status == 'sent' and status in terminal)
    if advances:
        op.delivery_status = status
        notification = await db.scalar(select(Notification).where(Notification.id == op.notification_id, Notification.tenant_id == op.tenant_id).with_for_update())
        if status == 'delivered':
            notification.status = NotificationStatus.DELIVERED
            notification.delivered_at = notification.delivered_at or datetime.now(timezone.utc)
        elif status in {'failed', 'undelivered'}:
            notification.status = NotificationStatus.FAILED
            notification.error_message = error_code or 'delivery_failed'
        else:
            notification.status = NotificationStatus.SENT
    if error_code == '21610' and status in {'failed', 'undelivered'} and op.recipient_kind == 'customer':
        customer = await db.scalar(select(Customer).where(Customer.id == op.recipient_id, Customer.tenant_id == op.tenant_id).with_for_update())
        if customer:
            customer.sms_opt_out = True
            customer.sms_opted_out_at = customer.sms_opted_out_at or datetime.now(timezone.utc)
            customer.sms_opt_out_source = 'twilio_callback'
