#!/usr/bin/env python3
"""Correct invoice_number on repair orders imported before invoiceNumber capture.

_create_invoice_and_payments falls back to the ETS *service* number when the
scrape has no invoiceNumber for that service: `ets_invoice_no = invoiceNumber
or service_no`. A handful of repair orders (imported before stage 05 started
capturing invoiceNumber) got stamped "ETSINV-{service_no}" this way instead of
"ETSINV-{real ETS invoice number}".

Every downstream script that maps a DB invoice back to scrape data does it by
stripping "ETSINV-" and matching the remaining digits against ETS's real
invoice numbers (see backfill_invoice_ets_date.py, backfill_ro_labor_hours.py,
_sync_payments_for_existing_invoices). For these legacy rows the stored digits
are a service number, not an invoice number — and ETS's numbering ranges
overlap, so the digits can coincidentally equal a real, unrelated invoice's
number. That silently pulled in the wrong invoice's date and hours: e.g.
service 1268's invoice (real number 1213, dated 08/08, 5h) was stored as
"ETSINV-1268", which matched the real invoice numbered 1268 (an unrelated
service, dated 08/17, 0h) — a 5h undercount hiding inside a coincidental
digit collision. Found via a full August ground-truth diff: 683.10h in the
scrape vs 665.50h in the DB, with the entire 17.6h gap traced to exactly
these rows.

This renames invoice_number using repair_orders.order_number (which reliably
encodes the service number: "ETS-{service_no}-...") to look up the service in
the scrape and find its real invoiceNumber, only when the two differ and the
target number isn't already taken by another invoice. Run this BEFORE
backfill_invoice_ets_date.py / backfill_ro_labor_hours.py so their digit-match
lookups land on the right row.

payments.payment_number is derived from invoice_number at creation time
("{invoice_number}-PAY-{n}") and does not get renamed along with it, which
left stale numbers like "ETSINV-1268-PAY-1" attached to an invoice now named
"ETSINV-1213" — and blocked creating the real ETSINV-1268 invoice later with a
unique-constraint violation on payment_number. This also renames any
payment_number whose invoice-number prefix no longer matches its invoice's
current invoice_number.

A second flavor of the same bug: a service ETS never assigned a real invoice
number to (invoiceNumber: null in the scrape — typically "Completed" work that
was never actually invoiced) still falls back to its own service number, e.g.
service 1092 became "ETSINV-1092". If a DIFFERENT service's real invoice
happens to be numbered 1092 too (service 1146's real invoice IS #1092), that
service can never get its correct number — the slot is squatted by an
unrelated row with no real claim to it. Found the same way: service 1146
(21.6h, 07/17) had zero active invoices in the DB at all. Phase 0 evicts these
squatters (own service has no real invoiceNumber, but its fallback digits are
someone else's real number) to a synthetic "ETSINV-SVC{service_no}" that can't
collide with any real numeric ETS invoice number, freeing the slot for
whichever service actually owns it.

    python3 fix_legacy_invoice_numbers.py --tenant-id <uuid> --dry-run
    python3 fix_legacy_invoice_numbers.py --tenant-id <uuid> --commit
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

psycopg2.extras.register_uuid()

INVOICES_FILE = Path(__file__).parent / "easytruck_sync" / "data" / "invoices.json"
IMPORT_SOURCE = "easy_truck_shop_import"
ORDER_NUMBER_RE = re.compile(r"^ETS-(\d+)-")


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
    scrape = json.loads(INVOICES_FILE.read_text())
    real_invoice_no_by_service = {
        k: str(v["invoiceNumber"]) for k, v in scrape.items() if v.get("invoiceNumber") is not None
    }

    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT i.id, i.invoice_number, r.order_number
             FROM invoices i JOIN repair_orders r ON r.id = i.repair_order_id
            WHERE i.tenant_id=%s AND r.source=%s AND i.deleted_at IS NULL
              AND i.status <> 'cancelled'""",
        (args.tenant_id, IMPORT_SOURCE))
    rows = cur.fetchall()
    existing_numbers = {r["invoice_number"] for r in rows}

    services_needing = {}
    for svc, no in real_invoice_no_by_service.items():
        services_needing.setdefault(no, []).append(svc)

    now = datetime.now(timezone.utc)
    w = conn.cursor()
    stats = {"checked": len(rows), "no_service_match": 0, "already_correct": 0,
             "target_taken": 0, "renamed": 0, "squatters_evicted": 0}

    # Phase 0: evict squatters — rows whose own service has no real ETS
    # invoice number, but whose fallback (service-number) digits are another
    # service's real invoice number, blocking that service from ever getting
    # its correct number.
    for r in rows:
        m = ORDER_NUMBER_RE.match(r["order_number"] or "")
        if not m:
            continue
        own_service = m.group(1)
        own_real = real_invoice_no_by_service.get(own_service)
        stored_digits = (r["invoice_number"] or "").replace("ETSINV-", "").split("-")[0]
        if own_real == stored_digits:
            continue
        other_claimants = [c for c in services_needing.get(stored_digits, []) if c != own_service]
        if not other_claimants:
            continue
        synthetic = f"ETSINV-SVC{own_service}"
        if synthetic in existing_numbers:
            print(f"  SKIP evict {r['invoice_number']} -> {synthetic}: target already exists", file=sys.stderr)
            continue
        print(f"  evict squatter {r['invoice_number']} -> {synthetic}  "
              f"(frees {stored_digits} for service {other_claimants})")
        w.execute(
            "UPDATE invoices SET invoice_number=%s, updated_at=%s WHERE id=%s",
            (synthetic, now, r["id"]))
        existing_numbers.discard(r["invoice_number"])
        existing_numbers.add(synthetic)
        r["invoice_number"] = synthetic
        stats["squatters_evicted"] += 1

    for r in rows:
        m = ORDER_NUMBER_RE.match(r["order_number"] or "")
        if not m:
            stats["no_service_match"] += 1
            continue
        service_no = m.group(1)
        real_no = real_invoice_no_by_service.get(service_no)
        if real_no is None:
            stats["no_service_match"] += 1
            continue
        stored_digits = (r["invoice_number"] or "").replace("ETSINV-", "").split("-")[0]
        if stored_digits == real_no:
            stats["already_correct"] += 1
            continue
        new_number = f"ETSINV-{real_no}"
        if new_number in existing_numbers:
            stats["target_taken"] += 1
            print(f"  SKIP {r['invoice_number']} -> {new_number}: target already exists", file=sys.stderr)
            continue
        print(f"  {r['invoice_number']} -> {new_number}  (order {r['order_number']})")
        w.execute(
            "UPDATE invoices SET invoice_number=%s, updated_at=%s WHERE id=%s",
            (new_number, now, r["id"]))
        existing_numbers.add(new_number)
        stats["renamed"] += 1

    # Phase 2: payments whose payment_number still references an invoice's old
    # (pre-rename) number. Match by invoice_id, not by the stale string.
    cur.execute(
        """SELECT p.id, p.payment_number, i.invoice_number
             FROM payments p JOIN invoices i ON i.id = p.invoice_id
            WHERE i.tenant_id=%s AND i.source=%s AND p.deleted_at IS NULL""",
        (args.tenant_id, IMPORT_SOURCE))
    pay_rows = cur.fetchall()
    existing_payment_numbers = {r["payment_number"] for r in pay_rows}
    stats["payments_checked"] = len(pay_rows)
    stats["payments_renamed"] = 0

    for r in pay_rows:
        m = re.match(r"^(.*)-PAY-(\d+)$", r["payment_number"] or "")
        if not m or m.group(1) == r["invoice_number"]:
            continue
        new_payment_number = f"{r['invoice_number']}-PAY-{m.group(2)}"
        if new_payment_number in existing_payment_numbers:
            print(f"  SKIP payment {r['payment_number']} -> {new_payment_number}: target already exists", file=sys.stderr)
            continue
        print(f"  payment {r['payment_number']} -> {new_payment_number}")
        w.execute(
            "UPDATE payments SET payment_number=%s, updated_at=%s WHERE id=%s",
            (new_payment_number, now, r["id"]))
        existing_payment_numbers.add(new_payment_number)
        stats["payments_renamed"] += 1

    print("=" * 72)
    print(f"LEGACY INVOICE NUMBER FIX {'(dry-run)' if args.dry_run else ''}")
    print("=" * 72)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if args.commit:
        conn.commit(); print("\nCOMMITTED.")
    else:
        conn.rollback(); print("\nDRY RUN — rolled back, nothing written.")
    w.close(); cur.close(); conn.close()


if __name__ == "__main__":
    main()
