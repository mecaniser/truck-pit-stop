from decimal import Decimal
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from tests.test_db048_tax_exemption import setup, apply
from app.schemas.invoice_settlement import InvoiceChargeAdjustmentCreate
from app.services import invoice_charge_adjustments as charges
from app.services.invoice_tax_exemption import snapshot
from app.services.invoice_cash_service import cash_eligibility, event_history_digest
from app.services.invoice_settlement_service import SettlementDomainError
from app.db.models.invoice_charge_adjustment import InvoiceChargeAdjustment
from app.db.models.invoice_settlement import InvoicePaymentLedgerEvent
from app.db.models.payment import Payment
from app.db.models.user import UserRole


async def adjust(db, ctx, tax=False, supplies=True, version=None, key=None):
    version = ctx[4].version if version is None else version
    body = InvoiceChargeAdjustmentCreate(expected_settlement_version=version,
        tax_exempt=tax, shop_supplies_enabled=supplies)
    return await charges.adjust(db, invoice=ctx[3], tenant=ctx[0], actor=ctx[1], body=body,
        idempotency_key=key or f"adjust-{version}")


@pytest.mark.asyncio
async def test_reversible_frozen_charges_preserve_legacy_audit_and_cash(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    invoice, settlement = ctx[3:]
    original = snapshot(invoice)
    await apply(db_session, ctx)
    audit = dict(invoice.tax_exemption)
    await adjust(db_session, ctx, tax=False, supplies=True)
    assert snapshot(invoice) == original and invoice.tax_exemption == audit
    assert not charges.effective_tax_exempt(invoice)
    await adjust(db_session, ctx, tax=False, supplies=False)
    assert invoice.shop_supplies_amount == 0
    assert invoice.service_fee_amount == Decimal("2.83")
    assert invoice.tax_amount == Decimal("8.48")
    assert invoice.total_amount == Decimal("111.31")
    await adjust(db_session, ctx, tax=True, supplies=False)
    assert invoice.tax_amount == 0 and settlement.max_card_fee_tax == 0
    assert invoice.total_amount == Decimal("102.83")
    await adjust(db_session, ctx, tax=False, supplies=True)
    assert snapshot(invoice) == original and invoice.tax_exemption == audit
    assert (await cash_eligibility(db_session, invoice, settlement))[0] is None
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(InvoicePaymentLedgerEvent)) == 0
    assert await db_session.scalar(select(func.count()).select_from(InvoiceChargeAdjustment)) == 4


@pytest.mark.asyncio
async def test_replay_conflict_stale_and_old_command_denied(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    await adjust(db_session, ctx, tax=True, version=1, key="same")
    await adjust(db_session, ctx, tax=True, version=1, key="same")
    assert ctx[4].version == 2
    with pytest.raises(SettlementDomainError, match="different charge"):
        await adjust(db_session, ctx, tax=False, version=1, key="same")
    with pytest.raises(SettlementDomainError):
        await adjust(db_session, ctx, version=1)
    with pytest.raises(SettlementDomainError):
        await apply(db_session, ctx, version=2)
    assert ctx[3].tax_exemption is None


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["pending", "paid", "qbo", "foreign", "role", "drift", "deleted"])
async def test_unsafe_adjustment_denied(db_session, monkeypatch, defect):
    from app.db.models.invoice import InvoiceStatus
    from datetime import datetime, timezone
    ctx = await setup(db_session, monkeypatch)
    if defect == "pending": ctx[4].active_pending_principal = Decimal("1")
    if defect == "paid": ctx[3].status = InvoiceStatus.PAID
    if defect == "qbo": ctx[3].quickbooks_invoice_id = "remote"
    if defect == "foreign": ctx[1].tenant_id = uuid4()
    if defect == "role": ctx[1].role = UserRole.RECEPTIONIST
    if defect == "deleted": ctx[2].deleted_at = datetime.now(timezone.utc)
    if defect == "drift": ctx[3].total_amount += Decimal("1")
    await db_session.flush()
    with pytest.raises(SettlementDomainError):
        await adjust(db_session, ctx, tax=True)
    assert await db_session.scalar(select(func.count()).select_from(InvoiceChargeAdjustment)) == 0


@pytest.mark.asyncio
async def test_history_binding_redaction_and_audit(db_session, monkeypatch):
    ctx = await setup(db_session, monkeypatch)
    before = event_history_digest(ctx[3])
    await adjust(db_session, ctx)  # No financial change still binds the audit.
    after = event_history_digest(ctx[3])
    assert before != after
    row = ctx[3].charge_adjustments[0]
    assert row.evidence["actor_id"] == str(ctx[1].id)
    assert row.evidence["support_reference"] is None
    assert row.evidence["before"] == row.evidence["after"]
    row.evidence = {**row.evidence, "support_reference": "tampered"}
    assert event_history_digest(ctx[3]) != after
    assert await charges.summary(db_session, ctx[3], ctx[4], ctx[0], ctx[1], audience="guest") is None
    assert await charges.summary(db_session, ctx[3], ctx[4], ctx[0], ctx[1], audience="customer") is None


def test_body_normalization_and_rejection():
    body = dict(expected_settlement_version=1, tax_exempt=False, shop_supplies_enabled=True)
    assert InvoiceChargeAdjustmentCreate(**body, support_reference="  ").support_reference is None
    for override in ({"tax_exempt": "true"}, {"support_reference": "x" * 256}, {"reason": "no"}, {"expected_settlement_version": 0}):
        with pytest.raises(ValidationError):
            InvoiceChargeAdjustmentCreate(**{**body, **override})


def test_discount_is_after_tax_and_original_restore_is_exact():
    original = dict(subtotal="100.00", shop_supplies_amount="6.00", service_fee_amount="3.00",
        tax_amount="8.99", discount_amount="10.00", total_amount="107.99")
    assert charges.calculate(original, tax_exempt=False, shop_supplies_enabled=True) == original
    without = charges.calculate(original, tax_exempt=False, shop_supplies_enabled=False)
    assert without["tax_amount"] == "8.48" and without["total_amount"] == "101.31"
    assert without["discount_amount"] == "10.00"


@pytest.mark.asyncio
async def test_profile_origin_audit_can_restore_tax_without_mutating_profile(db_session, monkeypatch):
    from app.services.customer_tax_exemption import stamp_invoice
    ctx = await setup(db_session, monkeypatch)
    invoice = ctx[3]
    original = snapshot(invoice)
    invoice.tax_amount = Decimal("0")
    invoice.total_amount -= Decimal(original["tax_amount"])
    default = {"customer_id": str(ctx[2].id), "version": 1, "audit_id": str(uuid4()),
        "support_reference": None, "actor": {"id": str(ctx[1].id), "name": "Owner", "role": "garage_owner"}}
    stamp_invoice(invoice, default, {"tax_amount": Decimal(original["tax_amount"])}, ctx[1].id)
    from app.services.invoice_settlement_service import invoice_money_snapshot
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(invoice)
    ctx[4].principal_total, ctx[4].max_card_fee, ctx[4].max_card_fee_tax = principal, fee, fee_tax
    ctx[4].sales_tax_rate_snapshot, ctx[4].card_fee_rate_snapshot = rate, fee_rate
    audit = dict(invoice.tax_exemption)
    await db_session.flush()
    await adjust(db_session, ctx, tax=False)
    assert snapshot(invoice) == original and invoice.tax_exemption == audit
    assert not charges.effective_tax_exempt(invoice)
