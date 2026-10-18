"""Pure DB-135 reviewed write-set construction; no database or file writes.

Source triage is never review evidence. Callers must obtain independent human
review and a private evidence digest before supplying any proposed decision.
This builder does not authorize a production apply or establish cohort coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from uuid import UUID

from app.services.receivable_attestation_eligibility import triage_receivable_source
from app.services.receivable_attestation_fingerprint import FINGERPRINT_VERSION, fingerprint_source_bundle
from app.services.receivable_attestation_reader import compute_manifest_digest
from app.services.receivable_attestation_source import ReceivableSourceBundle


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_OPAQUE = re.compile(r"[A-Za-z0-9._:-]{1,255}\Z")
_DECISION_FOR_PATH = {
    "open_operator_review": "verified_open",
    "paid_receipt_review": "verified_paid_tender",
}


@dataclass(frozen=True)
class ReviewedDecision:
    invoice_id: UUID
    decision: str
    source_fingerprint: str
    evidence_digest: str
    audit_reference: str
    reviewed_at: datetime
    valid_until: datetime
    version: int = 1
    supersedes_id: UUID | None = None


@dataclass(frozen=True)
class ReviewedWriteSet:
    invoice_ids: list[str]
    approved_entries: dict[str, dict[str, str]]
    manifest_digest: str


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Review times must be timezone aware")
    return value.astimezone(timezone.utc)


def _stamp(value: datetime) -> str:
    return _utc(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_reviewed_write_set(*, tenant_id: UUID,
                             decisions: list[ReviewedDecision],
                             bundles: dict[UUID, ReceivableSourceBundle],
                             reviewer_user_id: UUID, executor_user_id: UUID,
                             authorization_reference: str,
                             now: datetime) -> ReviewedWriteSet:
    """Match explicit reviewed decisions to a frozen source snapshot.

    This is only a canonical candidate for private review. The later writer
    must verify actors/authorization, all 32 dispositions, current source and
    predecessor lineage under the tenant financial lock before any insert.
    """
    current = _utc(now)
    if (not isinstance(tenant_id, UUID) or not isinstance(reviewer_user_id, UUID)
            or not isinstance(executor_user_id, UUID)
            or not decisions or len(decisions) > 100 or reviewer_user_id == executor_user_id
            or not isinstance(authorization_reference, str)
            or not _OPAQUE.fullmatch(authorization_reference)):
        raise ValueError("Invalid reviewed write-set scope or actors")
    if len({item.invoice_id for item in decisions}) != len(decisions):
        raise ValueError("Duplicate invoice in reviewed write set")
    if set(bundles) != {item.invoice_id for item in decisions}:
        raise ValueError("Source/write-set invoice mismatch")
    entries: dict[str, dict[str, str]] = {}
    for item in decisions:
        if (not isinstance(item.invoice_id, UUID)
                or type(item.version) is not int
                or (item.supersedes_id is not None and not isinstance(item.supersedes_id, UUID))):
            raise ValueError("Invalid reviewed version or predecessor")
        bundle = bundles[item.invoice_id]
        invoice, order, customer = bundle.invoice, bundle.order, bundle.customer
        if (invoice.id != item.invoice_id or invoice.tenant_id != tenant_id
                or order.tenant_id != tenant_id or customer.tenant_id != tenant_id
                or invoice.repair_order_id != order.id
                or (invoice.billed_customer_id or order.customer_id) != customer.id):
            raise ValueError("Source identity or tenant mismatch")
        actual = fingerprint_source_bundle(
            tenant_id=tenant_id, invoice=invoice, order=order,
            customer=customer, linked_rows=bundle.linked_rows)
        if actual != bundle.fingerprint or actual != item.source_fingerprint:
            raise ValueError("Reviewed source fingerprint changed")
        triage = triage_receivable_source(bundle)
        if (triage.review_path is None
                or item.decision != _DECISION_FOR_PATH.get(triage.review_path)):
            raise ValueError("Source is not eligible for reviewed decision")
        reviewed, expiry = _utc(item.reviewed_at), _utc(item.valid_until)
        if (reviewed > current or expiry <= current or expiry > reviewed + timedelta(days=7)
                or not isinstance(item.evidence_digest, str)
                or not _DIGEST.fullmatch(item.evidence_digest)
                or not isinstance(item.audit_reference, str)
                or not _OPAQUE.fullmatch(item.audit_reference)
                or item.version < 1
                or (item.version == 1) != (item.supersedes_id is None)):
            raise ValueError("Invalid reviewed evidence or validity")
        principal_cents = int(triage.principal * 100)
        if principal_cents <= 0:
            raise ValueError("Invalid reviewed principal")
        confirmed_cents = principal_cents if item.decision == "verified_paid_tender" else 0
        entries[str(item.invoice_id)] = {
            "repair_order_id": str(order.id), "customer_id": str(customer.id),
            "decision": item.decision,
            "principal_total_cents": str(principal_cents),
            "confirmed_principal_cents": str(confirmed_cents),
            "source_fingerprint": actual,
            "evidence_digest": item.evidence_digest,
            "fingerprint_version": FINGERPRINT_VERSION,
            "version": str(item.version),
            "supersedes_id": str(item.supersedes_id) if item.supersedes_id else "",
            "reviewed_at": _stamp(reviewed), "valid_until": _stamp(expiry),
            "audit_reference": item.audit_reference,
        }
    invoice_ids = sorted(entries)
    digest = compute_manifest_digest(
        tenant_id=tenant_id, invoice_ids=invoice_ids,
        approved_entries=entries, fingerprint_version=FINGERPRINT_VERSION,
        reviewer_user_id=reviewer_user_id, executor_user_id=executor_user_id,
        authorization_reference=authorization_reference,
        expected_insert_count=len(invoice_ids))
    return ReviewedWriteSet(invoice_ids, entries, digest)
