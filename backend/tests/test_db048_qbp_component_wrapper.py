"""The daily importer must work without callers supplying JournalEntry rows."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.invoice_settlement import ProviderSettlementBatch
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
from app.services import db048_accounting_reconciliation as reconciliation
from app.services import quickbooks_sync_service as sync
from test_db048_qbp_explicit_components import _explicit_fixture
from test_db048_accounting_reconciliation import _tenant_with_qbp_configuration, _qbp_payout_attempt


@pytest.mark.asyncio
async def test_daily_cdc_fetches_explicit_components_read_only(db_session, monkeypatch):
    monkeypatch.setattr(sync.settings,"INVOICE_SPLIT_PAYMENTS_ENABLED",False)
    monkeypatch.setattr(sync.settings,"DB048_GROSS_QBO_ACCOUNTING_ENABLED",False)
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


@pytest.mark.asyncio
@pytest.mark.parametrize("failure",["window","import","unexpected"])
async def test_optional_import_failure_preserves_legacy_cdc_and_rolls_back(db_session,monkeypatch,failure):
    connection,_,attempt,_=await _explicit_fixture(db_session)
    db_session.add(connection)
    invoice=await db_session.get(Invoice,attempt.invoice_id)
    payment=await db_session.get(Payment,attempt.payment_id)
    invoice.quickbooks_sync_status="failed"
    invoice.quickbooks_sync_error="old"
    payment.quickbooks_reconciled_at=None
    payment.quickbooks_sync_error="old"
    payment.quickbooks_refund_receipt_id="refund-fixture"
    # Same provider IDs in a foreign tenant must not be reconciled by this CDC.
    foreign_tenant=await _tenant_with_qbp_configuration(db_session)
    foreign_attempt=await _qbp_payout_attempt(db_session,tenant=foreign_tenant,realm="realm-qbp",
        charge_id="foreign-charge",gross=Decimal("100"),qbo_payment_id=payment.quickbooks_payment_id)
    foreign_invoice=await db_session.get(Invoice,foreign_attempt.invoice_id)
    foreign_payment=await db_session.get(Payment,foreign_attempt.payment_id)
    foreign_invoice.quickbooks_sync_status="failed"
    foreign_payment.quickbooks_reconciled_at=None
    foreign_payment.quickbooks_sync_error="foreign-old"
    await db_session.commit()
    now=datetime(2026,9,10,12,tzinfo=timezone.utc)
    monkeypatch.setattr(sync,"_now",lambda:now)
    monkeypatch.setattr(sync.settings,"INVOICE_SPLIT_PAYMENTS_ENABLED",False)
    monkeypatch.setattr(sync.settings,"DB048_GROSS_QBO_ACCOUNTING_ENABLED",False)
    monkeypatch.setattr(sync,"_refresh_if_needed",AsyncMock())
    monkeypatch.setattr(sync,"change_data_capture",AsyncMock(return_value={
        "Invoice":[{"Id":invoice.quickbooks_invoice_id}],
        "Payment":[{"Id":payment.quickbooks_payment_id}],"RefundReceipt":[{"Id":"refund-fixture"}]}))
    window=AsyncMock(return_value={"Deposit":[],"Purchase":[]})
    if failure=="window":window.side_effect=sync.QuickBooksAccountingError("private provider content")
    monkeypatch.setattr(sync,"qbp_settlement_window",window)
    async def importer(db,**kwargs):
        db.add(ProviderSettlementBatch(tenant_id=connection.tenant_id,provider="quickbooks_payments",
            provider_account_id=connection.realm_id,provider_batch_id="partial-fixture",entry_manifest_hash="a"*64))
        await db.flush()
        if failure=="unexpected":raise RuntimeError("private provider content")
        raise reconciliation.DB048ReconciliationError("private provider content")
    monkeypatch.setattr(sync,"reconcile_qbp_native_settlements",importer)
    @asynccontextmanager
    async def factory():yield db_session
    result=await sync.backfill_quickbooks_cdc(session_factory=factory)
    assert result["entities"]==3 and result["failed"]==result["settlement_failed"]==1
    assert result["settlement_batches"]==0
    assert invoice.quickbooks_sync_status=="synced" and invoice.quickbooks_sync_error is None
    assert payment.quickbooks_reconciled_at==now and payment.quickbooks_sync_error is None
    assert connection.last_cdc_at==now
    assert "private" not in connection.last_cdc_error
    assert sync._settlement_retry_from(connection.last_cdc_error,connection.realm_id)==(now-timedelta(days=7)).date()
    assert foreign_invoice.quickbooks_sync_status=="failed"
    assert foreign_payment.quickbooks_reconciled_at is None and foreign_payment.quickbooks_sync_error=="foreign-old"
    assert await db_session.scalar(select(func.count()).select_from(ProviderSettlementBatch))==0


@pytest.mark.asyncio
@pytest.mark.parametrize("scope",["no_history","foreign_tenant","wrong_realm"])
async def test_no_relevant_history_skips_new_window(db_session,monkeypatch,scope):
    if scope!="no_history":
        connection,_,_,_=await _explicit_fixture(db_session)
    if scope in {"no_history","foreign_tenant"}:
        tenant=Tenant(name="Legacy",slug=uuid4().hex)
        db_session.add(tenant)
        await db_session.flush()
        connection=QuickBooksConnection(tenant_id=tenant.id,realm_id="realm-qbp",status="connected")
    else:
        connection.realm_id="different-realm"
    connection.last_cdc_error=sync._settlement_retry_error(connection.realm_id,datetime(2026,8,1).date(),"settlement")
    original_error=connection.last_cdc_error
    db_session.add(connection)
    await db_session.commit()
    monkeypatch.setattr(sync,"_refresh_if_needed",AsyncMock())
    monkeypatch.setattr(sync,"change_data_capture",AsyncMock(return_value={}))
    window=AsyncMock(side_effect=AssertionError("Unexpected optional provider read"))
    importer=AsyncMock(side_effect=AssertionError("Unexpected importer"))
    monkeypatch.setattr(sync,"qbp_settlement_window",window)
    monkeypatch.setattr(sync,"reconcile_qbp_native_settlements",importer)
    @asynccontextmanager
    async def factory():yield db_session
    result=await sync.backfill_quickbooks_cdc(session_factory=factory)
    assert result["failed"]==result["settlement_failed"]==0
    assert connection.last_cdc_at is not None and connection.last_cdc_error==original_error
    window.assert_not_awaited();importer.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_retry_cursor_survives_long_outage_legacy_failure_and_clears_on_success(db_session,monkeypatch):
    connection,_,_,_=await _explicit_fixture(db_session)
    first_day=datetime(2026,9,10,12,tzinfo=timezone.utc)
    clock=[first_day]
    connection.last_cdc_at=first_day-timedelta(days=20)
    db_session.add(connection)
    await db_session.commit()
    monkeypatch.setattr(sync,"_now",lambda:clock[0])
    monkeypatch.setattr(sync,"_refresh_if_needed",AsyncMock())
    changes=AsyncMock(return_value={})
    window=AsyncMock(side_effect=sync.QuickBooksAccountingError("private"))
    importer=AsyncMock(return_value={"batches":0,"manual":0,"deferred":0})
    monkeypatch.setattr(sync,"change_data_capture",changes)
    monkeypatch.setattr(sync,"qbp_settlement_window",window)
    monkeypatch.setattr(sync,"reconcile_qbp_native_settlements",importer)
    @asynccontextmanager
    async def factory():yield db_session
    await sync.backfill_quickbooks_cdc(session_factory=factory)
    earliest=(first_day-timedelta(days=20)).date()
    assert window.call_args.kwargs["date_from"]==earliest
    clock[0]+=timedelta(days=15)
    await sync.backfill_quickbooks_cdc(session_factory=factory)
    assert window.call_args.kwargs["date_from"]==earliest
    changes.side_effect=sync.QuickBooksAccountingError("private")
    legacy_timestamp=connection.last_cdc_at
    failed=await sync.backfill_quickbooks_cdc(session_factory=factory)
    assert failed["failed"]==1 and failed["settlement_failed"]==0
    assert connection.last_cdc_at==legacy_timestamp
    assert '"failure":"legacy"' in connection.last_cdc_error
    assert sync._settlement_retry_from(connection.last_cdc_error,connection.realm_id)==earliest
    changes.side_effect=None
    window.side_effect=None
    window.return_value={"Deposit":[],"Purchase":[]}
    done=await sync.backfill_quickbooks_cdc(session_factory=factory)
    assert done["failed"]==0 and connection.last_cdc_error is None
    assert window.call_args.kwargs["date_from"]==earliest
    importer.assert_awaited_once()


@pytest.mark.parametrize("marker",["arbitrary provider content","DB048_SETTLEMENT_RETRY_V1:bad",
    'DB048_SETTLEMENT_RETRY_V1:{"realm":"foreign","retry_from":"2026-08-01","failure":"settlement"}',
    'DB048_SETTLEMENT_RETRY_V1:{"realm":"realm","retry_from":"9999-12-31","failure":"settlement"}',
    'DB048_SETTLEMENT_RETRY_V1:{"realm":"realm","retry_from":"1969-01-01","failure":"settlement"}'])
def test_retry_marker_rejects_untrusted_or_wrong_realm_cursor(marker):
    assert sync._settlement_retry_from(marker,"realm") is None
