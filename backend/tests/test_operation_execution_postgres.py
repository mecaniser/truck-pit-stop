"""DB110 real transaction races. Only opt-in isolated local db110_test databases."""
import os
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi import HTTPException
from app.db.base import Base
from app.db.models.tenant import Tenant
from app.db.models.mechanic_time import MechanicTimeSession
from app.db.models.labor import Labor
from app.schemas.operation_execution import OperationAssignment as Assign, OperationCompletion as Complete, OperationVersion as Version
from app.schemas.service_checklist import ChecklistTaskUpdate
from app.services import operation_execution as ops, service_checklist as checks
from test_operation_execution import seed

pytestmark=pytest.mark.asyncio

@pytest_asyncio.fixture
async def pg_case():
    url=os.environ.get('DB110_POSTGRES_TEST_URL')
    if not url:
        pytest.skip('DB110 isolated PostgreSQL not configured')
    parsed=make_url(url)
    if parsed.host not in {'127.0.0.1','localhost'} or not parsed.database.startswith('db110_test'):
        raise RuntimeError('Only isolated local DB110 test database is permitted')
    engine=create_async_engine(url)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as db:
        a=await seed(db)
    try:
        yield factory,a
    finally:
        async with factory() as db:
            for table in reversed(Base.metadata.sorted_tables):
                if 'tenant_id' in table.c:
                    await db.execute(delete(table).where(table.c.tenant_id==a.tenant.id))
            await db.execute(delete(Tenant).where(Tenant.id==a.tenant.id));await db.commit()
        await engine.dispose()

async def conflict(call, detail=None):
    with pytest.raises(HTTPException) as exc:
        await call
    assert exc.value.status_code==409
    if detail:assert detail in exc.value.detail

async def test_start_wins_assignment_race(pg_case):
    factory,a=pg_case
    async with factory() as one,factory() as two:
        await ops.timer(one,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
        await conflict(ops.assign(two,a.order.id,a.lines[1].id,a.owner,Assign(mechanic_id=a.lead.id,expected_version=0)),'another workflow')
        await two.rollback();await one.commit()
        await conflict(ops.assign(two,a.order.id,a.lines[1].id,a.owner,Assign(mechanic_id=a.lead.id,expected_version=0)),'Stop the operation timer')

async def test_assignment_wins_start_race(pg_case):
    factory,a=pg_case
    async with factory() as one,factory() as two:
        await ops.assign(one,a.order.id,a.lines[1].id,a.owner,Assign(mechanic_id=a.lead.id,expected_version=0))
        await conflict(ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0)),'another workflow')
        await two.rollback();await one.commit()
        with pytest.raises(HTTPException) as exc:
            await ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
        assert exc.value.status_code==403

async def test_complete_wins_start_race(pg_case):
    factory,a=pg_case
    async with factory() as one,factory() as two:
        await ops.complete(one,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=True,expected_version=0))
        await conflict(ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0)),'another workflow')
        await two.rollback();await one.commit()
        await conflict(ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=1)),'Assign or reopen')

@pytest.mark.parametrize('action',['hold','finish','remove'])
async def test_order_scope_wins_start_race(pg_case,action):
    factory,a=pg_case
    async with factory() as one,factory() as two:
        order=await ops.load_order(one,a.order.id,a.owner,write=True)
        if action=='hold':
            order.hold_reason='Parts';await ops.stop_order_sessions(one,order,a.lead,reason='hold')
        elif action=='finish':
            for line in (await one.scalars(select(Labor).where(Labor.repair_order_id==order.id))).all():
                if line.execution_status:line.execution_status='completed'
            await one.flush();await ops.finish_order(one,order,a.owner)
            from app.db.models.repair_order import RepairOrderStatus
            order.status=RepairOrderStatus.PENDING_REVIEW
        else:
            line=await ops.load_labor(one,order,a.lines[1].id)
            await checks.archive_labor(one,order,line,a.owner);await one.delete(line)
        await one.flush()
        await conflict(ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0)),'another workflow')
        await two.rollback();await one.commit()
        with pytest.raises(HTTPException) as exc:
            await ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
        assert exc.value.status_code in {403,404,409}

async def test_same_mechanic_double_start_replays_after_contention(pg_case):
    factory,a=pg_case
    async with factory() as one,factory() as two:
        first=await ops.timer(one,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
        await conflict(ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0)),'another workflow')
        await two.rollback();await one.commit()
        replay=await ops.timer(two,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0))
        assert first['items'][0]['active_session']['id']==replay['items'][0]['active_session']['id']
        sessions=(await two.scalars(select(MechanicTimeSession).where(MechanicTimeSession.tenant_id==a.tenant.id))).all()
        assert len(sessions)==1

async def test_checklist_reopen_wins_operation_completion_race(pg_case):
    factory,a=pg_case
    async with factory() as one,factory() as two:
        order=await ops.load_order(one,a.order.id,a.owner,write=True)
        line=await ops.load_labor(one,order,a.lines[1].id)
        await checks.snapshot_service(one,order,line,a.service,a.owner)
        page=await checks.read_checklist(one,order.id,a.helper)
        for task in page.items:
            if task.required:await checks.update_task(one,order.id,task.id,a.helper,ChecklistTaskUpdate(is_completed=True,expected_version=1))
        await one.commit()
        await checks.update_task(one,order.id,page.items[0].id,a.helper,ChecklistTaskUpdate(is_completed=False,expected_version=2))
        await conflict(ops.complete(two,order.id,line.id,a.helper,Complete(is_completed=True,expected_version=0)),'another workflow')
        await two.rollback();await one.commit()
        await conflict(ops.complete(two,order.id,line.id,a.helper,Complete(is_completed=True,expected_version=0)),'required checklist')

async def test_stale_manager_edit_cannot_overwrite_operation_stop(pg_case):
    from datetime import UTC, datetime, timedelta
    from app.services import mechanic_time_service as times
    factory,a=pg_case
    async with factory() as one,factory() as two:
        await ops.timer(one,a.order.id,a.lines[1].id,a.helper,Version(expected_version=0));await one.commit()
        stale=(await two.scalars(select(MechanicTimeSession).where(MechanicTimeSession.tenant_id==a.tenant.id))).one()
        assert stale.ended_at is None
        await ops.complete(one,a.order.id,a.lines[1].id,a.helper,Complete(is_completed=True,expected_version=0));await one.commit()
        await conflict(times.edit_session(two,session=stale,actor_user=a.owner,ended_at=datetime.now(UTC)+timedelta(minutes=5),manager_reason='Correction'),'changed while')
        await two.rollback()
        fresh=(await two.scalars(select(MechanicTimeSession).where(MechanicTimeSession.tenant_id==a.tenant.id))).one()
        stopped=fresh.ended_at
        # A refreshed deliberate correction remains supported with a reason.
        await times.edit_session(two,session=fresh,actor_user=a.owner,ended_at=stopped+timedelta(seconds=1),manager_reason='Reviewed correction')
        assert fresh.ended_at==stopped+timedelta(seconds=1)
