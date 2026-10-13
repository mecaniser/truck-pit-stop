"""Service checklist rules. All scope mutations serialize on the repair order.

Callers that apply/remove lines or finish work must already hold that row lock.
Checklist mutations never acquire the tenant financial lock after the order.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.labor import Labor
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.service import Service
from app.db.models.service_checklist import RepairOrderChecklistItem as Task
from app.db.models.user import User, UserRole
from app.schemas.service_checklist import (
    ChecklistActor,
    ChecklistPage,
    ChecklistSummary,
    ChecklistTaskResponse,
    ChecklistTaskUpdate,
    ChecklistTaskUpdateResponse,
    ChecklistTemplateResponse,
    ChecklistTemplateUpdate,
)

INTERNAL_EVENT_TYPES = frozenset(
    {
        "checklist_created",
        "checklist_completed",
        "checklist_reopened",
        "checklist_scope_removed",
    }
)
READ_ROLES = {
    UserRole.GARAGE_OWNER,
    UserRole.GARAGE_ADMIN,
    UserRole.RECEPTIONIST,
    UserRole.MECHANIC,
    UserRole.FLEET_MANAGER,
}
WRITE_TEMPLATE_ROLES = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN}


def require_staff(actor: User, *, template_write: bool = False):
    if actor.role not in (WRITE_TEMPLATE_ROLES if template_write else READ_ROLES):
        raise HTTPException(403, "Access denied")
    if not actor.tenant_id:
        raise HTTPException(400, "User must be associated with a tenant")


def actor_name(actor: User | None) -> str:
    if actor is None:
        return "System"
    return f"{actor.first_name or ''} {actor.last_name or ''}".strip() or "Staff"


def event(db, order, task, event_type, actor=None, *, previous=None):
    detail = f"{task.service_name_snapshot}: {task.label}"
    if previous:
        detail += f" (previously completed by {previous[0]} at {previous[1]})"
    db.add(
        RepairOrderHistoryEvent(
            tenant_id=order.tenant_id,
            repair_order_id=order.id,
            event_type=event_type,
            entity_id=task.id,
            label={
                "checklist_created": "Checklist task added",
                "checklist_completed": "Checklist task completed",
                "checklist_reopened": "Checklist task reopened",
                "checklist_scope_removed": "Checklist scope removed",
            }[event_type],
            detail=detail,
            actor_user_id=actor.id if actor else None,
            actor_name=actor_name(actor),
        )
    )


async def load_template(db, service_id, actor, *, for_update=False):
    require_staff(actor, template_write=for_update)
    stmt = (
        select(Service)
        .where(
            Service.id == service_id,
            Service.tenant_id == actor.tenant_id,
            Service.deleted_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    if for_update:
        stmt = stmt.with_for_update(of=Service)
    service = (await db.execute(stmt)).scalar_one_or_none()
    if service is None:
        raise HTTPException(404, "Service not found")
    return service


def template_response(service):
    return ChecklistTemplateResponse(
        service_id=service.id,
        version=service.checklist_version or 0,
        items=service.checklist_template or [],
    )


async def save_template(db, service_id, actor, body: ChecklistTemplateUpdate):
    service = await load_template(db, service_id, actor, for_update=True)
    if service.checklist_version != body.expected_version:
        raise HTTPException(409, "This checklist changed. Reload it before saving.")
    known = {entry["id"] for entry in service.checklist_template}
    if any(item.id is not None and str(item.id) not in known for item in body.items):
        raise HTTPException(422, "Unknown checklist task ID")
    items = [
        {"id": str(item.id or uuid4()), "label": item.label, "required": item.required}
        for item in body.items
    ]
    if items != service.checklist_template:
        service.checklist_template = items
        service.checklist_version += 1
    await db.flush()
    return template_response(service)


async def load_order(db, order_id, actor, *, for_update=False):
    from app.services.operation_execution import load_order as load_execution_order
    return await load_execution_order(db, order_id, actor, write=for_update)


def can_update(order):
    return bool(
        order.deleted_at is None
        and order.status
        in {RepairOrderStatus.IN_PROGRESS, RepairOrderStatus.PENDING_REVIEW}
        and not (
            order.pricing_locked_at is not None
            and order.pricing_lock_reason != "quote_sent"
        )
    )


def active_scope(order, actor=None):
    scope = (
        select(Task)
        .join(
            Labor,
            and_(
                Labor.id == Task.labor_id,
                Labor.tenant_id == order.tenant_id,
                Labor.repair_order_id == order.id,
                Labor.deleted_at.is_(None),
            ),
        )
        .where(
            Task.tenant_id == order.tenant_id,
            Task.repair_order_id == order.id,
            Task.removed_at.is_(None),
            Task.deleted_at.is_(None),
        )
    )
    if actor and actor.role == UserRole.MECHANIC and order.assigned_mechanic_id != actor.id:
        scope = scope.where(Labor.mechanic_id == actor.id)
    return scope


async def summary(db, order, actor=None):
    scope = active_scope(order, actor).subquery()
    row = (
        await db.execute(
            select(
                func.count(),
                func.sum(case((scope.c.is_completed.is_(True), 1), else_=0)),
                func.sum(case((scope.c.required.is_(True), 1), else_=0)),
                func.sum(
                    case(
                        (
                            and_(
                                scope.c.required.is_(True),
                                scope.c.is_completed.is_(False),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
            ).select_from(scope)
        )
    ).one()
    return ChecklistSummary(
        total=row[0],
        completed=row[1] or 0,
        required=row[2] or 0,
        required_remaining=row[3] or 0,
    )


def task_response(task):
    completed_at = task.completed_at
    if completed_at is not None and completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=UTC)
    return ChecklistTaskResponse(
        id=task.id,
        labor_id=task.labor_id,
        service_name=task.service_name_snapshot,
        label=task.label,
        required=task.required,
        position=task.position,
        is_completed=task.is_completed,
        completed_at=completed_at,
        completed_by=ChecklistActor(
            id=task.completed_by_user_id, name=task.completed_by_name
        )
        if task.is_completed
        else None,
        version=task.version,
    )


async def read_checklist(db, order_id, actor, skip=0, limit=100):
    order = await load_order(db, order_id, actor)
    totals = await summary(db, order, actor)
    tasks = (
        (
            await db.execute(
                active_scope(order, actor)
                .order_by(Labor.created_at, Labor.id, Task.position, Task.id)
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    assignments = dict((await db.execute(select(Labor.id, Labor.mechanic_id).where(Labor.tenant_id == order.tenant_id, Labor.repair_order_id == order.id))).all())
    items = []
    for task in tasks:
        item = task_response(task)
        item.can_update = can_update(order) and (actor.role != UserRole.MECHANIC or assignments.get(task.labor_id) == actor.id or (assignments.get(task.labor_id) is None and order.assigned_mechanic_id == actor.id))
        items.append(item)
    return ChecklistPage(
        items=items,
        total=totals.total,
        skip=skip,
        limit=limit,
        summary=totals,
        can_update=can_update(order),
    )


async def update_task(db, order_id, item_id, actor, body: ChecklistTaskUpdate):
    order = await load_order(db, order_id, actor, for_update=True)
    task = (
        await db.execute(
            active_scope(order)
            .where(Task.id == item_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "Checklist task not found")
    line = (await db.execute(select(Labor).where(Labor.id == task.labor_id, Labor.tenant_id == order.tenant_id, Labor.repair_order_id == order.id))).scalar_one()
    if actor.role == UserRole.MECHANIC and line.mechanic_id != actor.id and not (line.mechanic_id is None and order.assigned_mechanic_id == actor.id):
        raise HTTPException(403, "Only the assigned technician can update this operation's checklist.")
    if task.required and task.is_completed and not body.is_completed and line.execution_status == 'completed':
        raise HTTPException(409, "Reopen the operation before reopening a required task.")
    if not can_update(order):
        raise HTTPException(409, "Checklist changes require an open work order.")
    if task.version != body.expected_version:
        raise HTTPException(
            409, "This task changed. Refresh the checklist and try again."
        )
    if task.is_completed != body.is_completed:
        previous = (
            (task.completed_by_name, task.completed_at.isoformat())
            if task.is_completed
            else None
        )
        task.is_completed = body.is_completed
        task.completed_at = datetime.now(UTC) if body.is_completed else None
        task.completed_by_user_id = actor.id if body.is_completed else None
        task.completed_by_name = actor_name(actor) if body.is_completed else None
        task.version += 1
        event(
            db,
            order,
            task,
            "checklist_completed" if body.is_completed else "checklist_reopened",
            actor,
            previous=previous,
        )
        await db.flush()
    return ChecklistTaskUpdateResponse(
        **task_response(task).model_dump(exclude={"can_update"}),
        summary=await summary(db, order, actor),
        can_update=True,
    )


async def snapshot_service(db: AsyncSession, order, labor, service, actor=None):
    """Only call for a genuinely new application, never for an existing line."""
    if (
        labor.tenant_id != order.tenant_id
        or labor.repair_order_id != order.id
        or service.tenant_id != order.tenant_id
    ):
        raise HTTPException(404, "Source reference not found")
    await db.flush()
    for position, entry in enumerate(service.checklist_template or []):
        task = Task(
            id=uuid4(),
            tenant_id=order.tenant_id,
            repair_order_id=order.id,
            labor_id=labor.id,
            labor_id_snapshot=labor.id,
            source_service_id_snapshot=service.id,
            source_template_item_id=UUID(entry["id"]),
            source_template_version=service.checklist_version,
            service_name_snapshot=service.name,
            label=entry["label"],
            required=entry["required"],
            position=position,
            is_completed=False,
            version=1,
        )
        db.add(task)
        event(db, order, task, "checklist_created", actor)
    await db.flush()


async def archive_labor(db, order, labor, actor=None):
    from app.services.operation_execution import remove
    await remove(db, order, labor, actor)
    tasks = (
        (await db.execute(active_scope(order).where(Task.labor_id == labor.id)))
        .scalars()
        .all()
    )
    for task in tasks:
        task.removed_at = datetime.now(UTC)
        task.labor_id = None
        event(db, order, task, "checklist_scope_removed", actor)
    await db.flush()


async def preserve_labor_snapshot(db, order, old_labor, new_labor):
    """Retain even the absence of tasks when PM replaces a retained labor row."""
    tasks = (
        (await db.execute(active_scope(order).where(Task.labor_id == old_labor.id)))
        .scalars()
        .all()
    )
    await db.flush()
    for task in tasks:
        task.labor_id = new_labor.id
    await db.flush()


async def forbid_source_change(db, order, labor, source_service_id):
    if labor.source_service_id != source_service_id:
        found = await db.scalar(
            select(Task.id)
            .where(
                Task.tenant_id == order.tenant_id,
                Task.repair_order_id == order.id,
                Task.labor_id_snapshot == labor.id,
            )
            .limit(1)
        )
        attached = await db.scalar(
            select(Task.id)
            .where(
                Task.tenant_id == order.tenant_id,
                Task.repair_order_id == order.id,
                Task.labor_id == labor.id,
            )
            .limit(1)
        )
        if found or attached:
            raise HTTPException(
                409,
                "Remove this service and add the replacement to change its checklist.",
            )


async def guard_completion(db, order):
    from app.services.operation_execution import guard_completion as operations_guard
    remaining = (await summary(db, order)).required_remaining
    if remaining:
        raise HTTPException(
            409,
            f"Complete the {remaining} required checklist tasks before finishing this work order.",
        )
    await operations_guard(db, order)
