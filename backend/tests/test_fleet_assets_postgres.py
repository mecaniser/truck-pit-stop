"""Opt-in migration, database constraints and genuine concurrent pair writes.

Use an isolated local DB157 database. Every test gets its own disposable schema;
this suite never connects to configured application or provider databases.
"""

import asyncio
import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.fleet_asset_attachment import FleetAssetAttachment
from app.db.models.vehicle import Vehicle
from app.services import fleet_assets
from app.services.vehicle_identity import end_fleet_membership
from app.services.vehicle_merge import merge_vehicles
from tests.test_fleet_assets import prepared

pytestmark = pytest.mark.skipif(
    not os.environ.get("ASSET_TEST_DATABASE_URL"), reason="isolated local DB157 PostgreSQL required",
)


@pytest_asyncio.fixture
async def postgres_factory():
    url = os.environ["ASSET_TEST_DATABASE_URL"]
    parsed = make_url(url)
    assert parsed.host in {"localhost", "127.0.0.1"} and parsed.database.startswith("db157"), "isolated local DB157 database only"
    schema = "db157_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.asyncio
async def test_postgres_actual_migration_roundtrip_and_cross_tenant_fk(postgres_factory):
    spec = importlib.util.spec_from_file_location("db157_migration", Path(__file__).parents[1] / "alembic/versions/202_fleet_asset_attachments.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    def invoke(connection, operation):
        with Operations.context(MigrationContext.configure(connection)):
            operation()
    async with postgres_factory() as db:
        connection = await db.connection()
        await connection.run_sync(lambda c: invoke(c, migration.downgrade))
        await connection.run_sync(lambda c: invoke(c, migration.upgrade))
        await db.commit()
        tenant, _, actor, tractor, _, _, _, _ = await prepared(db)
        _, _, _, _, foreign_trailer, _, _, _ = await prepared(db)
        db.add(FleetAssetAttachment(tenant_id=tenant.id, tractor_id=tractor.id, trailer_id=foreign_trailer.id,
                                  attached_at=datetime.now(timezone.utc), attached_by_user_id=actor.id))
        with pytest.raises(IntegrityError, match="fk_fleet_attachment_trailer"):
            await db.flush()
        await db.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("compete_for", ["trailer", "tractor"])
async def test_postgres_concurrent_attach_has_one_winner_and_no_history_loss(postgres_factory, compete_for):
    async with postgres_factory() as setup:
        tenant, _, actor, tractor, trailer, other_tractor, other_trailer, _ = await prepared(setup)
        actor = SimpleNamespace(id=actor.id, tenant_id=tenant.id)
    ready = asyncio.Event()
    async def contender(source, counterpart):
        async with postgres_factory() as db:
            await ready.wait()
            try:
                await fleet_assets.change_attachment(db, actor, source, counterpart, None)
                await db.commit()
                return "created"
            except HTTPException as exc:
                await db.rollback()
                return exc.status_code
    second = (other_tractor.id, trailer.id) if compete_for == "trailer" else (tractor.id, other_trailer.id)
    jobs = [asyncio.create_task(contender(tractor.id, trailer.id)), asyncio.create_task(contender(*second))]
    ready.set()
    results = await asyncio.wait_for(asyncio.gather(*jobs), timeout=10)
    assert sorted(results, key=str) == [409, "created"]
    async with postgres_factory() as read:
        rows = (await read.execute(select(FleetAssetAttachment))).scalars().all()
        assert len(rows) == 1 and rows[0].detached_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["remove", "merge", "classify"])
async def test_postgres_attachment_serializes_with_lifecycle_and_type_change(postgres_factory, operation):
    async with postgres_factory() as setup:
        tenant, company, actor, tractor, trailer, other_tractor, _, _ = await prepared(setup)
        actor = SimpleNamespace(id=actor.id, tenant_id=tenant.id)
    async with postgres_factory() as winner:
        await fleet_assets.change_attachment(winner, actor, tractor.id, trailer.id, None)
        entered = asyncio.Event()
        async def competing_change():
            async with postgres_factory() as db:
                entered.set()
                try:
                    if operation == "remove":
                        await end_fleet_membership(db, tenant_id=tenant.id, vehicle_id=trailer.id, fleet_customer_id=company.id)
                    elif operation == "merge":
                        await merge_vehicles(db, tenant_id=tenant.id, canonical_id=other_tractor.id,
                                             duplicate_id=tractor.id, merged_by_user_id=actor.id)
                    else:
                        asset = await db.get(Vehicle, trailer.id)
                        await fleet_assets.change_equipment_type(db, asset, "other")
                    await db.commit()
                    return "changed"
                except HTTPException as exc:
                    await db.rollback()
                    return exc.status_code
        job = asyncio.create_task(competing_change())
        await entered.wait()
        await winner.commit()
        assert await asyncio.wait_for(job, timeout=10) == 409
    async with postgres_factory() as read:
        assert (await read.get(Vehicle, trailer.id)).equipment_type == "trailer"
        rows = (await read.execute(select(FleetAssetAttachment))).scalars().all()
        assert len(rows) == 1 and rows[0].detached_at is None
