"""DB131 real PostgreSQL locking, constraints, search and source projection proof.

Opt in only with DB131_POSTGRES_TEST_URL pointing at a disposable localhost
`db131_test*` database. Never uses or mutates the app's configured database.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
from uuid import uuid4

from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api.v1.endpoints import repair_orders as routes
from app.db.base import Base
from app.db.models.tenant import Tenant
from app.db.models.repair_order import RepairOrder, RepairOrderStatus as Status
from app.db.models.repair_order_read_model import RepairOrderReadModel
from app.db.models.repair_order_history import RepairOrderHistoryEvent
from app.services import repair_order_schedule as schedules, operation_execution as ops
from test_repair_order_schedule import seed, body, fails, NOW

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pg_case():
    raw = os.environ.get("DB131_POSTGRES_TEST_URL")
    if not raw:
        pytest.skip("DB131 isolated PostgreSQL not configured")
    url = make_url(raw)
    if url.host not in {"127.0.0.1", "localhost"} or not (url.database or "").startswith("db131_test"):
        raise RuntimeError("Only a disposable local db131_test database is permitted")
    engine = create_async_engine(raw)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        a = await seed(db)
    try:
        yield factory, a
    finally:
        async with factory() as db:
            for table in reversed(Base.metadata.sorted_tables):
                if "tenant_id" in table.c:
                    await db.execute(delete(table).where(table.c.tenant_id == a.tenant.id))
            await db.execute(delete(Tenant).where(Tenant.id == a.tenant.id))
            await db.commit()
        await engine.dispose()


async def test_two_editors_lock_then_stale_loser_has_one_event(pg_case):
    factory, a = pg_case
    initial = body(a.order)
    async with factory() as one, factory() as two:
        _, saved, _ = await schedules.update(one, a.order.id, a.owner, initial)
        await fails(409, None, schedules.update(two, a.order.id, a.owner, initial))
        await two.rollback()
        await one.commit()
        await fails(409, "schedule_changed", schedules.update(two, a.order.id, a.owner, initial))
        await two.rollback()
        assert await two.scalar(select(func.count(RepairOrderHistoryEvent.id)).where(
            RepairOrderHistoryEvent.repair_order_id == a.order.id)) == 1
        fresh = await schedules.read(two, a.order.id, a.owner)
        assert fresh.updated_at == saved.updated_at and fresh.promised_finish_at == saved.promised_finish_at


@pytest.mark.parametrize("transition", ["completed", "released", "deleted"])
async def test_finalization_wins_schedule_without_partial_write(pg_case, transition):
    factory, a = pg_case
    initial = body(a.order)
    async with factory() as one, factory() as two:
        order = await ops.load_order(one, a.order.id, a.owner, write=True)
        if transition == "completed":
            order.status = Status.COMPLETED
        elif transition == "released":
            order.vehicle_released_at = NOW
        else:
            order.deleted_at = NOW
        await one.flush()
        await fails(409, None, schedules.update(two, a.order.id, a.owner, initial))
        await two.rollback()
        await one.commit()
        await fails(404 if transition == "deleted" else 409,
                    None if transition == "deleted" else "schedule_locked",
                    schedules.update(two, a.order.id, a.owner, initial))
        await two.rollback()
        row = await two.get(RepairOrder, a.order.id)
        assert row.scheduled_start_at is None and row.promised_finish_at is None
        assert await two.scalar(select(func.count(RepairOrderHistoryEvent.id)).where(
            RepairOrderHistoryEvent.repair_order_id == a.order.id)) == 0


async def test_database_rejects_equal_or_reversed_instants(pg_case):
    factory, a = pg_case
    async with factory() as db:
        for finish in [NOW, NOW - timedelta(seconds=1)]:
            order = await db.get(RepairOrder, a.order.id)
            order.scheduled_start_at = NOW
            order.promised_finish_at = finish
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
        row = await db.get(RepairOrder, a.order.id)
        assert row.scheduled_start_at is None and row.promised_finish_at is None


@pytest.mark.parametrize("fallback", [False, True])
async def test_postgres_search_count_value_all_pages_source_and_projection(pg_case, monkeypatch, fallback):
    factory, a = pg_case
    monkeypatch.setattr(schedules, "now_utc", lambda: NOW)
    async with factory() as db:
        # Real trigger-backed projection; no manually fabricated payload rows.
        rows = []
        for index in range(31):
            row = RepairOrder(tenant_id=a.tenant.id, customer_id=a.customer.id, vehicle_id=a.vehicle.id,
                order_number=f"SCHEDULE-{uuid4().hex}", description="Hydraulic scheduling fixture" if index < 29 else "Other work",
                status=Status.IN_PROGRESS, total_cost=Decimal("10.00"),
                promised_finish_at=NOW - timedelta(hours=1 if index < 29 else 2))
            db.add(row)
            rows.append(row)
        await db.commit()
        if fallback:
            await db.execute(delete(RepairOrderReadModel).where(RepairOrderReadModel.tenant_id == a.tenant.id))
            await db.commit()
        args = dict(customer_id=a.customer.id, vehicle_id=a.vehicle.id, status=None,
                    search="Hydraulic", deleted=False, overdue=True, db=db, current_user=a.owner)
        first = await routes.list_repair_orders(**args, skip=0, limit=25, paginated=True)
        second = await routes.list_repair_orders(**args, skip=25, limit=25, paginated=True)
        # Paginated endpoints return JSONResponse rather than envelope models.
        import json
        first, second = json.loads(first.body), json.loads(second.body)
        assert first["total"] == second["total"] == 29
        assert len(first["items"]) == 25 and len(second["items"]) == 4
        ids = [r["id"] for r in first["items"] + second["items"]]
        assert ids == [str(r.id) for r in sorted(rows[:29], key=lambda r: r.id)]
        assert all(r["is_overdue"] and r["schedule_timezone"] == "America/New_York" for r in first["items"])
        summary = await routes.repair_order_value_summary(**args)
        assert summary.order_count == 29 and summary.order_value == Decimal("290.00")
        counts = await routes.repair_order_status_counts(**{k: v for k, v in args.items() if k != "status"})
        assert counts == {"in_progress": 29, "all": 29}
        for row in rows:
            await db.delete(row)
        await db.commit()
