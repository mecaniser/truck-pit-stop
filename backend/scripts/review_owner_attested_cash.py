"""Install an exact owner-attested historical-cash review; never calls providers.

The default scope pass is read-only. Apply only its reviewed manifest and exact
SHA-256. This operation records no payment and preserves all original history.
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text

from app.db.models.invoice import Invoice
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.provider_outbox import ProviderOutboxEvent
from app.db.session import AsyncSessionLocal
from app.services.historical_export_hold import digest, rows_digest
from app.services.invoice_accounting_policy import HISTORICAL_HOLD, locked_policy
from app.services.invoice_cash_service import (
    OWNER_CASH_REVIEW_KEY, cash_eligibility, event_history_digest,
    owner_attested_ancestor_snapshot, owner_cash_review_target, valid_owner_cash_review,
)


async def targets(db, scope, *, lock=False):
    invoice = await db.scalar(select(Invoice).where(
        Invoice.id == UUID(scope["invoice_id"]),
        Invoice.tenant_id == UUID(scope["tenant_id"]),
    ).execution_options(populate_existing=True))
    if invoice is None:
        raise ValueError("Exact tenant invoice not found")
    if lock:
        await locked_policy(db, invoice, nowait=True)
        await db.refresh(invoice, attribute_names=[column.name for column in Invoice.__table__.columns])
    query = select(ProviderOutboxEvent).where(
        ProviderOutboxEvent.id == UUID(scope["event_id"]),
        ProviderOutboxEvent.tenant_id == invoice.tenant_id,
        ProviderOutboxEvent.aggregate_id == invoice.id,
    )
    if lock:
        query = query.with_for_update(nowait=True)
    event = await db.scalar(query.execution_options(populate_existing=True))
    if event is None:
        raise ValueError("Exact invoice event not found")
    return invoice, event


async def prepare(db, scope):
    if scope.get("attestation") != "no_provider_payment_cash_received":
        raise ValueError("Exact owner cash attestation is required")
    if scope.get("provider_verified") is not False:
        raise ValueError("Owner attestation must not claim provider verification")
    evidence_sha = scope.get("evidence_manifest_sha256", "")
    if len(evidence_sha) != 64 or any(c not in "0123456789abcdef" for c in evidence_sha):
        raise ValueError("Exact lowercase SHA-256 evidence digest is required")
    if not str(scope.get("reviewer", "")).strip() or not str(scope.get("attestation_source", "")).strip():
        raise ValueError("Reviewer and attestation source are required")

    invoice, event = await targets(db, scope)
    if invoice.accounting_policy != HISTORICAL_HOLD or invoice.supersedes_invoice_id is None:
        raise ValueError("Owner review is limited to an exact held replacement invoice")
    if not owner_cash_review_target(event, invoice):
        raise ValueError("Owner review is limited to an exact ambiguous QuickBooks export hold")
    chain, ancestor_reviews = [], []
    seen = {invoice.id}
    parent_id = invoice.supersedes_invoice_id
    while parent_id:
        if parent_id in seen:
            raise ValueError("Cyclic invoice ancestry")
        seen.add(parent_id)
        chain.append(str(parent_id))
        parent = await db.scalar(select(Invoice).where(
            Invoice.id == parent_id, Invoice.tenant_id == invoice.tenant_id))
        if parent is None:
            raise ValueError("Missing tenant ancestor")
        snapshot = await owner_attested_ancestor_snapshot(db, parent)
        if snapshot is None:
            raise ValueError("Ancestor has unreviewable provider or money history")
        ancestor_reviews.append({
            "schema": "db048-owner-attested-ancestor-review-v1",
            "invoice_id": str(parent.id),
            "snapshot": snapshot,
        })
        parent_id = parent.supersedes_invoice_id

    marker = {
        "schema": "db048-owner-cash-review-v1",
        "tenant_id": str(invoice.tenant_id),
        "invoice_id": str(invoice.id),
        "invoice_history_sha256": event_history_digest(invoice),
        "event_id": str(event.id),
        "event_type": event.event_type,
        "event_status": event.status,
        "attempt_count": event.attempt_count,
        "original_history_sha256": event_history_digest(event),
        "attestation": scope["attestation"],
        "attestation_source": scope["attestation_source"].strip(),
        "provider_verified": False,
        "evidence_manifest_sha256": evidence_sha,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewer": scope["reviewer"].strip(),
        "supersedes_chain": chain,
        "ancestor_reviews": ancestor_reviews,
    }
    original = event.payload
    try:
        with db.no_autoflush:
            event.payload = {**(original or {}), OWNER_CASH_REVIEW_KEY: marker}
            if not valid_owner_cash_review(event, invoice):
                raise ValueError("Event does not qualify for bounded owner review")
            settlement = await db.scalar(select(InvoiceSettlement).where(
                InvoiceSettlement.tenant_id == invoice.tenant_id,
                InvoiceSettlement.invoice_id == invoice.id))
            if settlement is None:
                raise ValueError("Existing settlement required; review cannot create financial rows")
            reason, _ = await cash_eligibility(db, invoice, settlement)
            if reason:
                raise ValueError(reason)
    finally:
        event.payload = original
    return {
        "schema": "db048-owner-cash-manifest-v1",
        "scope": scope,
        "invoice_sha256": rows_digest([invoice]),
        "marker": marker,
    }


async def apply_review(db, manifest, expected_sha256):
    if digest(manifest) != expected_sha256 or manifest.get("schema") != "db048-owner-cash-manifest-v1":
        raise ValueError("Reviewed manifest digest/schema mismatch")
    invoice, event = await targets(db, manifest["scope"], lock=True)
    if rows_digest([invoice]) != manifest["invoice_sha256"]:
        raise ValueError("Invoice changed after review")
    marker = manifest["marker"]
    existing = (event.payload or {}).get(OWNER_CASH_REVIEW_KEY)
    if existing is not None and existing != marker:
        raise ValueError("Conflicting review cannot be overwritten")
    before = event_history_digest(event)
    event.payload = {**(event.payload or {}), OWNER_CASH_REVIEW_KEY: marker}
    if not valid_owner_cash_review(event, invoice):
        raise ValueError("Original event history changed after review")
    settlement = await db.scalar(select(InvoiceSettlement).where(
        InvoiceSettlement.tenant_id == invoice.tenant_id,
        InvoiceSettlement.invoice_id == invoice.id))
    if settlement is None:
        raise ValueError("Existing settlement required")
    reason, _ = await cash_eligibility(db, invoice, settlement, lock=True)
    if reason:
        raise ValueError(reason)
    await db.flush()
    return {
        "event_id": str(event.id),
        "before_history_sha256": before,
        "after_history_sha256": event_history_digest(event),
        "manifest_sha256": expected_sha256,
        "changed_fields": [] if existing else [f"payload.{OWNER_CASH_REVIEW_KEY}", "updated_at"],
        "provider_calls": 0,
        "payment_recorded": False,
    }


async def run(args):
    async with AsyncSessionLocal() as db:
        try:
            if args.apply:
                result = await apply_review(db, json.loads(Path(args.apply).read_text()), args.sha256)
                await db.commit()
            else:
                await db.execute(text("SET TRANSACTION READ ONLY"))
                manifest = await prepare(db, json.loads(Path(args.scope).read_text()))
                await db.rollback()
                result = {"sha256": digest(manifest), "manifest": manifest}
            print(json.dumps(result, indent=2))
        except BaseException:
            await db.rollback()
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scope")
    mode.add_argument("--apply")
    parser.add_argument("--sha256")
    asyncio.run(run(parser.parse_args()))
