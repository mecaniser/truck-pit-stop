#!/usr/bin/env python3
"""Give imported repair orders their real labor hours.

Reports read Labor.hours for "Invoiced Hours". The importer sourced hours from
the service-history row's clock duration, which is "0:00 Minutes" on every row
this shop has (no time-clocking is in use — ETS's own "Clocked Hours" tile is
0.0), so it fell back to a hardcoded 1.00h per repair order. That read 117h
against ETS's 683.2h for the same month.

The real figure comes from a field ETS itself uses to compute "Invoiced Hours"
server-side but never renders on the invoice page: service_item.charged, present
on every labor line regardless of billing method. Stage 05 now captures it as
laborHours (see lib/invoice_json.js for how it was derived and verified — 683.10h
against ETS's 683.2h for August, a 0.1h rounding difference).

Only the repair order carrying that service's invoice is updated, and only its
existing Labor row — never inserts a new one. A service with N line items
imports as N repair orders; writing hours to each would multiply the total the
same way duplicated invoices multiplied revenue.

    python3 backfill_ro_labor_hours.py --tenant-id <uuid> --dry-run
    python3 backfill_ro_labor_hours.py --tenant-id <uuid> --commit
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

import psycopg2
import psycopg2.extras

psycopg2.extras.register_uuid()

INVOICES_FILE = Path(__file__).parent / "easytruck_sync" / "data" / "invoices.json"
IMPORT_SOURCE = "easy_truck_shop_import"


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
    ap.add_argument("--json-out", help="write the stats dict as JSON to this path (for scripted callers)")
    args = ap.parse_args()

    if not INVOICES_FILE.exists():
        print(f"ERROR: {INVOICES_FILE} not found. Run scraper stage 05 first.", file=sys.stderr)
        sys.exit(1)
    invoices = json.loads(INVOICES_FILE.read_text())
    hours_by_invoice_no = {
        str(v["invoiceNumber"]): v["laborHours"]
        for v in invoices.values()
        if v.get("invoiceNumber") and v.get("laborHours") is not None
    }

    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT r.id AS ro_id, i.invoice_number, r.total_labor_cost,
                  l.id AS labor_id, l.hours AS current_hours
             FROM invoices i JOIN repair_orders r ON r.id = i.repair_order_id
             JOIN labor l ON l.repair_order_id = r.id AND l.line_type = 'manual'
            WHERE i.tenant_id=%s AND r.source=%s AND i.deleted_at IS NULL
              AND i.status <> 'cancelled'
            ORDER BY r.id, l.created_at, l.id""",
        (args.tenant_id, IMPORT_SOURCE))

    # Some repair orders already carry more than one 'manual' labor row (534 on
    # dev, predating this script). Joining without grouping updates EVERY one of
    # them to the full new total, multiplying an RO's counted hours by however
    # many rows it had — caught only after running: 530 ROs had all their labor
    # rows share one identical (wrong) hours value post-backfill. Group by
    # repair order first; only the earliest row gets the real total, any others
    # are zeroed so the SUM stays correct without deleting rows other tables
    # (parts_usage.source_line_id) may reference.
    by_ro: Dict[str, List] = {}
    for r in cur.fetchall():
        by_ro.setdefault(r["ro_id"], []).append(r)

    now = datetime.now(timezone.utc)
    w = conn.cursor()
    stats = {"repair_orders": len(by_ro), "no_scrape_data": 0, "already_correct": 0,
             "updated": 0, "extra_rows_zeroed": 0}
    hours_added = Decimal("0")

    for ro_id, labor_rows in by_ro.items():
        primary, extras = labor_rows[0], labor_rows[1:]
        ets_no = (primary["invoice_number"] or "").replace("ETSINV-", "").split("-")[0]
        new_hours = hours_by_invoice_no.get(ets_no)
        if new_hours is None:
            stats["no_scrape_data"] += 1
            continue
        new_hours = Decimal(str(new_hours)).quantize(Decimal("0.01"))
        current_total = sum(Decimal(str(r["current_hours"] or 0)) for r in labor_rows)
        # Multi-row ROs (534 on dev predate this script; the repair-order
        # consolidation issue in docs/ets-repair-order-consolidation.md means
        # more keep appearing) never satisfied len(labor_rows) == 1, so a
        # nightly rerun re-wrote the same values to the same rows forever —
        # ~500 "updates" every single night that changed nothing, tripping
        # the automation's own volume guardrail. Check the primary against
        # the target and every extra against zero instead of gating on row
        # count, so a row already in the correct shape is actually skipped.
        primary_hours = Decimal(str(primary["current_hours"] or 0))
        primary_correct = abs(new_hours - primary_hours) < Decimal("0.01")
        extras_zeroed = all(Decimal(str(e["current_hours"] or 0)) == 0 for e in extras)
        if primary_correct and extras_zeroed:
            stats["already_correct"] += 1
            continue

        new_rate = None
        labor_cost = Decimal(str(primary["total_labor_cost"] or 0))
        if new_hours > 0:
            new_rate = (labor_cost / new_hours).quantize(Decimal("0.01"))
            w.execute(
                "UPDATE labor SET hours=%s, hourly_rate=%s, updated_at=%s WHERE id=%s",
                (new_hours, new_rate, now, primary["labor_id"]))
        else:
            w.execute(
                "UPDATE labor SET hours=%s, updated_at=%s WHERE id=%s",
                (new_hours, now, primary["labor_id"]))
        for e in extras:
            w.execute(
                "UPDATE labor SET hours=0, updated_at=%s WHERE id=%s",
                (now, e["labor_id"]))
        stats["extra_rows_zeroed"] += len(extras)
        hours_added += (new_hours - current_total)
        stats["updated"] += 1

    print("=" * 74)
    print(f"REPAIR ORDER LABOR HOURS BACKFILL {'(dry-run)' if args.dry_run else ''}")
    print("=" * 74)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  net hours change: {hours_added:+.2f}")

    if args.commit:
        conn.commit(); print("\nCOMMITTED.")
    else:
        conn.rollback(); print("\nDRY RUN — rolled back, nothing written.")
    w.close(); cur.close(); conn.close()

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({**stats, "hours_added": float(hours_added)}))


if __name__ == "__main__":
    main()
