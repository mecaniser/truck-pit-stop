"""Write a private, read-only DB-135 source review for one explicit tenant.

This report is triage, not receipt/operator proof, a reviewed attestation, or
authorization to apply one. It never calls a financial writer. Run only with a
deliberately selected database and tenant; keep the 0600 output outside Git.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.invoice import Invoice, InvoiceStatus
from app.db.models.invoice_settlement import InvoiceSettlement
from app.db.models.tenant import Tenant
from app.db.session import AsyncSessionLocal
from app.services.customer_receivables import bucket_for
from app.services.receivable_attestation_eligibility import triage_receivable_source
from app.services.receivable_attestation_source import load_receivable_source


MAX_REVIEW_INVOICES = 100
ALLOWED_SCHEMA = {"178_merge_maintenance_bindings", "179_db135_receivables"}


async def collect_source_review(db: AsyncSession, *, tenant_id: UUID,
                                expected_count: int) -> dict:
    """Inspect all missing-settlement native candidates in one frozen snapshot."""
    if type(expected_count) is not int or not 1 <= expected_count <= MAX_REVIEW_INVOICES:
        raise ValueError("Expected review cohort count is required and bounded")
    await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
    await db.execute(text("SET LOCAL statement_timeout = '30s'"))
    await db.execute(text("SET LOCAL lock_timeout = '2s'"))
    revision = list((await db.execute(text(
        "SELECT version_num FROM alembic_version ORDER BY version_num"
    ))).scalars())
    if len(revision) != 1 or revision[0] not in ALLOWED_SCHEMA:
        raise RuntimeError("DB-135 source review requires known schema head")
    tenant = (await db.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one_or_none()
    if tenant is None:
        raise ValueError("Review tenant unavailable")
    observed = (await db.execute(text("SELECT transaction_timestamp()"))).scalar_one()
    read_only = (await db.execute(text("SHOW transaction_read_only"))).scalar_one().lower()
    isolation = (await db.execute(text("SHOW transaction_isolation"))).scalar_one().lower()
    if read_only != "on" or isolation != "repeatable read":
        raise RuntimeError("DB-135 source review requires repeatable-read read-only")
    no_settlement = ~exists(select(InvoiceSettlement.id).where(
        InvoiceSettlement.tenant_id == tenant_id,
        InvoiceSettlement.invoice_id == Invoice.id,
    ))
    candidates = list((await db.execute(select(Invoice).where(
        Invoice.tenant_id == tenant_id,
        Invoice.deleted_at.is_(None), Invoice.voided_at.is_(None),
        Invoice.is_internal.is_(False),
        Invoice.status.in_({InvoiceStatus.SENT, InvoiceStatus.OVERDUE, InvoiceStatus.PAID}),
        Invoice.source.is_distinct_from("easy_truck_shop_import"),
        Invoice.accounting_policy != "historical_export_hold",
        no_settlement,
    ).order_by(Invoice.id).limit(MAX_REVIEW_INVOICES + 1))).scalars())
    if len(candidates) != expected_count:
        raise RuntimeError("Missing-settlement cohort changed or exceeds safe bound")
    as_of = observed.astimezone(ZoneInfo(tenant.timezone)).date()
    rows: list[dict] = []
    for invoice in candidates:
        source = await load_receivable_source(db, tenant_id=tenant_id, invoice_id=invoice.id)
        triage = triage_receivable_source(source)
        due = (invoice.due_date.replace(tzinfo=invoice.due_date.tzinfo or timezone.utc)
               .astimezone(ZoneInfo(tenant.timezone)).date()) if invoice.due_date else None
        rows.append({
            "invoice_id": str(invoice.id), "repair_order_id": str(source.order.id),
            "customer_id": str(source.customer.id),
            "status": invoice.status.value,
            "source_fingerprint": source.fingerprint,
            "principal_cents": int(triage.principal * 100),
            "completed_payment_cents": int(triage.completed_payment_total * 100),
            "due_date": due.isoformat() if due else None,
            "potential_bucket": bucket_for(due, as_of),
            "review_path": triage.review_path,
            "hold_reasons": list(triage.hold_reasons),
            "linked_row_counts": {kind: len(items) for kind, items in source.linked_rows.items()},
            "operator_or_receipt_proof": "not_in_database_review",
            "disposition": "unresolved",
        })
    envelope = {
        "version": "db135-private-source-review-v1",
        "tenant_id": str(tenant_id), "observed_at": observed.isoformat(),
        "schema_head": revision[0], "read_only": True,
        "isolation": "repeatable read", "as_of_date": as_of.isoformat(),
        "invoice_count": len(rows),
        "source_classes": dict(Counter(row["status"] for row in rows)),
        "review_paths": dict(Counter(row["review_path"] or "held" for row in rows)),
        "cohort_digest": hashlib.sha256(json.dumps(
            [(row["invoice_id"], row["source_fingerprint"]) for row in rows],
            separators=(",", ":")).encode()).hexdigest(),
        "rows": rows,
    }
    return envelope


def save_private_review(path: Path, report: dict) -> str:
    """Create one private artifact without following links or overwriting files."""
    if not path.is_absolute() or not report.get("read_only"):
        raise ValueError("Private review requires absolute output and read-only source")
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    old_umask = os.umask(0o077)
    try:
        fd = os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    finally:
        os.umask(old_umask)
    return hashlib.sha256(payload).hexdigest()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only private DB-135 source review")
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--expected-count", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    async with AsyncSessionLocal() as db:
        try:
            report = await collect_source_review(db, tenant_id=args.tenant_id,
                                                 expected_count=args.expected_count)
        finally:
            await db.rollback()
    digest = save_private_review(args.output, report)
    print(f"Private review created: count={report['invoice_count']} sha256={digest}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
