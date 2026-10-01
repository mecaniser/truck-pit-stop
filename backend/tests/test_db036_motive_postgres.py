"""Opt-in tests against a disposable PostgreSQL database, never the app DB."""

import asyncio
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.motive import (
    MotiveAccount,
    MotiveBinding,
    MotiveIngestionReceipt,
    MotiveLocationSample,
)
from app.services.motive_sandbox import ingest_fixture_location
from tests.test_db036_motive_sandbox import NOW, SECRET, signed

# The shared SQLite fixture replaces these globally and does not restore them.
# Capture native processors at collection so this real-PostgreSQL fixture does
# not inherit SQLite compatibility shims when both suites run together.
NATIVE_UUID_BIND = PG_UUID.bind_processor
NATIVE_UUID_RESULT = PG_UUID.result_processor


@pytest_asyncio.fixture
async def pg_store(monkeypatch):
    dsn = os.environ.get("DB036_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip(
            "DB036_TEST_DATABASE_URL must name a disposable local db036_test database"
        )
    url = make_url(dsn)
    if url.host not in {"127.0.0.1", "localhost"} or url.database != "db036_test":
        pytest.fail("Refusing a non-test PostgreSQL target")
    monkeypatch.setattr(PG_UUID, "bind_processor", NATIVE_UUID_BIND)
    monkeypatch.setattr(PG_UUID, "result_processor", NATIVE_UUID_RESULT)
    schema = "db036_" + uuid4().hex
    admin = create_engine(url.set(drivername="postgresql+psycopg2"))
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    sync = create_engine(
        url.set(drivername="postgresql+psycopg2"),
        connect_args={"options": f"-csearch_path={schema}"},
    )
    spec = importlib.util.spec_from_file_location(
        "db036_migration",
        Path(__file__).parents[1] / "alembic/versions/151_motive_sandbox.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with sync.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tenants (id uuid PRIMARY KEY, is_active boolean NOT NULL DEFAULT true, deleted_at timestamptz)"
            )
        )
        conn.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
        conn.execute(
            text(
                "CREATE TABLE vehicles (id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES tenants(id), deleted_at timestamptz)"
            )
        )
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"),
        connect_args={"server_settings": {"search_path": schema}},
    )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False), sync, migration
    finally:
        await engine.dispose()
        sync.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


async def seed_pg(factory):
    from datetime import timedelta

    tenant_id, user_id, vehicle_id = uuid4(), uuid4(), uuid4()
    async with factory.begin() as db:
        await db.execute(
            text("INSERT INTO tenants (id) VALUES (:id)"), {"id": tenant_id}
        )
        await db.execute(text("INSERT INTO users VALUES (:id)"), {"id": user_id})
        await db.execute(
            text("INSERT INTO vehicles (id, tenant_id) VALUES (:id, :tenant)"),
            {"id": vehicle_id, "tenant": tenant_id},
        )
        account = MotiveAccount(
            id=uuid4(),
            tenant_id=tenant_id,
            external_company_id="fixture:company",
            enabled=True,
        )
        db.add(account)
        await db.flush()
        binding = MotiveBinding(
            id=uuid4(),
            tenant_id=tenant_id,
            account_id=account.id,
            vehicle_id=vehicle_id,
            provider_vehicle_id="123",
            gateway_id="fixture:gateway",
            valid_from=NOW - timedelta(days=1),
            verified_by_user_id=user_id,
        )
        db.add(binding)
    return account, binding


@pytest.mark.asyncio
async def test_postgres_migration_roundtrip(pg_store):
    _, sync, migration = pg_store
    with sync.begin() as conn:
        assert "motive_accounts" in inspect(conn).get_table_names()
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert "motive_accounts" not in inspect(conn).get_table_names()
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert "motive_location_samples" in inspect(conn).get_table_names()


@pytest.mark.asyncio
async def test_postgres_concurrent_duplicate_delivery(pg_store):
    factory, _, _ = pg_store
    account, _ = await seed_pg(factory)
    body, signature = signed()

    async def deliver():
        async with factory.begin() as db:
            return await ingest_fixture_location(
                db,
                tenant_id=account.tenant_id,
                account_id=account.id,
                raw_body=body,
                signature=signature,
                fixture_secret=SECRET,
                received_at=NOW,
            )

    results = await asyncio.gather(deliver(), deliver())
    assert sorted(r.outcome for r in results) == ["duplicate", "stored"]
    assert results[0].sample_id == results[1].sample_id
    async with factory() as db:
        assert len(list(await db.scalars(select(MotiveLocationSample)))) == 1
        assert len(list(await db.scalars(select(MotiveIngestionReceipt)))) == 2


@pytest.mark.asyncio
async def test_postgres_rejects_cross_tenant_binding_and_sample(pg_store):
    factory, _, _ = pg_store
    first, binding = await seed_pg(factory)
    other, other_binding = await seed_pg(factory)
    async with factory.begin() as db:
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    MotiveBinding(
                        id=uuid4(),
                        tenant_id=first.tenant_id,
                        account_id=other.id,
                        vehicle_id=binding.vehicle_id,
                        provider_vehicle_id="foreign",
                        valid_from=NOW,
                        verified_by_user_id=binding.verified_by_user_id,
                    )
                )
                await db.flush()
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    MotiveBinding(
                        id=uuid4(),
                        tenant_id=first.tenant_id,
                        account_id=first.id,
                        vehicle_id=other_binding.vehicle_id,
                        provider_vehicle_id="foreign-truck",
                        valid_from=NOW,
                        verified_by_user_id=binding.verified_by_user_id,
                    )
                )
                await db.flush()
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(
                    MotiveLocationSample(
                        id=uuid4(),
                        tenant_id=first.tenant_id,
                        account_id=first.id,
                        binding_id=other_binding.id,
                        event_id="foreign-sample",
                        located_at=NOW,
                        received_at=NOW,
                        lat=35,
                        lng=-80,
                        payload_sha256="a" * 64,
                        ingestion_sequence=1,
                    )
                )
                await db.flush()
