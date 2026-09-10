from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.services import invoice_cash_service as cash
from app.services.invoice_settlement_service import get_or_create_settlement, SettlementDomainError, create_attempt, create_refund
from app.db.models.invoice_settlement import InvoicePaymentAttempt, InvoicePaymentLedgerEvent, PaymentAccountingLink
from app.db.models.payment import Payment
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.invoice import InvoiceStatus
from app.schemas.invoice_settlement import CashConfirmationCreate
from tests.test_db048_invoice_settlements import _financial_context


async def context(db, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db, monkeypatch)
    settlement = await get_or_create_settlement(db, invoice=invoice, tenant=tenant, customer_id=customer.id)
    await db.flush()
    return tenant, owner, customer, invoice, settlement


async def pay(db, ctx, **kwargs):
    tenant, owner, customer, invoice, settlement = ctx
    return await cash.confirm_full_cash(db, invoice=invoice, tenant=tenant, customer_id=customer.id,
        actor=owner, expected_settlement_version=kwargs.pop("version", 1),
        idempotency_key=kwargs.pop("key", "cash-key"), **kwargs)


@pytest.mark.asyncio
async def test_cash_full_local_receipt_and_replay(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    tenant, owner, customer, invoice, settlement = ctx
    original_total = invoice.total_amount
    payment_id, result = await pay(db_session, ctx)
    await db_session.commit()
    again, _ = await pay(db_session, ctx)
    assert again == payment_id
    assert result.confirmed_principal == Decimal("100.00")
    assert result.accounting_sync_status == "not_applicable_local_cash"
    assert invoice.accounting_policy == "local_cash_only"
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.tax_amount == Decimal("0.00") and invoice.total_amount == original_total
    attempt = await db_session.scalar(select(InvoicePaymentAttempt).where(InvoicePaymentAttempt.payment_id == payment_id))
    assert attempt.rail == "cash" and attempt.card_fee_amount == 0 and attempt.processor_fee_amount == 0
    assert await db_session.scalar(select(func.count()).select_from(PaymentAccountingLink)) == 0
    assert await db_session.scalar(select(func.count()).select_from(ProviderOutboxEvent)) == 0
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)) == 1
    with pytest.raises(SettlementDomainError, match="another payment"):
        await pay(db_session, ctx, note="different")
    with pytest.raises(SettlementDomainError, match="refunds"):
        await create_refund(db_session, attempt=attempt, tenant_id=tenant.id, actor=owner,
            amount=Decimal("1"), reason="test", idempotency_key="refund")


@pytest.mark.asyncio
@pytest.mark.parametrize("state,attempts,allowed", [("pending",0,True),("processing",1,False),("dead",5,False),("succeeded",1,False)])
async def test_export_history_safety(db_session, monkeypatch, state, attempts, allowed):
    ctx = await context(db_session, monkeypatch)
    invoice = ctx[3]
    event = ProviderOutboxEvent(tenant_id=invoice.tenant_id, aggregate_id=invoice.id,
        aggregate_type="quickbooks_invoice", event_type="quickbooks.invoice.sync.v1",
        status=state, attempt_count=attempts, available_at=datetime.now(timezone.utc),
        idempotency_key="invoice-export", last_error="historical failure")
    db_session.add(event)
    await db_session.flush()
    if allowed:
        await pay(db_session, ctx)
        assert event.status == "suppressed" and event.last_error == "historical failure"
        assert event.payload["suppression_reason"] == "not_applicable_local_cash"
    else:
        with pytest.raises(SettlementDomainError):
            await pay(db_session, ctx)
        assert invoice.accounting_policy == "standard"


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["exported", "pending", "confirmed", "stale", "wrong_tenant", "voided", "legacy_zelle"])
async def test_cash_negative_cases(db_session, monkeypatch, defect):
    ctx = await context(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    if defect == "exported": invoice.quickbooks_invoice_id = "123"
    if defect == "pending": settlement.active_pending_principal = Decimal("1")
    if defect == "confirmed": settlement.confirmed_principal = Decimal("1")
    if defect == "stale": settlement.version = 2
    if defect == "wrong_tenant": ctx[1].tenant_id = uuid4()
    if defect == "voided": invoice.voided_at = datetime.now(timezone.utc)
    if defect == "legacy_zelle": invoice.zelle_pending_submitted_at = datetime.now(timezone.utc)
    await db_session.flush()
    with pytest.raises(SettlementDomainError):
        await pay(db_session, ctx)
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0


def test_cash_request_forbids_partial_amount_and_policy():
    from pydantic import ValidationError
    for field in ("amount", "tenant_id", "accounting_policy"):
        with pytest.raises(ValidationError):
            CashConfirmationCreate(expected_settlement_version=1, **{field: "1"})


@pytest.mark.asyncio
async def test_cash_excludes_enqueue_and_all_invoice_writers(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    await pay(db_session, ctx)
    from app.services.quickbooks_sync_service import enqueue_quickbooks_invoice_sync
    from app.services.quickbooks_accounting_service import sync_invoice, QuickBooksAccountingError
    from app.services.db048_accounting_reconciliation import sync_db048_principal_invoice
    assert await enqueue_quickbooks_invoice_sync(db_session, invoice=ctx[3]) is None
    with pytest.raises(QuickBooksAccountingError, match="Local cash"):
        await sync_invoice(None, ctx[3], ctx[2])
    with pytest.raises(QuickBooksAccountingError, match="Local cash"):
        await sync_db048_principal_invoice(connection=None, invoice=ctx[3], customer=ctx[2], settlement=ctx[4])


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_result", ["absent", "match", "malformed", "unavailable", "realm_changed"])
async def test_attempted_export_requires_exact_remote_absence(db_session, monkeypatch, provider_result):
    from app.db.models.quickbooks_connection import QuickBooksConnection
    from app.services import quickbooks_accounting_service as accounting
    from app.core.config import settings
    ctx = await context(db_session, monkeypatch)
    invoice = ctx[3]
    connection = await db_session.scalar(select(QuickBooksConnection).where(QuickBooksConnection.tenant_id == invoice.tenant_id))
    event = ProviderOutboxEvent(tenant_id=invoice.tenant_id, aggregate_id=invoice.id,
        aggregate_type="quickbooks_invoice", event_type="quickbooks.invoice.sync.v1",
        status="dead", attempt_count=1, available_at=datetime.now(timezone.utc),
        idempotency_key="invoice-export", last_response_code=401,
        payload={"cash_export_ambiguous": False, "cash_export_realm": connection.realm_id,
                 "cash_export_environment": settings.QUICKBOOKS_ACCOUNTING_ENVIRONMENT})
    db_session.add(event)
    await db_session.flush()
    requests = []
    async def request(_connection, method, resource, **kwargs):
        requests.append((method, resource))
        if provider_result == "unavailable": raise RuntimeError("provider unavailable")
        if provider_result == "malformed": return {}
        if provider_result == "match": return {"QueryResponse": {"Invoice": [{"Id": "123"}]}}
        return {"QueryResponse": {}}
    monkeypatch.setattr(accounting, "_request", request)
    if provider_result == "realm_changed": connection.realm_id = "other-realm"
    if provider_result == "absent":
        await pay(db_session, ctx)
        assert event.status == "suppressed"
    else:
        with pytest.raises(SettlementDomainError): await pay(db_session, ctx)
        assert invoice.accounting_policy == "standard"
    assert all(method == "GET" for method, _ in requests)


@pytest.mark.asyncio
async def test_manual_sync_is_durable_not_direct(db_session, monkeypatch):
    from app.api.v1.endpoints import quickbooks as endpoint
    ctx = await context(db_session, monkeypatch)
    async def accounting_context(_db, _id): return ctx[3], ctx[3].repair_order, ctx[2]
    async def unexpected(*args, **kwargs): raise AssertionError("Manual sync must never dispatch")
    monkeypatch.setattr(endpoint, "_invoice_accounting_context", accounting_context)
    monkeypatch.setattr(endpoint, "sync_invoice", unexpected)
    monkeypatch.setattr(endpoint, "sync_db048_principal_invoice", unexpected)
    result = await endpoint.sync_quickbooks_invoice_now(ctx[3].id, db_session, ctx[1])
    assert result.status == "awaiting_payment"
    assert await db_session.scalar(select(func.count()).select_from(ProviderOutboxEvent)) == 0


@pytest.mark.asyncio
async def test_cash_endpoint_denies_customer_and_cross_tenant(db_session, monkeypatch):
    from app.api.v1.endpoints.invoice_settlements import confirm_invoice_cash
    from app.db.models.user import UserRole
    from types import SimpleNamespace
    ctx = await context(db_session, monkeypatch)
    customer_actor = SimpleNamespace(role=UserRole.CUSTOMER, tenant_id=ctx[0].id, id=uuid4())
    with pytest.raises(SettlementDomainError):
        await confirm_invoice_cash(ctx[3].id, CashConfirmationCreate(expected_settlement_version=1),
            "key", db_session, customer_actor)
    ctx[1].tenant_id = uuid4()
    with pytest.raises(SettlementDomainError):
        await confirm_invoice_cash(ctx[3].id, CashConfirmationCreate(expected_settlement_version=1),
            "key", db_session, ctx[1])


@pytest.mark.asyncio
async def test_cash_keeps_service_tax_excludes_unearned_card_fee_and_its_tax(db_session, monkeypatch):
    tenant, owner, customer, invoice = await _financial_context(db_session, monkeypatch)
    invoice.tax_amount = Decimal("8.24")
    invoice.total_amount = Decimal("111.24")
    settlement = await get_or_create_settlement(db_session, invoice=invoice, tenant=tenant, customer_id=customer.id)
    await db_session.flush()
    payment_id, _ = await pay(db_session, (tenant, owner, customer, invoice, settlement))
    payment = await db_session.get(Payment, payment_id)
    assert payment.amount == Decimal("108.00")  # service100 + existing service tax8
    assert invoice.tax_amount == Decimal("8.24") and invoice.total_amount == Decimal("111.24")


@pytest.mark.asyncio
async def test_cash_native_receipt_is_not_reconstructed_by_backfill(db_session, monkeypatch):
    from app.services.invoice_settlement_backfill import _classify_existing_payment_links
    ctx = await context(db_session, monkeypatch)
    payment_id, _ = await pay(db_session, ctx)
    payment = await db_session.get(Payment, payment_id)
    linked, error = await _classify_existing_payment_links(db_session, tenant_id=ctx[0].id,
        invoices_by_id={ctx[3].id: ctx[3]}, payments=[payment], settlements_by_invoice={ctx[3].id:ctx[4]})
    assert error is None and payment_id in linked


@pytest.mark.asyncio
@pytest.mark.parametrize("with_event", [True, False])
async def test_realm_reset_cannot_erase_prior_export_evidence(db_session, monkeypatch, with_event):
    from app.api.v1.endpoints.quickbooks import _reset_accounting_links_for_realm_change
    ctx = await context(db_session, monkeypatch)
    invoice = ctx[3]
    invoice.quickbooks_invoice_id = "prior-company-invoice"
    invoice.quickbooks_synced_at = datetime.now(timezone.utc)
    if with_event:
        db_session.add(ProviderOutboxEvent(tenant_id=invoice.tenant_id, aggregate_id=invoice.id,
            aggregate_type="quickbooks_invoice", event_type="quickbooks.invoice.sync.v1",
            status="dead", attempt_count=5, available_at=datetime.now(timezone.utc),
            idempotency_key="old-export", payload={"cash_export_ambiguous": True}))
    await db_session.flush()
    await _reset_accounting_links_for_realm_change(db_session, tenant_id=ctx[0].id, now=datetime.now(timezone.utc))
    await db_session.flush()
    assert invoice.cash_export_review_required
    with pytest.raises(SettlementDomainError, match="company changes"):
        await pay(db_session, ctx)
    assert invoice.status != InvoiceStatus.PAID


@pytest.mark.asyncio
async def test_realm_reset_preserves_local_cash_suppression(db_session, monkeypatch):
    from app.api.v1.endpoints.quickbooks import _reset_accounting_links_for_realm_change
    ctx = await context(db_session, monkeypatch)
    invoice = ctx[3]
    event = ProviderOutboxEvent(tenant_id=invoice.tenant_id, aggregate_id=invoice.id,
        aggregate_type="quickbooks_invoice", event_type="quickbooks.invoice.sync.v1",
        status="pending", attempt_count=0, available_at=datetime.now(timezone.utc), idempotency_key="export")
    db_session.add(event)
    await db_session.flush()
    await pay(db_session, ctx)
    await _reset_accounting_links_for_realm_change(db_session, tenant_id=ctx[0].id, now=datetime.now(timezone.utc))
    await db_session.refresh(invoice, ["quickbooks_sync_status", "accounting_policy"])
    await db_session.refresh(event)
    assert invoice.quickbooks_sync_status == "not_applicable_local_cash"
    assert invoice.accounting_policy == "local_cash_only" and event.status == "suppressed"


@pytest.mark.asyncio
@pytest.mark.parametrize("ambiguous", [False, True])
async def test_proven_no_dispatch_does_not_need_provider_but_never_erases_ambiguity(db_session, monkeypatch, ambiguous):
    from app.services import quickbooks_accounting_service as accounting
    ctx = await context(db_session, monkeypatch)
    invoice = ctx[3]
    event = ProviderOutboxEvent(tenant_id=invoice.tenant_id, aggregate_id=invoice.id,
        aggregate_type="quickbooks_invoice", event_type="quickbooks.invoice.sync.v1",
        status="pending", attempt_count=5, available_at=datetime.now(timezone.utc), idempotency_key="export",
        payload={"cash_no_dispatch": True, "cash_export_ambiguous": ambiguous})
    db_session.add(event)
    await db_session.flush()
    async def unexpected(*args, **kwargs): raise AssertionError("No dispatch history needs no provider call")
    monkeypatch.setattr(accounting, "_request", unexpected)
    if ambiguous:
        with pytest.raises(SettlementDomainError): await pay(db_session, ctx)
    else:
        await pay(db_session, ctx)
        assert invoice.status == InvoiceStatus.PAID and event.status == "suppressed"
