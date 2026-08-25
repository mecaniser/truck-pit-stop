#!/usr/bin/env python3
"""Stamp the real ETS invoice date onto already-imported invoices.

invoices.created_at is set at import time, not the date shown on the ETS
invoice, so nothing on the row could tell the Invoiced Hours report which
month an invoice actually belongs to on ETS's own (invoice-date) basis. The
importer now writes ets_invoiced_at going forward; this backfills the
1,250+ invoices imported before that existed, from the date already captured
in invoices.json.

    python3 backfill_invoice_ets_date.py --tenant-id <uuid> --dry-run
    python3 backfill_invoice_ets_date.py --tenant-id <uuid> --commit
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

INVOICES_FILE = Path(__file__).parent / "easytruck_sync" / "data" / "invoices.json"
IMPORT_SOURCE = "easy_truck_shop_import"


def dsn_from_env():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")


def parse_ets_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    ap.add_argument("--tenant-id", required=True)
    ap.add_argument("--json-out", help="write the stats dict as JSON to this path (for scripted callers)")
    args = ap.parse_args()

    if not INVOICES_FILE.exists():
        print(f"ERROR: {INVOICES_FILE} not found. Run scraper stage 05 first.", file=sys.stderr)
        sys.exit(1)
    invoices = json.loads(INVOICES_FILE.read_text())
    date_by_invoice_no = {
        str(v["invoiceNumber"]): parse_ets_date(v.get("invoiceDate"))
        for v in invoices.values() if v.get("invoiceNumber")
    }

    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT id, invoice_number, ets_invoiced_at FROM invoices
            WHERE tenant_id=%s AND source=%s AND deleted_at IS NULL""",
        (args.tenant_id, IMPORT_SOURCE))
    rows = cur.fetchall()

    now = datetime.now(timezone.utc)
    w = conn.cursor()
    stats = {"invoices_checked": len(rows), "no_scrape_date": 0, "already_correct": 0, "updated": 0}

    for r in rows:
        ets_no = (r["invoice_number"] or "").replace("ETSINV-", "").split("-")[0]
        d = date_by_invoice_no.get(ets_no)
        if d is None:
            stats["no_scrape_date"] += 1
            continue
        if r["ets_invoiced_at"] == d:
            stats["already_correct"] += 1
            continue
        w.execute(
            "UPDATE invoices SET ets_invoiced_at=%s, updated_at=%s WHERE id=%s",
            (d, now, r["id"]))
        stats["updated"] += 1

    print("=" * 72)
    print(f"INVOICE ETS-DATE BACKFILL {'(dry-run)' if args.dry_run else ''}")
    print("=" * 72)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if args.commit:
        conn.commit(); print("\nCOMMITTED.")
    else:
        conn.rollback(); print("\nDRY RUN — rolled back, nothing written.")
    w.close(); cur.close(); conn.close()

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(stats))


if __name__ == "__main__":
    main()
