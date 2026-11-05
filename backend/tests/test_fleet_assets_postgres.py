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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.fleet_asset_attachment import FleetAssetAttachment
from app.db.models.vehicle import Vehicle
from app.db.models.vehicle_relationship import FleetMembership, VehicleCustomerRelationship
from app.api.v1.endpoints import customers, fleet, vehicles
from app.schemas.fleet import FleetTruckCreate
from app.schemas.vehicle import VehicleBase, VehicleCreate, VehicleRelationshipCreate
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
        tenant, company, actor, tractor, trailer, other_tractor, other_trailer, _ = await prepared(setup)
        actor = SimpleNamespace(id=actor.id, tenant_id=tenant.id)
    ready = asyncio.Event()
    async def contender(source, counterpart):
        async with postgres_factory() as db:
            await ready.wait()
            try:
                await fleet_assets.enroll_trailer(db, actor, counterpart, company.id, source)
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
        await fleet_assets.enroll_trailer(winner, actor, trailer.id, company.id, tractor.id)
        entered = asyncio.Event()
        async def competing_change():
            async with postgres_factory() as db:
                entered.set()
                try:
                    if operation == "remove":
                        await end_fleet_membership(db, tenant_id=tenant.id, vehicle_id=tractor.id, fleet_customer_id=company.id)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["vehicle", "customer_vehicle", "fleet_vehicle", "relationship"])
async def test_postgres_concurrent_real_entrypoints_lock_tenant_before_fk_flush(postgres_factory, monkeypatch, operation):
    from tests.test_fleet_board import _vehicle
    async def no_decode(_):
        pass
    for endpoint in (customers, vehicles, fleet):
        monkeypatch.setattr(endpoint, "sync_vehicle_nhtsa_snapshot", no_decode)
    async with postgres_factory() as setup:
        tenant, company, actor, _, _, _, _, _ = await prepared(setup)
        company.fleet_enabled = True
        offboard = [_vehicle(tenant.id, company.id, equipment_type="tractor", unit_number=f"Link {i}") for i in range(2)]
        setup.add_all(offboard)
        await setup.commit()
    real_lock, real_flush = fleet_assets.lock_tenant, AsyncSession.flush
    async def observed_lock(db, tenant_id):
        await real_lock(db, tenant_id)
        db.info["db157_tenant_lock_acquired"] = True
    async def guarded_flush(db, *args, **kwargs):
        if any(isinstance(row, (Vehicle, FleetMembership, VehicleCustomerRelationship)) for row in db.new):
            assert db.info.get("db157_tenant_lock_acquired"), "Tenant lock must precede FK-bearing entry writes"
        return await real_flush(db, *args, **kwargs)
    monkeypatch.setattr(fleet_assets, "lock_tenant", observed_lock)
    monkeypatch.setattr(AsyncSession, "flush", guarded_flush)
    ready = asyncio.Event()
    async def create(index):
        async with postgres_factory() as db:
            await ready.wait()
            unit = f"Concurrent {operation} {index}"
            if operation == "vehicle":
                result = await vehicles.create_vehicle(VehicleCreate(customer_id=company.id,
                    make="Test", model="Tractor", equipment_type="tractor", unit_number=unit), db, actor)
            elif operation == "customer_vehicle":
                result = await customers.create_customer_vehicle(company.id, VehicleBase(
                    make="Test", model="Tractor", equipment_type="tractor", unit_number=unit), db, actor)
            elif operation == "fleet_vehicle":
                result = await fleet.create_fleet_truck(FleetTruckCreate(customer_id=company.id,
                    make="Test", model="Tractor", equipment_type="tractor", unit_number=unit), db, actor)
            else:
                result = await vehicles.create_vehicle_relationship(offboard[index].id,
                    VehicleRelationshipCreate(customer_id=company.id, relationship_type="operator"), db, actor)
            return result.id
    jobs = [asyncio.create_task(create(index)) for index in range(2)]
    ready.set()
    ids = await asyncio.wait_for(asyncio.gather(*jobs), timeout=15)
    assert len(set(ids)) == 2
