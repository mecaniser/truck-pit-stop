"""Tenant-serialized staff holds. The caller owns the single transaction."""
from datetime import UTC, datetime, timedelta
import json

from fastapi import HTTPException

from app.db.models.repair_order import RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.user import UserRole
from app.services import operation_execution
from app.services.service_checklist import actor_name


INTERNAL_EVENT_TYPES = frozenset({"work_held", "work_hold_released"})


def can_read(actor):
    return actor.role in operation_execution.STAFF | {UserRole.MECHANIC}


def utc(value):
    return operation_execution.utc(value).astimezone(UTC)


async def transition(db, order_id, actor, body, *, release=False):
    # Staff-only before lookup; mechanic self-resume remains a separate route.
    if actor.role not in operation_execution.STAFF:
        raise HTTPException(403, "Only shop staff can manage work holds.")
    order = await operation_execution.load_order(db, order_id, actor, write=True)
    if not operation_execution.editable(order) or order.status != RepairOrderStatus.IN_PROGRESS:
        raise HTTPException(409, "Work holds require an editable in-progress order.")
    previous_updated_at = utc(order.updated_at)
    if utc(body.expected_updated_at) != previous_updated_at:
        raise HTTPException(409, "This order changed. Refresh it and try again.")
    if release and not order.hold_reason:
        raise HTTPException(409, "This order is not on hold. Refresh it and try again.")
    if not release and order.hold_reason:
        raise HTTPException(409, "This order is already on hold. Refresh it and try again.")

    stamp = max(datetime.now(UTC), previous_updated_at + timedelta(microseconds=1))
    former_reason = order.hold_reason
    former_held_at = utc(order.held_at).isoformat() if order.held_at else None
    stopped = []
    if release:
        order.hold_reason = None
        order.held_at = None
    else:
        stopped = await operation_execution.stop_order_sessions(
            db, order, actor, now=stamp, reason="hold"
        )
        order.hold_reason = body.reason
        order.held_at = stamp
    order.updated_at = stamp
    db.add(RepairOrderHistoryEvent(
        tenant_id=order.tenant_id,
        repair_order_id=order.id,
        event_type="work_hold_released" if release else "work_held",
        label="Work hold released" if release else "Work placed on hold",
        detail=json.dumps({
            "previous": {"hold_reason": former_reason, "held_at": former_held_at},
            "current": {"hold_reason": order.hold_reason,
                        "held_at": order.held_at.isoformat() if order.held_at else None},
        }),
        actor_user_id=actor.id,
        actor_name=actor_name(actor),
    ))
    await db.flush()
    await db.refresh(order)
    return order, stopped
