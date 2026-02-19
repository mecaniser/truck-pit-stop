from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

from app.services.pricing import (
    get_order_labor_total,
    get_order_parts_total,
    get_order_subtotal,
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
    def test_prefers_selected_services_over_labor_cost(self):
        notes = json.dumps({"selected_services": [{"base_price": "100"}]})
        order = SimpleNamespace(internal_notes=notes, total_labor_cost=50)
        assert get_order_labor_total(order) == Decimal("100")

    def test_falls_back_to_labor_cost_when_no_services(self):
        order = SimpleNamespace(internal_notes=None, total_labor_cost=75)
        assert get_order_labor_total(order) == Decimal("75")


class TestGetOrderSubtotal:
    def test_sums_parts_and_labor(self):
        order = SimpleNamespace(
            total_parts_cost=100,
            internal_notes=None,
            total_labor_cost=200,
        )
        assert get_order_subtotal(order) == Decimal("300")
