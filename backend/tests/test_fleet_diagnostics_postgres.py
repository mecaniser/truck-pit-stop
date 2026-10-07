"""Opt-in real PostgreSQL acceptance against an isolated migrated test database."""

import asyncio
import importlib.util
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.db.models.fleet_diagnostic import FleetDiagnosticCapture
from app.services import fleet_diagnostics as service
from app.services.fleet_telemetry import now
from scripts.motive_health.runner import run
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.test_db036_fleet_telemetry import prepared
from tests.test_fleet_diagnostics import document

pytestmark = pytest.mark.skipif(
    not os.environ.get("HEALTH_TEST_DATABASE_URL"),
    reason="isolated migrated PostgreSQL required",
)


@pytest.mark.asyncio
async def test_postgres_migration_fk_tenant_replay_and_protected_rollback(
    monkeypatch, tmp_path
):
    engine = create_async_engine(os.environ["HEALTH_TEST_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    spec = importlib.util.spec_from_file_location(
        "health_migration",
        Path(__file__).parents[1] / "alembic/versions/162_fleet_diagnostic_captures.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def invoke(connection, method):
        with Operations.context(MigrationContext.configure(connection)):
            method()

    # Empty additive table can be rolled back and upgraded on genuine PostgreSQL.
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: invoke(c, migration.downgrade))
        await connection.run_sync(lambda c: invoke(c, migration.upgrade))
    async with factory() as db:
        actor, vehicle, membership = await prepared(db, monkeypatch)
        membership.effective_from = now() - timedelta(days=1)
        await db.commit()
        tenant_id, actor_id, vehicle_id = actor.tenant_id, actor.id, vehicle.id
    async with factory() as locked:
        await service.authorize(locked, tenant_id, actor_id)

        async def revoke_in_other_transaction():
            async with factory() as other:
                await other.execute(
                    text("UPDATE users SET is_active = false WHERE id = :actor"),
                    {"actor": actor_id},
                )
                await other.rollback()

        revocation = asyncio.create_task(revoke_in_other_transaction())
        await asyncio.sleep(0.1)
        assert not revocation.done(), (
            "Actor authorization must remain locked until capture transaction ends"
        )
        await locked.rollback()
        await asyncio.wait_for(revocation, timeout=2)
    source = document()
    args = (
        factory,
        source,
        tenant_id,
        actor_id,
        "77 CARGO LLC",
        "KT8934277",
        tmp_path / "pg.json",
    )
    saved = await run(*args, commit=True)
    again = await run(*args, commit=True, recovery=True)
    assert saved["rows"][0]["capture_id"] == again["rows"][0]["capture_id"]
    async with factory() as db:
        row = (
            await db.execute(
                select(FleetDiagnosticCapture).where(
                    FleetDiagnosticCapture.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        snapshot_id = row.id
        # Composite customer/vehicle/member binding rejects cross-identity tampering.
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "UPDATE fleet_diagnostic_captures SET fleet_customer_id = :other WHERE id = :id"
                    ),
                    {"other": uuid4(), "id": snapshot_id},
                )
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "UPDATE fleet_diagnostic_captures SET explicit_empty = true WHERE id = :id"
                    ),
                    {"id": snapshot_id},
                )
        result = await service.read(db, tenant_id, vehicle_id)
        assert (
            result.capture_id == snapshot_id
            and result.codes[0].last_observed_at is None
        )
        await db.rollback()
    # Evidence-bearing downgrade refuses data loss and leaves the table readable.
    with pytest.raises(DBAPIError, match="Retain revision 162"):
        async with engine.begin() as connection:
            await connection.run_sync(lambda c: invoke(c, migration.downgrade))
    async with factory() as db:
        assert (
            await db.execute(
                select(FleetDiagnosticCapture.id).where(
                    FleetDiagnosticCapture.id == snapshot_id
                )
            )
        ).scalar_one() == snapshot_id
    await engine.dispose()
