"""Deterministic erasure of customer PII from conversion outbox payloads."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.db.models.invoice import Invoice
from app.db.models.provider_outbox import ProviderOutboxEvent, ProviderOutboxStatus
from app.db.models.repair_order import RepairOrder
from app.db.session import AsyncSessionLocal


CONVERSION_EVENT_TYPES = {
    "repair_order.paid",
    "repair_order.payment_refunded",
    "repair_order.payment_voided",
    "repair_order.payment_adjusted",
}
RETAINED_FIELDS = {
    "event_id", "event_type", "occurred_at", "shop_id", "repair_order_id",
    "invoice_id", "paid_at", "currency", "total_amount",
}
SENSITIVE_FIELDS = {"customer", "attribution", "service_lines"}
TERMINAL_STATUSES = {
    ProviderOutboxStatus.SUCCEEDED.value,
    ProviderOutboxStatus.DEAD.value,
    ProviderOutboxStatus.EXPIRED.value,
}
RETENTION_EXPIRY_ERROR = "Delivery expired under the conversion PII retention policy"


def redact_conversion_payload(event: ProviderOutboxEvent, *, redacted_at: Optional[datetime] = None) -> None:
    payload = event.payload or {}
    event.payload = {key: payload.get(key) for key in RETAINED_FIELDS if key in payload}
    event.payload["pii_redacted_at"] = (redacted_at or datetime.now(timezone.utc)).isoformat()


def conversion_retention_cutoff(
    current: datetime, *, safety_margin_seconds: float = 0
) -> datetime:
    """Oldest safe creation time, including a delivery-attempt safety margin."""
    return (
        current
        - timedelta(days=settings.CONVERSION_OUTBOX_PII_RETENTION_DAYS)
        + timedelta(seconds=safety_margin_seconds)
    )


def conversion_event_is_redacted(event: ProviderOutboxEvent) -> bool:
    return bool((event.payload or {}).get("pii_redacted_at"))


def conversion_event_must_expire(
    event: ProviderOutboxEvent,
    *,
    current: datetime,
    safety_margin_seconds: float = 0,
) -> bool:
    if event.status == ProviderOutboxStatus.EXPIRED.value or conversion_event_is_redacted(event):
        return True
    if event.created_at is None:
        return False
    created_at = event.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at <= conversion_retention_cutoff(
        current, safety_margin_seconds=safety_margin_seconds
    )


def expire_conversion_event(
    event: ProviderOutboxEvent, *, expired_at: Optional[datetime] = None
) -> None:
    """Atomically redact and terminalize a nonterminal conversion event."""
    current = expired_at or datetime.now(timezone.utc)
    redact_conversion_payload(event, redacted_at=current)
    if event.status not in TERMINAL_STATUSES:
        event.status = ProviderOutboxStatus.EXPIRED.value
        event.completed_at = current
        event.available_at = current
        event.lock_token = None
        event.locked_at = None
        event.locked_until = None
        event.last_error = RETENTION_EXPIRY_ERROR


async def purge_expired_conversion_event_pii(
    *, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    now: Optional[datetime] = None,
) -> int:
    current = now or datetime.now(timezone.utc)
    cutoff = conversion_retention_cutoff(current)
    async with session_factory() as db:
        rows = (await db.execute(select(ProviderOutboxEvent).where(
            ProviderOutboxEvent.event_type.in_(CONVERSION_EVENT_TYPES),
            # Retention is an absolute ceiling measured from creation, not
            # completion. It therefore includes queued, leased, and
            # configuration-blocked events.
            ProviderOutboxEvent.created_at <= cutoff,
        ).with_for_update())).scalars().all()
        affected = []
        for event in rows:
            has_pii = bool(SENSITIVE_FIELDS.intersection(event.payload or {}))
            is_nonterminal = event.status not in TERMINAL_STATUSES
            if not has_pii and not is_nonterminal:
                continue
            expire_conversion_event(event, expired_at=current)
            affected.append(event)
        await db.commit()
        return len(affected)


async def erase_customer_conversion_event_pii(db: AsyncSession, *, tenant_id: UUID, customer_id: UUID, apply: bool = False) -> int:
    rows = (await db.execute(
        select(ProviderOutboxEvent)
        .join(Invoice, ProviderOutboxEvent.aggregate_id == Invoice.id)
        .join(RepairOrder, Invoice.repair_order_id == RepairOrder.id)
        .where(
            ProviderOutboxEvent.tenant_id == tenant_id,
            ProviderOutboxEvent.event_type.in_(CONVERSION_EVENT_TYPES),
            RepairOrder.customer_id == customer_id,
        )
        .with_for_update()
    )).scalars().all()
    affected = [
        event for event in rows
        if SENSITIVE_FIELDS.intersection(event.payload or {})
        or event.status not in TERMINAL_STATUSES
    ]
    for event in affected:
        expire_conversion_event(event)
    if apply:
        await db.commit()
    else:
        await db.rollback()
    return len(affected)
