"""Durable worker recovery survives missing files and uncertain app commits."""

from dataclasses import replace
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models.fleet_driver_record import FleetDriverRecordCapture
from scripts.motive_drivers import journal, run_worker, runner
from tests.test_fleet_driver_records import fixture
from tests.test_motive_driver_worker import document


@pytest_asyncio.fixture
async def durable_setup(_db_engine, db_session, monkeypatch, tmp_path):
    actor, _vehicle, member = await fixture(db_session, monkeypatch)
    identity = journal.Identity(
        actor.tenant_id, actor.id, member.fleet_customer_id, "KT123", "Synthetic Fleet"
    )
    # A separate database connection is essential: checkpoint commit must never
    # commit/rollback the import session, even in the isolated SQLite test.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'journal.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(journal.metadata.create_all)
    yield engine, async_sessionmaker(_db_engine, expire_on_commit=False), identity
    await engine.dispose()


async def import_run(factory, identity, source, durable, receipt_path=None):
    return await runner.run(
        factory,
        source,
        identity.tenant_id,
        identity.actor_id,
        identity.company_label,
        identity.company_id,
        receipt_path,
        commit=True,
        expected_customer_id=identity.customer_id,
        durable=durable,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_phase, expected_rows",
    [("validated", 0), ("commit_pending", 0), ("committed", 1), ("verified", 1)],
)
async def test_crash_at_every_checkpoint_recovers_from_database_without_files(
    durable_setup,
    tmp_path,
    monkeypatch,
    failed_phase,
    expected_rows,
):
    engine, factory, identity = durable_setup
    source = document()
    original = journal.DurableRun.checkpoint

    async def interrupt(self, receipt, **kwargs):
        if receipt["stage"] == failed_phase:
            raise OSError("Synthetic journal interruption")
        return await original(self, receipt, **kwargs)

    async with engine.connect() as connection:
        store = journal.Journal(connection, identity, "synthetic-worker")
        durable = await store.create(source, commit=True)
        run_id = durable.id
        monkeypatch.setattr(journal.DurableRun, "checkpoint", interrupt)
        with pytest.raises(OSError, match="Synthetic"):
            await import_run(
                factory, identity, source, durable, tmp_path / "receipt.json"
            )
        saved = await durable.load()
        if saved["attempt"]:
            original_requests = saved["attempt"]["eligible_requests"]
        else:
            original_requests = None
    async with factory() as db:
        assert (
            await db.scalar(
                sa.select(sa.func.count()).select_from(FleetDriverRecordCapture)
            )
            == expected_rows
        )
        before_ids = (
            (await db.execute(sa.select(FleetDriverRecordCapture.id))).scalars().all()
        )
    # Simulate container replacement: no receipt/source/attempt files survive.
    for path in tmp_path.glob("*.json*"):
        path.unlink()
    monkeypatch.setattr(journal.DurableRun, "checkpoint", original)
    async with engine.connect() as connection:
        replacement = journal.Journal(connection, identity, "synthetic-worker")
        await run_worker.recover_database(replacement, factory, commit=True)
        assert await replacement.pending() == []
        restored = await journal.DurableRun(replacement, run_id).load()
        assert restored["source"] == source
        assert restored["receipt"]["stage"] == "verified"
        assert restored["receipt"]["readback_verified"] == 1
        if original_requests:
            assert restored["attempt"]["eligible_requests"] == original_requests
    async with factory() as db:
        after_ids = (
            (await db.execute(sa.select(FleetDriverRecordCapture.id))).scalars().all()
        )
        assert len(after_ids) == 1
        if expected_rows:
            assert after_ids == before_ids


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", uuid4()),
        ("actor_id", uuid4()),
        ("customer_id", uuid4()),
        ("company_id", "wrong-company"),
        ("company_label", "Wrong company"),
    ],
)
async def test_changed_worker_identity_cannot_read_or_recover_saved_source(
    durable_setup, field, value
):
    engine, _factory, identity = durable_setup
    async with engine.connect() as connection:
        initial = journal.Journal(connection, identity, "bound-worker")
        durable = await initial.create(document(), commit=True)
        wrong = journal.Journal(
            connection, replace(identity, **{field: value}), "bound-worker"
        )
        with pytest.raises(ValueError, match="identity mismatch"):
            await wrong.check_binding()
        with pytest.raises(ValueError, match="identity mismatch"):
            await journal.DurableRun(wrong, durable.id).load()
        with pytest.raises(ValueError, match="identity mismatch"):
            await wrong.pending()


@pytest.mark.asyncio
async def test_saved_source_tampering_and_dry_run_promotion_rejected(durable_setup):
    engine, factory, identity = durable_setup
    async with engine.connect() as connection:
        store = journal.Journal(connection, identity, "dry-worker")
        source = document()
        durable = await store.create(source)
        with pytest.raises(ValueError, match="intent or immutable identity"):
            await import_run(factory, identity, source, durable)
        assert await store.pending() == []
        # SQLite does not install the PostgreSQL immutable trigger, so this also
        # proves application recovery checks reject a corrupted artifact.
        async with connection.begin():
            await connection.execute(
                journal.runs.update()
                .where(journal.runs.c.id == durable.id)
                .values(source_document={**source, "complete": False})
            )
        with pytest.raises(ValueError, match="source changed"):
            await durable.load()


@pytest.mark.asyncio
async def test_pending_commit_blocks_collection_if_saving_is_disabled(durable_setup):
    engine, factory, identity = durable_setup
    async with engine.connect() as connection:
        store = journal.Journal(connection, identity, "pending-worker")
        await store.create(document(), commit=True)
        with pytest.raises(RuntimeError, match="saving is disabled"):
            await run_worker.recover_database(store, factory, commit=False)
        assert len(await store.pending()) == 1


@pytest.mark.asyncio
async def test_recovery_uses_stored_old_source_without_refreshing_its_time(
    durable_setup, monkeypatch
):
    from datetime import timedelta

    from scripts.motive_drivers import import_records

    engine, factory, identity = durable_setup
    source = document()
    async with engine.connect() as connection:
        store = journal.Journal(connection, identity, "older-source")
        durable = await store.create(source, commit=True)
        current_time = import_records.now()
        monkeypatch.setattr(
            import_records, "now", lambda: current_time + timedelta(days=3)
        )
        await run_worker.recover_database(store, factory, commit=True)
        saved = await durable.load()
        assert saved["source"]["finished_at"] == source["finished_at"]
        assert saved["receipt"]["stage"] == "verified"


@pytest.mark.asyncio
async def test_worker_checks_database_before_starting_collector(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def unavailable(*args, **kwargs):
        raise ConnectionError("Synthetic unavailable database")
        yield  # pragma: no cover

    identity = journal.Identity(uuid4(), uuid4(), uuid4(), "KT123", "Synthetic Fleet")
    monkeypatch.setattr(journal.Identity, "from_environment", lambda: identity)
    monkeypatch.setattr(journal, "database_journal", unavailable)
    calls = []
    monkeypatch.setattr(
        run_worker.subprocess, "run", lambda *args, **kwargs: calls.append(args)
    )
    with pytest.raises(ConnectionError):
        await run_worker.database_worker(tmp_path, engine=object(), factory=object())
    assert calls == []
