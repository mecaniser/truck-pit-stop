from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class OperationWarning:
    code: str
    message: str


@dataclass
class RepairOperationCandidate:
    operation_id: str
    name: str
    description: Optional[str]
    estimated_hours: Decimal
    provider: str = "internal_library"


@dataclass
class OperationEstimate:
    operation_id: str
    name: str
    description: Optional[str]
    estimated_hours: Decimal
    warnings: list[OperationWarning]
    provider: str = "internal_library"


_DEFAULT_OPERATION_LIBRARY: tuple[tuple[str, str, str, Decimal], ...] = (
    ("brake-change", "Brake Change", "Replace pads or shoes and inspect brake hardware.", Decimal("2.50")),
    ("egr-replacement", "EGR Replacement", "Replace EGR valve and verify operation.", Decimal("6.00")),
    ("dpf-service", "DPF Service", "Inspect DPF system and run the required service cycle.", Decimal("3.00")),
    ("coolant-leak-repair", "Coolant Leak Repair", "Pressure test cooling system and repair leak source.", Decimal("4.50")),
    ("starter-replacement", "Starter Replacement", "Remove and replace starter motor, then verify cranking.", Decimal("2.00")),
    ("alternator-replacement", "Alternator Replacement", "Replace alternator and verify charging output.", Decimal("2.50")),
)


def _normalize_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def slugify_operation(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", _normalize_text(value))
    return normalized.strip("-") or "custom-operation"


def _display_name_from_user_text(value: str) -> str:
    words = re.split(r"(\s+)", (value or "").strip())
    formatted: list[str] = []
    for word in words:
        if not word or word.isspace():
            formatted.append(word)
        elif any(ch.isupper() for ch in word[1:]) or word.isupper():
            formatted.append(word)
        else:
            formatted.append(word[:1].upper() + word[1:].lower())
    return "".join(formatted).strip()


def build_custom_candidate(query: str) -> RepairOperationCandidate:
    clean_query = (query or "").strip()
    name = _display_name_from_user_text(clean_query) or "Custom Operation"
    return RepairOperationCandidate(
        operation_id=f"custom:{slugify_operation(clean_query)}",
        name=name,
        description="New custom repair operation. Save hours once and the system will reuse them next time.",
        estimated_hours=Decimal("0.00"),
        provider="internal_library",
    )


def build_custom_estimate(operation_id: str, name: Optional[str] = None) -> OperationEstimate:
    fallback_name = _display_name_from_user_text((name or operation_id or "Custom Operation").replace("custom:", "").replace("-", " "))
    return OperationEstimate(
        operation_id=operation_id,
        name=fallback_name,
        description="No saved estimate yet. Enter hours once to teach the internal labor library.",
        estimated_hours=Decimal("0.00"),
        warnings=[
            OperationWarning(
                code="no_saved_match",
                message="No saved labor match yet. Enter hours once and future matching jobs will reuse them.",
            )
        ],
        provider="internal_library",
    )


def search_operation_library(query: str) -> list[RepairOperationCandidate]:
    q = _normalize_text(query)
    if not q:
        return []

    candidates: list[RepairOperationCandidate] = []
    for operation_id, name, description, hours in _DEFAULT_OPERATION_LIBRARY:
        haystack = " ".join([operation_id, name, description]).lower()
        if q in haystack:
            candidates.append(
                RepairOperationCandidate(
                    operation_id=operation_id,
                    name=name,
                    description=description,
                    estimated_hours=hours,
                    provider="internal_library",
                )
            )

    return candidates


def get_library_estimate(operation_id: str) -> Optional[OperationEstimate]:
    lookup = _normalize_text(operation_id.replace("custom:", ""))
    for catalog_operation_id, name, description, hours in _DEFAULT_OPERATION_LIBRARY:
        if lookup == _normalize_text(catalog_operation_id):
            return OperationEstimate(
                operation_id=catalog_operation_id,
                name=name,
                description=description,
                estimated_hours=hours,
                warnings=[],
                provider="internal_library",
            )
    return None
