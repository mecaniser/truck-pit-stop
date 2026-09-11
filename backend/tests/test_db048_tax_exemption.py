from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from pydantic import ValidationError
from tests.test_db048_cash import context
from app.services import invoice_tax_exemption as tax
from app.services.invoice_cash_service import cash_eligibility
from app.services.invoice_settlement_service import invoice_money_snapshot, SettlementDomainError
from app.db.models.invoice import InvoiceStatus
from app.db.models.invoice_settlement import InvoicePaymentLedgerEvent
from app.db.models.payment import Payment
from app.db.models.user import UserRole
from app.schemas.invoice_settlement import InvoiceTaxExemptionCreate


async def setup(db, monkeypatch):
    ctx = await context(db, monkeypatch)
    inv, settlement = ctx[3:]
    inv.shop_supplies_amount = Decimal("6.00")
    inv.tax_amount = Decimal("8.99")
    inv.total_amount = Decimal("117.99")
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(inv)
    settlement.principal_total, settlement.max_card_fee, settlement.max_card_fee_tax = principal, fee, fee_tax
    settlement.sales_tax_rate_snapshot, settlement.card_fee_rate_snapshot = rate, fee_rate
    await db.flush()
    return ctx


async def apply(db, ctx, **kw):
    body = InvoiceTaxExemptionCreate(expected_settlement_version=kw.pop("version", 1),
        reason=kw.pop("reason", "Owner validated exemption"), support_reference="Certificate ABC")
    return await tax.apply_exemption(db, invoice=ctx[3], tenant=ctx[0], actor=ctx[1], body=body,
        idempotency_key=kw.pop("key", "tax-exemption-test-key"))


@pytest.mark.asyncio
async def test_tax_only_cash_and_replay(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    await apply(db_session, ctx)
    assert invoice.total_amount == Decimal("109.00")
    assert invoice.tax_amount == 0 and invoice.shop_supplies_amount == 6 and invoice.service_fee_amount == 3
    assert settlement.principal_total == 106 and settlement.max_card_fee_tax == 0 and settlement.version == 2
    assert invoice.status == InvoiceStatus.SENT and settlement.state == "unpaid"
    assert invoice.tax_exemption["before"]["tax_amount"] == "8.99"
    assert (await cash_eligibility(db_session, invoice, settlement))[0] is None
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)) == 0
    audit = dict(invoice.tax_exemption)
    await apply(db_session, ctx)
    assert invoice.tax_exemption == audit and settlement.version == 2
    with pytest.raises(SettlementDomainError):
        await apply(db_session, ctx, reason="Different reason")
    with pytest.raises(SettlementDomainError):
        await apply(db_session, ctx, key="another-tax-exemption-key", version=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["paid", "cancelled", "internal", "pending", "qbo", "stale", "foreign", "receptionist", "inconsistent", "zelle", "no_tax", "deleted_tenant", "deleted_customer", "foreign_customer", "deleted_order", "cancelled_order"])
async def test_denials(db_session, monkeypatch, defect):
    from datetime import datetime, timezone
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    if defect == "paid": invoice.status = InvoiceStatus.PAID
    if defect == "cancelled": invoice.status = InvoiceStatus.CANCELLED
    if defect == "internal": invoice.is_internal = True
    if defect == "pending": settlement.active_pending_principal = Decimal("1")
    if defect == "qbo": invoice.quickbooks_invoice_id = "remote"
    if defect == "stale": settlement.version = 2
    if defect == "foreign": ctx[1].tenant_id = uuid4()
    if defect == "receptionist": ctx[1].role = UserRole.RECEPTIONIST
    if defect == "inconsistent": invoice.total_amount += 1
    if defect == "zelle": invoice.zelle_pending_submitted_at = datetime.now(timezone.utc)
    if defect == "no_tax": invoice.tax_amount = 0
    if defect == "deleted_tenant": ctx[0].deleted_at = datetime.now(timezone.utc)
    if defect == "deleted_customer": ctx[2].deleted_at = datetime.now(timezone.utc)
    if defect == "foreign_customer": ctx[2].tenant_id = uuid4()
    if defect in {"deleted_order", "cancelled_order"}:
        from app.db.models.repair_order import RepairOrder, RepairOrderStatus
        order = await db_session.get(RepairOrder, invoice.repair_order_id)
        if defect == "deleted_order": order.deleted_at = datetime.now(timezone.utc)
        else: order.status = RepairOrderStatus.CANCELLED
    await db_session.flush()
    with pytest.raises(SettlementDomainError):
        await apply(db_session, ctx)
    assert invoice.tax_exemption is None


@pytest.mark.asyncio
async def test_summary_redaction_and_preview(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    preview = await tax.summary(db_session, ctx[3], ctx[4], ctx[0], ctx[1], audience="staff")
    assert preview.can_apply and preview.exempt_principal_total == 106
    await apply(db_session, ctx)
    for audience in ("guest", "customer"):
        result = await tax.summary(db_session, ctx[3], ctx[4], ctx[0], ctx[1], audience=audience)
        assert result.applied and not result.can_apply
        assert result.reason is None and result.support_reference is None


@pytest.mark.parametrize("extra", [{"reason": "ab"}, {"support_reference": "x"*256}, {"amount": "1"}, {"reason": "x"*501}, {"support_reference": 123}, {"expected_settlement_version": 0}])
def test_request_validation(extra):
    fields = {"expected_settlement_version": 1, "reason": "Valid reason", "support_reference": "Reference", **extra}
    with pytest.raises(ValidationError):
        InvoiceTaxExemptionCreate(**fields)


@pytest.mark.parametrize("fields", [{}, {"support_reference": None}, {"support_reference": ""},
    {"support_reference": "  \t "}, {"reason": " "}, {"reason": None}])
def test_optional_tax_reference_normalization(fields):
    body = InvoiceTaxExemptionCreate(expected_settlement_version=1, **fields)
    assert body.model_dump() == {"expected_settlement_version": 1, "reason": None, "support_reference": None}


def test_legacy_tax_request_canonical_payload_unchanged():
    fields = {"expected_settlement_version": 1, "reason": "Existing reason", "support_reference": "Certificate ABC"}
    assert InvoiceTaxExemptionCreate(**fields).model_dump() == fields
    assert InvoiceTaxExemptionCreate(expected_settlement_version=1,
        reason="  Existing reason  ", support_reference=" Certificate ABC ").model_dump() == fields
    with pytest.raises(ValidationError):
        InvoiceTaxExemptionCreate(support_reference="Certificate ABC")


@pytest.mark.asyncio
async def test_apply_without_reference_retains_audit_and_normalized_replay(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    async def submit(body):
        return await tax.apply_exemption(db_session, invoice=invoice, tenant=ctx[0], actor=ctx[1],
            body=body, idempotency_key="optional-reference-key")
    await submit(InvoiceTaxExemptionCreate(expected_settlement_version=1))
    await db_session.refresh(invoice, attribute_names=["tax_exemption"])
    audit = dict(invoice.tax_exemption)
    assert audit["reason"] is None and audit["support_reference"] is None
    assert audit["actor_id"] == str(ctx[1].id) and audit["actor_name"] and audit["actor_role"]
    assert audit["applied_at"] and audit["request_hash"] and audit["idempotency_key"]
    assert audit["before"]["tax_amount"] == "8.99" and audit["after"]["tax_amount"] == "0.00"
    assert audit["before_settlement_version"] == 1 and audit["after_settlement_version"] == 2
    assert invoice.total_amount == 109 and invoice.shop_supplies_amount == 6
    for text in (None, "", " \t "):
        await submit(InvoiceTaxExemptionCreate(expected_settlement_version=1, reason=text, support_reference=text))
        assert invoice.tax_exemption == audit and settlement.version == 2
    for audience in ("staff", "guest", "customer"):
        summary = await tax.summary(db_session, invoice, settlement, ctx[0], ctx[1], audience=audience)
        assert summary.applied and summary.reason is None and summary.support_reference is None
    with pytest.raises(SettlementDomainError):
        await submit(InvoiceTaxExemptionCreate(expected_settlement_version=1, support_reference="New reference"))


@pytest.mark.asyncio
@pytest.mark.parametrize("status,attempts,allowed", [("pending", 0, True), ("dead", 2, False), ("succeeded", 1, False), ("processing", 0, False)])
async def test_export_guards(db_session, monkeypatch, status, attempts, allowed):
    from tests.test_db048_cash_payment_timing import event
    ctx = await setup(db_session, monkeypatch)
    queued = event(ctx[3], status=status, attempts=attempts)
    db_session.add(queued)
    await db_session.flush()
    if allowed:
        await apply(db_session, ctx)
        assert queued.status == status and queued.attempt_count == attempts
    else:
        with pytest.raises(SettlementDomainError):
            await apply(db_session, ctx)


@pytest.mark.asyncio
async def test_existing_review_and_full_cash_remain_valid(db_session, monkeypatch):
    from tests.test_db048_reviewed_sandbox_cash import reviewed
    from app.services import invoice_cash_service as cash
    from app.services import quickbooks_accounting_service as accounting
    from app.services import quickbooks_sync_service as sync
    from unittest.mock import AsyncMock
    ctx, queued, *_ = await reviewed(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    invoice.tax_amount = Decimal("8.50")
    invoice.total_amount += Decimal("8.50")
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(invoice)
    settlement.principal_total, settlement.max_card_fee, settlement.max_card_fee_tax = principal, fee, fee_tax
    settlement.sales_tax_rate_snapshot, settlement.card_fee_rate_snapshot = rate, fee_rate
    await db_session.flush()
    history = cash.event_history_digest(queued)
    await apply(db_session, ctx)
    assert cash.event_history_digest(queued) == history
    assert cash.valid_sandbox_cash_review(queued, invoice)
    assert (await cash.cash_eligibility(db_session, invoice, settlement))[0] is None
    monkeypatch.setattr(sync, "_refresh_if_needed", AsyncMock())
    from app.core.config import settings
    monkeypatch.setattr(settings, "QUICKBOOKS_ACCOUNTING_ENVIRONMENT", "production")
    monkeypatch.setattr(accounting, "_request", AsyncMock(return_value={"QueryResponse": {}}))
    await cash.confirm_full_cash(db_session, invoice=invoice, tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], expected_settlement_version=2, idempotency_key="exempt-reviewed-cash")
    assert invoice.tax_amount == 0 and invoice.accounting_policy == "local_cash_only"
    assert settlement.confirmed_principal == 100
    assert accounting._request.call_args.args[1] == "GET"


@pytest.mark.asyncio
async def test_new_noncash_attempt_uses_exempt_money(db_session, monkeypatch):
    from app.services.invoice_settlement_service import create_attempt
    ctx = await setup(db_session, monkeypatch)
    await apply(db_session, ctx)
    created = await create_attempt(db_session, invoice=ctx[3], tenant=ctx[0], customer_id=ctx[2].id,
        actor=ctx[1], amount=Decimal("106.00"), rail="card", expected_settlement_version=2,
        idempotency_key="exempt-new-card-attempt", source="staff", subject_type="staff", subject_id=ctx[1].id)
    assert created.attempt.principal_amount == 106
    assert created.attempt.card_fee_amount == 3 and created.attempt.card_fee_tax_amount == 0
    assert created.attempt.provider_charge_amount == 109


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["zelle", "qbo", "export"])
async def test_ancestor_legacy_activity_denied(db_session, monkeypatch, defect):
    from datetime import datetime, timezone
    from app.db.models.invoice import Invoice
    from tests.test_db048_cash_payment_timing import event
    ctx = await setup(db_session, monkeypatch)
    parent = Invoice(tenant_id=ctx[0].id, repair_order_id=ctx[3].repair_order_id,
        invoice_number=f"PARENT-{uuid4().hex}", subtotal=100, total_amount=100, status=InvoiceStatus.CANCELLED)
    if defect == "zelle": parent.zelle_pending_submitted_at = datetime.now(timezone.utc)
    if defect == "qbo": parent.quickbooks_invoice_id = "remote"
    db_session.add(parent)
    await db_session.flush()
    ctx[3].supersedes_invoice_id = parent.id
    if defect == "export": db_session.add(event(parent, status="processing", attempts=1))
    await db_session.flush()
    with pytest.raises(SettlementDomainError):
        await apply(db_session, ctx)


@pytest.mark.asyncio
async def test_reviewed_local_void_ancestor_allowed(db_session, monkeypatch):
    from tests.test_db048_reviewed_sandbox_cash import reviewed
    ctx, *_ = await reviewed(db_session, monkeypatch, local_void_parent=True)
    invoice, settlement = ctx[3:]
    invoice.tax_amount = Decimal("8.50")
    invoice.total_amount += Decimal("8.50")
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(invoice)
    settlement.principal_total, settlement.max_card_fee, settlement.max_card_fee_tax = principal, fee, fee_tax
    settlement.sales_tax_rate_snapshot, settlement.card_fee_rate_snapshot = rate, fee_rate
    await db_session.flush()
    await apply(db_session, ctx)
    assert invoice.tax_amount == 0 and invoice.accounting_policy == "historical_export_hold"
