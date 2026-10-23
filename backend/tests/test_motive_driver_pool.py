"""Batch advisory locks reserve one connection, independent of fleet count.

The always-on pool test uses real SQLAlchemy QueuePool checkout limits with
synthetic lock boundaries. The opt-in PostgreSQL test verifies server locks.
"""

import asyncio
import json
import os
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from scripts.motive_drivers import journal, run_fleets, run_worker, runner
from sqlalchemy.exc import TimeoutError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool
from tests.test_motive_driver_fleets import environment
from tests.test_motive_driver_worker import document


@pytest_asyncio.fixture
async def bounded_pool(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'pool.sqlite'}",
        poolclass=AsyncAdaptedQueuePool,
        pool_size=2,
        max_overflow=1,
        pool_timeout=0.05,
    )
    yield engine
    assert engine.pool.checkedout() == 0
    await engine.dispose()


def synthetic_locks(monkeypatch, engine, *, deny_key=None):
    """Keep real pool/session transactions; replace only PostgreSQL lock SQL."""
    held = set()
    connections = set()

    @asynccontextmanager
    async def locked(connection, identity, key):
        if key == deny_key:
            raise RuntimeError("Motive driver worker already running")
        connections.add(id(connection))
        assert key not in held
        held.add(key)
        try:
            yield journal.Journal(connection, identity, key)
        finally:
            held.remove(key)

    monkeypatch.setattr(journal, "_locked_journal", locked)
    return (
        SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"), connect=engine.connect
        ),
        held,
        connections,
    )


@pytest.mark.asyncio
async def test_original_one_connection_per_fleet_exhausts_pool_at_third_authorization(
    bounded_pool,
):
    # This is the original run_fleets checkout order: retain a journal, then
    # request a separate short authorization session, for each of three fleets.
    factory = async_sessionmaker(bounded_pool)
    async with AsyncExitStack() as stack:
        for ordinal in range(3):
            await stack.enter_async_context(bounded_pool.connect())
            async with factory() as db:
                if ordinal < 2:
                    assert await db.scalar(sa.text("SELECT 1")) == 1
                else:
                    with pytest.raises(TimeoutError, match="QueuePool limit"):
                        await db.scalar(sa.text("SELECT 1"))
    assert bounded_pool.pool.checkedout() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [3, 9])
@pytest.mark.parametrize("failure", [None, "authorization", "lock"])
async def test_batch_leaves_pool_room_for_authorization_and_projection(
    bounded_pool, monkeypatch, tmp_path, count, failure
):
    source = {
        **environment(),
        run_fleets.EXTRA_FLEETS: json.dumps([str(uuid4()) for _ in range(count - 1)]),
        "MOTIVE_DRIVER_STATE_DIR": str(tmp_path / "state"),
        "MOTIVE_DRIVER_COMMIT": "true",
    }
    children = run_fleets.fleet_environments(source)
    keys = sorted(child["MOTIVE_DRIVER_JOURNAL_KEY"] for child in children)
    engine, held, connections = synthetic_locks(
        monkeypatch, bounded_pool, deny_key=keys[-1] if failure == "lock" else None
    )
    factory = async_sessionmaker(bounded_pool)
    authorized, projected, collected = [], [], []

    async def authorize(factory, identity):
        async with factory() as db:
            assert await db.scalar(sa.text("SELECT 1")) == 1
        authorized.append(identity.customer_id)
        if failure == "authorization" and len(authorized) == count:
            raise ValueError("tenant denied")

    async def recover(store, factory, **kwargs):
        return 0

    def collect(command, **kwargs):
        collected.append(True)
        Path(command[-1]).write_text(json.dumps(document()))

    async def prepare(stores, document, **kwargs):
        assert len(held) == count
        assert len({id(s.connection) for s in stores}) == 1
        assert len({s.identity.customer_id for s in stores}) == count
        return list(stores)

    async def project(
        factory, document, tenant, actor, label, company, receipt, **kwargs
    ):
        assert len(held) == count
        assert kwargs["durable"].identity.customer_id == kwargs["expected_customer_id"]
        assert kwargs["durable"].identity.tenant_id == tenant
        async with factory() as db:
            assert await db.scalar(sa.text("SELECT 1")) == 1
        projected.append(kwargs["expected_customer_id"])
        return {"stage": "verified", "committed": True}

    monkeypatch.setattr(journal, "authorize_configuration", authorize)
    monkeypatch.setattr(journal, "prepare_batch", prepare)
    monkeypatch.setattr(run_worker, "recover_database", recover)
    monkeypatch.setattr(run_fleets, "read_process", collect)
    monkeypatch.setattr(runner, "run", project)
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            await run_fleets.database_fleets(children, engine=engine, factory=factory)
        assert not collected and not projected
    else:
        await run_fleets.database_fleets(children, engine=engine, factory=factory)
        assert len(collected) == 1 and len(projected) == count
        assert projected == authorized
    assert not held and len(connections) == 1
    assert bounded_pool.pool.checkedout() == 0


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DRIVER_POOL_TEST_DATABASE_URL"),
    reason="isolated PostgreSQL required",
)
@pytest.mark.parametrize("count", [3, 9])
async def test_postgres_shared_locks_identity_atomic_prepare_and_cleanup(count):
    engine = create_async_engine(
        os.environ["DRIVER_POOL_TEST_DATABASE_URL"],
        pool_size=2,
        max_overflow=1,
        pool_timeout=0.1,
    )
    assert engine.url.database.startswith("driver_journal_pool_")
    identity = journal.Identity(uuid4(), uuid4(), uuid4(), "KT123", "Synthetic Fleet")
    identities = [
        (replace(identity, customer_id=uuid4()), f"pool-{uuid4()}")
        for _ in range(count)
    ]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(journal.metadata.create_all)
        # Reproduce the previous retention pattern against actual PostgreSQL:
        # the third retained journal exhausts capacity for authorization checkout.
        factory = async_sessionmaker(engine)
        async with AsyncExitStack() as stack:
            for ordinal, (fleet, key) in enumerate(identities[:3]):
                await stack.enter_async_context(
                    journal.database_journal(engine, fleet, key)
                )
                async with factory() as db:
                    if ordinal < 2:
                        assert await db.scalar(sa.text("SELECT 1")) == 1
                    else:
                        with pytest.raises(TimeoutError, match="QueuePool limit"):
                            await db.scalar(sa.text("SELECT 1"))
        async with journal.database_journals(engine, identities) as stores:
            assert len({id(s.connection) for s in stores}) == 1
            for store in stores:
                await store._check_lock()
                await store.connection.rollback()
                async with engine.connect() as observer:
                    assert not await observer.scalar(
                        sa.text("SELECT pg_try_advisory_lock(:key)"),
                        {"key": journal.lock_key(store.worker_key)},
                    )
            saved = await journal.prepare_batch(stores, document(), commit=True)
            assert len(saved) == count
            for store, durable in zip(stores, saved, strict=True):
                assert (await durable.load())["receipt"]["expected_customer_id"] == str(
                    store.identity.customer_id
                )
                # Separate authorization/projection transactions can check out
                # while all nine real advisory locks remain held.
                async with factory() as db:
                    assert await db.scalar(sa.text("SELECT 1")) == 1
                    await db.rollback()
            # Each fleet's own lock is rechecked, including a non-primary fleet.
            async with stores[-1].connection.begin():
                await stores[-1].connection.execute(
                    sa.text("SELECT pg_advisory_unlock(:key)"),
                    {"key": journal.lock_key(stores[-1].worker_key)},
                )
            with pytest.raises(RuntimeError, match="lock was lost"):
                await journal.prepare_batch(stores, document(), commit=True)
            async with engine.connect() as observer:
                assert (
                    await observer.scalar(
                        sa.select(sa.func.count())
                        .select_from(journal.runs)
                        .where(
                            journal.runs.c.worker_key.in_(
                                [key for _, key in identities]
                            )
                        )
                    )
                    == count
                )
        assert engine.pool.checkedout() == 0
        # Binding failure releases all previously acquired session locks.
        last_key = max(key for _, key in identities)
        changed = [
            (replace(i, tenant_id=uuid4()) if key == last_key else i, key)
            for i, key in identities
        ]
        with pytest.raises(ValueError, match="identity mismatch"):
            async with journal.database_journals(engine, changed):
                pass
        # A lock conflict half-way through a batch also releases earlier locks.
        key = sorted(key for _, key in identities)[count // 2]
        owner = next(i for i, k in identities if k == key)
        async with journal.database_journal(engine, owner, key):
            with pytest.raises(RuntimeError, match="already running"):
                async with journal.database_journals(engine, identities):
                    pass
        async with journal.database_journals(engine, identities) as stores:
            for store in stores:
                await store.check_binding()
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["acquire", "unlock"])
@pytest.mark.parametrize("error_type", [OSError, asyncio.CancelledError])
async def test_ambiguous_acquisition_or_failed_cleanup_discards_session(
    monkeypatch, phase, error_type
):
    class Connection:
        invalidated = False
        unlocked = False

        async def scalar(self, statement, parameters=None):
            if "pg_try_advisory_lock" in str(statement):
                if phase == "acquire":
                    raise error_type("synthetic lost response")
                return True
            return 123

        async def commit(self):
            pass

        async def rollback(self):
            pass

        async def execute(self, statement, parameters=None):
            self.unlocked = True
            raise error_type("synthetic failed cleanup")

        async def invalidate(self):
            self.invalidated = True

    async def bound(self):
        pass

    monkeypatch.setattr(journal.Journal, "check_binding", bound)
    connection = Connection()
    identity = journal.Identity(uuid4(), uuid4(), uuid4(), "KT123", "Synthetic Fleet")
    with pytest.raises(error_type):
        async with journal._locked_journal(connection, identity, "test-key"):
            assert phase == "unlock"
    assert connection.invalidated
    assert connection.unlocked == (phase == "unlock")
