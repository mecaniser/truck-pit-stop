"""DB120 dialect/committed-edit checks on the existing opt-in isolated local PG."""
from datetime import UTC, date, datetime

from fastapi import HTTPException
import pytest
from sqlalchemy import update

from app.db.models.repair_order import RepairOrder
from app.db.models.repair_order import RepairOrderStatus as Status
from app.db.models.vehicle import Vehicle
from app.services import vehicle_history_export as service
from test_operation_execution_postgres import pg_case  # noqa: F401
from test_vehicle_history_export import decoded, order, outside

pytestmark = pytest.mark.asyncio


async def test_pg_native_dst_imported_calendar_and_scoped_stream(pg_case):
    factory, a = pg_case
    async with factory() as db:
        await order(db, a, description='Native DST', work_completed_at=datetime(2026, 3, 9, 3, 59, tzinfo=UTC))
        await order(db, a, description='Imported midnight', source=service.IMPORT_SOURCE, work_completed_at=datetime(2026, 3, 8, tzinfo=UTC))
        await order(db, a, description='After day', work_completed_at=datetime(2026, 3, 9, 4, tzinfo=UTC))
        await outside(db, a, description='Outside', service_date=date(2026, 3, 8))
        await db.commit()
    async with factory() as db:
        content, count = await service.export_csv(db, a.vehicle.id, a.owner, date_from=date(2026, 3, 8), date_to=date(2026, 3, 8))
        assert count == 3
        assert {row['Work description'] for row in decoded(content)} == {'Native DST', 'Imported midnight', 'Outside'}
        assert {row['Service date'] for row in decoded(content)} == {'2026-03-08'}


async def test_pg_committed_text_growth_between_preflight_and_fetch_is_bounded(pg_case, monkeypatch):
    factory, a = pg_case
    async with factory() as db:
        await db.execute(update(RepairOrder).where(RepairOrder.id == a.order.id).values(status=Status.COMPLETED))
        await db.commit()
    original = service.bounded_rows
    mutated = False
    async def grow(db, statement, raw_characters, maximum_rows):
        nonlocal mutated
        if not mutated:
            mutated = True
            async with factory() as writer:
                await writer.execute(update(RepairOrder).where(RepairOrder.id == a.order.id).values(description='x' * 5000))
                await writer.commit()
        return await original(db, statement, raw_characters, maximum_rows)
    monkeypatch.setattr(service, 'MAX_CSV_BYTES', 1024)
    monkeypatch.setattr(service, 'bounded_rows', grow)
    async with factory() as db:
        with pytest.raises(HTTPException) as exc:
            await service.export_csv(db, a.vehicle.id, a.owner)
        assert exc.value.status_code == 413 and exc.value.detail['code'] == 'history_export_too_large'


async def test_pg_committed_archive_before_return_rejects_stale_vehicle(pg_case, monkeypatch):
    factory, a = pg_case
    async with factory() as db:
        await outside(db, a)
        await db.commit()
    original = service.active_vehicle
    calls = 0
    async def archive_before_final_read(db, vehicle_id, tenant_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            async with factory() as writer:
                await writer.execute(update(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.tenant_id == tenant_id).values(deleted_at=datetime.now(UTC)))
                await writer.commit()
        return await original(db, vehicle_id, tenant_id)
    monkeypatch.setattr(service, 'active_vehicle', archive_before_final_read)
    async with factory() as db:
        with pytest.raises(HTTPException) as exc:
            await service.export_csv(db, a.vehicle.id, a.owner)
        assert exc.value.status_code == 404 and exc.value.detail['code'] == 'vehicle_not_found'
