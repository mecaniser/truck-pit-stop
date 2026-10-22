"""Real PostgreSQL: fan-out source preparation is all-or-nothing under held locks."""

import importlib.util
import os
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from scripts.motive_drivers import journal
from sqlalchemy.ext.asyncio import create_async_engine
from tests.test_motive_driver_worker import document

pytestmark = pytest.mark.skipif(
    not os.environ.get("MOTIVE_BATCH_TEST_DATABASE_URL"),
    reason="owned isolated PostgreSQL required",
)


@pytest.mark.asyncio
async def test_atomic_source_preparation_and_crash_rollback(monkeypatch):
    schema = "batch_" + uuid4().hex
    engine = create_async_engine(
        os.environ["MOTIVE_BATCH_TEST_DATABASE_URL"],
        connect_args={"server_settings": {"search_path": schema}},
    )
    assert engine.url.database.startswith("driver_journal_")
    async with engine.begin() as connection:
        await connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(sa.text("CREATE TABLE tenants (id uuid PRIMARY KEY)"))
        await connection.execute(
            sa.text("CREATE TABLE users (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
        )
        await connection.execute(
            sa.text(
                "CREATE TABLE customers (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, UNIQUE(tenant_id,id))"
            )
        )
        spec = importlib.util.spec_from_file_location(
            "journal_migration",
            Path(__file__).parents[1] / "alembic/versions/164_motive_driver_journal.py",
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        def migrate(sync_connection):
            from alembic.migration import MigrationContext
            from alembic.operations import Operations

            with Operations.context(MigrationContext.configure(sync_connection)):
                migration.upgrade()

        await connection.run_sync(migrate)
    identity = journal.Identity(uuid4(), uuid4(), uuid4(), "KT123", "Synthetic Fleet")
    prefix = "batch-" + str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            sa.text("INSERT INTO tenants(id) VALUES (:tenant)"),
            {"tenant": identity.tenant_id},
        )
        await connection.execute(
            sa.text("INSERT INTO users(id,tenant_id) VALUES (:actor,:tenant)"),
            {"actor": identity.actor_id, "tenant": identity.tenant_id},
        )
    try:
        async with AsyncExitStack() as stack:
            stores = []
            for ordinal in range(3):
                customer_id = uuid4()
                async with engine.begin() as connection:
                    await connection.execute(
                        sa.text(
                            "INSERT INTO customers(id,tenant_id) VALUES (:customer,:tenant)"
                        ),
                        {"customer": customer_id, "tenant": identity.tenant_id},
                    )
                stores.append(
                    await stack.enter_async_context(
                        journal.database_journal(
                            engine,
                            replace(identity, customer_id=customer_id),
                            prefix + str(ordinal),
                        )
                    )
                )
            saved = await journal.prepare_batch(stores, document(), commit=True)
            assert len(saved) == 3
            for store, durable in zip(stores, saved, strict=True):
                loaded = await durable.load()
                assert loaded["receipt"]["stage"] == "source_saved"
                assert loaded["receipt"]["expected_customer_id"] == str(
                    store.identity.customer_id
                )
                await store.connection.rollback()
            async with engine.connect() as observer:
                count = await observer.scalar(
                    sa.select(sa.func.count())
                    .select_from(journal.runs)
                    .where(journal.runs.c.worker_key.like(prefix + "%"))
                )
            assert count == 3
            # Duplicate primary keys fail during the multirow insert; no subset commits.
            duplicate = uuid4()
            monkeypatch.setattr(journal, "uuid4", lambda: duplicate)
            with pytest.raises(sa.exc.IntegrityError):
                await journal.prepare_batch(stores, document(), commit=True)
            async with engine.connect() as observer:
                count_after = await observer.scalar(
                    sa.select(sa.func.count())
                    .select_from(journal.runs)
                    .where(journal.runs.c.worker_key.like(prefix + "%"))
                )
            assert count_after == 3
            # Changing tenant/company or reusing fleet targets is rejected before writes.
            for other in [
                replace(identity, tenant_id=uuid4()),
                replace(identity, company_id="KT999"),
            ]:
                altered = journal.Journal(
                    stores[1].connection, other, prefix + "altered"
                )
                with pytest.raises(ValueError, match="identity mismatch"):
                    await journal.prepare_batch(
                        [stores[0], altered], document(), commit=True
                    )
    finally:
        await engine.dispose()
