"""Internal operation documentation, separate from customer-facing work scope."""
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrder
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.user import UserRole
from app.schemas.operation_notes import OperationNoteItem, OperationNotesPage
from app.services import operation_execution
from app.services.service_checklist import actor_name

EVENT_TYPE = "operation_note_shop"
SHOP_STAFF = frozenset({UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST})
READ_ROLES = SHOP_STAFF | {UserRole.MECHANIC}
ASSIGNMENT_REASON = "Only the technician assigned to this operation can add a shop note."
FROZEN_REASON = "Shop notes are read-only after the order is finalized or cancelled."
COLLISION_REASON = "This note save ID has already been used. Refresh and try again."


async def load_target(db, order_id, labor_id, actor, *, write=False):
    if actor.role not in READ_ROLES:
        raise HTTPException(403, "Access denied")
    if not actor.tenant_id:
        raise HTTPException(400, "User must be associated with a tenant")
    if write:
        # Match reassignment, finalization and removal lock ordering. Notes never
        # mutate those aggregates, but permission/lifecycle checks must be fresh.
        await operation_execution.lock_tenant_financials(db, actor.tenant_id)
    order_stmt = select(RepairOrder).where(
        RepairOrder.id == order_id, RepairOrder.tenant_id == actor.tenant_id,
        RepairOrder.deleted_at.is_(None),
    ).execution_options(populate_existing=True)
    if write:
        order_stmt = order_stmt.with_for_update(of=RepairOrder)
    order = (await db.execute(order_stmt)).scalar_one_or_none()
    if order is None:
        raise HTTPException(404, "Work order not found")
    line_stmt = select(Labor).where(
        Labor.id == labor_id, Labor.tenant_id == order.tenant_id,
        Labor.repair_order_id == order.id, Labor.deleted_at.is_(None),
    ).execution_options(populate_existing=True)
    if write:
        line_stmt = line_stmt.with_for_update(of=Labor)
    line = (await db.execute(line_stmt)).scalar_one_or_none()
    if line is None:
        raise HTTPException(404, "Operation not found")
    if actor.role == UserRole.MECHANIC:
        if line.line_type == LaborLineType.SUBLET or (
            order.assigned_mechanic_id != actor.id and line.mechanic_id != actor.id
        ):
            raise HTTPException(403, "This operation is not assigned to you")
        if write and line.mechanic_id != actor.id:
            raise HTTPException(403, ASSIGNMENT_REASON)
    return order, line


def read_only_reason(order, line, actor):
    if actor.role == UserRole.MECHANIC and line.mechanic_id != actor.id:
        return ASSIGNMENT_REASON
    if not operation_execution.editable(order):
        return FROZEN_REASON
    return None


def item(event):
    return OperationNoteItem(
        id=event.id, labor_id=event.entity_id, body=event.detail,
        actor_user_id=event.actor_user_id, actor_name=event.actor_name or "Unknown",
        created_at=operation_execution.utc(event.created_at),
    )


async def page(db, order_id, labor_id, actor):
    order, line = await load_target(db, order_id, labor_id, actor)
    events = (await db.scalars(select(RepairOrderHistoryEvent).where(
        RepairOrderHistoryEvent.tenant_id == order.tenant_id,
        RepairOrderHistoryEvent.repair_order_id == order.id,
        RepairOrderHistoryEvent.entity_id == line.id,
        RepairOrderHistoryEvent.event_type == EVENT_TYPE,
        RepairOrderHistoryEvent.deleted_at.is_(None),
    ).order_by(RepairOrderHistoryEvent.created_at, RepairOrderHistoryEvent.id))).all()
    reason = read_only_reason(order, line, actor)
    return OperationNotesPage(items=[item(event) for event in events], can_add=reason is None, read_only_reason=reason)


def exact_replay(event, order, line, actor, body):
    return event is not None and event.deleted_at is None and (
        event.tenant_id == order.tenant_id and event.repair_order_id == order.id
        and event.entity_id == line.id and event.event_type == EVENT_TYPE
        and event.actor_user_id == actor.id and event.detail == body.body
    )


async def append(db, order_id, labor_id, actor, body):
    order, line = await load_target(db, order_id, labor_id, actor, write=True)
    existing = await db.get(RepairOrderHistoryEvent, body.id, populate_existing=True)
    if existing is not None:
        if exact_replay(existing, order, line, actor, body):
            return item(existing), False
        raise HTTPException(409, COLLISION_REASON)
    if not operation_execution.editable(order):
        raise HTTPException(409, FROZEN_REASON)
    event = RepairOrderHistoryEvent(
        id=body.id, tenant_id=order.tenant_id, repair_order_id=order.id,
        entity_id=line.id, event_type=EVENT_TYPE,
        label=f"Shop note · {line.description}"[:255], detail=body.body,
        actor_user_id=actor.id, actor_name=actor_name(actor), created_at=datetime.now(UTC),
    )
    try:
        # Separate shops do not share the tenant lock. A global UUID collision
        # must fail safely without aborting unrelated outer-transaction work.
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        existing = await db.get(RepairOrderHistoryEvent, body.id, populate_existing=True)
        if exact_replay(existing, order, line, actor, body):
            return item(existing), False
        raise HTTPException(409, COLLISION_REASON) from None
    return item(event), True


async def visible_history(db, order, actor, events):
    """Apply the positive note policy before any generic history serialization."""
    if actor.role in SHOP_STAFF or not any(event.event_type == EVENT_TYPE for event in events):
        return events
    allowed_ids = set()
    if actor.role == UserRole.MECHANIC:
        statement = select(Labor.id).where(
            Labor.tenant_id == order.tenant_id, Labor.repair_order_id == order.id,
            Labor.deleted_at.is_(None), Labor.line_type != LaborLineType.SUBLET,
        )
        if order.assigned_mechanic_id != actor.id:
            statement = statement.where(Labor.mechanic_id == actor.id)
        allowed_ids = set((await db.scalars(statement)).all())
    return [event for event in events if event.event_type != EVENT_TYPE or event.entity_id in allowed_ids]
