"""Opt-in isolated PostgreSQL migration, retention and identity constraints."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.test_dashboard_vehicle_bindings import driver_body, setup
from tests.test_fleet_driver_records import fixture, save

pytestmark = pytest.mark.skipif(
    not os.environ.get("BINDING_TEST_DATABASE_URL"),
    reason="isolated PostgreSQL required",
)


@pytest.mark.asyncio
async def test_upgrade_retains_genuine_vin_rows_and_enforces_binding_xor(monkeypatch):
    engine = create_async_engine(os.environ["BINDING_TEST_DATABASE_URL"])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    spec = importlib.util.spec_from_file_location(
        "binding_migration",
        Path(__file__).parents[1]
        / "alembic/versions/177_dashboard_vehicle_bindings.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def invoke(connection, method):
        with Operations.context(MigrationContext.configure(connection)):
            method()

    async with factory() as db:
        actor, _, member = await fixture(db, monkeypatch)
        record, _ = await save(db, actor, member)
        await db.commit()
        record_id = record.id
        before = (
            await db.execute(
                text(
                    "SELECT verified_vin, content_sha256, payload::text FROM fleet_driver_record_captures WHERE id=:id"
                ),
                {"id": record_id},
            )
        ).one()
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: invoke(c, migration.downgrade))
        await conn.run_sync(lambda c: invoke(c, migration.upgrade))
    async with factory() as db:
        after = (
            await db.execute(
                text(
                    "SELECT verified_vin, content_sha256, payload::text FROM fleet_driver_record_captures WHERE id=:id"
                ),
                {"id": record_id},
            )
        ).one()
        assert before == after
        actor, _, member, binding, _ = await setup(db, monkeypatch)
        record, _ = await save(db, actor, member, driver_body(binding))
        await db.commit()
        for changes in [
            "verified_vin='1FUJGLDR9CLBU2344'",
            "dashboard_binding_id=NULL",
            "dashboard_binding_id='" + str(uuid4()) + "'",
        ]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(
                        text(
                            "UPDATE fleet_driver_record_captures SET "
                            + changes
                            + " WHERE id=:id"
                        ),
                        {"id": record.id},
                    )
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(
                        "INSERT INTO dashboard_vehicle_bindings SELECT :id, created_at, updated_at, deleted_at, tenant_id, vehicle_id, fleet_customer_id, fleet_membership_id, source_company_id, source_company_label, provider_vehicle_id, placeholder_vin, reviewed_by_user_id, reviewed_at, effective_from, effective_to, revoked_at, revoked_by_user_id, revocation_reason, revoked_source_vin, revoked_source_read_at, revoked_source_sha256, review_note, review_manifest_sha256, source_evidence_sha256, source_evidence_read_at, source_vin_state FROM dashboard_vehicle_bindings WHERE id=:existing"
                    ),
                    {"id": uuid4(), "existing": binding.id},
                )
    with pytest.raises(RuntimeError, match="history must be retained"):
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: invoke(c, migration.downgrade))
    async with engine.connect() as conn:
        assert (
            await conn.scalar(
                text(
                    "SELECT count(*) FROM fleet_driver_record_captures WHERE dashboard_binding_id IS NOT NULL"
                )
            )
            == 1
        )
    await engine.dispose()
