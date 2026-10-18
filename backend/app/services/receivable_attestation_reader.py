"""Fail-closed validation of a DB-135 historical receivable approval head.

The caller must load the complete invoice source and every approval version in
one repeatable-read snapshot. This pure gate neither writes nor grants approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Sequence
from uuid import UUID

from app.services.receivable_attestation_eligibility import triage_receivable_source
from app.services.receivable_attestation_fingerprint import FINGERPRINT_VERSION, fingerprint_source_bundle
from app.services.receivable_attestation_source import ReceivableSourceBundle


@dataclass(frozen=True)
class VerifiedReceivable:
    basis: str
    principal: Decimal
    confirmed: Decimal


MANIFEST_VERSION = "db135-attestation-manifest-v1"
ENTRY_KEYS = frozenset({
    "repair_order_id", "customer_id", "decision", "principal_total_cents",
    "confirmed_principal_cents", "source_fingerprint", "evidence_digest",
    "fingerprint_version", "version", "supersedes_id", "reviewed_at",
    "valid_until", "audit_reference",
})


def compute_manifest_digest(*, tenant_id: UUID, invoice_ids: list[str],
                            approved_entries: dict[str, dict[str, str]],
                            fingerprint_version: str, reviewer_user_id: UUID,
                            executor_user_id: UUID, authorization_reference: str,
                            expected_insert_count: int) -> str:
    """Versioned exact preimage shared by dry run, writer and read validation."""
    if (not isinstance(invoice_ids, list) or not isinstance(approved_entries, dict)
            or not invoice_ids or not isinstance(expected_insert_count, int)
            or expected_insert_count != len(invoice_ids)
            or not isinstance(authorization_reference, str) or not authorization_reference
            or fingerprint_version != FINGERPRINT_VERSION):
        raise ValueError("Invalid receivable manifest")
    try:
        ids = [str(UUID(value)) for value in invoice_ids]
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid receivable manifest invoice ID") from exc
    if ids != invoice_ids or ids != sorted(set(ids)) or set(approved_entries) != set(ids):
        raise ValueError("Invalid receivable manifest invoice set")
    for invoice_id, entry in approved_entries.items():
        if (not isinstance(entry, dict) or set(entry) != ENTRY_KEYS
                or any(not isinstance(value, str) for value in entry.values())):
            raise ValueError(f"Invalid receivable manifest entry for {invoice_id}")
    payload = {
        "version": MANIFEST_VERSION, "tenant_id": str(tenant_id),
        "invoice_ids": ids, "approved_entries": approved_entries,
        "fingerprint_version": fingerprint_version,
        "reviewer_user_id": str(reviewer_user_id),
        "executor_user_id": str(executor_user_id),
        "authorization_reference": authorization_reference,
        "expected_insert_count": expected_insert_count,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _utc(value: datetime) -> datetime | None:
    return value.astimezone(timezone.utc) if value.tzinfo is not None else None


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def verify_receivable_head(bundle: ReceivableSourceBundle, versions: Sequence[Any],
                           run: Any | None, *, now: datetime) -> VerifiedReceivable | None:
    """Return a display basis only for the sole current, source-matching head.

    A missing, expired, forked or drifted head leaves the full invoice in review.
    An older head can never replace a failed later version.
    """
    if not versions or run is None or _utc(now) is None:
        return None
    rows = bundle.linked_rows
    invoice, order, customer = bundle.invoice, bundle.order, bundle.customer
    try:
        actual_fingerprint = fingerprint_source_bundle(
            tenant_id=invoice.tenant_id, invoice=invoice, order=order,
            customer=customer, linked_rows=rows)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    if actual_fingerprint != bundle.fingerprint:
        return None
    if rows["settlements"]:
        return None
    ordered = sorted(versions, key=lambda row: row.version)
    for number, row in enumerate(ordered, 1):
        if (row.version != number or row.tenant_id != invoice.tenant_id
                or row.invoice_id != invoice.id or row.repair_order_id != order.id
                or row.customer_id != customer.id
                or row.supersedes_id != (ordered[number - 2].id if number > 1 else None)):
            return None
    head = ordered[-1]
    reviewed, applied, expiry = (_utc(head.reviewed_at), _utc(head.applied_at), _utc(head.valid_until))
    current = _utc(now)
    if (reviewed is None or applied is None or expiry is None or current is None
            or not reviewed <= applied <= current < expiry
            or expiry > reviewed + timedelta(days=7)):
        return None
    try:
        digest = compute_manifest_digest(tenant_id=run.tenant_id, invoice_ids=run.invoice_ids,
            approved_entries=run.approved_entries, fingerprint_version=run.fingerprint_version,
            reviewer_user_id=run.reviewer_user_id, executor_user_id=run.executor_user_id,
            authorization_reference=run.authorization_reference,
            expected_insert_count=run.expected_insert_count)
    except (ValueError, TypeError, AttributeError):
        return None
    if (head.currency != "USD" or head.fingerprint_version != FINGERPRINT_VERSION
            or head.source_fingerprint != bundle.fingerprint
            or head.reviewer_user_id == head.executor_user_id
            or head.run_id != run.id or head.tenant_id != run.tenant_id
            or run.state != "applied" or run.manifest_digest != head.manifest_digest
            or run.manifest_digest != digest
            or run.fingerprint_version != FINGERPRINT_VERSION
            or run.reviewer_user_id != head.reviewer_user_id
            or run.executor_user_id != head.executor_user_id
            or not run.authorization_reference):
        return None
    triage = triage_receivable_source(bundle)
    expected = {"open_operator_review": "verified_open", "paid_receipt_review": "verified_paid_tender"}
    if triage.review_path is None or head.decision != expected.get(triage.review_path):
        return None
    principal_cents = int(triage.principal * 100)
    confirmed_cents = 0 if head.decision == "verified_open" else principal_cents
    if (principal_cents <= 0 or head.principal_total_cents != principal_cents
            or head.confirmed_principal_cents != confirmed_cents):
        return None
    entry = run.approved_entries.get(str(invoice.id)) if isinstance(run.approved_entries, dict) else None
    if (str(invoice.id) not in run.invoice_ids
            or not isinstance(entry, dict)
            or entry != {
                "repair_order_id": str(order.id), "customer_id": str(customer.id),
                "decision": head.decision, "principal_total_cents": str(principal_cents),
                "confirmed_principal_cents": str(confirmed_cents),
                "source_fingerprint": bundle.fingerprint,
                "evidence_digest": head.evidence_digest,
                "fingerprint_version": FINGERPRINT_VERSION,
                "version": str(head.version),
                "supersedes_id": str(head.supersedes_id) if head.supersedes_id else "",
                "reviewed_at": _stamp(head.reviewed_at), "valid_until": _stamp(head.valid_until),
                "audit_reference": head.audit_reference,
            }):
        return None
    return VerifiedReceivable("reviewed_attestation", triage.principal,
                              Decimal(confirmed_cents) / 100)
