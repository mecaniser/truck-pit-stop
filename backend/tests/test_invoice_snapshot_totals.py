from decimal import Decimal

from app.services.invoice_snapshot_totals import invoice_snapshot_totals


def test_saved_totals_do_not_include_supplies_or_live_prices():
    assert invoice_snapshot_totals({"labor": [{"total_cost": "100.00"}], "parts": [{"total_price": "104.50"}]}) == {
        "labor_total": Decimal("100.00"), "parts_total": Decimal("104.50")}


def test_empty_collections_are_known_zero():
    assert invoice_snapshot_totals({"labor": [], "parts": []}) == {
        "labor_total": Decimal("0.00"), "parts_total": Decimal("0.00")}


def test_missing_or_invalid_snapshot_is_not_fabricated():
    for snapshot in (None, {}, {"labor": []}, {"labor": None, "parts": []},
                     {"labor": [{}], "parts": []}, {"labor": [None], "parts": []},
                     {"labor": [{"total_cost": "NaN"}], "parts": []},
                     {"labor": [{"total_cost": "1e999999999"}], "parts": []},
                     {"labor": [{"total_cost": "-1"}], "parts": []}):
        assert invoice_snapshot_totals(snapshot) == {}
