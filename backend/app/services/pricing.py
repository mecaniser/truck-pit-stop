import json
from decimal import Decimal
from typing import Any, Optional


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def get_selected_services_total(internal_notes: Optional[str]) -> Decimal:
    if not internal_notes:
        return Decimal("0.00")

    try:
        notes_data = json.loads(internal_notes)
        selected_services = notes_data.get("selected_services", [])
    except (json.JSONDecodeError, TypeError, ValueError):
        return Decimal("0.00")

    total = Decimal("0.00")
    for svc in selected_services:
        total += _to_decimal(svc.get("base_price", "0"))
    return total


def get_order_parts_total(order: Any) -> Decimal:
    return _to_decimal(getattr(order, "total_parts_cost", 0))


def get_order_labor_total(order: Any) -> Decimal:
    # Source of truth is total_labor_cost computed from structured labor lines.
    return _to_decimal(getattr(order, "total_labor_cost", 0))


def get_order_subtotal(order: Any) -> Decimal:
    return get_order_parts_total(order) + get_order_labor_total(order)


def get_order_total(order: Any) -> Decimal:
    parts_total = get_order_parts_total(order)
    labor_total = get_order_labor_total(order)
    labor_discount = _to_decimal(getattr(order, "labor_discount_amount", 0))
    order_discount = _to_decimal(getattr(order, "order_discount_amount", 0))
    labor_net = max(Decimal("0.00"), labor_total - labor_discount)
    return max(Decimal("0.00"), parts_total + labor_net - order_discount)


def get_order_checkout_breakdown(order: Any, tenant: Any) -> dict[str, Decimal]:
    """Return customer-facing checkout estimates using the same repair net total.

    Card total includes the card processing fee (stored as service_fee_amount)
    and tax on that fee. Zelle total excludes the card processing fee and the
    tax attributable to it, since Zelle has no card processing cost.
    """
    parts_total = get_order_parts_total(order)
    labor_total = get_order_labor_total(order)
    labor_discount = _to_decimal(getattr(order, "labor_discount_amount", 0))
    order_discount = _to_decimal(getattr(order, "order_discount_amount", 0))
    labor_net = max(Decimal("0.00"), labor_total - labor_discount)
    repair_total = max(Decimal("0.00"), parts_total + labor_net - order_discount)

    shop_supplies_rate = _to_decimal(getattr(tenant, "shop_supplies_rate", 0)) / Decimal("100")
    service_fee_rate = _to_decimal(getattr(tenant, "service_fee_rate", 0)) / Decimal("100")
    sales_tax_rate = _to_decimal(getattr(tenant, "sales_tax_rate", 0)) / Decimal("100")

    shop_supplies_amount = (labor_net * shop_supplies_rate).quantize(Decimal("0.01"))
    pre_fee_taxable = repair_total + shop_supplies_amount
    service_fee_amount = (pre_fee_taxable * service_fee_rate).quantize(Decimal("0.01"))
    card_taxable_amount = pre_fee_taxable + service_fee_amount
    tax_amount = (card_taxable_amount * sales_tax_rate).quantize(Decimal("0.01"))
    estimated_card_total = (card_taxable_amount + tax_amount).quantize(Decimal("0.01"))
    zelle_tax_amount = (pre_fee_taxable * sales_tax_rate).quantize(Decimal("0.01"))
    estimated_zelle_total = (pre_fee_taxable + zelle_tax_amount).quantize(Decimal("0.01"))

    return {
        "parts_total": parts_total.quantize(Decimal("0.01")),
        "labor_total": labor_total.quantize(Decimal("0.01")),
        "labor_net": labor_net.quantize(Decimal("0.01")),
        "labor_discount_amount": labor_discount.quantize(Decimal("0.01")),
        "order_discount_amount": order_discount.quantize(Decimal("0.01")),
        "repair_total": repair_total.quantize(Decimal("0.01")),
        "shop_supplies_amount": shop_supplies_amount,
        "service_fee_amount": service_fee_amount,
        "tax_amount": tax_amount,
        "estimated_card_total": estimated_card_total,
        "estimated_zelle_total": estimated_zelle_total,
        "zelle_savings_amount": max(Decimal("0.00"), estimated_card_total - estimated_zelle_total).quantize(Decimal("0.01")),
    }
