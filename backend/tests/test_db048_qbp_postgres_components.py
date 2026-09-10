"""Optional real-PostgreSQL acceptance, restricted to the disposable verify DB."""
import os

import pytest
from sqlalchemy import update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.models.quickbooks_connection import QuickBooksConnection
from test_db048_qbp_explicit_components import test_explicit_fee_tax_components_and_replay as run_components
from test_db048_qbp_component_wrapper import test_daily_cdc_fetches_explicit_components_read_only as run_wrapper


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["preloaded", "fetch", "daily_wrapper"])
async def test_postgres_explicit_components(monkeypatch, scenario):
    raw = os.environ.get("DB048_VERIFY_DATABASE_URL")
    if not raw:
        pytest.skip("Dedicated disposable PostgreSQL verification database not configured")
    url = make_url(raw)
    assert url.database == "db048_fee_identity_verify_20260909"
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False,
                                        join_transaction_mode="create_savepoint") as session:
                    # Restored local sandbox connections must not join this
                    # synthetic test. Outer transaction restores every row.
                    await session.execute(update(QuickBooksConnection).values(status="disconnected"))
                    if scenario == "daily_wrapper":
                        await run_wrapper(session, monkeypatch)
                    else:
                        await run_components(session, monkeypatch, scenario == "fetch")
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
