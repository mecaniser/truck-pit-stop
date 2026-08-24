#!/usr/bin/env python3
"""Reconcile imported payments against what Easy Truck Shop actually recorded.

The importer's payment sync originally paired an existing payment with a scraped
one on (amount, date). Payments written by an earlier import carry that run's
timestamp rather than the date ETS recorded, so they never matched and were
re-inserted: 42 invoices ended up with doubled payments and $45,599 of money that
was never received.

This makes each invoice's payments match ETS's list exactly, as a multiset of
amounts — retiring extras that have no counterpart. Safe to re-run; an invoice
already in agreement is left alone.

    python3 reconcile_ets_payments.py --tenant-id <uuid> --dry-run
    python3 reconcile_ets_payments.py --tenant-id <uuid> --commit
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
    scraped = json.loads(INVOICES_FILE.read_text())
    by_no = {str(v["invoiceNumber"]): v for v in scraped.values() if v.get("invoiceNumber")}

    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT id, invoice_number, total_amount, status FROM invoices
            WHERE tenant_id=%s AND source=%s AND deleted_at IS NULL AND status <> 'cancelled'""",
        (args.tenant_id, "easy_truck_shop_import"))
    invoices = cur.fetchall()

    now = datetime.now(timezone.utc)
    w = conn.cursor()
    stats = {"invoices_checked": len(invoices), "invoices_corrected": 0,
             "payments_retired": 0, "status_reverted": 0, "totals_corrected": 0}
    money_removed = Decimal("0.00")

    for inv in invoices:
        ets_no = (inv["invoice_number"] or "").replace("ETSINV-", "").split("-")[0]
        d = by_no.get(ets_no)
        if not d:
            continue

        # Invoice financials must agree with ETS, because total_amount is the
        # denominator when a payment is attributed pro rata. A stale total makes
        # a part payment look like it settles the whole invoice: ETSINV-1189 held
        # $625.47 against ETS's $2,648.53, so a $625 payment recognised all
        # $2,446.68 of its parts instead of a quarter of them. Legacy invoices
        # had their parts backfilled without their totals being corrected.
        ets_total = Decimal(str(d.get("total") or 0))
        if ets_total > 0 and abs(Decimal(str(inv["total_amount"] or 0)) - ets_total) > Decimal("0.01"):
            w.execute(
                """UPDATE invoices SET total_amount=%s, subtotal=%s, tax_amount=%s,
                       shop_supplies_amount=%s, updated_at=%s
                    WHERE id=%s""",
                (ets_total,
                 Decimal(str(d.get("subtotal") or 0)),
                 Decimal(str(d.get("tax") or 0)),
                 Decimal(str(d.get("fees") or 0)),
                 now, inv["id"]))
            stats["totals_corrected"] += 1

        want = [Decimal(str(p["amount"])) for p in (d.get("payments") or [])]

        cur.execute(
            """SELECT id, amount, payment_number FROM payments
                WHERE invoice_id=%s AND deleted_at IS NULL
             ORDER BY created_at, payment_number""", (inv["id"],))
        rows = cur.fetchall()

        remaining = list(want)
        extras = []
        for r in rows:
            amt = Decimal(str(r["amount"]))
            if amt in remaining:
                remaining.remove(amt)
            else:
                extras.append(r)
        if not extras:
            continue

        ids = [r["id"] for r in extras]
        money_removed += sum(Decimal(str(r["amount"])) for r in extras)
        w.execute(
            """UPDATE payments SET status='failed', deleted_at=%s, updated_at=%s,
                   notes=coalesce(notes,'') ||
                         ' [retired: no matching payment in Easy Truck Shop]'
                WHERE id = ANY(%s::uuid[])""",
            (now, now, ids))
        stats["payments_retired"] += len(ids)
        stats["invoices_corrected"] += 1

        # An invoice only marked paid because of the phantom money must go back.
        kept = sum(Decimal(str(r["amount"])) for r in rows if r["id"] not in ids)
        total = Decimal(str(inv["total_amount"] or 0))
        if inv["status"] == "paid" and kept < (total - Decimal("0.01")):
            w.execute(
                "UPDATE invoices SET status='sent', paid_at=NULL, updated_at=%s WHERE id=%s",
                (now, inv["id"]))
            stats["status_reverted"] += 1

    print("=" * 72)
    print(f"ETS PAYMENT RECONCILE {'(dry-run)' if args.dry_run else ''}")
    print("=" * 72)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  money removed from totals: ${money_removed:,.2f}")

    if args.commit:
        conn.commit(); print("\nCOMMITTED.")
    else:
        conn.rollback(); print("\nDRY RUN — rolled back, nothing written.")
    w.close(); cur.close(); conn.close()


if __name__ == "__main__":
    main()
