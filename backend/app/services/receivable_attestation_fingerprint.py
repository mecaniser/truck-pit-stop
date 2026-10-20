"""Versioned, private source digest shared by future DB-135 dry-run/apply/read paths.

The caller must load every linked row under one repeatable-read transaction.
This module only serializes that complete, tenant-scoped source bundle; it does
not decide eligibility or turn a digest into a collectible balance.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Iterable
from uuid import UUID

from sqlalchemy.inspection import inspect


FINGERPRINT_VERSION = "db135-source-v1"
MAX_SOURCE_ROWS_PER_KIND = 10_000
REQUIRED_RELATIONS = frozenset({
    "settlements", "payments", "payment_attempts", "ledger_events", "refunds",
    "overpayments", "customer_credits", "provider_disputes", "superseding_invoices",
})
_REFERENCE_NAMES = (
    "provider_reference", "provider_account_id", "provider_intent_id",
    "provider_charge_id", "provider_event_id", "provider_dispute_id",
    "stripe_", "quickbooks_", "reference_number", "authorization_number",
    "receipt_url", "manual_reference_fingerprint",
)


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return _canonical(value.value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest()}
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    raise TypeError(f"Unsupported attestation source value: {type(value).__name__}")


def _row_payload(row: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    for column in inspect(type(row)).columns:
        value = _canonical(getattr(row, column.key))
        if value is not None and any(marker in column.key for marker in _REFERENCE_NAMES):
            raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            value = {"sha256": hashlib.sha256(raw).hexdigest()}
        payload[column.key] = value
    return payload


def fingerprint_source_bundle(*, tenant_id: UUID, invoice: object, order: object,
                              customer: object, linked_rows: dict[str, Iterable[object]]) -> str:
    """Hash exact source rows; every caller must use the same complete relation map.

    An empty relation is represented explicitly. Rows are sorted by their stable
    primary key, so database return order cannot change the digest. Deleted rows
    remain in the bundle and change the digest when their tombstone changes.
    """
    source = {"invoice": invoice, "order": order, "customer": customer}
    for kind, row in source.items():
        if getattr(row, "tenant_id", None) != tenant_id:
            raise ValueError(f"Attestation {kind} tenant mismatch")
    if getattr(invoice, "repair_order_id", None) != getattr(order, "id", None):
        raise ValueError("Attestation invoice/order mismatch")
    if getattr(invoice, "billed_customer_id", None) not in (None, getattr(customer, "id", None)):
        raise ValueError("Attestation bill-to mismatch")
    if getattr(invoice, "billed_customer_id", None) is None and getattr(order, "customer_id", None) != getattr(customer, "id", None):
        raise ValueError("Attestation order/customer mismatch")
    if set(linked_rows) != REQUIRED_RELATIONS:
        raise ValueError("Attestation source relation map incomplete")

    relations: dict[str, list[dict[str, object]]] = {}
    for kind, rows in sorted(linked_rows.items()):
        if not kind or kind in source:
            raise ValueError("Invalid attestation relation kind")
        materialized = list(rows)
        if len(materialized) > MAX_SOURCE_ROWS_PER_KIND:
            raise ValueError("Attestation source relation exceeds safe read limit")
        if any(getattr(row, "tenant_id", None) != tenant_id for row in materialized):
            raise ValueError(f"Attestation {kind} tenant mismatch")
        ids = [str(getattr(row, "id", None)) for row in materialized]
        if "None" in ids or len(set(ids)) != len(ids):
            raise ValueError(f"Attestation {kind} identity missing or duplicated")
        relations[kind] = [_row_payload(row) for row in sorted(materialized, key=lambda row: str(row.id))]
    payload = {
        "version": FINGERPRINT_VERSION,
        "source": {kind: _row_payload(row) for kind, row in source.items()},
        "relations": relations,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()
