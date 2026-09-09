"""The daily importer must work without callers supplying JournalEntry rows."""
from contextlib import asynccontextmanager

import pytest

from app.services import db048_accounting_reconciliation as reconciliation
from app.services import quickbooks_sync_service as sync
from test_db048_qbp_explicit_components import _explicit_fixture


@pytest.mark.asyncio
async def test_daily_cdc_fetches_explicit_components_read_only(db_session, monkeypatch):
    connection, records, _attempt, _link = await _explicit_fixture(db_session)
    db_session.add(connection)
    await db_session.flush()
    calls = []

    async def no_refresh(_connection):
        pass

    async def changes(_connection, **kwargs):
        return {}

    async def window(_connection, **kwargs):
        return {"Deposit": records["deposits"], "Purchase": records["purchases"]}

    async def account(_connection, value):
        return {"Clearing": "1", "Income": "2", "Tax": "3"}[value]

    async def request(_connection, method, path, **kwargs):
        assert method == "GET", "Settlement ingestion must never create accounting rows"
        calls.append(path)
        kind, identifier = path.split("/", 1)
        source = records["payments"] if kind == "payment" else records["journals"]
        assert kind in ("payment", "journalentry")
        return {"Payment" if kind == "payment" else "JournalEntry": next(
            row for row in source if str(row["Id"]) == identifier
        )}

    @asynccontextmanager
    async def factory():
        yield db_session

    monkeypatch.setattr(sync, "_refresh_if_needed", no_refresh)
    monkeypatch.setattr(sync, "change_data_capture", changes)
    monkeypatch.setattr(sync, "qbp_settlement_window", window)
    monkeypatch.setattr(reconciliation, "_resolve_qbo_account_reference", account)
    monkeypatch.setattr(reconciliation, "_request", request)
    first = await sync.backfill_quickbooks_cdc(session_factory=factory)
    assert first["failed"] == 0
    assert first["settlement_batches"] == 1
    assert first["settlement_manual"] == 0
    assert any(path.startswith("payment/") for path in calls)
    assert any(path.startswith("journalentry/") for path in calls)
    second = await sync.backfill_quickbooks_cdc(session_factory=factory)
    assert second["failed"] == 0
    assert second["settlement_batches"] == 1
    assert second["settlement_manual"] == 0
