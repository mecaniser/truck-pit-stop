"""DB110 execution identity, authorization and lifecycle acceptance."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.db.models.labor import Labor, LaborLineType
from app.db.models.user import User, UserRole
from app.db.models.mechanic_time import MechanicTimeSession
from app.db.models.repair_order import RepairOrderStatus as Status
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.db.models.service_checklist import RepairOrderChecklistItem as Task
from app.schemas.operation_execution import OperationAssignment as Assign, OperationCompletion as Complete, OperationVersion as Version, OperationTimerStop as Stop
from app.schemas.service_checklist import ChecklistTaskUpdate
from app.services import operation_execution as ops, service_checklist as checks, mechanic_time_service as times
from app.api.v1.endpoints import repair_orders, mechanics
from test_service_checklists import seed as base_seed

pytestmark = pytest.mark.asyncio

async def seed(db):
    a = await base_seed(db)
    users = [User(id=uuid4(), tenant_id=a.tenant.id, email=f'{uuid4()}@example.invalid', hashed_password='unused', first_name=name, last_name='Technician', role=UserRole.MECHANIC, is_active=True) for name in ['Lead','Helper']]
    db.add_all(users)
    await db.flush()
    a.lead, a.helper = users
    a.order.assigned_mechanic_id = a.lead.id
    a.order.work_started_at = datetime.now(UTC) - timedelta(hours=2)
    a.lines = [Labor(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=a.order.id, description=f'Operation {i}', hours=Decimal(i+1), hourly_rate=100, total_cost=100*(i+1), mechanic_id=users[i].id, execution_status='pending', execution_version=0) for i in range(2)]
    a.legacy = Labor(id=uuid4(), tenant_id=a.tenant.id, repair_order_id=a.order.id, description='Legacy work', hours=3, hourly_rate=100, total_cost=300)
    db.add_all(a.lines+[a.legacy])
    await db.commit()
    return a

async def assert_error(code, awaitable, match=None):
    with pytest.raises(HTTPException) as exc:
        await awaitable
    assert exc.value.status_code == code
    if match:
        assert match in exc.value.detail

async def test_projection_assignment_versions_and_legacy(db_session):
    a=await seed(db_session)
    page=await ops.page(db_session,a.order.id,a.owner)
    assert page['summary']==dict(tracked=2,completed=0,remaining=2,legacy_untracked=1)
    assert next(x for x in page['items'] if x['labor_id']==a.legacy.id)['tracked_seconds'] is None
    assert (await ops.page(db_session,a.order.id,a.helper))['summary']['tracked']==1
    await ops.assign(db_session,a.order.id,a.legacy.id,a.owner,Assign(mechanic_id=a.helper.id,expected_version=0))
    assert a.legacy.execution_version==1 and a.legacy.execution_status=='pending'
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id)))==0
    await ops.assign(db_session,a.order.id,a.legacy.id,a.owner,Assign(mechanic_id=a.helper.id,expected_version=1))
    assert a.legacy.execution_version==1
    await assert_error(409,ops.assign(db_session,a.order.id,a.legacy.id,a.owner,Assign(mechanic_id=None,expected_version=0)))
    await assert_error(403,ops.assign(db_session,a.order.id,a.lines[1].id,a.helper,Assign(mechanic_id=None,expected_version=0)))
    await assert_error(404,ops.assign(db_session,a.order.id,a.lines[1].id,a.owner,Assign(mechanic_id=a.owner.id,expected_version=0)))
    a.helper.is_active=False;await db_session.flush()
    await assert_error(404,ops.assign(db_session,a.order.id,a.lines[0].id,a.owner,Assign(mechanic_id=a.helper.id,expected_version=0)))

async def test_timer_replay_switch_delayed_stop_and_completion(db_session):
    a=await seed(db_session)
    await ops.timer(db_session,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
    first=await times.get_active_session(db_session,tenant_id=a.tenant.id,mechanic_id=a.helper.id)
    await ops.timer(db_session,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
    assert (await times.get_active_session(db_session,tenant_id=a.tenant.id,mechanic_id=a.helper.id)).id==first.id
    await assert_error(409,ops.assign(db_session,a.order.id,a.lines[1].id,a.owner,Assign(mechanic_id=a.lead.id,expected_version=0)))
    await ops.assign(db_session,a.order.id,a.legacy.id,a.owner,Assign(mechanic_id=a.helper.id,expected_version=0))
    await ops.timer(db_session,a.order.id,a.legacy.id,a.helper,Version(expected_version=1))
    second=await times.get_active_session(db_session,tenant_id=a.tenant.id,mechanic_id=a.helper.id)
    assert second.id!=first.id and ops.utc(first.ended_at)==ops.utc(second.started_at)
    assert a.order.hold_reason is None
    await assert_error(409,ops.timer(db_session,a.order.id,a.lines[1].id,a.helper,Stop(expected_version=0,session_id=first.id),stop=True))
    # Completing a different operation must leave the helper's new timer running.
    await ops.complete(db_session,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=True,expected_version=0))
    assert (await times.get_active_session(db_session,tenant_id=a.tenant.id,mechanic_id=a.helper.id)).id==second.id
    await ops.complete(db_session,a.order.id,a.legacy.id,a.helper,Complete(is_completed=True,expected_version=1))
    assert await times.get_active_session(db_session,tenant_id=a.tenant.id,mechanic_id=a.helper.id) is None
    assert a.order.status==Status.IN_PROGRESS

async def test_helper_scope_checklist_and_completion_reopen(db_session):
    a=await seed(db_session)
    await checks.snapshot_service(db_session,a.order,a.lines[1],a.service,a.owner)
    await checks.snapshot_service(db_session,a.order,a.lines[0],a.service,a.owner)
    page=await checks.read_checklist(db_session,a.order.id,a.helper)
    assert page.total==3 and all(x.labor_id==a.lines[1].id and x.can_update for x in page.items)
    lead_page=await checks.read_checklist(db_session,a.order.id,a.lead)
    assert all(not x.can_update for x in lead_page.items if x.labor_id==a.lines[1].id)
    await assert_error(403,ops.complete(db_session,a.order.id,a.lines[1].id,a.lead,Complete(is_completed=True,expected_version=0)))
    await assert_error(409,ops.complete(db_session,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=True,expected_version=0)))
    for item in page.items:
        if item.required:
            await checks.update_task(db_session,a.order.id,item.id,a.helper,ChecklistTaskUpdate(is_completed=True,expected_version=1))
    await ops.complete(db_session,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=True,expected_version=0))
    await assert_error(409,checks.update_task(db_session,a.order.id,page.items[0].id,a.helper,ChecklistTaskUpdate(is_completed=False,expected_version=2)))
    a.order.status=Status.PENDING_REVIEW;a.order.work_completed_at=datetime.now(UTC);await db_session.flush()
    await ops.complete(db_session,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=False,expected_version=1))
    assert a.order.status==Status.IN_PROGRESS and a.order.work_completed_at is None
    assert a.lines[1].completed_by_name is None
    await checks.update_task(db_session,a.order.id,page.items[0].id,a.helper,ChecklistTaskUpdate(is_completed=False,expected_version=2))

async def test_parallel_person_time_union_and_book_scope(db_session):
    a=await seed(db_session)
    now=datetime.now(UTC)
    a.legacy.mechanic_id = a.helper.id  # Historical adding mechanic is not tracked assignment.
    for mechanic,line in zip([a.lead,a.helper],a.lines):
        db_session.add(MechanicTimeSession(tenant_id=a.tenant.id, mechanic_id=mechanic.id, repair_order_id=a.order.id, labor_id=line.id, labor_id_snapshot=line.id, labor_description_snapshot=line.description, session_type='repair_order', started_at=now-timedelta(hours=1), ended_at=now, started_by_user_id=mechanic.id))
        line.execution_status='completed'
    await db_session.flush()
    await ops.finish_order(db_session,a.order,a.owner)
    assert a.order.actual_tracked_minutes==120
    assert 59 <= a.order.total_hold_minutes <= 61
    assert await times._compute_book_hours_for_orders(db_session,order_ids=[a.order.id],tenant_id=a.tenant.id,mechanic_id=a.lead.id)==4
    assert await times._compute_book_hours_for_orders(db_session,order_ids=[a.order.id],tenant_id=a.tenant.id,mechanic_id=a.helper.id)==2

async def test_remove_preserves_timer_identity_and_scope_guard(db_session):
    a=await seed(db_session)
    await ops.timer(db_session,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
    await assert_error(409,ops.remove(db_session,a.order,a.lines[1],a.owner))
    await ops.complete(db_session,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=True,expected_version=0))
    await assert_error(409,ops.guard_material_edit(db_session,a.order,a.lines[1],{'hours':4}))
    await ops.guard_material_edit(db_session,a.order,a.lines[1],{'hourly_rate':120})
    removed=a.lines[1].id
    await checks.archive_labor(db_session,a.order,a.lines[1],a.owner)
    await db_session.delete(a.lines[1]);await db_session.flush()
    session=await db_session.scalar(select(MechanicTimeSession).where(MechanicTimeSession.labor_id_snapshot==removed))
    assert session.labor_id is None and session.labor_description_snapshot=='Operation 1'
    await assert_error(404,ops.complete(db_session,a.order.id,removed,a.owner,Complete(is_completed=True,expected_version=1)))

@pytest.mark.parametrize('status',[Status.DRAFT,Status.ASSIGNED,Status.PENDING_REVIEW,Status.COMPLETED,Status.CANCELLED])
async def test_timer_stage_guard(db_session,status):
    a=await seed(db_session);a.order.status=status;await db_session.commit()
    await assert_error(409,ops.timer(db_session,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0)))
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id)))==0

async def test_hold_closes_all_timers_and_finalize_guard(db_session,monkeypatch):
    a=await seed(db_session)
    for who,line in zip([a.lead,a.helper],a.lines):
        await ops.timer(db_session,a.order.id,line.id,who,Version(expected_version=0))
    await assert_error(409,checks.guard_completion(db_session,a.order))
    await ops.stop_order_sessions(db_session,a.order,a.lead,reason='hold')
    a.order.hold_reason='Waiting for parts';await db_session.flush()
    assert await db_session.scalar(select(func.count(MechanicTimeSession.id)).where(MechanicTimeSession.ended_at.is_(None)))==0
    await assert_error(409,ops.timer(db_session,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0)))
    await assert_error(409,ops.complete(db_session,a.order.id,a.lines[1].id,a.owner,Complete(is_completed=True,expected_version=0)))

async def test_tenant_and_foreign_child_boundaries(db_session):
    a=await seed(db_session);b=await seed(db_session)
    await assert_error(404,ops.page(db_session,b.order.id,a.owner))
    await assert_error(404,ops.assign(db_session,a.order.id,b.lines[0].id,a.owner,Assign(mechanic_id=a.lead.id,expected_version=0)))
    await assert_error(404,ops.assign(db_session,a.order.id,a.lines[0].id,a.owner,Assign(mechanic_id=b.lead.id,expected_version=0)))
    await assert_error(403,ops.page(db_session,a.order.id,SimpleNamespace(role=UserRole.CUSTOMER,tenant_id=a.tenant.id)))
from app.schemas.repair_order import LaborCreate, LaborUpdate
from app.db.models.labor import Labor, LaborLineType
from app.db.models.repair_order import RepairOrderStatus as Status
from app.services import operation_execution as ops
from app.api.v1.endpoints import repair_orders
from app.services.price_build_service import PriceBuildService
from sqlalchemy import select
import pytest

@pytest.mark.asyncio
async def test_new_sublet_converted_to_manual_remains_completion_gated(db_session):
    a = await seed(db_session)
    created = await repair_orders.add_labor_to_repair_order(a.order.id, LaborCreate(description='External work', hours=1, hourly_rate=100, line_type=LaborLineType.SUBLET), db_session, a.owner)
    changed = await repair_orders.update_repair_order_labor(a.order.id, created.id, LaborUpdate(line_type=LaborLineType.MANUAL), db_session, a.owner)
    line = await db_session.scalar(select(Labor).where(Labor.id == created.id))
    assert line.execution_status == 'pending', f'new internal work is {line.execution_status=}'

@pytest.mark.asyncio
async def test_adding_service_to_review_reopens_operation_work(db_session):
    a = await seed(db_session)
    a.order.status=Status.PENDING_REVIEW
    for line in a.lines: line.execution_status='completed'
    await db_session.commit()
    await PriceBuildService().add_flat_service_line(db_session, a.order, a.service.id, actor=a.owner)
    assert a.order.status == Status.IN_PROGRESS, f'{a.order.status=}'

@pytest.mark.asyncio
async def test_helper_cannot_edit_whole_order_through_legacy_put(db_session, monkeypatch):
    from unittest.mock import AsyncMock
    from app.schemas.repair_order import RepairOrderUpdate
    from fastapi import HTTPException
    a = await seed(db_session)
    monkeypatch.setattr(repair_orders, 'broadcast_repair_order_update', AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await repair_orders.update_repair_order(a.order.id, RepairOrderUpdate(description='Helper changed the full order'), db_session, a.helper)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_helper_cannot_read_whole_order_detail(db_session):
    from fastapi import HTTPException
    a = await seed(db_session)
    with pytest.raises(HTTPException) as exc:
        await repair_orders.get_repair_order_detail(a.order.id, db_session, a.helper)
    assert exc.value.status_code == 403

async def test_review_approval_does_not_count_review_wait_as_hold(db_session):
    a=await seed(db_session)
    now=datetime.now(UTC)
    a.order.work_started_at=now-timedelta(hours=3)
    a.order.work_completed_at=now-timedelta(hours=1)
    a.order.status=Status.PENDING_REVIEW
    for line in a.lines:line.execution_status='completed'
    db_session.add(MechanicTimeSession(tenant_id=a.tenant.id, mechanic_id=a.helper.id, repair_order_id=a.order.id,
        labor_id=a.lines[1].id,labor_id_snapshot=a.lines[1].id,session_type='repair_order',
        started_at=now-timedelta(hours=2),ended_at=now-timedelta(hours=1),started_by_user_id=a.helper.id))
    await db_session.flush()
    await ops.finish_order(db_session,a.order,a.owner)
    assert a.order.actual_tracked_minutes==60
    assert a.order.total_hold_minutes==60

@pytest.mark.parametrize('transition',['start','resume'])
async def test_order_timer_failure_does_not_commit_stage_change(db_session,monkeypatch,transition):
    from unittest.mock import AsyncMock
    a=await seed(db_session)
    db_session.autoflush=False
    if transition=='start':a.order.status=Status.ASSIGNED
    else:a.order.hold_reason='Waiting for parts'
    await db_session.commit()
    monkeypatch.setattr(repair_orders,'start_session',AsyncMock(side_effect=RuntimeError('Synthetic timer failure')))
    action=repair_orders.start_work if transition=='start' else repair_orders.resume_repair_order
    with pytest.raises(RuntimeError,match='Synthetic timer failure'):
        await action(a.order.id,db_session,a.lead)
    await db_session.rollback()
    await db_session.refresh(a.order)
    assert (a.order.status==Status.ASSIGNED) if transition=='start' else a.order.hold_reason=='Waiting for parts'


@pytest.mark.parametrize('transition, initial_status', [
    ('start', Status.ASSIGNED),
    ('start', Status.ACKNOWLEDGED),
    ('resume', Status.IN_PROGRESS),
])
async def test_mechanic_order_transition_starts_timer_with_autoflush_disabled(db_session, monkeypatch, transition, initial_status):
    from unittest.mock import AsyncMock
    a = await seed(db_session)
    db_session.autoflush = False  # Production AsyncSessionLocal does not autoflush.
    a.order.status = initial_status
    if transition == 'resume':
        a.order.hold_reason = 'Waiting for parts'
    await db_session.commit()
    monkeypatch.setattr(repair_orders, 'broadcast_repair_order_update', AsyncMock())
    monkeypatch.setattr(repair_orders, 'broadcast_mechanic_timer_update', AsyncMock())
    monkeypatch.setattr(repair_orders, 'broadcast_mechanic_attendance_update', AsyncMock())
    monkeypatch.setattr(repair_orders, '_enqueue_order_customer_sms', AsyncMock())

    action = repair_orders.start_work if transition == 'start' else repair_orders.resume_repair_order
    await action(a.order.id, db_session, a.lead)

    await db_session.refresh(a.order)
    assert a.order.status == Status.IN_PROGRESS
    assert a.order.hold_reason is None
    session = await times.get_active_session(db_session, tenant_id=a.tenant.id, mechanic_id=a.lead.id)
    assert session is not None and session.repair_order_id == a.order.id
    assert session.ended_at is None

@pytest.mark.parametrize('route',['mechanic','admin','approve','fleet','pending_review','completed','invoiced','paid','invoice_helper','invoice_manual'])
async def test_pending_operations_guard_every_completion_entrypoint(db_session,monkeypatch,route):
    from unittest.mock import AsyncMock
    from app.api.v1.endpoints import fleet,invoices
    from app.schemas.repair_order import RepairOrderUpdate
    a=await seed(db_session)
    if route=='admin':a.order.assigned_mechanic_id=None
    if route=='approve':a.order.status=Status.PENDING_REVIEW
    if route=='invoice_manual':a.order.status=Status.COMPLETED
    await db_session.commit()
    side_effect=AsyncMock(side_effect=AssertionError('Completion side effect before operation gate'))
    monkeypatch.setattr(repair_orders,'broadcast_repair_order_update',side_effect)
    monkeypatch.setattr(repair_orders,'enqueue_automated_sms',side_effect)
    monkeypatch.setattr(fleet,'_load_fleet_ro_or_404',AsyncMock(return_value=a.order))
    if route=='mechanic':call=repair_orders.complete_work(a.order.id,db_session,a.lead)
    elif route=='admin':call=repair_orders.admin_complete_unassigned_work(a.order.id,db_session,a.owner)
    elif route=='approve':call=repair_orders.approve_completion(a.order.id,body=None,idempotency_key=None,db=db_session,current_user=a.owner)
    elif route=='fleet':call=fleet.complete_work_order(a.order.id,db=db_session,current_user=a.owner)
    elif route=='invoice_helper':call=invoices.auto_create_invoice_for_order(db_session,a.order,a.tenant,a.owner.id,commit=False,notify=False)
    elif route=='invoice_manual':call=invoices.create_invoice(invoices.InvoiceCreate(repair_order_id=a.order.id),db=db_session,current_user=a.owner)
    else:call=repair_orders.update_repair_order(a.order.id,RepairOrderUpdate(status=Status(route)),db_session,a.owner)
    await assert_error(409,call,'remaining operations')
    side_effect.assert_not_awaited()

@pytest.mark.parametrize('action',['delete','reopen','base','workspace','photos','notes'])
async def test_helper_generic_workspace_and_writes_stay_forbidden(db_session,action):
    a=await seed(db_session)
    routes={'delete':repair_orders.delete_repair_order,'reopen':repair_orders.reopen_repair_order,
        'base':repair_orders.get_repair_order,'workspace':repair_orders.get_repair_order_workspace,
        'photos':repair_orders.list_repair_order_photos,'notes':repair_orders.list_repair_order_notes}
    await assert_error(403,routes[action](a.order.id,db_session,a.helper))

async def test_helper_discovery_returns_only_reduced_assigned_scope(db_session):
    a=await seed(db_session)
    jobs=await mechanics.get_my_jobs(skip=0,limit=100,paginated=False,db=db_session,current_user=a.helper)
    assert len(jobs)==1 and jobs[0].is_order_lead is False and jobs[0].services_count==1
    detail=await mechanics.get_my_job_detail(a.order.id,db_session,a.helper)
    assert detail.is_order_lead is False
    assert [row.name for row in detail.services]==[a.lines[1].description]
    assert all(row.base_price is None for row in detail.services)
    assert not {'customer_email','customer_phone','total_cost','internal_notes'} & detail.model_dump().keys()


@pytest.mark.asyncio
async def test_generic_review_transition_records_effective_work_end(db_session, monkeypatch):
    from unittest.mock import AsyncMock
    from app.api.v1.endpoints import repair_orders
    from app.schemas.repair_order import RepairOrderUpdate
    a = await seed(db_session)
    for line in a.lines:
        line.execution_status = 'completed'
    await db_session.commit()
    monkeypatch.setattr(repair_orders, 'broadcast_repair_order_update', AsyncMock())
    await repair_orders.update_repair_order(a.order.id, RepairOrderUpdate(status=Status.PENDING_REVIEW), db_session, a.owner)
    assert a.order.work_completed_at is not None, 'Generic completion lost the effective work-end cutoff'

@pytest.mark.asyncio
async def test_generic_reopen_clears_effective_work_end(db_session, monkeypatch):
    from unittest.mock import AsyncMock
    from app.api.v1.endpoints import repair_orders
    from app.schemas.repair_order import RepairOrderUpdate
    a = await seed(db_session)
    a.order.status = Status.PENDING_REVIEW
    a.order.work_completed_at = datetime.now(UTC) - timedelta(hours=1)
    a.order.actual_tracked_minutes = 60
    a.order.total_hold_minutes = 0
    for line in a.lines:
        line.execution_status = 'completed'
    await db_session.commit()
    monkeypatch.setattr(repair_orders, 'broadcast_repair_order_update', AsyncMock())
    await repair_orders.update_repair_order(a.order.id, RepairOrderUpdate(status=Status.IN_PROGRESS), db_session, a.owner)
    assert a.order.work_completed_at is None, 'Reopened work retained a stale completion cutoff'
    assert a.order.actual_tracked_minutes is None and a.order.total_hold_minutes is None

async def test_operation_publish_invalidates_without_status_notification(db_session,monkeypatch):
    from unittest.mock import AsyncMock
    from app.core import websocket
    a=await seed(db_session)
    sent=AsyncMock();customer=AsyncMock()
    monkeypatch.setattr(websocket.manager,'broadcast_to_tenant',sent)
    monkeypatch.setattr(websocket.manager,'send_to_customer',customer)
    monkeypatch.setattr(repair_orders,'broadcast_mechanic_timer_update',AsyncMock())
    await repair_orders.assign_order_operation(a.order.id,a.lines[0].id,Assign(mechanic_id=a.helper.id,expected_version=0),db_session,a.owner)
    payload=sent.await_args.args[1]
    assert payload['type']=='repair_order_update' and payload['notify_status_change'] is False
    customer.assert_not_awaited()

async def test_operation_reopen_review_loop_credits_order_only_once(db_session,monkeypatch):
    from unittest.mock import AsyncMock
    from app.db.models.mechanic_points import MechanicPoints,MechanicPointsBalance
    a=await seed(db_session)
    for name in ['send_email','enqueue_automated_sms','broadcast_repair_order_update','broadcast_mechanic_timer_update']:
        monkeypatch.setattr(repair_orders,name,AsyncMock())
    for line in a.lines:
        await ops.complete(db_session,a.order.id,line.id,a.owner,Complete(is_completed=True,expected_version=0))
    await repair_orders.complete_work(a.order.id,db_session,a.lead)
    points=(await db_session.scalars(select(MechanicPoints).where(MechanicPoints.repair_order_id==a.order.id))).all()
    assert len(points)==1
    initial_credit=points[0].points
    balance=await db_session.scalar(select(MechanicPointsBalance).where(MechanicPointsBalance.mechanic_id==a.lead.id))
    initial_streak=balance.current_streak_days
    await ops.complete(db_session,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=False,expected_version=1))
    await ops.complete(db_session,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=True,expected_version=2))
    await repair_orders.complete_work(a.order.id,db_session,a.lead)
    await db_session.refresh(balance)
    assert await db_session.scalar(select(func.count(MechanicPoints.id)).where(MechanicPoints.repair_order_id==a.order.id))==1
    assert balance.total_earned==initial_credit and balance.available_points==initial_credit
    assert balance.current_streak_days==initial_streak
