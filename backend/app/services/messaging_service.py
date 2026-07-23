from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.core.config import settings
from app.core.logging import get_logger
from app.core.phone import normalize_phone
from app.core.redis import get_redis
from app.core.websocket import broadcast_sms_message_event, broadcast_sms_thread_event
from app.db.models.customer import Customer
from app.db.models.message_thread import MessageThread
from app.db.models.notification import Notification, NotificationStatus, NotificationType
from app.db.models.sms_message import SMSDeliveryStatus, SMSMessage, SMSMessageDirection, SMSMessageSource
from app.db.models.tenant import Tenant

logger = get_logger(__name__)

_STOP_KEYWORDS = {"STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"}
_START_KEYWORDS = {"START", "UNSTOP"}
_TWILIO_OPTOUT_ERROR_CODE = "21610"


def _get_twilio_client() -> Optional[Client]:
    """Create the provider client only when this deployment has SMS credentials."""
    account_sid = settings.TWILIO_ACCOUNT_SID.strip()
    auth_token = settings.TWILIO_AUTH_TOKEN.strip()
    if not account_sid or not auth_token:
        return None
    return Client(account_sid, auth_token)


def _coerce_uuid(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _coerce_source(value: SMSMessageSource | str) -> SMSMessageSource:
    if isinstance(value, SMSMessageSource):
        return value
    return SMSMessageSource(str(value))


def _normalize_for_twilio(phone: str) -> str:
    text = (phone or "").strip()
    if not text:
        return text

    digits = normalize_phone(text)
    if not digits:
        return text

    # Normalize common US-local inputs to E.164.
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    # Normalize explicit international prefixes.
    if text.startswith("00") and len(digits) > 2:
        return f"+{digits[2:]}"

    return f"+{digits}"


def _phone_match_candidates(phone: str) -> list[str]:
    """
    Return equivalent digit-only variants for matching stored phone numbers.

    For US numbers, treat 10-digit and leading-1 11-digit formats as equivalent.
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return []

    candidates = [normalized]
    if len(normalized) == 11 and normalized.startswith("1"):
        candidates.append(normalized[1:])
    elif len(normalized) == 10:
        candidates.append(f"1{normalized}")

    # Preserve order while deduplicating.
    return list(dict.fromkeys(candidates))


def _canonical_customer_phone(phone: str) -> Optional[str]:
    """
    Canonical customer phone storage format.

    Prefer 10-digit US format when input is +1/11-digit US; otherwise keep
    normalized digits as-is.
    """
    candidates = _phone_match_candidates(phone)
    if not candidates:
        return None
    first = candidates[0]
    if len(first) == 11 and first.startswith("1"):
        return first[1:]
    return first


def _twilio_status_to_delivery_status(raw_status: Optional[str]) -> SMSDeliveryStatus:
    value = (raw_status or "").strip().lower()
    if value == "queued":
        return SMSDeliveryStatus.QUEUED
    if value in {"sending", "sent"}:
        return SMSDeliveryStatus.SENT
    if value in {"delivered", "received", "receiving"}:
        return SMSDeliveryStatus.DELIVERED
    if value == "undelivered":
        return SMSDeliveryStatus.UNDELIVERED
    if value in {"failed", "canceled"}:
        return SMSDeliveryStatus.FAILED
    return SMSDeliveryStatus.PENDING


def _delivery_status_to_notification_status(delivery_status: SMSDeliveryStatus) -> NotificationStatus:
    if delivery_status == SMSDeliveryStatus.DELIVERED:
        return NotificationStatus.DELIVERED
    if delivery_status in {SMSDeliveryStatus.FAILED, SMSDeliveryStatus.UNDELIVERED}:
        return NotificationStatus.FAILED
    if delivery_status in {SMSDeliveryStatus.QUEUED, SMSDeliveryStatus.SENT}:
        return NotificationStatus.SENT
    return NotificationStatus.PENDING


def _preview_text(body: str) -> str:
    text = (body or "").strip()
    if len(text) <= 140:
        return text
    return f"{text[:137]}..."


def _status_callback_url() -> Optional[str]:
    base = (settings.PUBLIC_API_BASE_URL or "").strip()
    if not base:
        return None

    parsed = urlparse(base)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or hostname.endswith(".local"):
        return None

    return f"{base.rstrip('/')}/api/v1/webhooks/twilio/sms/status"


async def _resolve_tenant_by_to_number(db: AsyncSession, to_number: str) -> Optional[Tenant]:
    number = (to_number or "").strip()
    if not number:
        return None

    result = await db.execute(
        select(Tenant).where(
            and_(Tenant.sms_enabled == True, Tenant.sms_phone_number == number)  # noqa: E712
        )
    )
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant

    candidates = _phone_match_candidates(number)
    if not candidates:
        return None

    result = await db.execute(
        select(Tenant).where(
            and_(Tenant.sms_enabled == True, Tenant.sms_phone_number.is_not(None))  # noqa: E712
        )
    )
    for candidate in result.scalars().all():
        candidate_phone = normalize_phone(candidate.sms_phone_number)
        if candidate_phone and candidate_phone in candidates:
            return candidate
    return None


async def _get_or_create_thread(
    db: AsyncSession,
    tenant_id: UUID,
    customer: Customer,
) -> MessageThread:
    result = await db.execute(
        select(MessageThread).where(
            and_(
                MessageThread.tenant_id == tenant_id,
                MessageThread.customer_id == customer.id,
                MessageThread.deleted_at.is_(None),
            )
        )
    )
    thread = result.scalar_one_or_none()
    if thread:
        if customer.phone and thread.customer_phone != customer.phone:
            thread.customer_phone = customer.phone
        # Archive is a staff-view preference; any new inbound/outbound message should revive the thread.
        if thread.archived_at is not None:
            thread.archived_at = None
            thread.archived_by_user_id = None
        return thread

    thread = MessageThread(
        tenant_id=tenant_id,
        customer_id=customer.id,
        customer_phone=customer.phone,
        unread_count_staff=0,
    )
    db.add(thread)
    await db.flush()
    return thread


def _keyword_token(body: str) -> str:
    stripped = (body or "").strip()
    if not stripped:
        return ""
    return stripped.split()[0].upper()


def _apply_opt_keyword(customer: Customer, body: str) -> None:
    token = _keyword_token(body)
    now = datetime.now(timezone.utc)
    if token in _STOP_KEYWORDS:
        customer.sms_opt_out = True
        customer.sms_opted_out_at = now
        customer.sms_opt_out_source = "inbound_keyword"
    elif token in _START_KEYWORDS:
        customer.sms_opt_out = False
        customer.sms_opted_out_at = None
        customer.sms_opt_out_source = "inbound_keyword"


async def enforce_tenant_send_rate_limit(
    tenant_id: UUID | str,
    *,
    limit: int = 30,
    window_seconds: int = 60,
) -> bool:
    tenant_key = str(tenant_id)
    bucket = int(time.time() // window_seconds)
    key = f"sms:send:tenant:{tenant_key}:{bucket}"
    redis = await get_redis()
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    return count <= limit


def validate_twilio_signature(
    request_url: str,
    params: dict[str, Any],
    signature: Optional[str],
) -> bool:
    token = settings.TWILIO_AUTH_TOKEN
    if not token:
        return settings.ENVIRONMENT != "production"
    if not signature:
        return False
    validator = RequestValidator(token)
    return validator.validate(request_url, params, signature)


async def send_sms_with_tracking(
    db: AsyncSession,
    tenant_id: UUID | str,
    to: str,
    body: str,
    *,
    template_name: Optional[str] = None,
    customer_id: Optional[UUID | str] = None,
    source: SMSMessageSource | str = SMSMessageSource.AUTOMATED,
    created_by_user_id: Optional[UUID | str] = None,
    raise_on_failure: bool = False,
) -> tuple[Notification, Optional[SMSMessage], Optional[MessageThread]]:
    tenant_uuid = _coerce_uuid(tenant_id)
    source_enum = _coerce_source(source)
    now = datetime.now(timezone.utc)

    notification = Notification(
        tenant_id=tenant_uuid,
        type=NotificationType.SMS,
        status=NotificationStatus.PENDING,
        recipient_phone=to,
        body=body,
        template_name=template_name,
    )
    db.add(notification)
    await db.flush()

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
    tenant = result.scalar_one_or_none()
    if not tenant:
        notification.status = NotificationStatus.FAILED
        notification.error_message = "Tenant not found for SMS send"
        await db.commit()
        await db.refresh(notification)
        if raise_on_failure:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        return notification, None, None

    from_number = tenant.sms_phone_number or settings.TWILIO_PHONE_NUMBER
    if not from_number:
        notification.status = NotificationStatus.FAILED
        notification.error_message = "SMS sending number is not configured"
        await db.commit()
        await db.refresh(notification)
        if raise_on_failure:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SMS number not configured for this tenant",
            )
        return notification, None, None

    customer: Optional[Customer] = None
    thread: Optional[MessageThread] = None
    sms_message: Optional[SMSMessage] = None

    if customer_id:
        customer_uuid = _coerce_uuid(customer_id)
        result = await db.execute(
            select(Customer).where(
                and_(
                    Customer.id == customer_uuid,
                    Customer.tenant_id == tenant_uuid,
                )
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            notification.status = NotificationStatus.FAILED
            notification.error_message = "Customer not found for tenant"
            await db.commit()
            await db.refresh(notification)
            if raise_on_failure:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
            return notification, None, None

        if customer.sms_opt_out:
            notification.status = NotificationStatus.FAILED
            notification.error_message = "Customer has opted out of SMS"
            await db.commit()
            await db.refresh(notification)
            if raise_on_failure:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Customer has opted out of SMS",
                )
            return notification, None, None

        thread = await _get_or_create_thread(db, tenant_uuid, customer)
        sms_message = SMSMessage(
            tenant_id=tenant_uuid,
            thread_id=thread.id,
            customer_id=customer.id,
            created_by_user_id=_coerce_uuid(created_by_user_id) if created_by_user_id else None,
            direction=SMSMessageDirection.OUTBOUND,
            source=source_enum,
            body=body,
            from_number=from_number,
            to_number=to,
            delivery_status=SMSDeliveryStatus.PENDING,
        )
        db.add(sms_message)
        await db.flush()

    try:
        twilio_client = _get_twilio_client()
        if not twilio_client:
            raise RuntimeError("SMS provider credentials are not configured")

        twilio_payload: dict[str, str] = {
            "body": body,
            "from_": _normalize_for_twilio(from_number),
            "to": _normalize_for_twilio(to),
        }
        status_callback = _status_callback_url()
        if status_callback:
            twilio_payload["status_callback"] = status_callback

        message = twilio_client.messages.create(**twilio_payload)
        delivery_status = _twilio_status_to_delivery_status(getattr(message, "status", None))
        notification.status = _delivery_status_to_notification_status(delivery_status)
        notification.external_id = message.sid
        notification.sent_at = now

        if sms_message:
            sms_message.twilio_message_sid = message.sid
            sms_message.delivery_status = delivery_status
            sms_message.sent_at = now
            thread.last_message_at = now
            thread.last_message_preview = _preview_text(body)

    except TwilioRestException as exc:
        logger.warning(
            "twilio_send_failed",
            tenant_id=str(tenant_uuid),
            customer_id=str(customer.id) if customer else None,
            twilio_error_code=str(exc.code) if exc.code else None,
            twilio_message=str(exc.msg),
        )
        notification.status = NotificationStatus.FAILED
        notification.error_message = str(exc.msg)
        if sms_message:
            sms_message.delivery_status = SMSDeliveryStatus.FAILED
            sms_message.error_code = str(exc.code) if exc.code else None
            sms_message.error_message = str(exc.msg)
            sms_message.failed_at = now
            thread.last_message_at = now
            thread.last_message_preview = _preview_text(body)

        if customer and str(exc.code) == _TWILIO_OPTOUT_ERROR_CODE:
            customer.sms_opt_out = True
            customer.sms_opted_out_at = now
            customer.sms_opt_out_source = "send_error"

        await db.commit()
        await db.refresh(notification)
        if raise_on_failure:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc.msg or "Failed to send SMS"),
            )
        return notification, sms_message, thread

    except Exception as exc:
        notification.status = NotificationStatus.FAILED
        notification.error_message = str(exc)
        if sms_message:
            sms_message.delivery_status = SMSDeliveryStatus.FAILED
            sms_message.error_message = str(exc)
            sms_message.failed_at = now
            thread.last_message_at = now
            thread.last_message_preview = _preview_text(body)
        await db.commit()
        await db.refresh(notification)
        if raise_on_failure:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send SMS")
        return notification, sms_message, thread

    await db.commit()
    await db.refresh(notification)

    if sms_message and thread:
        await db.refresh(sms_message)
        await db.refresh(thread)
        await broadcast_sms_message_event(
            tenant_id=str(tenant_uuid),
            thread_id=str(thread.id),
            message_id=str(sms_message.id),
            customer_id=str(sms_message.customer_id),
            direction=sms_message.direction.value,
            source=sms_message.source.value,
            body=sms_message.body,
            delivery_status=sms_message.delivery_status.value,
            created_at=sms_message.created_at.isoformat() if sms_message.created_at else None,
        )
        await broadcast_sms_thread_event(
            tenant_id=str(tenant_uuid),
            thread_id=str(thread.id),
            customer_id=str(thread.customer_id),
            unread_count_staff=thread.unread_count_staff,
            last_message_at=thread.last_message_at.isoformat() if thread.last_message_at else None,
            last_message_preview=thread.last_message_preview,
        )

    return notification, sms_message, thread


async def handle_inbound_sms(
    db: AsyncSession,
    *,
    to_number: str,
    from_number: str,
    body: str,
    twilio_message_sid: Optional[str] = None,
) -> tuple[MessageThread, Optional[SMSMessage], Customer, bool]:
    tenant = await _resolve_tenant_by_to_number(db, to_number)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SMS tenant number not recognized")

    if twilio_message_sid:
        result = await db.execute(select(SMSMessage).where(SMSMessage.twilio_message_sid == twilio_message_sid))
        existing = result.scalar_one_or_none()
        if existing:
            thread_result = await db.execute(
                select(MessageThread).where(
                    and_(
                        MessageThread.id == existing.thread_id,
                        MessageThread.tenant_id == tenant.id,
                    )
                )
            )
            thread = thread_result.scalar_one()
            customer_result = await db.execute(
                select(Customer).where(
                    and_(
                        Customer.id == existing.customer_id,
                        Customer.tenant_id == tenant.id,
                    )
                )
            )
            customer = customer_result.scalar_one()
            return thread, existing, customer, True

    sender_candidates = _phone_match_candidates(from_number)
    normalized_sender = _canonical_customer_phone(from_number)
    if not sender_candidates or not normalized_sender:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid inbound sender number")

    # First, check for existing thread by phone - preserves conversation continuity
    customer: Optional[Customer] = None
    thread_result = await db.execute(
        select(MessageThread)
        .where(
            and_(
                MessageThread.tenant_id == tenant.id,
                MessageThread.customer_phone.in_(sender_candidates),
            )
        )
        .order_by(MessageThread.last_message_at.desc().nulls_last())
        .limit(1)
    )
    existing_thread = thread_result.scalar_one_or_none()
    if existing_thread:
        customer_result = await db.execute(
            select(Customer).where(Customer.id == existing_thread.customer_id)
        )
        customer = customer_result.scalar_one_or_none()

    # Fall back to most recently active customer with this phone
    if not customer:
        result = await db.execute(
            select(Customer)
            .where(
                and_(
                    Customer.tenant_id == tenant.id,
                    Customer.phone.in_(sender_candidates),
                )
            )
            .order_by(Customer.updated_at.desc())
            .limit(1)
        )
        customer = result.scalar_one_or_none()
    if not customer:
        customer = Customer(
            tenant_id=tenant.id,
            first_name="SMS",
            last_name="Customer",
            email=f"sms+{normalized_sender}@placeholder.dieselbridge.network",
            phone=normalized_sender,
            source="sms",
            sms_opt_out=False,
        )
        db.add(customer)
        await db.flush()

    _apply_opt_keyword(customer, body)
    thread = await _get_or_create_thread(db, tenant.id, customer)
    now = datetime.now(timezone.utc)

    message = SMSMessage(
        tenant_id=tenant.id,
        thread_id=thread.id,
        customer_id=customer.id,
        direction=SMSMessageDirection.INBOUND,
        source=SMSMessageSource.INBOUND,
        body=body or "",
        from_number=from_number,
        to_number=to_number,
        twilio_message_sid=twilio_message_sid,
        delivery_status=SMSDeliveryStatus.DELIVERED,
        sent_at=now,
        delivered_at=now,
    )
    db.add(message)

    thread.last_message_at = now
    thread.last_message_preview = _preview_text(body or "")
    thread.unread_count_staff = (thread.unread_count_staff or 0) + 1

    await db.commit()
    await db.refresh(message)
    await db.refresh(thread)
    await db.refresh(customer)

    await broadcast_sms_message_event(
        tenant_id=str(tenant.id),
        thread_id=str(thread.id),
        message_id=str(message.id),
        customer_id=str(customer.id),
        direction=message.direction.value,
        source=message.source.value,
        body=message.body,
        delivery_status=message.delivery_status.value,
        created_at=message.created_at.isoformat() if message.created_at else None,
    )
    await broadcast_sms_thread_event(
        tenant_id=str(tenant.id),
        thread_id=str(thread.id),
        customer_id=str(customer.id),
        unread_count_staff=thread.unread_count_staff,
        last_message_at=thread.last_message_at.isoformat() if thread.last_message_at else None,
        last_message_preview=thread.last_message_preview,
    )

    return thread, message, customer, False


async def process_twilio_status_callback(
    db: AsyncSession,
    *,
    message_sid: Optional[str],
    message_status: Optional[str],
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[SMSMessage]:
    if not message_sid:
        return None

    result = await db.execute(select(SMSMessage).where(SMSMessage.twilio_message_sid == message_sid))
    sms_message = result.scalar_one_or_none()
    if not sms_message:
        return None

    now = datetime.now(timezone.utc)
    delivery_status = _twilio_status_to_delivery_status(message_status)
    sms_message.delivery_status = delivery_status
    if delivery_status in {SMSDeliveryStatus.QUEUED, SMSDeliveryStatus.SENT} and not sms_message.sent_at:
        sms_message.sent_at = now
    if delivery_status == SMSDeliveryStatus.DELIVERED:
        sms_message.delivered_at = now
    if delivery_status in {SMSDeliveryStatus.UNDELIVERED, SMSDeliveryStatus.FAILED}:
        sms_message.failed_at = now
        sms_message.error_code = error_code
        sms_message.error_message = error_message

    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.external_id == message_sid,
                Notification.type == NotificationType.SMS,
            )
        )
    )
    notification = result.scalar_one_or_none()
    if notification:
        notification.status = _delivery_status_to_notification_status(delivery_status)
        if delivery_status == SMSDeliveryStatus.DELIVERED:
            notification.delivered_at = now
        if delivery_status in {SMSDeliveryStatus.UNDELIVERED, SMSDeliveryStatus.FAILED}:
            notification.error_message = error_message or notification.error_message

    if error_code == _TWILIO_OPTOUT_ERROR_CODE:
        result = await db.execute(select(Customer).where(Customer.id == sms_message.customer_id))
        customer = result.scalar_one_or_none()
        if customer:
            customer.sms_opt_out = True
            customer.sms_opted_out_at = now
            customer.sms_opt_out_source = "twilio_callback"

    await db.commit()
    await db.refresh(sms_message)

    await broadcast_sms_message_event(
        tenant_id=str(sms_message.tenant_id),
        thread_id=str(sms_message.thread_id),
        message_id=str(sms_message.id),
        customer_id=str(sms_message.customer_id),
        direction=sms_message.direction.value,
        source=sms_message.source.value,
        body=sms_message.body,
        delivery_status=sms_message.delivery_status.value,
        created_at=sms_message.created_at.isoformat() if sms_message.created_at else None,
    )

    return sms_message
