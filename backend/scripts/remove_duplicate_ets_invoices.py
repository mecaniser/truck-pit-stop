#!/usr/bin/env python3
"""Remove duplicate invoices created by the ETS invoice backfill.

An Easy Truck Shop service carries ONE invoice, but a service with N line items
imports as N repair orders here (see build_records in import_to_truckpitstop.py).
The backfill attached the full invoice to each of them, so service #1217 — ten
line items — booked its $6,950 ten times. The clash was "resolved" by suffixing
the invoice number (ETSINV-1193-ETS-1217-118833-2), which created the duplicate
rather than preventing it.

Prod effect: 1861 invoice rows for 1115 real ETS invoices, all-time revenue
reported as $2.70M against an actual $1.13M.

This retires the suffixed copies, keeping one invoice per ETS invoice number —
preferring the row on the unsuffixed repair order, then the earliest. Cancelling
(not just soft-deleting) matters: the revenue reports filter on status='paid'
and do NOT filter deleted_at, so a soft delete alone would leave the money in
the totals.

Repair orders are left alone. Consolidating N-per-service repair orders into one
is a separate, larger modelling change.

    python3 remove_duplicate_ets_invoices.py --tenant-id <uuid> --dry-run
    python3 remove_duplicate_ets_invoices.py --tenant-id <uuid> --commit
"""
import argparse
import os
import re
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras


def dsn_from_env():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")


def ets_base(invoice_number):
    """"ETSINV-1193-ETS-1217-118833-2" -> "ETSINV-1193". The suffix is the
    repair-order number the backfill appended on a clash."""
    m = re.match(r"^(ETSINV-[^-]+)", invoice_number or "")
    return m.group(1) if m else invoice_number


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    ap.add_argument("--tenant-id", required=True)
    args = ap.parse_args()

    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT i.id, i.invoice_number, i.total_amount, i.status, i.paid_at, i.created_at,
                  r.order_number,
                  (SELECT count(*) FROM payments p WHERE p.invoice_id = i.id) AS pay_rows
             FROM invoices i JOIN repair_orders r ON r.id = i.repair_order_id
            WHERE i.tenant_id = %s AND i.source = 'easy_truck_shop_import'
              AND i.deleted_at IS NULL AND i.status <> 'cancelled'""",
        (args.tenant_id,))
    rows = cur.fetchall()

    groups = {}
    for r in rows:
        groups.setdefault(ets_base(r["invoice_number"]), []).append(r)
    dups = {k: v for k, v in groups.items() if len(v) > 1}

    now = datetime.now(timezone.utc)
    w = conn.cursor()
    stats = {"ets_invoices_with_duplicates": 0, "invoices_cancelled": 0,
             "payments_cancelled": 0}
    removed_value = 0.0

    for base, group in sorted(dups.items()):
        # Keep the invoice whose number was never suffixed (it sits on the first
        # repair order of the service); fall back to the earliest row.
        keeper = sorted(group, key=lambda r: (r["invoice_number"] != base, r["created_at"]))[0]
        losers = [r for r in group if r["id"] != keeper["id"]]
        stats["ets_invoices_with_duplicates"] += 1
        removed_value += sum(float(l["total_amount"] or 0) for l in losers)

        loser_ids = [l["id"] for l in losers]
        w.execute(
            """UPDATE payments SET status='failed', deleted_at=%s, updated_at=%s
                WHERE invoice_id = ANY(%s::uuid[]) AND deleted_at IS NULL""",
            (now, now, loser_ids))
        stats["payments_cancelled"] += w.rowcount
        w.execute(
            """UPDATE invoices SET status='cancelled', deleted_at=%s, updated_at=%s,
                   void_reason='Duplicate created by the ETS invoice backfill: one ETS '
                               'service invoice was attached to every repair order of '
                               'that service.'
                WHERE id = ANY(%s::uuid[])""",
            (now, now, loser_ids))
        stats["invoices_cancelled"] += w.rowcount

    print("=" * 74)
    print(f"DUPLICATE ETS INVOICE CLEANUP {'(dry-run)' if args.dry_run else ''}")
    print("=" * 74)
    print(f"  active ETS invoice rows examined: {len(rows)}")
    print(f"  distinct ETS invoices:            {len(groups)}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  revenue removed from totals:      ${removed_value:,.2f}")

    cur.execute(
        """SELECT coalesce(sum(total_amount),0) FROM invoices
            WHERE tenant_id=%s AND source='easy_truck_shop_import'
              AND status='paid' AND deleted_at IS NULL""",
        (args.tenant_id,))
    print(f"  paid ETS revenue after cleanup:   ${float(cur.fetchone()['coalesce']):,.2f}")

    if args.commit:
        conn.commit(); print("\nCOMMITTED.")
    else:
        conn.rollback(); print("\nDRY RUN — rolled back, nothing written.")
    w.close(); cur.close(); conn.close()


if __name__ == "__main__":
    main()
