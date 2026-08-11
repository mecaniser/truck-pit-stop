"""Shared exact bounds for repair-work quantities and labor hours."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


WORK_VALUE_MIN = Decimal("0.01")
WORK_VALUE_MAX = Decimal("999.99")
WORK_VALUE_QUANTUM = Decimal("0.01")


def validate_work_value(value: Any, *, label: str) -> Decimal:
    """Return an exact bounded decimal; never round or clamp input.

    Equality with the two-decimal quantization accepts harmless trailing zeroes
    while rejecting values whose numeric precision would be changed by the
    database column.
    """
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        two_decimal_value = decimal_value.quantize(WORK_VALUE_QUANTUM)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(
            f"{label} must be finite from 0.01 through 999.99 with at most two decimal places"
        ) from exc

    if (
        not decimal_value.is_finite()
        or decimal_value < WORK_VALUE_MIN
        or decimal_value > WORK_VALUE_MAX
        or decimal_value != two_decimal_value
    ):
        raise ValueError(
            f"{label} must be finite from 0.01 through 999.99 with at most two decimal places"
        )
    return decimal_value


def validate_part_quantity(value: Any) -> Decimal:
    return validate_work_value(value, label="Part quantity")


def validate_labor_hours(value: Any) -> Decimal:
    return validate_work_value(value, label="Labor hours")
