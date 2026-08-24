#!/usr/bin/env python3
"""Populate the labor/parts split on ETS-imported repair orders.

Reports read repair_orders.total_parts_cost / total_labor_cost for the
labor-vs-parts breakdown. The importer used to hardcode parts to 0.00 and labor
to the service-history row's charge — and those rows frequently carry no charge,
so repair orders landed with BOTH at zero. In prod every August repair order had
parts $0.00 and labor $0.00, so the Part Revenue and Labor Revenue reports read
zero against ETS's $49,823.29 and $62,749.68, while total revenue still looked
right because it comes from the invoice.

ETS states the split on each invoice ("Default Labor" / "Default Matrix Parts"),
captured by lib/invoice_parse.js. Apply it to the repair order that carries the
invoice.

Only that one repair order is updated. A service with N line items imports as N
repair orders, so writing the split onto each would multiply parts and labor the
same way the duplicated invoices multiplied revenue.

    python3 backfill_ro_labor_parts_split.py --tenant-id <uuid> --dry-run
    python3 backfill_ro_labor_parts_split.py --tenant-id <uuid> --commit
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras

INVOICES_FILE = Path(__file__).parent / "easytruck_sync" / "data" / "invoices.json"


def dsn_from_env():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    ap.add_argument("--tenant-id", required=True)
    args = ap.parse_args()

    if not INVOICES_FILE.exists():
        print(f"ERROR: {INVOICES_FILE} not found. Run scraper stage 05 first.", file=sys.stderr)
        sys.exit(1)
    invoices = json.loads(INVOICES_FILE.read_text())
    # ETS invoice number -> the split, so a repair order can be matched through
    # the invoice it carries rather than through its service number.
    by_invoice_no = {}
    for svc, d in invoices.items():
        num = d.get("invoiceNumber")
        if num and (d.get("laborTotal") is not None or d.get("partsTotal") is not None):
            by_invoice_no[str(num)] = d

    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT r.id, r.order_number, r.total_parts_cost, r.total_labor_cost,
                  i.invoice_number
             FROM repair_orders r
             JOIN invoices i ON i.repair_order_id = r.id
            WHERE r.tenant_id = %s AND r.source = 'easy_truck_shop_import'
              AND i.deleted_at IS NULL AND i.status <> 'cancelled'""",
        (args.tenant_id,))
    rows = cur.fetchall()

    now = datetime.now(timezone.utc)
    w = conn.cursor()
    stats = {"examined": len(rows), "updated": 0, "no_split_data": 0, "already_correct": 0}
    added_parts = added_labor = Decimal("0.00")

    for r in rows:
        num = (r["invoice_number"] or "").replace("ETSINV-", "").split("-")[0]
        d = by_invoice_no.get(num)
        if not d:
            stats["no_split_data"] += 1
            continue
        parts = Decimal(str(d.get("partsTotal") or 0)).quantize(Decimal("0.01"))
        labor = Decimal(str(d.get("laborTotal") or 0)).quantize(Decimal("0.01"))
        if (r["total_parts_cost"] or 0) == parts and (r["total_labor_cost"] or 0) == labor:
            stats["already_correct"] += 1
            continue
        added_parts += parts - Decimal(str(r["total_parts_cost"] or 0))
        added_labor += labor - Decimal(str(r["total_labor_cost"] or 0))
        w.execute(
            """UPDATE repair_orders SET total_parts_cost=%s, total_labor_cost=%s, updated_at=%s
                WHERE id=%s""",
            (parts, labor, now, r["id"]))
        stats["updated"] += 1

    print("=" * 74)
    print(f"REPAIR ORDER LABOR/PARTS BACKFILL {'(dry-run)' if args.dry_run else ''}")
    print("=" * 74)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  parts total change: ${added_parts:,.2f}")
    print(f"  labor total change: ${added_labor:,.2f}")

    cur.execute(
        """SELECT coalesce(sum(r.total_parts_cost),0) p, coalesce(sum(r.total_labor_cost),0) l
             FROM invoices i JOIN repair_orders r ON r.id = i.repair_order_id
            WHERE i.tenant_id=%s AND i.status='paid' AND i.deleted_at IS NULL
              AND date(i.paid_at) >= date_trunc('month', now())::date""",
        (args.tenant_id,))
    m = cur.fetchone()
    print(f"  THIS MONTH after: parts ${float(m['p']):,.2f}  labor ${float(m['l']):,.2f}")

    if args.commit:
        conn.commit(); print("\nCOMMITTED.")
    else:
        conn.rollback(); print("\nDRY RUN — rolled back, nothing written.")
    w.close(); cur.close(); conn.close()


if __name__ == "__main__":
    main()
