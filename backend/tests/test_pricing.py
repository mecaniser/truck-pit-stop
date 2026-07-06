from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

from app.services.pricing import (
    get_order_labor_total,
    get_order_parts_total,
    get_order_subtotal,
    get_order_total,
    get_selected_services_total,
)


class TestGetSelectedServicesTotal:
    def test_none_returns_zero(self):
        assert get_selected_services_total(None) == Decimal("0.00")

    def test_empty_string_returns_zero(self):
        assert get_selected_services_total("") == Decimal("0.00")

    def test_invalid_json_returns_zero(self):
        assert get_selected_services_total("not json") == Decimal("0.00")

    def test_no_selected_services_key(self):
        assert get_selected_services_total(json.dumps({"other": 1})) == Decimal("0.00")

    def test_sums_base_prices(self):
        notes = json.dumps({
            "selected_services": [
                {"name": "Oil Change", "base_price": "49.99"},
                {"name": "Tire Rotation", "base_price": "25.00"},
            ]
        })
        assert get_selected_services_total(notes) == Decimal("74.99")

    def test_missing_base_price_treated_as_zero(self):
        notes = json.dumps({"selected_services": [{"name": "Free Check"}]})
        assert get_selected_services_total(notes) == Decimal("0.00")


class TestGetOrderPartsTotal:
    def test_returns_parts_cost(self):
        order = SimpleNamespace(total_parts_cost=150.50)
        assert get_order_parts_total(order) == Decimal("150.5")

    def test_missing_attr_returns_zero(self):
        order = SimpleNamespace()
        assert get_order_parts_total(order) == Decimal("0.00")


class TestGetOrderLaborTotal:
    def test_uses_stored_labor_cost_over_selected_services(self):
        notes = json.dumps({"selected_services": [{"base_price": "100"}]})
        order = SimpleNamespace(internal_notes=notes, total_labor_cost=50)
        assert get_order_labor_total(order) == Decimal("50")

    def test_uses_stored_labor_cost_when_no_services(self):
        order = SimpleNamespace(internal_notes=None, total_labor_cost=75)
        assert get_order_labor_total(order) == Decimal("75")

    def test_does_not_fallback_to_selected_services_when_stored_labor_is_zero(self):
        notes = json.dumps({"selected_services": [{"base_price": "100"}]})
        order = SimpleNamespace(internal_notes=notes, total_labor_cost=0)
        assert get_order_labor_total(order) == Decimal("0")


class TestGetOrderSubtotal:
    def test_sums_parts_and_labor(self):
        order = SimpleNamespace(
            total_parts_cost=100,
            internal_notes=None,
            total_labor_cost=200,
        )
        assert get_order_subtotal(order) == Decimal("300")


class TestGetOrderTotal:
    def test_applies_labor_and_order_discounts(self):
        order = SimpleNamespace(
            total_parts_cost=100,
            total_labor_cost=200,
            labor_discount_amount=50,
            order_discount_amount=30,
        )
        assert get_order_total(order) == Decimal("220")

    def test_total_cannot_go_below_zero(self):
        order = SimpleNamespace(
            total_parts_cost=25,
            total_labor_cost=50,
            labor_discount_amount=100,
            order_discount_amount=100,
        )
        assert get_order_total(order) == Decimal("0.00")
