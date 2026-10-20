"""Reserved receivers never fall back to customer guessing or managed routing."""
import hashlib
import re
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, text
from app.db.models.twilio_reply_route import TwilioReplyRoute
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.db.models.sms_message import SMSMessageDirection


def reject():
    raise HTTPException(409, detail='Reply route not authorized')


def validate_window(route):
    now = datetime.now(timezone.utc)
    if not route.enabled or route.deleted_at or route.revoked_at or not (route.approved_at <= now < route.expires_at):
        reject()


async def resolve(db, *, to_number, from_number, authenticated_account_sid, message_sid):
    from app.services.messaging_service import _normalize_for_twilio
    to_phone, from_phone = _normalize_for_twilio(to_number), _normalize_for_twilio(from_number)
    # Include every historical row: inactive approval is still a reservation.
    rows = (await db.execute(select(TwilioReplyRoute).where(
        TwilioReplyRoute.to_number == to_phone).order_by(TwilioReplyRoute.id)
        .with_for_update().execution_options(populate_existing=True))).scalars().all()
    if not rows:
        return None
    if not authenticated_account_sid or not re.fullmatch(r'SM[0-9a-fA-F]{32}', message_sid or ''):
        reject()
    now = datetime.now(timezone.utc)
    matches = [r for r in rows if r.account_sid == authenticated_account_sid and r.from_number == from_phone
               and r.enabled and not r.deleted_at and not r.revoked_at and r.approved_at <= now < r.expires_at]
    if len(matches) != 1:
        reject()
    route = matches[0]
    key = int.from_bytes(hashlib.sha256(f'sms-inbound:{route.account_sid}:{message_sid}'.encode()).digest()[:8], 'big', signed=True)
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
    tenant = await db.scalar(select(Tenant).where(Tenant.id == route.tenant_id, Tenant.deleted_at.is_(None), Tenant.is_active.is_(True)))
    actor = await db.scalar(select(User).where(User.id == route.approving_actor_id, User.tenant_id == route.tenant_id,
        User.deleted_at.is_(None), User.is_active.is_(True), User.role.in_([UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST, UserRole.MECHANIC])))
    customer = await db.scalar(select(Customer).where(Customer.id == route.customer_id, Customer.tenant_id == route.tenant_id,
        Customer.deleted_at.is_(None)).with_for_update().execution_options(populate_existing=True))
    thread = await db.scalar(select(MessageThread).where(MessageThread.id == route.thread_id, MessageThread.tenant_id == route.tenant_id,
        MessageThread.customer_id == route.customer_id, MessageThread.thread_kind == 'customer', MessageThread.deleted_at.is_(None))
        .with_for_update().execution_options(populate_existing=True))
    if not tenant or not actor or not customer or not thread or _normalize_for_twilio(customer.phone) != route.from_number:
        reject()
    if not route.approval_reference.strip() or to_phone != route.to_number or from_phone != route.from_number:
        reject()
    validate_window(route)
    return route, tenant, customer, thread


def validate_duplicate(existing, route, to_number, from_number):
    from app.services.messaging_service import _normalize_for_twilio
    if (existing.direction != SMSMessageDirection.INBOUND or existing.twilio_reply_route_id != route.id
        or existing.twilio_account_sid != route.account_sid or existing.tenant_id != route.tenant_id
        or existing.customer_id != route.customer_id or existing.thread_id != route.thread_id
        or _normalize_for_twilio(existing.to_number) != to_number
        or _normalize_for_twilio(existing.from_number) != from_number):
        reject()
