"""Shop-wide recent activity feed.

Merges timestamped events from RepairOrder/Quote/Invoice/Payment into one
chronological, cursor-paginated feed — no dedicated activity-log table.
Reuses the same event vocabulary as the per-order timeline synthesized in
the frontend (RepairOrdersPage.tsx's priceBuilderHistoryEvents), just
computed shop-wide instead of for a single order.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_db
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.quote import Quote
from app.db.models.repair_order import RepairOrder
from app.db.models.user import User

router = APIRouter()

# Staff roles that can see the shop-wide feed. Mechanics/fleet managers stay
# scoped to their own boards; this is an owner/admin/receptionist overview.
ACTIVITY_ROLES = ("garage_owner", "garage_admin", "receptionist")

# How many source rows to pull per entity per page — generous over-fetch so
# merging+sorting across tables still yields `limit` results after the
# cursor cut, without pulling the whole table every request.
_FANOUT_MULTIPLIER = 4

# Same-day cancel+delete count that triggers the anomaly callout — a rough
# "heads up, something unusual is happening" signal, not a hard rule.
_ANOMALY_THRESHOLD = 3


class ActivityEvent(BaseModel):
    id: str
    event_type: str
    label: str
    occurred_at: datetime
    actor_name: Optional[str] = None
    actor_id: Optional[str] = None
    order_number: Optional[str] = None
    order_id: Optional[str] = None
    detail: Optional[str] = None


class ActivityActor(BaseModel):
    id: str
    name: str


class ActivityFeedResponse(BaseModel):
    items: list[ActivityEvent]
    next_cursor: Optional[str] = None
    has_more: bool = False
    available_actors: list[ActivityActor] = []
    warnings: list[str] = []


def _encode_cursor(dt: datetime, event_id: str) -> str:
    return f"{dt.isoformat()}|{event_id}"


def _decode_cursor(cursor: Optional[str]) -> tuple[Optional[datetime], Optional[str]]:
    if not cursor:
        return None, None
    try:
        raw_dt, raw_id = cursor.split("|", 1)
        return datetime.fromisoformat(raw_dt), raw_id
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor")


def _user_name(u: Optional[User]) -> Optional[str]:
    return f"{u.first_name} {u.last_name}".strip() if u else None


def _aware(dt: datetime) -> datetime:
    # Some drivers (notably SQLite, used in tests) return naive datetimes
    # even for timezone(True) columns. Treat naive values as UTC so they
    # compare cleanly against aware ones from other rows.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@router.get("", response_model=ActivityFeedResponse)
async def list_activity(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor_id: Optional[UUID] = Query(None),
    event_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.role not in ACTIVITY_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if not current_user.tenant_id:
        return ActivityFeedResponse(items=[], next_cursor=None, has_more=False)

    tenant_id = current_user.tenant_id
    cursor_dt, cursor_id = _decode_cursor(cursor)
    fetch_n = limit * _FANOUT_MULTIPLIER

    events: list[ActivityEvent] = []

    ro_result = await db.execute(
        select(RepairOrder)
        .where(RepairOrder.tenant_id == tenant_id)
        .order_by(RepairOrder.created_at.desc())
        .limit(fetch_n)
    )
    orders = ro_result.scalars().all()

    quote_result = await db.execute(
        select(Quote)
        .join(RepairOrder, RepairOrder.id == Quote.repair_order_id)
        .where(RepairOrder.tenant_id == tenant_id, Quote.sent_at.isnot(None))
        .order_by(Quote.sent_at.desc())
        .limit(fetch_n)
    )
    quotes = quote_result.scalars().all()

    invoice_result = await db.execute(
        select(Invoice)
        .where(Invoice.tenant_id == tenant_id)
        .order_by(Invoice.created_at.desc())
        .limit(fetch_n)
    )
    invoices = invoice_result.scalars().all()

    payment_result = await db.execute(
        select(Payment)
        .where(Payment.tenant_id == tenant_id)
        .order_by(Payment.created_at.desc())
        .limit(fetch_n)
    )
    payments = payment_result.scalars().all()

    # Batch-resolve actor names and order numbers in one pass each.
    actor_ids: set[UUID] = set()
    for o in orders:
        if o.cancelled_by_user_id:
            actor_ids.add(o.cancelled_by_user_id)
        if o.deleted_by_user_id:
            actor_ids.add(o.deleted_by_user_id)
    for q in quotes:
        if q.sent_by_user_id:
            actor_ids.add(q.sent_by_user_id)
    for inv in invoices:
        if inv.created_by_user_id:
            actor_ids.add(inv.created_by_user_id)
    for p in payments:
        if p.recorded_by_user_id:
            actor_ids.add(p.recorded_by_user_id)

    actor_map: dict[UUID, str] = {}
    if actor_ids:
        actor_result = await db.execute(
            select(User.id, User.first_name, User.last_name).where(User.id.in_(actor_ids))
        )
        actor_map = {row[0]: f"{row[1]} {row[2]}".strip() for row in actor_result.fetchall()}

    order_number_by_id: dict[UUID, str] = {o.id: o.order_number for o in orders}
    order_ids_needed = {q.repair_order_id for q in quotes} | {i.repair_order_id for i in invoices}
    order_ids_needed -= set(order_number_by_id.keys())
    if order_ids_needed:
        extra_result = await db.execute(
            select(RepairOrder.id, RepairOrder.order_number).where(RepairOrder.id.in_(order_ids_needed))
        )
        order_number_by_id.update({row[0]: row[1] for row in extra_result.fetchall()})

    invoice_order_id: dict[UUID, UUID] = {i.id: i.repair_order_id for i in invoices}
    invoice_number_by_id: dict[UUID, str] = {i.id: i.invoice_number for i in invoices}

    for o in orders:
        events.append(ActivityEvent(
            id=f"ro-{o.id}-created", event_type="ro_created", label="Repair order created",
            occurred_at=_aware(o.created_at), order_number=o.order_number, order_id=str(o.id),
        ))
        if o.cancelled_at:
            events.append(ActivityEvent(
                id=f"ro-{o.id}-cancelled", event_type="ro_cancelled", label="Order cancelled",
                occurred_at=_aware(o.cancelled_at), order_number=o.order_number, order_id=str(o.id),
                actor_name=actor_map.get(o.cancelled_by_user_id) if o.cancelled_by_user_id else None,
                actor_id=str(o.cancelled_by_user_id) if o.cancelled_by_user_id else None,
            ))
        if o.deleted_at:
            events.append(ActivityEvent(
                id=f"ro-{o.id}-deleted", event_type="ro_deleted", label="Order deleted",
                occurred_at=_aware(o.deleted_at), order_number=o.order_number, order_id=str(o.id),
                actor_name=actor_map.get(o.deleted_by_user_id) if o.deleted_by_user_id else None,
                actor_id=str(o.deleted_by_user_id) if o.deleted_by_user_id else None,
            ))
        if o.work_completed_at:
            events.append(ActivityEvent(
                id=f"ro-{o.id}-completed", event_type="ro_completed", label="Work completed",
                occurred_at=_aware(o.work_completed_at), order_number=o.order_number, order_id=str(o.id),
            ))

    for q in quotes:
        events.append(ActivityEvent(
            id=f"quote-{q.id}-sent", event_type="quote_sent", label="Quote sent to customer",
            occurred_at=_aware(q.sent_at), detail=q.quote_number,
            order_number=order_number_by_id.get(q.repair_order_id),
            order_id=str(q.repair_order_id),
            actor_name=actor_map.get(q.sent_by_user_id) if q.sent_by_user_id else None,
            actor_id=str(q.sent_by_user_id) if q.sent_by_user_id else None,
        ))

    for inv in invoices:
        events.append(ActivityEvent(
            id=f"invoice-{inv.id}-created", event_type="invoice_created", label="Invoice created",
            occurred_at=_aware(inv.created_at), detail=inv.invoice_number,
            order_number=order_number_by_id.get(inv.repair_order_id),
            order_id=str(inv.repair_order_id),
            actor_name=actor_map.get(inv.created_by_user_id) if inv.created_by_user_id else None,
            actor_id=str(inv.created_by_user_id) if inv.created_by_user_id else None,
        ))
        if inv.paid_at:
            events.append(ActivityEvent(
                id=f"invoice-{inv.id}-paid", event_type="invoice_paid", label="Invoice paid",
                occurred_at=_aware(inv.paid_at), detail=inv.invoice_number,
                order_number=order_number_by_id.get(inv.repair_order_id),
                order_id=str(inv.repair_order_id),
            ))

    for p in payments:
        order_id = invoice_order_id.get(p.invoice_id)
        events.append(ActivityEvent(
            id=f"payment-{p.id}-recorded", event_type="payment_recorded", label="Payment recorded",
            occurred_at=_aware(p.created_at), detail=invoice_number_by_id.get(p.invoice_id),
            order_number=order_number_by_id.get(order_id) if order_id else None,
            order_id=str(order_id) if order_id else None,
            actor_name=actor_map.get(p.recorded_by_user_id) if p.recorded_by_user_id else None,
            actor_id=str(p.recorded_by_user_id) if p.recorded_by_user_id else None,
        ))

    events.sort(key=lambda e: (e.occurred_at, e.id), reverse=True)

    # Anomaly signal: an unusual same-day spike in cancellations/deletions,
    # computed over the full unfiltered merge so it reflects today
    # regardless of what filters the caller applied to the returned page.
    today = datetime.now(timezone.utc).date()
    today_cancel_delete = sum(
        1 for e in events
        if e.event_type in ("ro_cancelled", "ro_deleted") and e.occurred_at.date() == today
    )
    warnings: list[str] = []
    if today_cancel_delete >= _ANOMALY_THRESHOLD:
        warnings.append(f"{today_cancel_delete} orders were cancelled or deleted today — worth a look.")

    available_actors = [
        ActivityActor(id=str(uid), name=name) for uid, name in sorted(actor_map.items(), key=lambda kv: kv[1])
    ]

    if actor_id is not None:
        events = [e for e in events if e.actor_id == str(actor_id)]
    if event_type is not None:
        events = [e for e in events if e.event_type == event_type]
    if date_from is not None:
        events = [e for e in events if e.occurred_at.date() >= date_from]
    if date_to is not None:
        events = [e for e in events if e.occurred_at.date() <= date_to]

    if cursor_dt and cursor_id:
        events = [e for e in events if (e.occurred_at, e.id) < (cursor_dt, cursor_id)]

    has_more = len(events) > limit
    page = events[:limit]
    next_cursor = _encode_cursor(page[-1].occurred_at, page[-1].id) if has_more and page else None

    return ActivityFeedResponse(
        items=page, next_cursor=next_cursor, has_more=has_more,
        available_actors=available_actors, warnings=warnings,
    )
