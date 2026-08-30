"""What a non-card method actually collects.

The invoice stores the card view: repairs + shop supplies + card processing fee
+ tax on all three, less any invoice discount. A manual method never pays the
card fee, so it must not pay the tax that fee attracted either. Cash settles
without tax at all — the shop is tax exempt.
"""
from decimal import Decimal
from types import SimpleNamespace

from app.api.v1.endpoints.payments import _manual_collected_amount


def _invoice(subtotal, supplies, fee, tax, discount=Decimal("0.00")):
    return SimpleNamespace(
        subtotal=subtotal,
        shop_supplies_amount=supplies,
        service_fee_amount=fee,
        tax_amount=tax,
        discount_amount=discount,
    )


# repairs 2400 + supplies 120, 3% card fee, 5% tax on (repairs + supplies + fee)
BASE = Decimal("2520.00")
FEE = Decimal("75.60")
TAX = Decimal("129.78")


def test_cash_collects_repairs_and_supplies_only():
    invoice = _invoice(Decimal("2400.00"), Decimal("120.00"), FEE, TAX)
    assert _manual_collected_amount(invoice, "cash") == BASE


def test_other_manual_methods_keep_tax_but_drop_the_fee_and_its_tax():
    invoice = _invoice(Decimal("2400.00"), Decimal("120.00"), FEE, TAX)
    # 2520 * 1.05 — tax on the base only, never on the fee
    expected = Decimal("2646.00")
    for method in ("zelle", "check", "ach", "fleet_payment"):
        assert _manual_collected_amount(invoice, method) == expected


def test_the_old_rule_over_collected_by_the_tax_on_the_fee():
    invoice = _invoice(Decimal("2400.00"), Decimal("120.00"), FEE, TAX)
    total = BASE + FEE + TAX
    previously = total - FEE
    assert previously - _manual_collected_amount(invoice, "zelle") == Decimal("3.78")
    assert Decimal("3.78") == (FEE * Decimal("0.05")).quantize(Decimal("0.01"))


def test_invoice_discount_applies_to_whichever_method_is_used():
    invoice = _invoice(Decimal("2400.00"), Decimal("120.00"), FEE, TAX, Decimal("100.00"))
    assert _manual_collected_amount(invoice, "cash") == Decimal("2420.00")
    assert _manual_collected_amount(invoice, "zelle") == Decimal("2546.00")


def test_discount_never_drives_the_amount_below_zero():
    invoice = _invoice(Decimal("10.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("999.00"))
    assert _manual_collected_amount(invoice, "cash") == Decimal("0.00")
    assert _manual_collected_amount(invoice, "zelle") == Decimal("0.00")


def test_invoice_without_fee_or_tax_is_unchanged_by_method():
    invoice = _invoice(Decimal("100.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
    assert _manual_collected_amount(invoice, "cash") == Decimal("100.00")
    assert _manual_collected_amount(invoice, "zelle") == Decimal("100.00")


def test_missing_money_columns_are_treated_as_zero():
    invoice = SimpleNamespace(
        subtotal=Decimal("50.00"),
        shop_supplies_amount=None,
        service_fee_amount=None,
        tax_amount=None,
        discount_amount=None,
    )
    assert _manual_collected_amount(invoice, "cash") == Decimal("50.00")
    assert _manual_collected_amount(invoice, "zelle") == Decimal("50.00")
