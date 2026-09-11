"""Audited reversible invoice charges using only frozen invoice amounts."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from app.core.config import settings
from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.invoice_charge_adjustment import InvoiceChargeAdjustment
from app.services.invoice_accounting_policy import locked_policy
from app.services.invoice_tax_exemption import authorized, eligibility, snapshot, MONEY_FIELDS
from app.services.invoice_settlement_service import SettlementDomainError, money, invoice_money_snapshot, _canonical_hash, _actor_snapshot
from app.schemas.invoice_settlement import InvoiceChargeControls
from app.services.invoice_charge_state import latest, effective_tax_exempt


def original_snapshot(invoice):
    row = latest(invoice)
    audit = getattr(invoice, "tax_exemption", None) or {}
    original = row.evidence["original"] if row else audit.get("before", snapshot(invoice))
    expected = row.evidence["after"] if row else audit.get("after", snapshot(invoice))
    if expected != snapshot(invoice):
        raise ValueError("Invoice charges changed outside the audited adjustment history.")
    try:
        values = {key: Decimal(original[key]) for key in MONEY_FIELDS}
        if (any(not value.is_finite() or value < 0 or money(value) != value for value in values.values())
                or values["total_amount"] != values["subtotal"] + values["shop_supplies_amount"]
                + values["service_fee_amount"] + values["tax_amount"] - values["discount_amount"]
                or values["subtotal"] + values["shop_supplies_amount"] <= 0):
            raise ValueError("Original invoice amounts require review.")
    except (KeyError, InvalidOperation, TypeError):
        raise ValueError("Original invoice amounts require review.")
    return {key: str(money(value)) for key, value in values.items()}


def calculate(original, *, tax_exempt, shop_supplies_enabled):
    values = {key: Decimal(original[key]) for key in MONEY_FIELDS}
    subtotal, supplies, fee, tax = (values[key] for key in
        ("subtotal", "shop_supplies_amount", "service_fee_amount", "tax_amount"))
    base = subtotal + supplies
    new_supplies = supplies if shop_supplies_enabled else Decimal("0.00")
    new_fee = fee if shop_supplies_enabled else money(subtotal * fee / base)
    new_tax = Decimal("0.00") if tax_exempt else (tax if shop_supplies_enabled
        else money((subtotal + new_fee) * tax / (base + fee)))
    values.update(shop_supplies_amount=new_supplies, service_fee_amount=new_fee, tax_amount=new_tax)
    values["total_amount"] = subtotal + new_supplies + new_fee + new_tax - values["discount_amount"]
    if values["total_amount"] - new_fee - new_tax <= 0:
        raise ValueError("Adjusted invoice principal must remain positive.")
    return {key: str(money(value)) for key, value in values.items()}


async def summary(db, invoice, settlement, tenant, actor, *, audience):
    if audience != "staff" or not authorized(actor) or actor.tenant_id != tenant.id:
        return None
    reason = await eligibility(db, invoice, settlement, adjustment=True)
    if not tenant.is_active or tenant.deleted_at:
        reason = "This shop is unavailable."
    elif not settings.INVOICE_SPLIT_PAYMENTS_ENABLED or not tenant.invoice_split_payments_enabled:
        reason = "Invoice settlement is not enabled for this shop."
    try:
        original = original_snapshot(invoice)
    except ValueError as exc:
        original, reason = snapshot(invoice), str(exc)
    row = latest(invoice)
    return InvoiceChargeControls(tax_exempt=effective_tax_exempt(invoice),
        shop_supplies_enabled=row.evidence["settings"]["shop_supplies_enabled"] if row else True,
        can_adjust=reason is None, unavailable_reason=reason,
        support_reference=(row.evidence if row else invoice.tax_exemption or {}).get("support_reference"),
        original_shop_supplies_amount=money(original["shop_supplies_amount"]),
        original_tax_amount=money(original["tax_amount"]))


async def adjust(db, *, invoice, tenant, actor, body, idempotency_key):
    if (not authorized(actor) or actor.tenant_id != tenant.id or invoice.tenant_id != tenant.id
            or not tenant.is_active or tenant.deleted_at):
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    if not settings.INVOICE_SPLIT_PAYMENTS_ENABLED or not tenant.invoice_split_payments_enabled:
        raise SettlementDomainError("split_payments_disabled", "Invoice settlement is not enabled for this shop.")
    await locked_policy(db, invoice)
    await db.refresh(invoice, attribute_names=[column.name for column in Invoice.__table__.columns] + ["charge_adjustments"])
    await db.refresh(tenant)
    if not tenant.is_active or tenant.deleted_at:
        raise SettlementDomainError("invoice_not_found", "Invoice not found.", status_code=404)
    settlement = await db.scalar(select(InvoiceSettlement).where(InvoiceSettlement.invoice_id == invoice.id,
        InvoiceSettlement.tenant_id == tenant.id).execution_options(populate_existing=True))
    if not settlement:
        raise SettlementDomainError("charge_adjustment_unavailable", "Refresh the invoice before changing charges.")
    request_hash = _canonical_hash({"invoice_id": str(invoice.id), "actor_id": str(actor.id), **body.model_dump()})
    previous = next((row for row in invoice.charge_adjustments if row.idempotency_key == idempotency_key), None)
    if previous:
        if previous.request_hash != request_hash:
            raise SettlementDomainError("idempotency_conflict", "This key was used for a different charge adjustment.")
        return settlement
    if settlement.version != body.expected_settlement_version:
        raise SettlementDomainError("stale_settlement_version", "The invoice changed. Refresh before changing charges.", current_version=settlement.version)
    reason = await eligibility(db, invoice, settlement, lock=True, adjustment=True)
    if reason:
        raise SettlementDomainError("charge_adjustment_unavailable", reason)
    try:
        original = original_snapshot(invoice)
        after = calculate(original, tax_exempt=body.tax_exempt, shop_supplies_enabled=body.shop_supplies_enabled)
    except ValueError as exc:
        raise SettlementDomainError("charge_adjustment_unavailable", str(exc))
    before, version = snapshot(invoice), settlement.version
    for key, value in after.items():
        setattr(invoice, key, Decimal(value))
    principal, fee, fee_tax, rate, fee_rate = invoice_money_snapshot(invoice)
    settlement.principal_total, settlement.max_card_fee, settlement.max_card_fee_tax = principal, fee, fee_tax
    settlement.sales_tax_rate_snapshot, settlement.card_fee_rate_snapshot = rate, fee_rate
    settlement.version += 1
    actor_id, actor_name, actor_role = _actor_snapshot(actor)
    row = InvoiceChargeAdjustment(tenant_id=tenant.id, invoice_id=invoice.id,
        version=settlement.version, idempotency_key=idempotency_key, request_hash=request_hash,
        evidence={"schema": "invoice-charge-adjustment-v1", "original": original, "before": before, "after": after,
            "settings": {"tax_exempt": body.tax_exempt, "shop_supplies_enabled": body.shop_supplies_enabled},
            "support_reference": body.support_reference, "actor_id": str(actor_id), "actor_name": actor_name,
            "actor_role": actor_role, "applied_at": datetime.now(timezone.utc).isoformat(),
            "before_settlement_version": version, "after_settlement_version": settlement.version})
    invoice.charge_adjustments.append(row)
    db.add(row)
    await db.flush()
    return settlement
