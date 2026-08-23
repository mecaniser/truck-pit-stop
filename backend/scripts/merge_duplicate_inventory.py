#!/usr/bin/env python3
"""Merge inventory rows that are the same part under a differently-spelled SKU.

Easy Truck Shop part numbers are free text, and the resync importer used to match
on the raw "ETS-<number>" string. Any drift in spelling therefore forked a second
inventory row instead of updating the first:

    ETS-W261624   location D2, stock 2      <- the good row
    ETS-w261624   no location, stock 2      <- a second copy of the same shelf part

In prod that produced 58 duplicate groups / 69 excess rows, with location and
photo landing on one copy and repair-order history split across both.

This collapses each group onto one surviving row, moves the history over, and
soft-deletes the rest. It deliberately only merges rows whose part numbers are
identical once case and punctuation are removed — genuinely different numbers
(2401771 vs 2401771DH) are a renumbering question for a human and are left alone.

    python3 merge_duplicate_inventory.py --tenant-id <uuid> --dry-run
    python3 merge_duplicate_inventory.py --tenant-id <uuid> --commit

Reads $DATABASE_URL (async URLs are normalised), same as the resync importer.
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

PARTS_FILE = Path(__file__).parent / "easytruck_sync" / "data" / "parts_inventory.json"


def dsn_from_env():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace("+asyncpg", "")
    return url


def canon(sku):
    """Same key the importer matches on: drop the ETS- prefix and every
    non-alphanumeric, upper-case. "TCX T130158342AC2" == "TCXT130158342AC2"."""
    s = (sku or "").strip()
    if s.upper().startswith("ETS-"):
        s = s[4:]
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def load_live_parts():
    """Current ETS catalogue keyed by canonical part number, so a surviving row
    can adopt the spelling, stock and pricing ETS shows today. Missing file just
    means we fall back to whatever the richest local row already has."""
    if not PARTS_FILE.exists():
        return {}
    out = {}
    for p in json.loads(PARTS_FILE.read_text()):
        pn = (p.get("partNumber") or "").strip()
        if pn:
            out[canon(pn)] = p
    return out


def _upper_sku(sku):
    """SKUs are stored upper-cased unconditionally. That is the rule that keeps
    "w261624" from ever coming back as a second row beside "W261624"."""
    s = (sku or "").strip()
    if s.upper().startswith("ETS-"):
        s = s[4:]
    return f"ETS-{s.upper()}"[:100]


def parse_money(s):
    if s is None:
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(s).strip().split()[0] if str(s).strip() else "")
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def pick_survivor(rows, live):
    """Priority agreed with the shop: a row carrying a LOCATION wins, then one
    carrying a PHOTO, then the row already spelled the way ETS spells it today,
    then the one with the most repair-order history, then the oldest row so the
    choice is stable across runs."""
    def rank(r):
        return (
            r["location"] is not None and r["location"] != "",
            r["image_url"] is not None,
            live.get(canon(r["sku"]), {}).get("partNumber", "").upper() == (r["sku"] or "")[4:].upper(),
            r["uses"],
            -r["created_at"].timestamp(),
        )
    return sorted(rows, key=rank, reverse=True)[0]


def merged_values(survivor, group, live):
    """Field-level merge. Location and photo are the two fields the shop cares
    most about, so take them from whichever copy has one. Stock is NOT summed —
    the copies describe the same physical shelf item, so double-counting would
    inflate on-hand; ETS's current count wins, else the highest copy."""
    ets = live.get(canon(survivor["sku"]))

    # The survivor's own location wins; only fall back to a duplicate's when the
    # survivor has none. Taking "first non-empty in the group" would let a stale
    # copy's bin override the shelf location someone actually maintains.
    location = survivor["location"] or next((r["location"] for r in group if r["location"]), None)
    image_url = survivor["image_url"]
    public_id = survivor["cloudinary_public_id"]
    if not image_url:
        # public_id must travel with its image — it is how the asset is deleted later.
        donor = next((r for r in group if r["image_url"]), None)
        if donor:
            image_url, public_id = donor["image_url"], donor["cloudinary_public_id"]

    if ets:
        sku = _upper_sku(ets.get("partNumber") or "")
        stock = ets.get("stock") if isinstance(ets.get("stock"), int) else max(r["stock_quantity"] for r in group)
        cost = parse_money(ets.get("cost"))
        price = parse_money(ets.get("price"))
        name = (ets.get("description") or "").strip() or survivor["name"]
    else:
        # Not in ETS any more (a retired part, or an ad-hoc placeholder that was
        # never a catalogue entry). Still upper-case it: the rule is that SKUs are
        # always upper-case regardless of how ETS spells them, which is what stops
        # the same part drifting back into two rows later. The display NAME is
        # left alone, so "AC compressor" stays readable.
        sku = _upper_sku(survivor["sku"])
        stock = max(r["stock_quantity"] for r in group)
        cost = price = None
        name = survivor["name"]

    # "virtual" is ETS's word for an ad-hoc placeholder and is useless as a name;
    # prefer any real name in the group, else fall back to the part number.
    if name.strip().lower() == "virtual":
        real = next((r["name"] for r in group
                     if r["name"] and r["name"].strip().lower() != "virtual"), None)
        name = real or sku[4:]

    return {
        "sku": sku,
        "name": name[:255],
        "location": location,
        "image_url": image_url,
        "cloudinary_public_id": public_id,
        "stock_quantity": stock,
        "cost": cost if cost is not None else float(survivor["cost"] or 0),
        "selling_price": price if price is not None else float(survivor["selling_price"] or 0),
        # Only stays a placeholder if every copy was one; if any copy became a
        # real stocked part, the merged row is a real part.
        "is_placeholder": all(r["is_placeholder"] for r in group),
    }


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    ap.add_argument("--tenant-id", required=True)
    ap.add_argument("--verbose", action="store_true", help="print every group, not just the first 25")
    args = ap.parse_args()

    live = load_live_parts()
    conn = psycopg2.connect(dsn_from_env())
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """SELECT i.id, i.sku, i.name, i.location, i.image_url, i.cloudinary_public_id,
                  i.stock_quantity, i.cost, i.selling_price, i.is_placeholder, i.created_at,
                  (SELECT count(*) FROM parts_usage pu WHERE pu.inventory_id = i.id) AS uses,
                  (SELECT count(*) FROM service_parts sp WHERE sp.inventory_id = i.id) AS svc_uses
             FROM inventory i
            WHERE i.tenant_id = %s AND i.deleted_at IS NULL""",
        (args.tenant_id,))
    rows = cur.fetchall()

    groups = {}
    for r in rows:
        groups.setdefault(canon(r["sku"]), []).append(r)
    dups = {k: v for k, v in groups.items() if len(v) > 1 and k}

    if not dups:
        # Still fall through: the SKU upper-casing pass below is worth running on
        # its own, and is what keeps a re-run idempotent.
        print("No duplicate groups found — checking SKU casing only.")

    now = datetime.now(timezone.utc)
    w = conn.cursor()
    stats = {"groups": 0, "rows_retired": 0, "usage_repointed": 0,
             "service_parts_repointed": 0, "location_recovered": 0, "image_recovered": 0}

    print("=" * 78)
    print(f"INVENTORY DUPLICATE MERGE  {'(dry-run)' if args.dry_run else ''}")
    print("=" * 78)

    for idx, (key, group) in enumerate(sorted(dups.items())):
        survivor = pick_survivor(group, live)
        losers = [r for r in group if r["id"] != survivor["id"]]
        vals = merged_values(survivor, group, live)

        if not survivor["location"] and vals["location"]:
            stats["location_recovered"] += 1
        if not survivor["image_url"] and vals["image_url"]:
            stats["image_recovered"] += 1

        if args.verbose or idx < 25:
            print(f"\n[{vals['name'][:44]}]")
            print(f"   KEEP    {survivor['sku']:<28} loc={survivor['location'] or '-':<5} "
                  f"img={'Y' if survivor['image_url'] else 'n'} stock={survivor['stock_quantity']:<4} uses={survivor['uses']}")
            for l in losers:
                print(f"   retire  {l['sku']:<28} loc={l['location'] or '-':<5} "
                      f"img={'Y' if l['image_url'] else 'n'} stock={l['stock_quantity']:<4} uses={l['uses']}")
            changes = []
            if vals["sku"] != survivor["sku"]:
                changes.append(f"sku -> {vals['sku']}")
            if vals["location"] != survivor["location"]:
                changes.append(f"location -> {vals['location']}")
            if vals["image_url"] != survivor["image_url"]:
                changes.append("image recovered from duplicate")
            if vals["stock_quantity"] != survivor["stock_quantity"]:
                changes.append(f"stock -> {vals['stock_quantity']}")
            if changes:
                print(f"   result  {'; '.join(changes)}")

        loser_ids = [l["id"] for l in losers]
        moved = sum(l["uses"] for l in losers)
        moved_svc = sum(l["svc_uses"] for l in losers)

        w.execute(
            """UPDATE inventory SET sku=%s, name=%s, location=%s, image_url=%s,
                 cloudinary_public_id=%s, stock_quantity=%s, cost=%s, selling_price=%s,
                 is_placeholder=%s, updated_at=%s
               WHERE id=%s""",
            (vals["sku"], vals["name"], vals["location"], vals["image_url"],
             vals["cloudinary_public_id"], vals["stock_quantity"], vals["cost"],
             vals["selling_price"], vals["is_placeholder"], now, survivor["id"]))
        if loser_ids:
            w.execute("UPDATE parts_usage SET inventory_id=%s WHERE inventory_id = ANY(%s::uuid[])",
                      (survivor["id"], loser_ids))
            w.execute("UPDATE service_parts SET inventory_id=%s WHERE inventory_id = ANY(%s::uuid[])",
                      (survivor["id"], loser_ids))
            # Soft delete: the rows stay recoverable, and anything still pointing
            # at them has already been moved above.
            w.execute("UPDATE inventory SET deleted_at=%s, updated_at=%s WHERE id = ANY(%s::uuid[])",
                      (now, now, loser_ids))

        stats["groups"] += 1
        stats["rows_retired"] += len(losers)
        stats["usage_repointed"] += moved
        stats["service_parts_repointed"] += moved_svc

    if not args.verbose and len(dups) > 25:
        print(f"\n… {len(dups) - 25} more groups (use --verbose to list all)")

    # Finally, upper-case every remaining SKU. Merging only normalised the rows it
    # touched, which would leave "ETS-ff42128nn" free to drift back into a second
    # row later. This cannot collide: two SKUs that differ only by case share a
    # canonical key, so they were already merged above.
    w.execute(
        """UPDATE inventory
              SET sku = 'ETS-' || upper(regexp_replace(sku, '^ETS-', '')), updated_at=%s
            WHERE tenant_id=%s AND deleted_at IS NULL
              AND sku LIKE 'ETS-%%' AND sku <> 'ETS-' || upper(regexp_replace(sku, '^ETS-', ''))""",
        (now, args.tenant_id))
    stats["skus_uppercased"] = w.rowcount

    print("\n" + "=" * 78)
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if args.commit:
        conn.commit()
        print("\nCOMMITTED.")
    else:
        conn.rollback()
        print("\nDRY RUN — rolled back, nothing written.")
    w.close()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
