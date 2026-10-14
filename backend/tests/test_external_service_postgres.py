"""DB119 real concurrency and migration constraints on opt-in isolated PG only."""
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.db.models.external_service import ExternalServiceEvent as Event, ExternalServiceRecord as Record
from app.schemas.external_service import ExternalServiceVoid as Void
from app.services import external_service as service
from app.services.vehicle_merge import merge_vehicles
from test_external_service import add_vehicle, create, update as correction
from test_operation_execution_postgres import pg_case  # noqa: F401

pytestmark = pytest.mark.asyncio


async def blocked_call(db, call, release):
    """Start the second transaction and release the first after its lock query."""
    entered = asyncio.Event()
    connection = await db.connection()
    def before_cursor(conn, cursor, statement, parameters, context, many):
        if "FOR UPDATE" in statement and "vehicles" in statement:
            entered.set()
    event.listen(connection.sync_connection, "before_cursor_execute", before_cursor)
    pending = asyncio.create_task(call)
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert not pending.done()
        await release()
        return await asyncio.wait_for(pending, 5)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", before_cursor)
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_duplicate_create_after_lock_wait_returns_one_record(pg_case):
    factory, a = pg_case
    request = create()
    async with factory() as one, factory() as two:
        first = await service.mutate(one, a.vehicle.id, a.owner, request)
        second = await blocked_call(two, service.mutate(two, a.vehicle.id, a.owner, request), one.commit)
        assert second.replayed and first.record.id == second.record.id
        assert await two.scalar(select(func.count(Record.id)).where(Record.tenant_id == a.tenant.id)) == 1
        assert await two.scalar(select(func.count(Event.id)).where(Event.tenant_id == a.tenant.id)) == 1


@pytest.mark.parametrize("second_action", ["update", "void"])
async def test_competing_revision_has_one_winner(pg_case, second_action):
    factory, a = pg_case
    async with factory() as setup:
        record = (await service.mutate(setup, a.vehicle.id, a.owner, create())).record
        await setup.commit()
    async with factory() as one, factory() as two:
        await service.mutate(one, a.vehicle.id, a.owner, correction(record, description="Winner"), action="update", record_id=record.id)
        second = correction(record, description="Losing correction") if second_action == "update" else Void(request_id=uuid4(), expected_version=1, reason="Losing void")
        with pytest.raises(HTTPException) as failure:
            await blocked_call(two, service.mutate(two, a.vehicle.id, a.owner, second, action=second_action, record_id=record.id), one.commit)
        assert failure.value.status_code == 409 and failure.value.detail == service.STALE
        await two.rollback()
        current = (await service.page(two, a.vehicle.id, a.owner)).items[0]
        assert current.description == "Winner" and current.version == 2 and current.voided_at is None


async def test_cross_vehicle_request_race_rolls_back_orphan_and_preserves_transaction(pg_case):
    factory, a = pg_case
    async with factory() as setup:
        other = await add_vehicle(setup, a)
    request = create()
    async with factory() as one, factory() as two:
        first = await service.mutate(one, a.vehicle.id, a.owner, request)
        flushing = asyncio.Event()
        def before_flush(session, context, instances):
            if any(isinstance(obj, Event) and obj.request_id == request.request_id for obj in session.new):
                flushing.set()
        event.listen(two.sync_session, "before_flush", before_flush)
        pending = asyncio.create_task(service.mutate(two, other.id, a.owner, request))
        try:
            await asyncio.wait_for(flushing.wait(), 5)
            assert not pending.done()
            await one.commit()
            with pytest.raises(HTTPException) as failure:
                await asyncio.wait_for(pending, 5)
            assert failure.value.status_code == 409 and failure.value.detail == service.COLLISION
            assert await two.scalar(select(func.count(Record.id)).where(Record.tenant_id == a.tenant.id)) == 1
            retry = await service.mutate(two, other.id, a.owner, create())
            assert retry.record.id != first.record.id
            await two.commit()
        finally:
            event.remove(two.sync_session, "before_flush", before_flush)
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.parametrize("write_action", ["create", "update"])
@pytest.mark.parametrize("merge_first", [True, False])
async def test_vehicle_merge_write_race_is_serialized(pg_case, write_action, merge_first):
    factory, a = pg_case
    async with factory() as setup:
        canonical = await add_vehicle(setup, a)
        from app.db.models.vehicle import Vehicle
        await setup.execute(update(Vehicle).where(Vehicle.id == a.vehicle.id).values(vin=canonical.vin))
        record = (await service.mutate(setup, a.vehicle.id, a.owner, create())).record
        await setup.commit()
    payload = create() if write_action == "create" else correction(record, description="Race correction")
    kwargs = {} if write_action == "create" else dict(action="update", record_id=record.id)
    async with factory() as one, factory() as two:
        async def merge(db):
            return await merge_vehicles(db, tenant_id=a.tenant.id, canonical_id=canonical.id, duplicate_id=a.vehicle.id, merged_by_user_id=a.owner.id, confirm_vin=canonical.vin)
        if merge_first:
            await merge(one)
            with pytest.raises(HTTPException) as failure:
                await blocked_call(two, service.mutate(two, a.vehicle.id, a.owner, payload, **kwargs), one.commit)
            assert failure.value.status_code == 404
            await two.rollback()
        else:
            saved = await service.mutate(one, a.vehicle.id, a.owner, payload, **kwargs)
            await blocked_call(two, merge(two), one.commit)
            await two.commit()
            result = await service.page(two, canonical.id, a.owner)
            assert saved.record.id in {item.id for item in result.items}
        records = (await service.page(two, canonical.id, a.owner)).items
        assert all(item.original_vehicle_id == a.vehicle.id for item in records)
        events = (await two.scalars(select(Event).where(Event.tenant_id == a.tenant.id))).all()
        assert all(item.snapshot["original_vehicle_id"] == str(a.vehicle.id) for item in events)


async def test_migration_head_and_tenant_fk_check_unique_constraints(pg_case):
    factory, a = pg_case
    async with factory() as db:
        assert await db.scalar(text("select version_num from alembic_version")) == "169_external_service_history"
        record = (await service.mutate(db, a.vehicle.id, a.owner, create())).record
        await db.commit()
        # DB checks, not just API checks; each failed savepoint must recover.
        for values in [dict(version=0), dict(odometer=-1), dict(odometer=100000000), dict(reported_cost=-1), dict(tenant_id=uuid4()), dict(vehicle_id=uuid4())]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(update(Record).where(Record.id == record.id).values(**values))
        original = await db.scalar(select(Event).where(Event.record_id == record.id))
        for values in [dict(version=0), dict(action="delete"), dict(record_id=uuid4()), dict(tenant_id=uuid4())]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(update(Event).where(Event.id == original.id).values(**values))
        for values in [dict(request_id=original.request_id, version=2), dict(request_id=uuid4(), version=1)]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    db.add(Event(id=uuid4(), tenant_id=a.tenant.id, record_id=record.id, request_hash="0" * 64, action="update", actor_user_id=a.owner.id, actor_name="QA", snapshot=original.snapshot, **values))
                    await db.flush()
        # An existing different tenant isolates the composite FKs from the
        # simpler tenant-existence FK, proving same-tenant identity in storage.
        from app.db.models.tenant import Tenant
        other_tenant = Tenant(id=uuid4(), name="DB119 FK QA", slug=f"db119-fk-{uuid4().hex}")
        db.add(other_tenant)
        await db.flush()
        for model, identity in [(Record, record.id), (Event, original.id)]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(update(model).where(model.id == identity).values(tenant_id=other_tenant.id))
        await db.execute(delete(Tenant).where(Tenant.id == other_tenant.id))
        assert (await service.page(db, a.vehicle.id, a.owner)).items[0].version == 1
