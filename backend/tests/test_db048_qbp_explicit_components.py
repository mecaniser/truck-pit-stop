"""Explicit composition contract fixtures, not evidence of Intuit adoption."""
from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from app.db.models.invoice import Invoice
from app.db.models.payment import Payment
from app.db.models.invoice_settlement import PaymentAccountingLink, ProviderSettlementBatch, ProviderSettlementEntry, TenantPaymentProviderConfiguration
from app.db.models.quickbooks_connection import QuickBooksConnection
from app.db.models.tenant import Tenant
from app.db.models.user import User, UserRole
from app.services import db048_accounting_reconciliation as service
from test_db048_accounting_reconciliation import _tenant_with_qbp_configuration, _qbp_payout_attempt


async def _explicit_fixture(db_session, *, foreign_link=False, link_realm="realm-qbp"):
    tenant = Tenant(name="Explicit QBP", slug=f"explicit-{uuid4().hex}")
    db_session.add(tenant)
    await db_session.flush()
    owner = User(tenant_id=tenant.id, email=f"explicit-{uuid4().hex}@example.com", first_name="Test", last_name="Owner", role=UserRole.GARAGE_OWNER)
    db_session.add(owner)
    await db_session.flush()
    db_session.add(TenantPaymentProviderConfiguration(
        tenant_id=tenant.id, version=1, selected_provider="quickbooks_payments", readiness_state="ready",
        is_active=True, actor_user_id=owner.id, actor_name_snapshot="Owner", provider_account_snapshot="realm-qbp",
        qbo_realm_snapshot="realm-qbp", writer_strategy="dieselbridge", idempotency_key=uuid4().hex,
        request_hash="a" * 64, qbp_clearing_account="Clearing", card_fee_income_account="Income",
        sales_tax_liability_account="Tax", processor_fee_expense_account="Processor Fees", checking_account="bank-qbp"))
    await db_session.flush()
    attempt = await _qbp_payout_attempt(db_session, tenant=tenant, realm="realm-qbp", charge_id="charge-explicit",
        gross=Decimal("103.15"), customer_fee=Decimal("3.00"), customer_fee_tax=Decimal("0.15"), qbo_payment_id="payment-explicit")
    payment = await db_session.get(Payment, attempt.payment_id)
    invoice = await db_session.get(Invoice, attempt.invoice_id)
    mappings = {"qbp_clearing_account": "Clearing", "card_fee_income_account": "Income", "sales_tax_liability_account": "Tax"}
    link_tenant = await _tenant_with_qbp_configuration(db_session) if foreign_link else tenant
    link = PaymentAccountingLink(tenant_id=link_tenant.id, attempt_id=attempt.id, invoice_id=invoice.id,
        financial_object_type="payment", financial_object_id=attempt.id, operation_version=1,
        owning_writer="dieselbridge", account_mapping_snapshot=mappings, qbo_realm_snapshot=link_realm,
        provider_fee_journal_id="journal-explicit")
    db_session.add(link)
    await db_session.flush()
    p = service.db048_qbo_payment_payload(payment=payment, invoice=invoice, attempt=attempt,
        qbo_customer_id="qbo-customer-qbp", qbo_invoice_id="qbo-invoice-qbp",
        principal_amount=Decimal("100"), received_principal_amount=Decimal("100"), deposit_account="1")
    p.update(Id="payment-explicit", TxnDate="2026-09-03",
             CreditCardPayment={"CreditChargeResponse": {"CCTransId": "charge-explicit"}})
    _, j = service.db048_qbo_adjustment_payloads(attempt=attempt, payment=payment, mappings=mappings)[0]
    j.update(Id="journal-explicit", TxnDate="2026-09-03")
    j["PrivateNote"] += f"; attempt={attempt.id}"
    for index, line in enumerate(j["Line"], 1):
        line["Id"] = str(index)
        line["JournalEntryLineDetail"]["AccountRef"]["value"] = str(index)
    d = {"Id": "deposit-explicit", "TotalAmt": 103.15, "TxnDate": "2026-09-03",
         "DepositToAccountRef": {"value": "35", "name": "bank-qbp"},
         "Line": [{"Amount": 100, "LinkedTxn": [{"TxnType": "Payment", "TxnId": p["Id"], "TxnLineId": "0"}]},
                  {"Amount": 3.15, "LinkedTxn": [{"TxnType": "JournalEntry", "TxnId": j["Id"], "TxnLineId": "1"}]}]}
    f = {"Id": "fee-explicit", "TotalAmt": 3.08, "TxnDate": "2026-09-03",
         "AccountRef": {"value": "35", "name": "bank-qbp"},
         "EntityRef": {"value": "vendor", "name": "QuickBooks Payments"},
         "PrivateNote": "System-recorded fee for QuickBooks Payments",
         "Line": [{"AccountBasedExpenseLineDetail": {"AccountRef": {"value": "9", "name": "Processor Fees"}}}]}
    connection = QuickBooksConnection(tenant_id=tenant.id, realm_id="realm-qbp", status="connected")
    return connection, dict(deposits=[d], payments=[p], purchases=[f], journals=[j]), attempt, link


def _read_only(monkeypatch, journal):
    async def resolve(connection, name):
        return {"Clearing": "1", "Income": "2", "Tax": "3"}[name]
    async def request(connection, method, path, **kwargs):
        assert method == "GET", "Importer must never write QuickBooks"
        assert path == "journalentry/journal-explicit"
        return {"JournalEntry": journal}
    monkeypatch.setattr(service, "_resolve_qbo_account_reference", resolve)
    monkeypatch.setattr(service, "_request", request)


@pytest.mark.asyncio
@pytest.mark.parametrize("fetch", [False, True])
async def test_explicit_fee_tax_components_and_replay(db_session, monkeypatch, fetch):
    connection, kwargs, attempt, link = await _explicit_fixture(db_session)
    _read_only(monkeypatch, kwargs["journals"][0])
    if fetch: kwargs.pop("journals")
    first = await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs)
    await db_session.flush()
    assert first["matched"] == 1
    if not fetch:
        kwargs["journals"][0]["SyncToken"] = "9"
        kwargs["journals"][0]["MetaData"] = {"LastUpdatedTime": "2026-09-04T12:00:00Z"}
    assert await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs) == first
    entries = list((await db_session.scalars(select(ProviderSettlementEntry))).all())
    assert len(entries) == 3
    assert next(e for e in entries if e.entry_type == "qbp_customer_fee_journal").amount == Decimal("3.15")
    batch = await db_session.scalar(select(ProviderSettlementBatch))
    assert (batch.gross_receipts, batch.customer_card_fees, batch.card_fee_tax, batch.net_payout) == (
        Decimal("100"), Decimal("3"), Decimal("0.15"), Decimal("100.07"))


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing_id", "wrong_id", "account", "direction", "amount", "tenant", "realm", "duplicate", "unknown", "line_id", "gross", "refunded", "legacy", "malformed"])
async def test_explicit_components_fail_closed(db_session, monkeypatch, fault):
    connection, kwargs, attempt, link = await _explicit_fixture(db_session,
        foreign_link=fault == "tenant", link_realm="foreign" if fault == "realm" else "realm-qbp")
    journal, deposit = kwargs["journals"][0], kwargs["deposits"][0]
    _read_only(monkeypatch, journal)
    if fault == "missing_id": link.provider_fee_journal_id = None
    if fault == "wrong_id": link.provider_fee_journal_id = "wrong"
    if fault == "account": journal["Line"][0]["JournalEntryLineDetail"]["AccountRef"]["value"] = "wrong"
    if fault == "direction": journal["Line"][0]["JournalEntryLineDetail"]["PostingType"] = "Credit"
    if fault == "amount": journal["Line"][0]["Amount"] = 3
    if fault == "duplicate": deposit["Line"].append(deepcopy(deposit["Line"][1]))
    if fault == "unknown": deposit["Line"].append({"Amount": 0, "LinkedTxn": [{"TxnType": "Other", "TxnId": "x"}]})
    if fault == "line_id": deposit["Line"][1]["LinkedTxn"][0]["TxnLineId"] = "2"
    if fault == "gross": kwargs["payments"][0]["TotalAmt"] = 103.15
    if fault == "refunded": attempt.state = "refunded"
    if fault == "legacy": journal["PrivateNote"] = "DB-048 customer card fee and fee tax"
    if fault == "malformed":
        journal["Line"] = [None]
        kwargs.pop("journals")
    await db_session.flush()
    result = await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs)
    assert result["manual"] == 1 and result["matched"] == 0


@pytest.mark.asyncio
async def test_component_cross_batch_reuse_and_manual_manifest(db_session, monkeypatch):
    connection, kwargs, _, _ = await _explicit_fixture(db_session)
    _read_only(monkeypatch, kwargs["journals"][0])
    assert (await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs))["matched"] == 1
    await db_session.flush()
    kwargs["deposits"][0]["Id"] = "second-deposit"
    assert (await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs))["manual"] == 1
    await db_session.flush()
    assert len(list((await db_session.scalars(select(ProviderSettlementEntry))).all())) == 3


@pytest.mark.asyncio
async def test_manual_manifest_never_silently_upgrades(db_session, monkeypatch):
    connection, kwargs, _, link = await _explicit_fixture(db_session)
    _read_only(monkeypatch, kwargs["journals"][0])
    link.provider_fee_journal_id = None
    await db_session.flush()
    assert (await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs))["manual"] == 1
    await db_session.flush()
    link.provider_fee_journal_id = "journal-explicit"
    await db_session.flush()
    with pytest.raises(service.DB048ReconciliationError, match="immutable manifest"):
        await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs)


@pytest.mark.asyncio
async def test_replay_rejects_new_zero_unknown_component(db_session, monkeypatch):
    connection, kwargs, _, _ = await _explicit_fixture(db_session)
    _read_only(monkeypatch, kwargs["journals"][0])
    assert (await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs))["matched"] == 1
    await db_session.flush()
    kwargs["deposits"][0]["Line"].append({"Amount": 0, "LinkedTxn": [{"TxnType": "Other", "TxnId": "unknown"}]})
    with pytest.raises(service.DB048ReconciliationError, match="immutable manifest"):
        await service.reconcile_qbp_native_settlements(db_session, connection=connection, **kwargs)
