from decimal import Decimal
from types import SimpleNamespace

from app.services.pricing import get_order_checkout_breakdown


def test_parts_never_increase_shop_supplies():
    tenant = SimpleNamespace(shop_supplies_rate=3)
    for parts in ("0", "104.50", "10000"):
        order = SimpleNamespace(total_labor_cost=100, total_parts_cost=parts)
        assert get_order_checkout_breakdown(order, tenant)["shop_supplies_amount"] == Decimal("3.00")


def test_labor_discount_reduces_shop_supplies_and_parts_only_has_no_supplies():
    tenant = SimpleNamespace(shop_supplies_rate=3)
    order = SimpleNamespace(total_labor_cost=100, total_parts_cost=500, labor_discount_amount=20)
    assert get_order_checkout_breakdown(order, tenant)["shop_supplies_amount"] == Decimal("2.40")
    order.total_labor_cost = 0
    assert get_order_checkout_breakdown(order, tenant)["shop_supplies_amount"] == Decimal("0.00")
