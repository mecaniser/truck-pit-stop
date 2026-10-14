"""Real two-connection DB115 races; reuse the opt-in isolated DB110 database."""
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select, func

from app.api.v1.endpoints import repair_orders as routes
from app.db.models.mechanic_time import MechanicTimeSession
from app.db.models.repair_order import RepairOrder, RepairOrderStatus
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.schemas.operation_execution import OperationVersion
from app.schemas.staff_work_hold import StaffReleaseHoldRequest
from app.services import operation_execution as ops, staff_work_hold as holds
from test_operation_execution_postgres import pg_case, conflict  # noqa: F401
from test_staff_work_hold import hold_body

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def load_seed_version(pg_case):
    factory, a = pg_case
    async with factory() as db:
        a.order = await db.get(RepairOrder, a.order.id)


async def no_held_timer(db, order_id):
    assert await db.scalar(select(func.count(MechanicTimeSession.id)).where(
        MechanicTimeSession.repair_order_id == order_id,
        MechanicTimeSession.ended_at.is_(None), MechanicTimeSession.deleted_at.is_(None),
    )) == 0


async def test_hold_wins_timer_start(pg_case):
    factory, a = pg_case
    async with factory() as one, factory() as two:
        order, _ = await holds.transition(one, a.order.id, a.owner, hold_body(a.order))
        await conflict(ops.timer(two, a.order.id, a.lines[1].id, a.helper,
                                OperationVersion(expected_version=0)), "another workflow")
        await two.rollback()
        await one.commit()
        await conflict(ops.timer(two, a.order.id, a.lines[1].id, a.helper,
                                OperationVersion(expected_version=0)), "held")
        assert order.hold_reason is not None
        await no_held_timer(two, order.id)


async def test_timer_start_wins_hold_retry_stops_committed_timer(pg_case):
    factory, a = pg_case
    async with factory() as one, factory() as two:
        await ops.timer(one, a.order.id, a.lines[1].id, a.helper, OperationVersion(expected_version=0))
        await conflict(holds.transition(two, a.order.id, a.owner, hold_body(a.order)), "another workflow")
        await two.rollback()
        await one.commit()
        fresh = await ops.load_order(two, a.order.id, a.owner)
        order, stopped = await holds.transition(two, a.order.id, a.owner, hold_body(fresh))
        await two.commit()
        assert len(stopped) == 1 and stopped[0].mechanic_id == a.helper.id
        assert stopped[0].stopped_by_user_id == a.owner.id
        await no_held_timer(two, order.id)


async def test_competing_holds_and_release_stale_losers(pg_case):
    factory, a = pg_case
    async with factory() as one, factory() as two:
        initial = hold_body(a.order)
        held, _ = await holds.transition(one, a.order.id, a.owner, initial)
        await conflict(holds.transition(two, a.order.id, a.owner, initial), "another workflow")
        await two.rollback()
        await one.commit()
        await conflict(holds.transition(two, a.order.id, a.owner, initial), "changed")
        await two.rollback()
        release = StaffReleaseHoldRequest(expected_updated_at=held.updated_at)
        await holds.transition(one, a.order.id, a.owner, release, release=True)
        await conflict(holds.transition(two, a.order.id, a.owner, release, release=True), "another workflow")
        await two.rollback()
        await one.commit()
        await conflict(holds.transition(two, a.order.id, a.owner, release, release=True), "changed")
        assert await two.scalar(select(func.count(RepairOrderHistoryEvent.id)).where(
            RepairOrderHistoryEvent.repair_order_id == a.order.id)) == 2
        await no_held_timer(two, a.order.id)


async def test_release_wins_mechanic_resume(pg_case, monkeypatch):
    factory, a = pg_case
    async with factory() as one, factory() as two:
        held, _ = await holds.transition(one, a.order.id, a.owner, hold_body(a.order))
        await one.commit()
        release = StaffReleaseHoldRequest(expected_updated_at=held.updated_at)
        await holds.transition(one, a.order.id, a.owner, release, release=True)
        # The legacy mechanic route retains the app-level domain-error handler.
        from app.services.invoice_settlement_service import SettlementDomainError
        with pytest.raises(SettlementDomainError) as busy:
            await routes.resume_repair_order(a.order.id, two, a.lead)
        assert busy.value.status_code == 409 and busy.value.code == "invoice_busy"
        await two.rollback()
        await one.commit()
        with pytest.raises(HTTPException) as exc:
            await routes.resume_repair_order(a.order.id, two, a.lead)
        assert exc.value.status_code == 400 and "not on hold" in exc.value.detail
        await no_held_timer(two, a.order.id)


async def test_mechanic_resume_wins_stale_staff_release(pg_case, monkeypatch):
    for name in ["broadcast_repair_order_update", "broadcast_mechanic_timer_update", "broadcast_mechanic_attendance_update"]:
        monkeypatch.setattr(routes, name, AsyncMock())
    factory, a = pg_case
    async with factory() as one, factory() as two:
        held, _ = await holds.transition(one, a.order.id, a.owner, hold_body(a.order))
        await one.commit()
        release = StaffReleaseHoldRequest(expected_updated_at=held.updated_at)
        # Hold the same lock mechanic resume uses before entering the handler.
        await ops.lock_tenant_financials(one, a.tenant.id)
        await conflict(holds.transition(two, a.order.id, a.owner, release, release=True), "another workflow")
        await two.rollback()
        resumed = await routes.resume_repair_order(a.order.id, one, a.lead)
        assert resumed.hold_reason is None
        await conflict(holds.transition(two, a.order.id, a.owner, release, release=True), "changed")
        sessions = (await two.scalars(select(MechanicTimeSession).where(
            MechanicTimeSession.repair_order_id == a.order.id, MechanicTimeSession.ended_at.is_(None)))).all()
        assert len(sessions) == 1 and sessions[0].mechanic_id == a.lead.id


@pytest.mark.parametrize("finalization", ["completed", "pricing_lock"])
async def test_finalization_wins_hold(pg_case, finalization):
    from datetime import UTC, datetime
    factory, a = pg_case
    async with factory() as one, factory() as two:
        order = await ops.load_order(one, a.order.id, a.owner, write=True)
        if finalization == "completed":
            order.status = RepairOrderStatus.COMPLETED
        else:
            order.pricing_locked_at = datetime.now(UTC)
            order.pricing_lock_reason = "invoice_created"
        await one.flush()
        await conflict(holds.transition(two, a.order.id, a.owner, hold_body(a.order)), "another workflow")
        await two.rollback()
        await one.commit()
        await conflict(holds.transition(two, a.order.id, a.owner, hold_body(a.order)), "editable")
        assert await two.scalar(select(func.count(RepairOrderHistoryEvent.id)).where(
            RepairOrderHistoryEvent.repair_order_id == a.order.id)) == 0
