"""Transactional outbox helpers and worker-side provider delivery.

The request path only creates a Notification and outbox record in its existing
transaction. Provider I/O happens after a worker commits a short lease, so a
slow network call never occupies the request's database connection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.notification import Notification, NotificationStatus, NotificationType
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.session import AsyncSessionLocal


logger = get_logger(__name__)
EMAIL_NOTIFICATION_EVENT = "email.notification.v1"


class ProviderDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class ClaimedOutboxEvent:
    event_id: UUID
    lock_token: str


@dataclass(frozen=True)
class EmailDelivery:
    event_id: UUID
    lock_token: str
    notification_id: UUID
    idempotency_key: str
    sender_name: Optional[str]
    recipient: str
    subject: str
    body: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _format_sender(sender_name: Optional[str]) -> str:
    display_name = (sender_name or "").strip().replace('"', "'")
    if not display_name:
        return settings.RESEND_FROM_EMAIL
    return f'"{display_name}" <{settings.RESEND_FROM_EMAIL}>'


def _safe_error(error: BaseException) -> str:
    """Keep provider failures useful without persisting message content or PII."""
    return f"{type(error).__name__}: {str(error)[:500]}"


def _retry_delay(attempt_count: int) -> timedelta:
    # 30s, 60s, 120s, 240s... capped so a bad provider does not create a hot loop.
    seconds = min(
        settings.PROVIDER_OUTBOX_RETRY_BASE_SECONDS * (2 ** max(attempt_count - 1, 0)),
        settings.PROVIDER_OUTBOX_RETRY_MAX_SECONDS,
    )
    return timedelta(seconds=seconds)


async def enqueue_email_notification(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID,
    idempotency_key: str,
    recipient: str,
    subject: str,
    body: str,
    template_name: Optional[str],
    sender_name: Optional[str],
) -> ProviderOutboxEvent:
    """Add the email history record and its durable delivery event to ``db``.

    The caller owns the transaction and must commit its domain change and the
    returned event together. No provider request is made here.
    """
    notification = Notification(
        tenant_id=tenant_id,
        type=NotificationType.EMAIL,
        status=NotificationStatus.PENDING,
        recipient_email=recipient,
        subject=subject,
        body=body,
        template_name=template_name,
    )
    db.add(notification)
    await db.flush()

    event = ProviderOutboxEvent(
        tenant_id=tenant_id,
        event_type=EMAIL_NOTIFICATION_EVENT,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        # The payload intentionally references persisted data instead of
        # duplicating recipient/content in the outbox table.
        payload={"notification_id": str(notification.id), "sender_name": sender_name},
        idempotency_key=idempotency_key,
        status=ProviderOutboxStatus.PENDING.value,
        available_at=_now(),
    )
    db.add(event)
    return event


async def _claim_due_events(db: AsyncSession, *, limit: int) -> list[ClaimedOutboxEvent]:
    now = _now()
    due = or_(
        and_(
            ProviderOutboxEvent.status == ProviderOutboxStatus.PENDING.value,
            ProviderOutboxEvent.available_at <= now,
        ),
        and_(
            ProviderOutboxEvent.status == ProviderOutboxStatus.PROCESSING.value,
            ProviderOutboxEvent.locked_until.is_not(None),
            ProviderOutboxEvent.locked_until <= now,
        ),
    )
    result = await db.execute(
        select(ProviderOutboxEvent)
        .where(ProviderOutboxEvent.event_type == EMAIL_NOTIFICATION_EVENT, due)
        .order_by(ProviderOutboxEvent.available_at, ProviderOutboxEvent.created_at)
        .limit(limit)
        # PostgreSQL workers do not block or double-claim each other's rows.
        # SQLite ignores this clause in the focused test suite.
        .with_for_update(skip_locked=True)
    )
    events = result.scalars().all()
    claimed: list[ClaimedOutboxEvent] = []
    for event in events:
        token = uuid4().hex
        event.status = ProviderOutboxStatus.PROCESSING.value
        event.attempt_count += 1
        event.locked_at = now
        event.locked_until = now + timedelta(seconds=settings.PROVIDER_OUTBOX_LEASE_SECONDS)
        event.lock_token = token
        claimed.append(ClaimedOutboxEvent(event.id, token))
    await db.commit()
    return claimed


async def _load_email_delivery(
    db: AsyncSession,
    claim: ClaimedOutboxEvent,
) -> Optional[EmailDelivery]:
    event = await db.get(ProviderOutboxEvent, claim.event_id)
    if (
        not event
        or event.status != ProviderOutboxStatus.PROCESSING.value
        or event.lock_token != claim.lock_token
        or event.event_type != EMAIL_NOTIFICATION_EVENT
    ):
        return None

    notification_id = (event.payload or {}).get("notification_id")
    if not notification_id:
        return None
    notification = await db.get(Notification, UUID(str(notification_id)))
    if not notification or notification.type != NotificationType.EMAIL:
        return None
    if not notification.recipient_email or not notification.subject:
        return None

    return EmailDelivery(
        event_id=event.id,
        lock_token=claim.lock_token,
        notification_id=notification.id,
        idempotency_key=event.idempotency_key,
        sender_name=(event.payload or {}).get("sender_name"),
        recipient=notification.recipient_email,
        subject=notification.subject,
        body=notification.body,
    )


async def _deliver_email(delivery: EmailDelivery) -> Optional[str]:
    if not settings.RESEND_API_KEY:
        raise ProviderDeliveryError("Resend is not configured", retryable=False)

    try:
        timeout = httpx.Timeout(settings.PROVIDER_OUTBOX_EMAIL_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    # Resend retains this key for 24 hours, protecting the
                    # narrow worker-crash window after provider acceptance.
                    "Idempotency-Key": delivery.idempotency_key,
                    "User-Agent": "truck-pit-stop-provider-outbox/1.0",
                },
                json={
                    "from": _format_sender(delivery.sender_name),
                    "to": delivery.recipient,
                    "subject": delivery.subject,
                    "html": delivery.body,
                },
            )
        if response.status_code >= 400:
            raise ProviderDeliveryError(
                f"Resend returned HTTP {response.status_code}",
                retryable=response.status_code == 429 or response.status_code >= 500,
            )
        response_data = response.json()
        return str(response_data.get("id")) if isinstance(response_data, dict) and response_data.get("id") else None
    except ProviderDeliveryError:
        raise
    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as error:
        raise ProviderDeliveryError("Resend network request failed", retryable=True) from error
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderDeliveryError("Resend response was invalid", retryable=False) from error


async def _mark_succeeded(
    db: AsyncSession,
    delivery: EmailDelivery,
    provider_message_id: Optional[str],
) -> bool:
    event = await db.get(ProviderOutboxEvent, delivery.event_id)
    notification = await db.get(Notification, delivery.notification_id)
    if (
        not event
        or event.status != ProviderOutboxStatus.PROCESSING.value
        or event.lock_token != delivery.lock_token
        or not notification
    ):
        return False

    now = _now()
    event.status = ProviderOutboxStatus.SUCCEEDED.value
    event.completed_at = now
    event.provider_message_id = provider_message_id
    event.last_error = None
    event.locked_until = None
    notification.status = NotificationStatus.SENT
    notification.external_id = provider_message_id
    notification.sent_at = now
    await db.commit()
    return True


async def _mark_failed(
    db: AsyncSession,
    claim: ClaimedOutboxEvent,
    error: BaseException,
    *,
    retryable: bool,
) -> bool:
    event = await db.get(ProviderOutboxEvent, claim.event_id)
    if (
        not event
        or event.status != ProviderOutboxStatus.PROCESSING.value
        or event.lock_token != claim.lock_token
    ):
        return False

    now = _now()
    event.last_error = _safe_error(error)
    event.locked_until = None
    event.lock_token = None
    should_retry = retryable and event.attempt_count < settings.PROVIDER_OUTBOX_MAX_ATTEMPTS
    if should_retry:
        event.status = ProviderOutboxStatus.PENDING.value
        event.available_at = now + _retry_delay(event.attempt_count)
    else:
        event.status = ProviderOutboxStatus.DEAD.value
        event.completed_at = now
        notification_id = (event.payload or {}).get("notification_id")
        if notification_id:
            notification = await db.get(Notification, UUID(str(notification_id)))
            if notification:
                notification.status = NotificationStatus.FAILED
                notification.error_message = event.last_error
    await db.commit()
    return should_retry


async def process_due_provider_outbox_events(
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    deliver_email: Callable[[EmailDelivery], object] = _deliver_email,
    batch_size: Optional[int] = None,
) -> dict[str, int]:
    """Claim and process one bounded outbox batch.

    Each claim and final state update gets a short DB transaction. The Resend
    request runs between them, with no session/transaction held open.
    """
    limit = batch_size or settings.PROVIDER_OUTBOX_BATCH_SIZE
    async with session_factory() as db:
        claims = await _claim_due_events(db, limit=limit)

    results = {"claimed": len(claims), "succeeded": 0, "retried": 0, "dead": 0, "invalid": 0}
    for claim in claims:
        async with session_factory() as db:
            delivery = await _load_email_delivery(db, claim)

        if not delivery:
            async with session_factory() as db:
                retried = await _mark_failed(
                    db,
                    claim,
                    ProviderDeliveryError("Outbox email payload is invalid", retryable=False),
                    retryable=False,
                )
            results["retried" if retried else "invalid"] += 1
            continue

        try:
            provider_message_id = await deliver_email(delivery)
        except ProviderDeliveryError as error:
            async with session_factory() as db:
                retried = await _mark_failed(db, claim, error, retryable=error.retryable)
            results["retried" if retried else "dead"] += 1
            logger.warning(
                "provider_outbox_email_failed",
                event_id=str(claim.event_id),
                retry_scheduled=retried,
            )
            continue
        except Exception:  # pragma: no cover - defensive worker boundary
            async with session_factory() as db:
                retried = await _mark_failed(
                    db,
                    claim,
                    ProviderDeliveryError("Unexpected email delivery error", retryable=True),
                    retryable=True,
                )
            results["retried" if retried else "dead"] += 1
            logger.exception(
                "provider_outbox_email_unexpected_failure",
                event_id=str(claim.event_id),
                retry_scheduled=retried,
            )
            continue

        async with session_factory() as db:
            marked = await _mark_succeeded(db, delivery, provider_message_id)
        if marked:
            results["succeeded"] += 1

    return results
