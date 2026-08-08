#!/usr/bin/env python3
"""
Idempotent resync of scraped Easy Truck Shop data into TruckPitStop.

Unlike the original one-shot import, this can be re-run safely as Easy Truck
Shop keeps adding data: it matches each scraped record to the row it already
created and only inserts what's new / updates what changed.

Matching keys
-------------
- customers : ets_external_id  (the ETS numeric customer id)
- vehicles  : ets_external_id  (the ETS numeric vehicle id)
- repair_orders : order_number (deterministic: ETS-{service_no}-{customer_id})

Merge policy (per the resync decision)
--------------------------------------
- INSERT rows we don't have yet.
- UPDATE an existing import-tagged row in place ONLY if a local user hasn't
  hand-edited it since import (updated_at within a small epsilon of created_at).
  A scraped field that is empty never overwrites a non-empty local value.
- Never touch rows that aren't tagged source='easy_truck_shop_import'.

Modes
-----
    --dry-run                 plan + summary, no writes (default-safe)
    --commit                  apply (asks for confirmation)
    --backfill-external-ids   one-time: stamp ets_external_id onto existing
                              import rows (customers by company_name, vehicles
                              by vin) so historical rows become matchable.
                              Combine with --dry-run / --commit.

DB target comes from $DATABASE_URL (async URL is normalized to psycopg2), or
falls back to the local dev DSN. Tenant via --tenant-id (required for import).
"""
import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg2
import psycopg2.extras

# Let psycopg2 adapt uuid.UUID objects directly in parameterized queries.
psycopg2.extras.register_uuid()

DATA_FILE = Path(__file__).parent / "data" / "customer_details.json"
PARTS_FILE = Path(__file__).parent / "data" / "parts_inventory.json"
IMAGE_CACHE_FILE = Path(__file__).parent / "data" / "part_image_cache.json"
ORDER_NUMBER_PREFIX = "ETS"
IMPORT_SOURCE = "easy_truck_shop_import"
# Commit the DB in batches so a dropped connection loses at most one batch and
# the run is safely resumable (important over the Railway proxy).
COMMIT_BATCH = 50


def _norm_sku(raw_pn):
    pn = (raw_pn or "").strip()
    if not pn:
        return None
    return (pn if pn.startswith("ETS-") else f"ETS-{pn}")[:100]


def _load_image_cache():
    if IMAGE_CACHE_FILE.exists():
        try:
            return json.loads(IMAGE_CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_image_cache(cache):
    IMAGE_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def _placeholder_urls(parts, threshold=3):
    counts = {}
    for p in parts:
        u = p.get("imageUrl")
        if u:
            counts[u] = counts.get(u, 0) + 1
    return {u for u, n in counts.items() if n >= threshold}


def upload_all_images():
    """DB-free image pre-upload: host every non-placeholder part image to
    Cloudinary, caching results to disk (resumable). Run this before the DB
    commit so the DB pass makes no slow network calls — essential over a flaky
    proxy that kills long-lived connections."""
    parts = json.loads(PARTS_FILE.read_text())
    placeholders = _placeholder_urls(parts)
    cache = _load_image_cache()
    srcs = []
    for p in parts:
        u = p.get("imageUrl")
        if u and u not in placeholders and u not in cache:
            srcs.append(u)
    srcs = list(dict.fromkeys(srcs))
    if not srcs:
        print(f"All part images already cached ({sum(1 for v in cache.values() if v[0])} hosted).")
        return
    print(f"Uploading {len(srcs)} image(s) to Cloudinary ({len(cache)} already cached)...")
    for i, src in enumerate(srcs, 1):
        url, pid = _rehost_part_image(src, uuid.uuid4())
        cache[src] = [url, pid]
        if i % 20 == 0:
            _save_image_cache(cache)
            print(f"  {i}/{len(srcs)}")
    _save_image_cache(cache)
    print(f"Done: {sum(1 for v in cache.values() if v[0])} images hosted, "
          f"{sum(1 for v in cache.values() if not v[0])} failed.")

LOCAL_DEV_DSN = "host=localhost port=5432 dbname=truckpitstop user=truckpitstop password=truckpitstop_dev"

# A row whose updated_at is within this window of created_at is considered
# "untouched since import" and therefore safe to update from source.
UNTOUCHED_EPSILON = timedelta(seconds=5)

STATUS_MAP = {"paid": "paid", "invoiced": "invoiced", "completed": "completed"}


# ---------------------------------------------------------------------------
# parsing helpers (unchanged from the original importer)
# ---------------------------------------------------------------------------
def parse_money(s):
    if not s:
        return Decimal("0.00")
    # Some price cells carry a trailing discount, e.g. "$55.35 30%". Take only
    # the first monetary token so the "30" can't merge into the amount.
    token = s.strip().split()[0] if s.strip().split() else s
    cleaned = re.sub(r"[^0-9.\-]", "", token)
    if not cleaned:
        return Decimal("0.00")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def parse_year_make_model_vin(list_cell_text):
    year = make = model = None
    m = re.match(r"(\d{4})\s*•\s*([^•]+)\s*•\s*(.+)", list_cell_text or "")
    if m:
        year = int(m.group(1))
        make = m.group(2).strip()
        model = m.group(3).split("\n")[0].strip()
    return year, make, model


def parse_mileage(s):
    if not s:
        return None
    cleaned = re.sub(r"[^0-9]", "", s)
    return int(cleaned) if cleaned else None


def split_company_name(company):
    company = (company or "Unknown").strip()
    parts = company.split(" ", 1)
    if len(parts) == 2:
        return parts[0][:100], parts[1][:100]
    return company[:100], "-"


def pick_email(contacts, customer_id):
    for c in contacts:
        if c.get("email") and "@" in c["email"]:
            return c["email"].strip().lower()
    return f"noemail+{customer_id}@import.local"


def pick_phone(contacts):
    for c in contacts:
        if c.get("phone"):
            return c["phone"][:20]
    return None


def map_status(source_status):
    return STATUS_MAP.get((source_status or "").strip().lower(), "completed")


def parse_service_row(row):
    service_no, item_desc, duration, charged, completed_block, status = (row + [None] * 6)[:6]
    completed_date = None
    mileage = None
    if completed_block:
        lines = completed_block.split("\n")
        if lines and lines[0].strip():
            try:
                completed_date = datetime.strptime(lines[0].strip(), "%m/%d/%Y").date()
            except ValueError:
                completed_date = None
        if len(lines) > 1:
            mileage = parse_mileage(lines[1])
    hours = None
    if duration:
        m = re.match(r"(\d+)\s*(?:hour|hr)s?\s*(\d+)?\s*(?:minute|min)?", duration, re.I)
        if m:
            h = int(m.group(1) or 0)
            mm = int(m.group(2) or 0)
            hours = Decimal(h) + Decimal(mm) / Decimal(60)
        elif "minute" in duration.lower():
            m2 = re.match(r"(\d+)", duration)
            if m2:
                hours = Decimal(m2.group(1)) / Decimal(60)
    return {
        "service_no": (service_no or "").strip().lstrip("#"),
        "description": (item_desc or "Service").strip(),
        "charged": parse_money(charged),
        "completed_date": completed_date,
        "mileage": mileage,
        "status": (status or "").strip(),
        "hours": hours,
    }


# ---------------------------------------------------------------------------
# transform: scraped customers -> normalized records keyed by ETS source ids
# ---------------------------------------------------------------------------
def build_records(customers, tenant_id):
    """Pure transform. Each record carries its ETS source id so the DB step can
    match/upsert. No UUIDs assigned here — the DB step reuses existing ids."""
    out = {"customers": [], "vehicles": [], "repair_orders": []}
    order_numbers_used = set()

    for cust in customers:
        first_name, last_name = split_company_name(cust["company"])
        out["customers"].append({
            "ets_external_id": str(cust["id"]),
            "tenant_id": tenant_id,
            "first_name": first_name,
            "last_name": last_name,
            "company_name": cust["company"],
            "email": pick_email(cust["contacts"], cust["id"]),
            "phone": pick_phone(cust["contacts"]),
            "source": IMPORT_SOURCE,
        })

        for v in cust.get("vehicles", []):
            if not v.get("vehicleId"):
                continue
            edit = v.get("edit") or {}
            list_cells = v.get("listCells") or []
            unit_number = (list_cells[0].strip() if list_cells and list_cells[0] else None) or (edit.get("unit") or None)
            make = (edit.get("make") or "").strip() or None
            model = (edit.get("model") or "").strip() or None
            year = None
            if edit.get("year"):
                try:
                    year = int(edit["year"])
                except ValueError:
                    year = None
            if not make or not model:
                raw = list_cells[2] if len(list_cells) > 2 else ""
                fy, fmake, fmodel = parse_year_make_model_vin(raw)
                make, model, year = make or fmake, model or fmodel, year or fy
            make = (make or "UNKNOWN")[:100]
            model = (model or "UNKNOWN")[:100]
            vin = (edit.get("vin") or "").strip() or None

            out["vehicles"].append({
                "ets_external_id": str(v["vehicleId"]),
                "ets_customer_id": str(cust["id"]),
                "tenant_id": tenant_id,
                "vin": vin,
                "unit_number": unit_number,
                "make": make,
                "model": model,
                "year": year,
                "mileage": parse_mileage(edit.get("odometer")) if edit.get("odometer") else None,
                "source": IMPORT_SOURCE,
            })

            for row in v.get("serviceHistory") or []:
                parsed = parse_service_row(row)
                base = f"{ORDER_NUMBER_PREFIX}-{parsed['service_no'] or 'NA'}-{cust['id']}"
                order_no, suffix = base, 1
                while order_no in order_numbers_used:
                    suffix += 1
                    order_no = f"{base}-{suffix}"
                order_numbers_used.add(order_no)
                total = parsed["charged"]
                hours = parsed["hours"] if parsed["hours"] and parsed["hours"] > 0 else Decimal("1.00")
                out["repair_orders"].append({
                    "order_number": order_no,
                    "ets_customer_id": str(cust["id"]),
                    "ets_vehicle_id": str(v["vehicleId"]),
                    "tenant_id": tenant_id,
                    "status": map_status(parsed["status"]),
                    "description": parsed["description"][:2000],
                    "mileage": parsed["mileage"],
                    "total_cost": total,
                    "labor_hours": hours.quantize(Decimal("0.01")),
                    "labor_rate": (total / hours).quantize(Decimal("0.01")) if hours else total,
                    "work_completed_at": parsed["completed_date"],
                    "source": IMPORT_SOURCE,
                })
    return out


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def dsn_from_env():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return LOCAL_DEV_DSN
    # normalize SQLAlchemy async URL to plain postgres for psycopg2
    url = (url.replace("postgresql+asyncpg://", "postgresql://")
              .replace("postgresql+psycopg://", "postgresql://"))
    # TCP keepalives keep the connection alive through proxies (e.g. Railway's
    # shortline.proxy) that drop idle/long-running connections.
    if "keepalives" not in url:
        sep = "&" if "?" in url else "?"
        url += f"{sep}keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=5"
    return url


def _untouched(created_at, updated_at):
    """True if the row hasn't been hand-edited since import."""
    if created_at is None or updated_at is None:
        return True
    return (updated_at - created_at) <= UNTOUCHED_EPSILON


def backfill_external_ids(conn, tenant_id, commit):
    """Stamp ets_external_id onto existing import rows that predate the column,
    so a resync updates them instead of duplicating. Only touches rows where
    ets_external_id IS NULL and source=import.

    Matching, most-reliable first:
      1. vehicles by VIN (exact) — VIN is a stable natural key.
      2. customers whose VIN-matched vehicle links them to an ETS customer id.
      3. remaining customers by company_name, case-insensitive + trimmed.
    """
    customers = json.loads(DATA_FILE.read_text())
    recs = build_records(customers, tenant_id)

    vin_to_id = {v["vin"]: v["ets_external_id"] for v in recs["vehicles"] if v["vin"]}
    # ETS vehicle id -> ETS customer id, so a VIN match can also identify the customer.
    vehicle_to_customer = {v["ets_external_id"]: v["ets_customer_id"] for v in recs["vehicles"]}
    vin_to_customer = {
        v["vin"]: vehicle_to_customer.get(v["ets_external_id"])
        for v in recs["vehicles"] if v["vin"]
    }
    # normalized company name -> ETS customer id
    company_to_id = {}
    for c in recs["customers"]:
        if c["company_name"]:
            company_to_id[c["company_name"].strip().lower()] = c["ets_external_id"]

    cur = conn.cursor()

    # 1) vehicles by VIN
    veh_updates = 0
    for vin, ets_id in vin_to_id.items():
        cur.execute(
            """UPDATE vehicles SET ets_external_id=%s
               WHERE tenant_id=%s AND source=%s AND ets_external_id IS NULL AND vin=%s""",
            (ets_id, tenant_id, IMPORT_SOURCE, vin))
        veh_updates += cur.rowcount

    # 2) customers via their VIN-matched vehicle's owner
    cust_by_vin = 0
    for vin, cust_ets in vin_to_customer.items():
        if not cust_ets:
            continue
        cur.execute(
            """UPDATE customers SET ets_external_id=%s
               WHERE tenant_id=%s AND source=%s AND ets_external_id IS NULL
                 AND id = (SELECT customer_id FROM vehicles
                           WHERE tenant_id=%s AND source=%s AND vin=%s LIMIT 1)""",
            (cust_ets, tenant_id, IMPORT_SOURCE, tenant_id, IMPORT_SOURCE, vin))
        cust_by_vin += cur.rowcount

    # 3) remaining customers by case-insensitive, trimmed company_name
    cust_by_name = 0
    for company_norm, ets_id in company_to_id.items():
        cur.execute(
            """UPDATE customers SET ets_external_id=%s
               WHERE tenant_id=%s AND source=%s AND ets_external_id IS NULL
                 AND lower(trim(company_name))=%s""",
            (ets_id, tenant_id, IMPORT_SOURCE, company_norm))
        cust_by_name += cur.rowcount

    cur.close()
    print(f"Backfill: vehicles by VIN={veh_updates}; "
          f"customers by VIN-owner={cust_by_vin}, by name={cust_by_name} "
          f"(total customers={cust_by_vin + cust_by_name}).")
    if not commit:
        print("(dry-run — rolled back)")
        conn.rollback()
    else:
        conn.commit()
        print("Backfill COMMITTED.")


def resync(conn, tenant_id, commit):
    customers = json.loads(DATA_FILE.read_text())
    recs = build_records(customers, tenant_id)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.utcnow()

    # --- load existing import rows keyed by external id ---
    cur.execute("SELECT id, ets_external_id, created_at, updated_at FROM customers "
                "WHERE tenant_id=%s AND source=%s AND ets_external_id IS NOT NULL",
                (tenant_id, IMPORT_SOURCE))
    existing_cust = {r["ets_external_id"]: r for r in cur.fetchall()}
    cur.execute("SELECT id, ets_external_id, created_at, updated_at FROM vehicles "
                "WHERE tenant_id=%s AND source=%s AND ets_external_id IS NOT NULL",
                (tenant_id, IMPORT_SOURCE))
    existing_veh = {r["ets_external_id"]: r for r in cur.fetchall()}
    cur.execute("SELECT id, order_number FROM repair_orders WHERE tenant_id=%s AND source=%s",
                (tenant_id, IMPORT_SOURCE))
    existing_ro = {r["order_number"]: r for r in cur.fetchall()}

    stats = {"cust_ins": 0, "cust_upd": 0, "cust_skip_edited": 0,
             "veh_ins": 0, "veh_upd": 0, "veh_skip_edited": 0,
             "ro_ins": 0, "ro_exists": 0}

    w = conn.cursor()
    cust_uuid_by_ets = {}
    for c in recs["customers"]:
        ex = existing_cust.get(c["ets_external_id"])
        if ex:
            cust_uuid_by_ets[c["ets_external_id"]] = ex["id"]
            if _untouched(ex["created_at"], ex["updated_at"]):
                w.execute(
                    """UPDATE customers SET company_name=%s,
                         email=COALESCE(NULLIF(%s,''), email),
                         phone=COALESCE(%s, phone), updated_at=%s
                       WHERE id=%s""",
                    (c["company_name"], c["email"], c["phone"], now, ex["id"]))
                stats["cust_upd"] += 1
            else:
                stats["cust_skip_edited"] += 1
        else:
            new_id = uuid.uuid4()
            cust_uuid_by_ets[c["ets_external_id"]] = new_id
            w.execute(
                """INSERT INTO customers (id, tenant_id, first_name, last_name, company_name,
                     email, phone, source, ets_external_id, sms_opt_out, is_internal_fleet,
                     created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (new_id, c["tenant_id"], c["first_name"], c["last_name"], c["company_name"],
                 c["email"], c["phone"], c["source"], c["ets_external_id"], False, False, now, now))
            stats["cust_ins"] += 1

    veh_uuid_by_ets = {}
    for v in recs["vehicles"]:
        cust_id = cust_uuid_by_ets.get(v["ets_customer_id"])
        if not cust_id:
            continue
        ex = existing_veh.get(v["ets_external_id"])
        if ex:
            veh_uuid_by_ets[v["ets_external_id"]] = ex["id"]
            if _untouched(ex["created_at"], ex["updated_at"]):
                w.execute(
                    """UPDATE vehicles SET
                         vin=COALESCE(NULLIF(%s,''), vin),
                         unit_number=COALESCE(%s, unit_number),
                         make=%s, model=%s, year=COALESCE(%s, year),
                         mileage=COALESCE(%s, mileage), updated_at=%s
                       WHERE id=%s""",
                    (v["vin"], v["unit_number"], v["make"], v["model"], v["year"],
                     v["mileage"], now, ex["id"]))
                stats["veh_upd"] += 1
            else:
                stats["veh_skip_edited"] += 1
        else:
            new_id = uuid.uuid4()
            veh_uuid_by_ets[v["ets_external_id"]] = new_id
            w.execute(
                """INSERT INTO vehicles (id, tenant_id, customer_id, vin, unit_number,
                     make, model, year, mileage, source, ets_external_id, pm_interval_miles,
                     created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (new_id, v["tenant_id"], cust_id, v["vin"], v["unit_number"], v["make"],
                 v["model"], v["year"], v["mileage"], v["source"], v["ets_external_id"], 0, now, now))
            stats["veh_ins"] += 1

    # Repair orders: order_number is deterministic, so existing ones are simply
    # left as-is (historical work orders don't change). Only insert new ones.
    for r in recs["repair_orders"]:
        if r["order_number"] in existing_ro:
            stats["ro_exists"] += 1
            continue
        cust_id = cust_uuid_by_ets.get(r["ets_customer_id"])
        veh_id = veh_uuid_by_ets.get(r["ets_vehicle_id"])
        if not cust_id or not veh_id:
            continue
        ro_id = uuid.uuid4()
        w.execute(
            """INSERT INTO repair_orders (id, tenant_id, customer_id, vehicle_id, order_number,
                 status, description, mileage_in, mileage_out, total_parts_cost, total_labor_cost,
                 total_cost, work_completed_at, source, is_internal, is_pm,
                 labor_discount_amount, order_discount_amount, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (ro_id, r["tenant_id"], cust_id, veh_id, r["order_number"], r["status"],
             r["description"], r["mileage"], r["mileage"], Decimal("0.00"), r["total_cost"],
             r["total_cost"], r["work_completed_at"], r["source"], False, False,
             Decimal("0.00"), Decimal("0.00"), now, now))
        w.execute(
            """INSERT INTO labor (id, tenant_id, repair_order_id, description, hours,
                 hourly_rate, total_cost, line_type, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uuid.uuid4(), r["tenant_id"], ro_id, r["description"], r["labor_hours"],
             r["labor_rate"], r["total_cost"], "manual", now, now))
        stats["ro_ins"] += 1

    w.close()
    cur.close()

    print("=" * 70)
    print("RESYNC PLAN" + ("" if commit else "  (dry-run)"))
    print("=" * 70)
    for k, val in stats.items():
        print(f"  {k}: {val}")

    if commit:
        conn.commit()
        print("\nCOMMITTED.")
    else:
        conn.rollback()
        print("\nDRY RUN — rolled back, no changes written.")


def _rehost_part_image(image_url, inventory_item_id):
    """Re-upload an Easy Truck Shop part image to Cloudinary. Cloudinary fetches
    the remote URL server-side, so no local download is needed. Returns
    (secure_url, public_id) or (None, None) on any failure / if not configured."""
    try:
        import cloudinary
        import cloudinary.uploader
    except ImportError:
        return None, None
    if not os.environ.get("CLOUDINARY_URL") and not os.environ.get("CLOUDINARY_CLOUD_NAME"):
        return None, None
    try:
        result = cloudinary.uploader.upload(
            image_url,
            folder=f"inventory_parts/{inventory_item_id}",
            resource_type="image",
            transformation=[{"quality": "auto:good"}, {"fetch_format": "auto"}],
            context={"inventory_item_id": str(inventory_item_id)},
        )
        return result["secure_url"], result["public_id"]
    except Exception as e:
        print(f"  ! image re-host failed for {inventory_item_id}: {e}", file=sys.stderr)
        return None, None


def resync_parts(conn, tenant_id, commit, rehost_images):
    """Resync parts inventory. Matches on sku (= ETS part number) scoped to
    tenant + import source. Location and images (re-hosted to Cloudinary) are
    the priority fields. Insert-new / update-unedited-only, same policy as the
    rest of the resync."""
    if not PARTS_FILE.exists():
        print(f"(skipping parts — {PARTS_FILE.name} not found)")
        return

    parts = json.loads(PARTS_FILE.read_text())

    # Guard against placeholder images: a real part photo is unique to its part.
    # If the same image URL is shared across many parts it's a generic
    # "no image" placeholder, not a real photo — never re-host those.
    _img_counts: Dict[str, int] = {}
    for _p in parts:
        u = _p.get("imageUrl")
        if u:
            _img_counts[u] = _img_counts.get(u, 0) + 1
    PLACEHOLDER_THRESHOLD = 3
    placeholder_urls = {u for u, n in _img_counts.items() if n >= PLACEHOLDER_THRESHOLD}
    if placeholder_urls:
        print(f"NOTE: ignoring {len(placeholder_urls)} image URL(s) shared by "
              f">={PLACEHOLDER_THRESHOLD} parts (treated as placeholders).")

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, sku, image_url, created_at, updated_at FROM inventory "
        "WHERE tenant_id=%s AND source=%s", (tenant_id, IMPORT_SOURCE))
    existing = {r["sku"]: r for r in cur.fetchall()}
    cur.close()

    # Images are uploaded ahead of time (see upload_all_images / --upload-images-
    # only) and cached to disk. Here we only READ that cache, so the DB pass makes
    # no slow network calls and won't hold the transaction open long enough for a
    # flaky proxy to kill it. If an image isn't cached yet, upload it lazily.
    image_cache = _load_image_cache()
    if commit and rehost_images:
        for part in parts:
            src = part.get("imageUrl")
            if src and src not in placeholder_urls and src not in image_cache:
                url, pid = _rehost_part_image(src, uuid.uuid4())
                image_cache[src] = [url, pid]
        _save_image_cache(image_cache)

    now = datetime.utcnow()
    w = conn.cursor()
    stats = {"ins": 0, "upd": 0, "skip_edited": 0, "img_rehosted": 0,
             "no_sku": 0, "img_placeholder_skipped": 0}
    processed = 0

    for part in parts:
        raw_pn = (part.get("partNumber") or "").strip()
        if not raw_pn:
            stats["no_sku"] += 1
            continue
        # The original import stored part SKUs with an "ETS-" prefix. Match that
        # convention so the resync updates existing rows instead of duplicating
        # them. Tolerate a part number that already carries the prefix.
        sku = _norm_sku(raw_pn)
        name = (part.get("description") or sku)[:255]
        location = (part.get("location") or None)
        cost = parse_money(part.get("cost"))
        price = parse_money(part.get("price"))
        stock = part.get("stock") if isinstance(part.get("stock"), int) else 0
        src_img = part.get("imageUrl")
        if src_img and src_img in placeholder_urls:
            stats["img_placeholder_skipped"] += 1
            src_img = None

        ex = existing.get(sku)
        if ex:
            item_id = ex["id"]
            if not _untouched(ex["created_at"], ex["updated_at"]):
                stats["skip_edited"] += 1
                continue
            image_url, public_id = ex["image_url"], None
            # only re-host if we don't already have an image locally. Uses the
            # pre-uploaded cache (keyed by source URL) so no slow network call
            # happens inside the DB transaction — critical over a flaky proxy.
            if rehost_images and src_img and not ex["image_url"] and commit:
                image_url, public_id = image_cache.get(src_img, (None, None))
                if image_url:
                    stats["img_rehosted"] += 1
            w.execute(
                """UPDATE inventory SET name=%s,
                     location=COALESCE(%s, location), cost=%s, selling_price=%s,
                     stock_quantity=%s,
                     image_url=COALESCE(%s, image_url),
                     cloudinary_public_id=COALESCE(%s, cloudinary_public_id),
                     updated_at=%s
                   WHERE id=%s""",
                (name, location, cost, price, stock, image_url, public_id, now, item_id))
            stats["upd"] += 1
        else:
            item_id = uuid.uuid4()
            image_url = public_id = None
            if rehost_images and src_img and commit:
                image_url, public_id = image_cache.get(src_img, (None, None))
                if image_url:
                    stats["img_rehosted"] += 1
            w.execute(
                """INSERT INTO inventory (id, tenant_id, sku, name, description, location,
                     cost, selling_price, stock_quantity, source, image_url,
                     cloudinary_public_id, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (item_id, tenant_id, sku, name, name, location, cost, price, stock,
                 IMPORT_SOURCE, image_url, public_id, now, now))
            stats["ins"] += 1

        # Commit periodically so a dropped connection (e.g. Railway proxy) loses
        # at most one batch, and the run can be safely re-run to finish.
        processed += 1
        if commit and processed % COMMIT_BATCH == 0:
            conn.commit()

    w.close()
    print("=" * 70)
    print("PARTS RESYNC PLAN" + ("" if commit else "  (dry-run)"))
    print("=" * 70)
    for k, val in stats.items():
        print(f"  {k}: {val}")
    if commit:
        conn.commit()
        print("Parts COMMITTED.")
    else:
        conn.rollback()
        print("Parts DRY RUN — rolled back.")


def main():
    p = argparse.ArgumentParser()
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--commit", action="store_true")
    grp.add_argument("--upload-images-only", action="store_true",
                     help="DB-free: pre-upload all part images to Cloudinary and cache "
                          "them, so a later --commit does no network I/O in its DB pass")
    p.add_argument("--backfill-external-ids", action="store_true",
                   help="one-time: stamp ets_external_id onto pre-existing import rows")
    p.add_argument("--parts", action="store_true",
                   help="resync parts inventory (location + Cloudinary-hosted images)")
    p.add_argument("--only-parts", action="store_true",
                   help="resync ONLY parts inventory, skip customers/vehicles/ROs")
    p.add_argument("--no-rehost-images", action="store_true",
                   help="with --parts: don't upload part images to Cloudinary")
    p.add_argument("--tenant-id", help="target tenant UUID (not needed for --upload-images-only)")
    args = p.parse_args()

    # DB-free image pre-upload — no connection, no tenant required.
    if args.upload_images_only:
        if not PARTS_FILE.exists():
            print(f"ERROR: {PARTS_FILE} not found. Run scraper 04 first.", file=sys.stderr)
            sys.exit(1)
        upload_all_images()
        return

    if not args.tenant_id:
        print("ERROR: --tenant-id is required.", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(dsn_from_env())
    try:
        if args.backfill_external_ids:
            if not DATA_FILE.exists():
                print(f"ERROR: {DATA_FILE} not found. Run scraper 02 first.", file=sys.stderr)
                sys.exit(1)
            backfill_external_ids(conn, args.tenant_id, commit=args.commit)
        else:
            if args.commit:
                if input(f"About to resync into tenant {args.tenant_id} on "
                         f"{dsn_from_env().split('@')[-1].split(' ')[0]}. Type 'yes': ").strip().lower() != "yes":
                    print("Aborted.")
                    sys.exit(1)
            if not args.only_parts:
                if not DATA_FILE.exists():
                    print(f"ERROR: {DATA_FILE} not found. Run the scrapers (01..07) first.", file=sys.stderr)
                    sys.exit(1)
                resync(conn, args.tenant_id, commit=args.commit)
            if args.parts or args.only_parts:
                resync_parts(conn, args.tenant_id, commit=args.commit,
                             rehost_images=not args.no_rehost_images)
            if args.commit:
                cur = conn.cursor()
                cur.execute("UPDATE tenants SET ets_last_synced_at = %s WHERE id = %s",
                            (datetime.now(timezone.utc), args.tenant_id))
                conn.commit()
                cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
