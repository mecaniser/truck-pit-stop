#!/usr/bin/env python3
"""Give imported repair orders their parts cost, so Parts Profit is a profit.

The importer creates repair orders and labor lines but never creates parts_usage
rows, which are where the reports read parts COST from. With no cost side,
`parts_profit = parts_revenue - 0`, so the dashboard reported parts revenue under
the label "Parts Profit" — $48,234.92 against Easy Truck Shop's $15,976.87 for
the same month, an overstatement of about 3x on a number a shop owner would
actually act on.

The data was already being scraped and thrown away: stage 03 (parts_usage.json)
records every part on every service with its unit cost and unit price. Summing
qty x unit_price reproduces the invoice's parts total exactly on 1161 of 1247
services, which is what confirms the columns are read correctly.

Parts are attached to the repair order carrying that service's invoice, and only
that one. A service with N line items imports as N repair orders, so attaching to
each would multiply cost and revenue the same way duplicated invoices multiplied
revenue.

Part numbers that have no inventory row (137 of 928 — ad-hoc entries like
"SWITCH" or "KINGPIN") get a placeholder inventory row, the same treatment ETS's
own "virtual" parts already receive.

    python3 backfill_parts_usage_cost.py --tenant-id <uuid> --dry-run
    python3 backfill_parts_usage_cost.py --tenant-id <uuid> --commit
"""
import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras

psycopg2.extras.register_uuid()

DATA = Path(__file__).parent / "easytruck_sync" / "data"
PARTS_USAGE_FILE = DATA / "parts_usage.json"
INVOICES_FILE = DATA / "invoices.json"
IMPORT_SOURCE = "easy_truck_shop_import"


def dsn_from_env():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")


def canon(s):
    s = (s or "").strip()
    if s.upper().startswith("ETS-"):
        s = s[4:]
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def money(x):
    s = (x or "").strip()
    c = re.sub(r"[^0-9.\-]", "", s.split()[0] if s else "")
    try:
        return Decimal(c) if c else Decimal("0")
    except Exception:
        return Decimal("0")


def qty(x):
    m = re.match(r"([\d.]+)", (x or "").strip())
    return Decimal(m.group(1)) if m else Decimal("0")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    ap.add_argument("--tenant-id", required=True)
    args = ap.parse_args()

    for f in (PARTS_USAGE_FILE, INVOICES_FILE):
        if not f.exists():
            print(f"ERROR: {f} not found. Run scraper stages 03 and 05 first.", file=sys.stderr)
            sys.exit(1)
    parts_by_service = json.loads(PARTS_USAGE_FILE.read_text())
    invoices = json.loads(INVOICES_FILE.read_text())
    # ETS invoice number -> service number, so a repair order can be reached
    # through the invoice it carries.
    service_by_invoice_no = {}
    for svc, d in invoices.items():
        if d.get("invoiceNumber"):
            service_by_invoice_no[str(d["invoiceNumber"])] = svc

    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)

    cur.execute(
        "SELECT id, sku FROM inventory WHERE tenant_id=%s AND deleted_at IS NULL",
        (args.tenant_id,))
    inventory_by_canon = {canon(r["sku"]): r["id"] for r in cur.fetchall()}

    cur.execute(
        """SELECT r.id AS ro_id, i.invoice_number,
                  (SELECT count(*) FROM parts_usage pu WHERE pu.repair_order_id = r.id) AS existing
             FROM invoices i JOIN repair_orders r ON r.id = i.repair_order_id
            WHERE i.tenant_id=%s AND r.source=%s AND i.deleted_at IS NULL
              AND i.status <> 'cancelled'""",
        (args.tenant_id, IMPORT_SOURCE))
    targets = cur.fetchall()

    w = conn.cursor()
    stats = {"repair_orders": len(targets), "skipped_have_parts": 0, "no_scrape_data": 0,
             "ro_filled": 0, "usage_rows": 0, "placeholders_created": 0, "scale_rejected": 0}
    total_cost = total_rev = Decimal("0")

    for t in targets:
        if t["existing"]:
            stats["skipped_have_parts"] += 1
            continue
        ets_no = (t["invoice_number"] or "").replace("ETSINV-", "").split("-")[0]
        svc = service_by_invoice_no.get(ets_no)
        rows = [r for grp in (parts_by_service.get(svc) or []) for r in grp.get("rows", []) if len(r) > 3]
        if not rows:
            stats["no_scrape_data"] += 1
            continue

        # Scale cost to the parts revenue the invoice actually bills.
        #
        # Revenue is taken from the invoice's own parts total, but cost can only
        # come from the stage-03 line items, and the two disagree on 86 of 1247
        # services — the parts list carries lines the invoice does not bill
        # (removed items, discounts). Subtracting unscaled cost from billed
        # revenue understates profit: it charges for parts whose revenue was
        # never counted. On dev that read $11,663 against ETS's $15,976.
        billed = invoices.get(svc, {}).get("partsTotal")
        listed = sum(qty(r[1]) * money(r[3]) for r in rows)
        cost_scale = Decimal("1")
        if billed is not None and listed > 0:
            cost_scale = (Decimal(str(billed)) / listed)
            if cost_scale > 2 or cost_scale < Decimal("0.1"):
                # Wildly divergent: trust the line items rather than a factor
                # that would distort every cost on the service.
                cost_scale = Decimal("1")
                stats["scale_rejected"] += 1

        for r in rows:
            name_cell = (r[0] or "").split("\n")
            pn = (name_cell[0] or "").strip()
            label = (name_cell[1] if len(name_cell) > 1 else pn).strip() or pn
            if not pn:
                continue
            q = qty(r[1])
            unit_cost = (money(r[2]) * cost_scale).quantize(Decimal("0.01"))
            unit_price = money(r[3])
            if q <= 0:
                continue

            key = canon(pn)
            inv_id = inventory_by_canon.get(key)
            if not inv_id:
                # Ad-hoc part with no catalogue entry — model it the same way
                # ETS's own "virtual" parts are modelled rather than dropping the
                # line and losing its cost.
                inv_id = uuid.uuid4()
                w.execute(
                    """INSERT INTO inventory (id, tenant_id, sku, name, description, category,
                         stock_quantity, on_order_quantity, reorder_level, cost, selling_price,
                         core_charge, unit_type, source, is_placeholder, ets_imported_at,
                         created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,NULL,0,0,0,%s,%s,0,'each',%s,true,%s,%s,%s)""",
                    (inv_id, args.tenant_id, f"ETS-{pn.upper()}"[:100], label[:255], label[:255],
                     unit_cost, unit_price, IMPORT_SOURCE, now, now, now))
                inventory_by_canon[key] = inv_id
                stats["placeholders_created"] += 1

            line_total = (q * unit_price).quantize(Decimal("0.01"))
            w.execute(
                """INSERT INTO parts_usage (id, tenant_id, repair_order_id, inventory_id,
                     quantity, unit_cost, unit_price, list_price, total_price,
                     stock_shortage_override, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,%s)""",
                (uuid.uuid4(), args.tenant_id, t["ro_id"], inv_id,
                 q, unit_cost, unit_price, unit_price, line_total, now, now))
            stats["usage_rows"] += 1
            total_cost += (q * unit_cost)
            total_rev += (q * unit_price)
        stats["ro_filled"] += 1

    print("=" * 74)
    print(f"PARTS USAGE / COST BACKFILL {'(dry-run)' if args.dry_run else ''}")
    print("=" * 74)
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  parts revenue represented: ${total_rev:,.2f}")
    print(f"  parts cost represented:    ${total_cost:,.2f}")
    if total_rev:
        print(f"  implied margin:            {(1 - total_cost / total_rev) * 100:.1f}%")

    if args.commit:
        conn.commit(); print("\nCOMMITTED.")
    else:
        conn.rollback(); print("\nDRY RUN — rolled back, nothing written.")
    w.close(); cur.close(); conn.close()


if __name__ == "__main__":
    main()
