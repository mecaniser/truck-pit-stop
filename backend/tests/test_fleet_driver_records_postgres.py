"""Opt-in migration, trigger, tenant FK and downgrade checks on isolated PG."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.services import fleet_driver_records as service
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.test_fleet_driver_records import body, fixture, save

pytestmark = pytest.mark.skipif(
    not os.environ.get("DRIVER_TEST_DATABASE_URL"),
    reason="isolated migrated PostgreSQL required",
)


@pytest.mark.asyncio
async def test_postgres_migration_trigger_fk_and_evidence_rollback(
    monkeypatch, tmp_path
):
    engine = create_async_engine(os.environ["DRIVER_TEST_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    spec = importlib.util.spec_from_file_location(
        "driver_migration",
        Path(__file__).parents[1] / "alembic/versions/163_fleet_driver_records.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def invoke(connection, method):
        with Operations.context(MigrationContext.configure(connection)):
            method()

    async with engine.begin() as connection:
        await connection.run_sync(lambda c: invoke(c, migration.downgrade))
        await connection.run_sync(lambda c: invoke(c, migration.upgrade))
    async with factory() as db:
        actor, vehicle, member = await fixture(db, monkeypatch)
        source = body()
        record, _ = await save(db, actor, member, source)
        await db.commit()
        record_id, tenant_id, vehicle_id = record.id, actor.tenant_id, vehicle.id
        repeated, status = await save(db, actor, member, source)
        assert status == "unchanged" and repeated.id == record_id
        await db.rollback()
    async with factory() as db:
        result = await service.read(db, tenant_id, vehicle_id)
        assert result.record.capture_id == record_id
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "UPDATE fleet_driver_record_captures SET fleet_customer_id=:customer WHERE id=:id"
                    ),
                    {"customer": uuid4(), "id": record_id},
                )
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "UPDATE fleet_driver_record_captures SET source_read_at=captured_at+interval '1 minute' WHERE id=:id"
                    ),
                    {"id": record_id},
                )
        revision = await db.scalar(
            text("SELECT driver_assignment_revision FROM vehicles WHERE id=:id"),
            {"id": vehicle_id},
        )
        # Raw SQL proves the trigger covers paths that bypass ORM event hooks.
        for name in ("Different driver", "Synthetic Driver"):
            await db.execute(
                text("UPDATE vehicles SET driver_name=:name WHERE id=:id"),
                {"name": name, "id": vehicle_id},
            )
        await db.commit()
        assert (
            await db.scalar(
                text("SELECT driver_assignment_revision FROM vehicles WHERE id=:id"),
                {"id": vehicle_id},
            )
            == revision + 2
        )
        assert (await service.read(db, tenant_id, vehicle_id)).record is None
        # Unrelated edits do not invalidate unchanged driver identity.
        await db.execute(
            text("UPDATE vehicles SET mileage=mileage+1 WHERE id=:id"),
            {"id": vehicle_id},
        )
        await db.commit()
        assert (
            await db.scalar(
                text("SELECT driver_assignment_revision FROM vehicles WHERE id=:id"),
                {"id": vehicle_id},
            )
            == revision + 2
        )
    from scripts.motive_drivers.runner import run
    from tests.test_motive_driver_worker import document

    async with factory() as db:
        customer_id = await db.scalar(
            text(
                "SELECT fleet_customer_id FROM fleet_driver_record_captures WHERE id=:id"
            ),
            {"id": record_id},
        )
        actor_id = await db.scalar(
            text(
                "SELECT captured_by_user_id FROM fleet_driver_record_captures WHERE id=:id"
            ),
            {"id": record_id},
        )
    source = document()
    receipt = await run(
        factory,
        source,
        tenant_id,
        actor_id,
        "Synthetic Fleet",
        "KT123",
        tmp_path / "pg-driver.json",
        commit=True,
        expected_customer_id=customer_id,
    )
    assert receipt["stage"] == "verified" and receipt["readback_verified"] == 1
    empty = document()
    empty.update(
        drivers=[], driver_directory_count=0, terminal_evidence="Showing 0 of 0"
    )
    await run(
        factory,
        empty,
        tenant_id,
        actor_id,
        "Synthetic Fleet",
        "KT123",
        tmp_path / "pg-empty.json",
        commit=True,
        expected_customer_id=customer_id,
    )
    async with factory() as db:
        assert (await service.read(db, tenant_id, vehicle_id)).record is None
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "UPDATE fleet_driver_directory_captures SET fleet_customer_id=:customer"
                    ),
                    {"customer": uuid4()},
                )
    with pytest.raises(DBAPIError, match="Retain revision 163"):
        async with engine.begin() as connection:
            await connection.run_sync(lambda c: invoke(c, migration.downgrade))
    await engine.dispose()
