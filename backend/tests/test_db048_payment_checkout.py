from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from app.api.v1.endpoints.invoice_settlements import read_invoice_payment_quote, settlement_summary
from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoicePaymentAttempt, InvoicePaymentLedgerEvent, InvoiceSettlementBackfillRun
from app.db.models.payment import Payment, PaymentMethod, PaymentStatus
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.models.user import UserRole
from app.services.invoice_settlement_service import provider_readiness, create_attempt, SettlementDomainError, _card_fee_allocation, invoice_money_snapshot
from tests.test_db048_cash import context


async def quote(db, ctx, rail="card", amount="100", version=1):
    return await read_invoice_payment_quote(ctx[3].id, rail, Decimal(amount), version, db, ctx[1])


@pytest.mark.asyncio
async def test_unrelated_missing_settlement_does_not_disable_target(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    from tests.test_db048_invoice_settlements import _add_eligible_invoice
    other = await _add_eligible_invoice(db_session, tenant=ctx[0], customer=ctx[2],
        reference_invoice=ctx[3], with_shadow_settlement=False)
    await db_session.flush()
    assert "invoice_settlement_backfill_stale_invoice" in (await provider_readiness(db_session, ctx[0])).reasons
    assert (await provider_readiness(db_session, ctx[0], invoice_id=ctx[3].id)).status == "ready"
    assert (await provider_readiness(db_session, ctx[0], invoice_id=other.id)).status != "ready"
    summary = await settlement_summary(db_session, ctx[4], ctx[0], audience="staff", current_user=ctx[1])
    assert summary.allowed_actions.rails == ["card", "zelle", "check", "ach"]
    assert summary.allowed_actions.confirm_cash
    assert summary.breakdown.principal_total == 100
    await quote(db_session, ctx)
    created = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("10"), rail="check", expected_settlement_version=1,
        idempotency_key="checkout-admission", source="staff", subject_type="staff", subject_id=ctx[1].id)
    assert created.attempt.principal_amount == 10
    assert other.accounting_policy == "standard"


@pytest.mark.asyncio
@pytest.mark.parametrize("rail", ["card", "zelle", "check", "ach", "cash"])
async def test_quote_is_read_only_and_matches_fee_allocator(db_session, monkeypatch, rail):
    ctx = await context(db_session, monkeypatch)
    before = (ctx[4].version, ctx[4].active_pending_principal, ctx[3].accounting_policy)
    result = await quote(db_session, ctx, rail)
    fee, tax = await _card_fee_allocation(db_session, ctx[4], Decimal("100")) if rail == "card" else (0, 0)
    assert result.total_amount == Decimal("100") + fee + tax
    assert result.card_fee_amount == fee and result.card_fee_tax_amount == tax
    assert before == (ctx[4].version, ctx[4].active_pending_principal, ctx[3].accounting_policy)
    for model in (InvoicePaymentAttempt, InvoicePaymentLedgerEvent, Payment, ProviderOutboxEvent):
        assert await db_session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["stale", "partial_cash", "over", "fraction", "zero", "foreign", "customer", "deleted_customer", "pending_zelle", "unverified", "hold", "unprojected_payment", "mismatched_settlement"])
async def test_quote_denials(db_session, monkeypatch, defect):
    ctx = await context(db_session, monkeypatch)
    rail, amount, version = "card", "100", 1
    if defect == "stale": version = 2
    if defect == "partial_cash": rail, amount = "cash", "10"
    if defect == "over": amount = "101"
    if defect == "fraction": amount = "1.001"
    if defect == "zero": amount = "0"
    if defect == "foreign": ctx[1].tenant_id = uuid4()
    if defect == "customer": ctx[1].role = UserRole.CUSTOMER
    if defect == "deleted_customer": ctx[2].deleted_at = datetime.now(timezone.utc)
    if defect == "pending_zelle": ctx[3].zelle_pending_submitted_at = datetime.now(timezone.utc)
    if defect == "unverified":
        for run in (await db_session.scalars(select(InvoiceSettlementBackfillRun))).all(): run.state = "failed"
    if defect == "hold": ctx[3].accounting_policy = "historical_export_hold"
    if defect == "mismatched_settlement": ctx[4].customer_id = uuid4()
    if defect == "unprojected_payment":
        db_session.add(Payment(tenant_id=ctx[0].id, invoice_id=ctx[3].id, payment_number="OLD-PAYMENT",
            amount=Decimal("10"), method=PaymentMethod.CHECK, status=PaymentStatus.COMPLETED,
            reference_number="CHECK-10", recorded_by_user_id=ctx[1].id))
    await db_session.flush()
    with pytest.raises(SettlementDomainError):
        await quote(db_session, ctx, rail, amount, version)
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)) == 0


@pytest.mark.asyncio
async def test_partial_card_quote_respects_existing_cumulative_allocation(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("33.33"), rail="card", expected_settlement_version=1,
        idempotency_key="prior-card", source="staff", subject_type="staff", subject_id=ctx[1].id)
    result = await quote(db_session, ctx, amount="33.33", version=ctx[4].version)
    fee, tax = await _card_fee_allocation(db_session, ctx[4], Decimal("33.33"))
    assert result.card_fee_amount == fee and result.card_fee_tax_amount == tax
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentAttempt)) == 1


@pytest.mark.asyncio
async def test_breakdown_retains_supplies_discount_and_separates_fee_tax(db_session, monkeypatch):
    ctx = await context(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    invoice.shop_supplies_amount = Decimal("6")
    invoice.discount_amount = Decimal("5")
    invoice.tax_amount = Decimal("8.99")
    invoice.total_amount = Decimal("112.99")
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(invoice)
    settlement.principal_total, settlement.max_card_fee, settlement.max_card_fee_tax = principal, fee, fee_tax
    settlement.sales_tax_rate_snapshot, settlement.card_fee_rate_snapshot = rate, fee_rate
    await db_session.flush()
    summary = await settlement_summary(db_session, settlement, ctx[0], audience="staff", current_user=ctx[1])
    breakdown = summary.breakdown
    assert breakdown.subtotal == 100 and breakdown.shop_supplies_amount == 6 and breakdown.discount_amount == 5
    assert breakdown.sales_tax_amount + fee_tax == invoice.tax_amount
    assert breakdown.subtotal + breakdown.shop_supplies_amount + breakdown.sales_tax_amount - breakdown.discount_amount == principal
    result = await quote(db_session, ctx, amount=str(principal))
    assert result.total_amount == invoice.total_amount
