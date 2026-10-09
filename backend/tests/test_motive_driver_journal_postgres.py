"""Opt-in real Postgres advisory locks, checkpoint isolation and immutability."""

import asyncio
import importlib.util
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.fleet_driver_record import FleetDriverRecordCapture
from scripts.motive_drivers import journal, run_worker
from tests.test_fleet_driver_records import fixture
from tests.test_motive_driver_journal import import_run
from tests.test_motive_driver_worker import document

pytestmark = pytest.mark.skipif(
    not os.environ.get("DRIVER_JOURNAL_TEST_DATABASE_URL"),
    reason="isolated migrated journal PostgreSQL required",
)


@pytest.mark.asyncio
async def test_postgres_lock_checkpoint_replacement_and_immutable_evidence(monkeypatch):
    engine = create_async_engine(os.environ["DRIVER_JOURNAL_TEST_DATABASE_URL"])
    assert engine.url.database.startswith("driver_journal_"), (
        "Use an owned isolated driver_journal_ database"
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    spec = importlib.util.spec_from_file_location(
        "journal_migration",
        Path(__file__).parents[1] / "alembic/versions/164_motive_driver_journal.py",
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
        actor, _vehicle, member = await fixture(db, monkeypatch)
        identity = journal.Identity(
            actor.tenant_id,
            actor.id,
            member.fleet_customer_id,
            "KT123",
            "Synthetic Fleet",
        )
    await journal.authorize_configuration(factory, identity)
    original = journal.DurableRun.checkpoint
    observed_pending = False

    async def fail_after_application_commit(self, receipt, **kwargs):
        nonlocal observed_pending
        if receipt["stage"] == "committed":
            raise OSError("Synthetic replacement after uncertain commit")
        await original(self, receipt, **kwargs)
        if receipt["stage"] == "commit_pending":
            async with engine.connect() as observer:
                assert (
                    await observer.scalar(
                        sa.select(journal.runs.c.stage).where(
                            journal.runs.c.id == self.id
                        )
                    )
                    == "commit_pending"
                )
                assert (
                    await observer.scalar(
                        sa.select(sa.func.count()).select_from(FleetDriverRecordCapture)
                    )
                    == 0
                )
            observed_pending = True

    async with journal.database_journal(
        engine, identity, "test-driver-service"
    ) as store:
        async with engine.connect() as observer:
            assert (
                await observer.scalar(
                    sa.text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": journal.lock_key("test-driver-service")},
                )
                is False
            )
        with pytest.raises(RuntimeError, match="already running"):
            async with journal.database_journal(
                engine, identity, "test-driver-service"
            ):
                pass
        durable = await store.create(document(), commit=True)
        run_id = durable.id
        monkeypatch.setattr(
            journal.DurableRun, "checkpoint", fail_after_application_commit
        )
        with pytest.raises(OSError, match="uncertain commit"):
            await asyncio.wait_for(
                import_run(
                    factory, identity, (await durable.load())["source"], durable
                ),
                timeout=15,
            )
        assert observed_pending
        pending = await durable.load()
        assert pending["receipt"]["stage"] == "commit_pending"
        capture_id = pending["receipt"]["rows"][0]["capture_id"]
    monkeypatch.setattr(journal.DurableRun, "checkpoint", original)
    async with journal.database_journal(
        engine, identity, "test-driver-service"
    ) as replacement:
        await asyncio.wait_for(
            run_worker.recover_database(replacement, factory, commit=True), timeout=15
        )
        assert await replacement.pending() == []
        saved = await journal.DurableRun(replacement, run_id).load()
        assert saved["receipt"]["rows"][0]["capture_id"] == capture_id
        assert saved["receipt"]["stage"] == "verified"
        async with engine.connect() as observer:
            receipts = await observer.scalar(
                sa.select(journal.runs.c.receipts).where(journal.runs.c.id == run_id)
            )
            assert [item["stage"] for item in receipts] == [
                "source_saved",
                "validated",
                "commit_pending",
                "validated",
                "commit_pending",
                "committed",
                "verified",
            ]
    for changed in (
        replace(identity, tenant_id=uuid4()),
        replace(identity, actor_id=uuid4()),
        replace(identity, company_id="foreign"),
    ):
        with pytest.raises(ValueError, match="identity mismatch"):
            async with journal.database_journal(engine, changed, "test-driver-service"):
                pass
    # Direct SQL cannot alter the retained source/attempt/receipt or remove it.
    for mutation in (
        journal.runs.update()
        .where(journal.runs.c.id == run_id)
        .values(source_document={}),
        journal.runs.update()
        .where(journal.runs.c.id == run_id)
        .values(attempt_document={}),
        journal.runs.update().where(journal.runs.c.id == run_id).values(receipts=[]),
        journal.runs.delete().where(journal.runs.c.id == run_id),
    ):
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(mutation)
    with pytest.raises(DBAPIError, match="Retain revision 164"):
        async with engine.begin() as connection:
            await connection.run_sync(lambda c: invoke(c, migration.downgrade))
    async with journal.database_journal(
        engine, identity, "test-driver-service"
    ) as store:
        incomplete = await store.create(document())
        saved = await incomplete.load()
        # NULL must not make PostgreSQL CHECK treat this invalid state as unknown.
        with pytest.raises(DBAPIError):
            async with engine.begin() as connection:
                await connection.execute(
                    journal.runs.update()
                    .where(journal.runs.c.id == incomplete.id)
                    .values(
                        stage="validated",
                        receipts=[
                            saved["receipt"],
                            {**saved["receipt"], "stage": "validated"},
                        ],
                    )
                )
    # A dropped/released lock fails closed instead of silently using a new
    # connection that no longer serializes this worker.
    async with journal.database_journal(
        engine, identity, "test-driver-service"
    ) as store:
        async with store.connection.begin():
            await store.connection.execute(
                sa.text("SELECT pg_advisory_unlock(:key)"),
                {"key": journal.lock_key("test-driver-service")},
            )
        with pytest.raises(RuntimeError, match="lock was lost"):
            await store.pending()
    await engine.dispose()
