"""Tenant-serialized operation workflow; helpers never acquire whole-order authority."""
from datetime import UTC, datetime
from fastapi import HTTPException
from sqlalchemy import select, and_, or_, func
from app.db.models.labor import Labor, LaborLineType
from app.db.models.mechanic_time import MechanicTimeSession, MechanicSessionType
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.service_checklist import RepairOrderChecklistItem as Task
from app.db.models.user import User, UserRole
from app.services.financial_transaction_lock import lock_tenant_financials as _lock_tenant
from app.services.service_checklist import actor_name

STAFF = {UserRole.GARAGE_OWNER, UserRole.GARAGE_ADMIN, UserRole.RECEPTIONIST, UserRole.FLEET_MANAGER}
INTERNAL_EVENT_TYPES = frozenset({'operation_assigned', 'operation_completed', 'operation_reopened', 'operation_scope_removed'})
FINAL = {Status.COMPLETED, Status.INVOICED, Status.PAID, Status.CANCELLED}

async def lock_tenant_financials(db, tenant_id):
    from app.services.invoice_settlement_service import SettlementDomainError
    try:
        await _lock_tenant(db, tenant_id)
    except SettlementDomainError as exc:
        raise HTTPException(409, 'This shop has another workflow update in progress. Refresh and retry.') from exc


def utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value

def assignment_scope(tenant_id, mechanic_id):
    return select(Labor.id).where(Labor.tenant_id == tenant_id, Labor.repair_order_id == RepairOrder.id,
        Labor.mechanic_id == mechanic_id, Labor.deleted_at.is_(None), Labor.line_type != LaborLineType.SUBLET).exists()

def job_scope(tenant_id, mechanic_id):
    return or_(RepairOrder.assigned_mechanic_id == mechanic_id, assignment_scope(tenant_id, mechanic_id))

def editable(order):
    return order.deleted_at is None and order.status not in FINAL and not (order.pricing_locked_at and order.pricing_lock_reason != 'quote_sent')

def clear_completion_snapshot(order):
    order.work_completed_at = None
    order.actual_tracked_minutes = None
    order.total_hold_minutes = None


def enroll_new_scope(order):
    if order.status == Status.PENDING_REVIEW:
        order.status = Status.IN_PROGRESS
        clear_completion_snapshot(order)


def executable(order):
    return editable(order) and order.status == Status.IN_PROGRESS and not order.hold_reason

async def load_order(db, order_id, actor, *, write=False):
    if actor.role not in STAFF | {UserRole.MECHANIC}:
        raise HTTPException(403, 'Access denied')
    if not actor.tenant_id:
        raise HTTPException(400, 'User must be associated with a tenant')
    if write:
        await lock_tenant_financials(db, actor.tenant_id)
    stmt = select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.tenant_id == actor.tenant_id, RepairOrder.deleted_at.is_(None)).execution_options(populate_existing=True)
    if write:
        stmt = stmt.with_for_update(of=RepairOrder)
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(404, 'Work order not found')
    if actor.role == UserRole.FLEET_MANAGER and not (order.is_internal or order.is_fleet_work):
        raise HTTPException(403, 'Access denied')
    if actor.role == UserRole.MECHANIC and order.assigned_mechanic_id != actor.id:
        if not await db.scalar(select(Labor.id).where(Labor.tenant_id == actor.tenant_id, Labor.repair_order_id == order.id, Labor.mechanic_id == actor.id, Labor.deleted_at.is_(None), Labor.line_type != LaborLineType.SUBLET).limit(1)):
            raise HTTPException(403, 'This job is not assigned to you')
    return order

async def load_labor(db, order, labor_id):
    line = (await db.execute(select(Labor).where(Labor.id == labor_id, Labor.tenant_id == order.tenant_id,
        Labor.repair_order_id == order.id, Labor.deleted_at.is_(None)).execution_options(populate_existing=True).with_for_update(of=Labor))).scalar_one_or_none()
    if not line:
        raise HTTPException(404, 'Operation not found')
    return line

async def validate_assignee(db, tenant_id, mechanic_id):
    if mechanic_id is None:
        return None
    user = (await db.execute(select(User).where(User.id == mechanic_id, User.tenant_id == tenant_id, User.deleted_at.is_(None), User.is_active.is_(True), User.role == UserRole.MECHANIC))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, 'Choose an active technician from this shop.')
    return user

def version(line, expected):
    if (line.execution_version or 0) != expected:
        raise HTTPException(409, 'This operation changed. Refresh it and try again.')

def require_internal(line):
    if line.line_type == LaborLineType.SUBLET:
        raise HTTPException(409, 'Sublet work is reviewed with the order and has no internal technician execution.')

def require_executor(actor, line):
    if actor.role == UserRole.MECHANIC and line.mechanic_id != actor.id:
        raise HTTPException(403, 'Only the assigned technician can execute this operation.')

def record(db, order, line, kind, actor, before):
    db.add(RepairOrderHistoryEvent(tenant_id=order.tenant_id, repair_order_id=order.id, entity_id=line.id,
        event_type=kind, label={'operation_assigned':'Operation technician changed','operation_completed':'Operation completed','operation_reopened':'Operation reopened','operation_scope_removed':'Operation removed'}[kind],
        detail=f'{line.description}; before: {before}; after: technician={line.mechanic_id}, status={line.execution_status}, version={line.execution_version}',
        actor_user_id=actor.id if actor else None, actor_name=actor_name(actor)))

def snapshot(line):
    return f'technician={line.mechanic_id}, status={line.execution_status}, version={line.execution_version}, completed_by={line.completed_by_name}, completed_at={line.completed_at}'

async def active_for_line(db, order, line):
    return (await db.execute(select(MechanicTimeSession).where(MechanicTimeSession.tenant_id == order.tenant_id, MechanicTimeSession.repair_order_id == order.id,
        MechanicTimeSession.labor_id_snapshot == line.id, MechanicTimeSession.ended_at.is_(None), MechanicTimeSession.deleted_at.is_(None)).execution_options(populate_existing=True))).scalars().all()

async def required_remaining(db, order, line):
    return await db.scalar(select(func.count(Task.id)).where(Task.tenant_id == order.tenant_id, Task.repair_order_id == order.id, Task.labor_id == line.id,
        Task.deleted_at.is_(None), Task.removed_at.is_(None), Task.required.is_(True), Task.is_completed.is_(False))) or 0

async def assign(db, order_id, labor_id, actor, body):
    order = await load_order(db, order_id, actor, write=True)
    line = await load_labor(db, order, labor_id)
    if actor.role not in STAFF:
        raise HTTPException(403, 'Only shop staff can assign operations.')
    require_internal(line)
    version(line, body.expected_version)
    if not editable(order) or order.status == Status.PENDING_REVIEW:
        raise HTTPException(409, 'Reopen work before changing assignments on an order awaiting review.')
    await validate_assignee(db, order.tenant_id, body.mechanic_id)
    if line.mechanic_id == body.mechanic_id and line.execution_status is not None:
        return await page(db, order_id, actor)
    if line.execution_status == 'completed':
        raise HTTPException(409, 'Reopen the operation before changing its technician.')
    if await active_for_line(db, order, line):
        raise HTTPException(409, 'Stop the operation timer before changing its technician.')
    before = snapshot(line)
    line.mechanic_id = body.mechanic_id
    line.execution_status = 'pending'
    line.execution_version = (line.execution_version or 0) + 1
    record(db, order, line, 'operation_assigned', actor, before)
    await db.flush()
    return await page(db, order_id, actor)

async def complete(db, order_id, labor_id, actor, body):
    order = await load_order(db, order_id, actor, write=True)
    line = await load_labor(db, order, labor_id)
    require_internal(line)
    require_executor(actor, line)
    version(line, body.expected_version)
    if not editable(order):
        raise HTTPException(409, 'Operation changes require an editable order.')
    if (line.execution_status == 'completed') == body.is_completed:
        return await page(db, order_id, actor)
    if body.is_completed and not executable(order):
        raise HTTPException(409, 'Start or resume the order before completing this operation.')
    if not body.is_completed and order.status not in {Status.IN_PROGRESS, Status.PENDING_REVIEW}:
        raise HTTPException(409, 'Reopen requires in-progress work or pending review.')
    if body.is_completed and await required_remaining(db, order, line):
        raise HTTPException(409, 'Complete the required checklist tasks before completing this operation.')
    now = datetime.now(UTC)
    before = snapshot(line)
    if body.is_completed:
        await stop_order_sessions(db, order, actor, labor_id=line.id, now=now, reason='auto_complete_work')
    elif order.status == Status.PENDING_REVIEW:
        order.status = Status.IN_PROGRESS
        clear_completion_snapshot(order)
    line.execution_status = 'completed' if body.is_completed else 'pending'
    line.execution_version = (line.execution_version or 0) + 1
    line.completed_at = now if body.is_completed else None
    line.completed_by_user_id = actor.id if body.is_completed else None
    line.completed_by_name = actor_name(actor) if body.is_completed else None
    record(db, order, line, 'operation_completed' if body.is_completed else 'operation_reopened', actor, before)
    await db.flush()
    return await page(db, order_id, actor)

async def timer(db, order_id, labor_id, actor, body, *, stop=False):
    from app.services import mechanic_time_service as times
    order = await load_order(db, order_id, actor, write=True)
    line = await load_labor(db, order, labor_id)
    require_internal(line)
    if actor.role != UserRole.MECHANIC or line.mechanic_id != actor.id:
        raise HTTPException(403, 'Only the assigned technician can control this timer.')
    version(line, body.expected_version)
    if stop:
        session = (await db.execute(select(MechanicTimeSession).where(MechanicTimeSession.id == body.session_id, MechanicTimeSession.tenant_id == order.tenant_id,
            MechanicTimeSession.repair_order_id == order.id, MechanicTimeSession.labor_id_snapshot == line.id, MechanicTimeSession.mechanic_id == actor.id,
            MechanicTimeSession.deleted_at.is_(None)).execution_options(populate_existing=True))).scalar_one_or_none()
        if not session:
            raise HTTPException(404, 'Operation timer not found')
        if session.ended_at is not None:
            raise HTTPException(409, 'This timer has already stopped. Refresh the operation.')
        await times.stop_active_session(db, tenant_id=order.tenant_id, mechanic_id=actor.id, actor_user=actor)
    else:
        tenant, mechanic = await times.fetch_tenant_and_mechanic(db, tenant_id=actor.tenant_id, mechanic_id=actor.id)
        await times.start_session(db, tenant=tenant, mechanic=mechanic, actor_user=actor, session_type='repair_order', repair_order_id=order.id, labor_id=line.id)
    await db.flush()
    return await page(db, order_id, actor)

async def validate_timer(db, tenant_id, mechanic_id, order_id, labor_id=None):
    order = (await db.execute(select(RepairOrder).where(RepairOrder.id == order_id, RepairOrder.tenant_id == tenant_id, RepairOrder.deleted_at.is_(None)).execution_options(populate_existing=True).with_for_update(of=RepairOrder))).scalar_one_or_none()
    if not order:
        raise HTTPException(404, 'Work order not found')
    if not executable(order):
        raise HTTPException(409, 'Timers require an in-progress order that is not held or finalized.')
    if labor_id is None:
        if order.assigned_mechanic_id != mechanic_id:
            raise HTTPException(403, 'Only the order lead can start a general order timer.')
        return None
    line = await load_labor(db, order, labor_id)
    require_internal(line)
    if line.mechanic_id != mechanic_id:
        raise HTTPException(403, 'The timer technician must be assigned to this operation.')
    if line.execution_status != 'pending':
        raise HTTPException(409, 'Assign or reopen the operation before starting its timer.')
    return line

async def stop_order_sessions(db, order, actor, *, labor_id=None, now=None, reason='auto_complete_work'):
    from app.services.mechanic_time_service import stop_active_session
    await lock_tenant_financials(db, order.tenant_id)
    stmt = select(MechanicTimeSession).where(MechanicTimeSession.tenant_id == order.tenant_id, MechanicTimeSession.repair_order_id == order.id,
        MechanicTimeSession.deleted_at.is_(None), MechanicTimeSession.ended_at.is_(None))
    if labor_id is not None:
        stmt = stmt.where(MechanicTimeSession.labor_id_snapshot == labor_id)
    sessions = (await db.execute(stmt.execution_options(populate_existing=True))).scalars().all()
    stamp = now or datetime.now(UTC)
    for session in sessions:
        await stop_active_session(db, tenant_id=order.tenant_id, mechanic_id=session.mechanic_id, actor_user=actor, stopped_at=stamp, stop_reason=reason)
    await db.flush()
    return sessions

async def guard_completion(db, order):
    remaining = await db.scalar(select(func.count(Labor.id)).where(Labor.tenant_id == order.tenant_id, Labor.repair_order_id == order.id,
        Labor.deleted_at.is_(None), Labor.line_type != LaborLineType.SUBLET, Labor.execution_status == 'pending'))
    if remaining:
        noun = 'operation' if remaining == 1 else 'operations'
        raise HTTPException(409, f'Complete the {remaining} remaining {noun} before finishing this work order.')
    if order.hold_reason:
        raise HTTPException(409, 'Resume the held order before finishing work.')

async def finish_order(db, order, actor):
    from app.services.mechanic_time_service import _merge_intervals, _sum_interval_seconds
    await guard_completion(db, order)
    now = datetime.now(UTC)
    if order.work_completed_at is None:
        order.work_completed_at = now
    await stop_order_sessions(db, order, actor, now=now)
    sessions = (await db.execute(select(MechanicTimeSession).where(MechanicTimeSession.tenant_id == order.tenant_id,
        MechanicTimeSession.repair_order_id == order.id, MechanicTimeSession.deleted_at.is_(None)))).scalars().all()
    intervals = [(utc(s.started_at), utc(s.ended_at) or now) for s in sessions]
    order.actual_tracked_minutes = sum(max(0, int((e-s).total_seconds())) for s,e in intervals) // 60
    if order.work_started_at:
        start = utc(order.work_started_at)
        work_end = utc(order.work_completed_at) or now
        clipped = [(max(s,start), min(e,work_end)) for s,e in intervals if min(e,work_end)>max(s,start)]
        order.total_hold_minutes = max(0, int((work_end-start).total_seconds()) - _sum_interval_seconds(_merge_intervals(clipped))) // 60
    from app.services.fleet_financial_wakeup import enqueue_order_financial_change
    await enqueue_order_financial_change(db, order)


async def guard_material_edit(db, order, line, changes):
    if 'mechanic_id' in changes and changes['mechanic_id'] != line.mechanic_id:
        raise HTTPException(409, 'Use the operation technician assignment control to change this assignment.')
    material = {'description','hours','line_type','source_service_id','service_code','provider','provider_operation_id'}
    if line.execution_status == 'completed' and any(key in changes and changes[key] != getattr(line,key) for key in material):
        raise HTTPException(409, 'Reopen this operation before changing its work scope.')
    if 'line_type' in changes and changes['line_type'] != line.line_type:
        if await active_for_line(db, order, line):
            raise HTTPException(409, 'Stop the operation timer before changing its work type.')
        if line.line_type == LaborLineType.SUBLET and changes['line_type'] != LaborLineType.SUBLET:
            line.execution_status = 'pending'
            line.execution_version = (line.execution_version or 0) + 1
            enroll_new_scope(order)


async def remove(db, order, line, actor=None):
    await lock_tenant_financials(db, order.tenant_id)
    if await active_for_line(db, order, line):
        raise HTTPException(409, 'Stop the operation timer before removing this work.')
    record(db, order, line, 'operation_scope_removed', actor, snapshot(line))
    # Explicitly detach as well as FK SET NULL for SQLite fixture compatibility.
    sessions = (await db.execute(select(MechanicTimeSession).where(MechanicTimeSession.tenant_id == order.tenant_id, MechanicTimeSession.labor_id == line.id))).scalars().all()
    for session in sessions:
        session.labor_id = None
    await db.flush()

async def page(db, order_id, actor):
    order = await load_order(db, order_id, actor)
    lead = order.assigned_mechanic_id == actor.id
    stmt = select(Labor, User).outerjoin(User, and_(User.id == Labor.mechanic_id, User.tenant_id == order.tenant_id)).where(Labor.tenant_id == order.tenant_id,
        Labor.repair_order_id == order.id, Labor.deleted_at.is_(None), Labor.line_type != LaborLineType.SUBLET)
    if actor.role == UserRole.MECHANIC and not lead:
        stmt = stmt.where(Labor.mechanic_id == actor.id)
    rows = (await db.execute(stmt.order_by(Labor.created_at,Labor.id))).all()
    ids = [line.id for line, _ in rows]
    now = datetime.now(UTC)
    session_filters = (MechanicTimeSession.tenant_id == order.tenant_id, MechanicTimeSession.repair_order_id == order.id,
        MechanicTimeSession.labor_id_snapshot.in_(ids), MechanicTimeSession.deleted_at.is_(None))
    if db.get_bind().dialect.name == 'postgresql':
        seconds = func.extract('epoch', func.coalesce(MechanicTimeSession.ended_at, now) - MechanicTimeSession.started_at)
    else:
        seconds = (func.julianday(func.coalesce(MechanicTimeSession.ended_at, now)) - func.julianday(MechanicTimeSession.started_at)) * 86400
    totals = dict((await db.execute(select(MechanicTimeSession.labor_id_snapshot, func.sum(seconds)).where(*session_filters).group_by(MechanicTimeSession.labor_id_snapshot))).all()) if ids else {}
    sessions = (await db.execute(select(MechanicTimeSession).where(*session_filters, MechanicTimeSession.ended_at.is_(None)))).scalars().all() if ids else []
    active_by_line = {session.labor_id_snapshot: session for session in sessions}
    counts = dict((await db.execute(select(Task.labor_id, func.count(Task.id)).where(Task.tenant_id == order.tenant_id, Task.repair_order_id == order.id, Task.labor_id.in_(ids), Task.required.is_(True), Task.is_completed.is_(False), Task.removed_at.is_(None), Task.deleted_at.is_(None)).group_by(Task.labor_id))).all()) if ids else {}
    now = datetime.now(UTC)
    items = []
    for line, technician in rows:
        active = active_by_line.get(line.id)
        mine = line.mechanic_id == actor.id and actor.role == UserRole.MECHANIC
        execute = actor.role in STAFF or mine
        remaining = counts.get(line.id, 0)
        items.append(dict(labor_id=line.id, description=line.description, mechanic_id=line.mechanic_id, mechanic_name=actor_name(technician) if technician else None,
            status=line.execution_status, version=line.execution_version or 0, completed_at=utc(line.completed_at),
            completed_by=dict(id=line.completed_by_user_id,name=line.completed_by_name) if line.execution_status == 'completed' else None,
            tracked_seconds=max(0,int(totals.get(line.id) or 0)) if line.execution_status else None,
            active_session=dict(id=active.id,mechanic_id=active.mechanic_id,mechanic_name=actor_name(technician),started_at=utc(active.started_at)) if active else None,
            required_tasks_remaining=remaining, can_assign=actor.role in STAFF and editable(order) and order.status != Status.PENDING_REVIEW and line.execution_status != 'completed' and not active,
            can_complete=execute and executable(order) and line.execution_status != 'completed' and not remaining,
            can_reopen=execute and editable(order) and order.status in {Status.IN_PROGRESS,Status.PENDING_REVIEW} and line.execution_status == 'completed',
            can_start_timer=mine and executable(order) and line.execution_status == 'pending' and not active,
            can_stop_timer=mine and active is not None and active.mechanic_id == actor.id))
    return dict(items=items, summary=dict(tracked=sum(i['status'] is not None for i in items), completed=sum(i['status']=='completed' for i in items),
        remaining=sum(i['status']=='pending' for i in items),legacy_untracked=sum(i['status'] is None for i in items)),order_status=order.status.value,is_order_lead=lead)
