# Easy Truck Shop → TruckPitStop sync

Permanent tooling to pull shop data from **easytruck.shop** (a Laravel/Sanctum
app) and resync it into TruckPitStop. Safe to re-run as Easy Truck Shop keeps
adding data — it only inserts what's new and updates what changed, matching on
stable ids.

## Layout

```
easytruck_sync/
  lib/auth.js            Playwright login session (reads ../.env)
  lib/scrape_helpers.js  shared per-customer scrape routines
  01..07_scrape_*.js     the scrape pipeline (writes data/*.json)
  import_to_truckpitstop.py  idempotent resync importer
  .env.example           copy to .env and fill in (gitignored)
  data/                  scraped JSON output (gitignored)
```

## Setup (one time)

```bash
cd backend/scripts/easytruck_sync
cp .env.example .env         # then edit .env with real ETS_EMAIL / ETS_PASSWORD
npm install
npx playwright install chromium
```

**Never commit `.env` or `data/`** — both are gitignored. They hold credentials
and real customer data. Do not paste the password into a chat/PR.

## Scrape

Run the pipeline in order (each stage is resumable — re-running skips work
already saved in `data/`):

```bash
node 01_scrape_customer_ids.js       # -> data/customer_ids.json
node 02_scrape_customer_details.js   # -> data/customer_details.json (contacts, vehicles, service history)
node 03_scrape_parts_usage.js
node 04_scrape_parts_inventory.js
node 05_scrape_invoices.js
node 06_scrape_attachments.js
node 07_scrape_mc_qb.js
```

Stage 02 (`customer_details.json`) is what the importer consumes for
customers / vehicles / repair orders.

## Import / resync

Uses `$DATABASE_URL` (async URLs are normalized) or falls back to the local dev
DSN. Always dry-run first.

```bash
# activate the backend venv so psycopg2 is available
cd backend && source venv/bin/activate && cd scripts/easytruck_sync

# 1) ONE TIME on a DB that was populated by the original (pre-external-id) import:
#    stamp ets_external_id onto existing rows so they become matchable.
python3 import_to_truckpitstop.py --backfill-external-ids --tenant-id <TENANT_UUID> --dry-run
python3 import_to_truckpitstop.py --backfill-external-ids --tenant-id <TENANT_UUID> --commit

# 2) Every resync thereafter (customers / vehicles / repair orders):
python3 import_to_truckpitstop.py --tenant-id <TENANT_UUID> --dry-run
python3 import_to_truckpitstop.py --tenant-id <TENANT_UUID> --commit

# Include parts inventory (location + images) in the same run:
python3 import_to_truckpitstop.py --tenant-id <TENANT_UUID> --parts --dry-run
python3 import_to_truckpitstop.py --tenant-id <TENANT_UUID> --parts --commit

# Parts only:
python3 import_to_truckpitstop.py --tenant-id <TENANT_UUID> --only-parts --commit

# Parts without re-hosting images to Cloudinary (metadata + location only):
python3 import_to_truckpitstop.py --tenant-id <TENANT_UUID> --only-parts --no-rehost-images --commit
```

### Parts inventory

Matched on `sku` (= Easy Truck Shop part number) scoped to the tenant + import
source. Priority fields are **location** and **images**:

- `location` comes from the parts list's LOCATION column.
- Part images are scraped from each part's detail page and, on `--commit` with
  Cloudinary configured (`CLOUDINARY_URL` / `CLOUDINARY_*` env), re-uploaded via
  Cloudinary so they survive independently of Easy Truck Shop. Existing local
  images are never overwritten. `--no-rehost-images` skips the upload.

Requires no schema change — the `inventory` table already has `location`,
`image_url`, and `cloudinary_public_id`.

### Matching & merge policy

| Entity        | Match key                                   |
|---------------|---------------------------------------------|
| customers     | `ets_external_id` (ETS customer id)         |
| vehicles      | `ets_external_id` (ETS vehicle id)          |
| repair_orders | `order_number` = `ETS-{service_no}-{cust}`  |

- Inserts records we don't have.
- Updates an existing import-tagged row **only if it hasn't been hand-edited
  since import** (`updated_at` within a few seconds of `created_at`). A scraped
  field that is empty never overwrites a non-empty local value.
- Never touches rows whose `source` isn't `easy_truck_shop_import`.
- Repair orders are insert-only (historical work orders don't change).

Requires migration `080_add_ets_external_id` (adds the `ets_external_id`
columns) to be applied on the target DB.
