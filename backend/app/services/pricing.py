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
    # New source of truth is total_labor_cost computed from structured labor lines.
    # Keep one-release fallback for legacy internal_notes.selected_services.
    stored_labor = _to_decimal(getattr(order, "total_labor_cost", 0))
    if stored_labor > 0:
        return stored_labor

    service_total = get_selected_services_total(getattr(order, "internal_notes", None))
    if service_total > 0:
        return service_total
    return Decimal("0.00")


def get_order_subtotal(order: Any) -> Decimal:
    return get_order_parts_total(order) + get_order_labor_total(order)
