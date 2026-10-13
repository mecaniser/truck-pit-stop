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
