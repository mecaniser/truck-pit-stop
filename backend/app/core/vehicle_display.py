"""Shared vehicle display label, mirroring frontend/src/lib/vehicleName.ts.

Bulk imports sometimes have no make/model on file (only a unit number), and
the placeholder value for those fields is the literal string "UNKNOWN" —
never show that to a user. Falls back to "Equipment" (optionally with the
unit number) when make and/or model are missing or the "UNKNOWN" placeholder.
"""
from typing import Optional


def _is_known(value: Optional[str]) -> bool:
    return bool(value) and value.strip().upper() != "UNKNOWN"


def vehicle_display_label(
    year: Optional[int] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    unit_number: Optional[str] = None,
    include_year: bool = True,
) -> str:
    known_make = make.strip() if _is_known(make) else None
    known_model = model.strip() if _is_known(model) else None

    if not known_make and not known_model:
        return f"Equipment · Unit {unit_number}" if unit_number else "Equipment"

    parts = [str(year)] if include_year and year else []
    parts += [p for p in (known_make, known_model) if p]
    return " ".join(parts).strip()
