# DB-038 Parts and Purchasing Redesign Contract v2

Status: Architecture GO for bounded implementation

Product approval: 2026-08-24

Implementation base: `20d9d658443b7931c437508d78d155f9017a4f5a`

Supersedes only the presentation, read-projection, supplier-source, and grouped-purchasing boundaries of `DB-038_PARTS_OPERATIONS_CONTRACT.md`. Stock, WAC, receipt, return, core, tenant, authorization, idempotency, and compatibility invariants from v1 remain binding.

## 1. Product decision

DieselBridge will provide two connected My Shop destinations:

- **Parts & inventory** — All parts, Needs reorder, and Movement.
- **Purchasing** — Purchase orders, Suppliers, Receiving, and Returns & cores.

The redesign is additive. A design handoff may introduce structure and visual language, but omission from that handoff never removes an existing production capability. Part photos, archived-part safety, repair-demand provenance, purchase-order lifecycle, receiving, returns, cores, movement history, adjustment reasons, tenant boundaries, and role gates remain required.

CSV inventory import is explicitly deferred. No inactive or placeholder Import CSV control may render.

## 2. Operating model

The primary audience is shop staff working under time pressure at a parts counter, service desk, or mobile device. The interface is an **Operate** surface: scanability, trustworthy state, and fast completion outrank decoration.

### Parts & inventory answers

- What is available now?
- What is needed for open repairs?
- What has reached its reorder point?
- What supply is already incoming?
- Where is the part and what does it look like?
- Which source should replenish it?
- What stock movement produced the current balance?

### Purchasing answers

- What needs to be purchased and why?
- Which supplier should receive each line?
- Which lines can be consolidated?
- What is draft, submitted, partially received, received, delayed, cancelled, returned, or credited?
- What did the shop last pay and which source is preferred?

### Cross-workspace continuity

- Needs reorder can prepare purchasing lines and open Purchasing with those lines in context.
- A part's Ordering detail links to its open and historical purchase orders.
- A purchase-order line links back to the canonical part.
- Receiving refreshes available stock, incoming supply, WAC, and movement history atomically.
- Cancelled and short-received quantities return to the reorder projection when still needed.

## 3. Stock and costing language

`inventory.stock_quantity` remains the canonical available package balance. Repair reservation already decrements this balance. The redesign must never calculate `free = on_hand - committed`, because that would subtract repair reservations twice.

Human-facing quantities are:

- **Available** — `inventory.stock_quantity`.
- **Needed for open repairs** — repair shortage packages not physically reserved.
- **Reorder at** — configured shelf threshold.
- **Incoming** — remaining submitted or partially received PO packages plus unreconciled legacy incoming quantity.
- **Recommended order** — the v1 demand projection.

WAC is displayed as **Average unit cost**. It changes through receiving or an explicit audited correction. The new interface does not expose a naked WAC field or direct Incoming edit. Legacy mutation compatibility remains available through the v1 rollback surface until separately retired.

## 4. Data amendment

Migration revision: `125_inventory_supplier_sources`, directly after `124_parts_operations_v1`.

### 4.1 Supplier purchasing profile

Add nullable fields to `suppliers`:

- `payment_terms VARCHAR(100)`
- `default_lead_time_days INTEGER`, constrained `0..365`
- `minimum_order_amount NUMERIC(12,2)`, constrained non-negative
- `purchasing_notes TEXT`

These are tenant-owned commercial facts. On-time performance is derived from submitted PO expectations and immutable receipts; it is never directly entered.

### 4.2 Inventory supplier sources

Create `inventory_supplier_sources`:

- `id`, `tenant_id`, `inventory_id`, `supplier_id`
- `supplier_part_number VARCHAR(150)`
- `is_preferred BOOLEAN NOT NULL DEFAULT FALSE`
- `minimum_order_quantity INTEGER`, constrained `1..999`
- `pack_quantity INTEGER`, constrained `1..999`
- `last_unit_cost NUMERIC(12,2)`, nullable and non-negative
- `lead_time_days INTEGER`, nullable and constrained `0..365`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- timestamps and soft deletion

Constraints:

- unique live `(tenant_id, inventory_id, supplier_id)`;
- at most one live preferred source per tenant/inventory;
- every referenced inventory and supplier belongs to the same tenant;
- setting a preferred source synchronizes `inventory.preferred_supplier_id` in the same transaction;
- removing the preferred source clears or replaces that pointer explicitly, never implicitly across tenants.

`last_unit_cost` is updated from the latest accepted receipt for that source. It is not a replacement for inventory WAC.

## 5. Read API amendment

Base path remains `/api/v1/parts-operations`. All collection responses use `{items,total,skip,limit,has_more}` when `paginated=true`; default `limit=50`, maximum `100`, with stable ordering ending in UUID.

### 5.1 Parts collection

`GET /parts?view=active|archived|all&attention=needs_reorder|out_of_stock|incoming&supplier_id=&search=&sort=catalog|name|available|reorder&skip=&limit=&paginated=true`

Example item:

```json
{
  "id": "10000000-0000-4000-8000-000000000101",
  "sku": "DB-OIL-FILTER-01",
  "name": "Oil filter",
  "image_url": "https://cdn.example/part.jpg",
  "unit_type": "each",
  "location": "A3-S2",
  "available_packages": 1,
  "needed_for_open_repairs": 2,
  "reorder_level": 3,
  "incoming_packages": 1,
  "recommended_order_packages": 3,
  "average_unit_cost": "16.00",
  "is_archived": false,
  "is_placeholder": false,
  "preferred_source": {
    "source_id": "41000000-0000-4000-8000-000000000411",
    "supplier_id": "40000000-0000-4000-8000-000000000401",
    "supplier_name": "Fleet Supply",
    "supplier_part_number": "FS-OF-01",
    "minimum_order_quantity": 1,
    "pack_quantity": 1,
    "lead_time_days": 2,
    "last_unit_cost": "15.75"
  }
}
```

Search covers name, SKU, supplier name, supplier part number, and location. Archived records are excluded by default and remain read-only in the new surface.

### 5.2 Part detail

`GET /parts/{inventory_id}` returns the collection item plus:

- active supplier sources;
- open purchase-order lines;
- last five receipts;
- last twenty movements;
- repair-demand sources with repair order ID, order number, status, vehicle/unit display, shortage packages, and source link.

Foreign, missing, deleted, disabled, and unlinked records are indistinguishable generic `404`.

### 5.3 Supplier purchasing detail

`GET /suppliers/{supplier_id}/purchasing` returns the compatible supplier projection plus terms, default lead time, minimum order, purchasing notes, active part-source count, open PO count/value, last receipt date, and derived on-time evidence. A rate or percentage is `null` until the server has a meaningful denominator; the UI displays “Not enough receiving history.”

## 6. Supplier-source mutations

- `POST /parts/{inventory_id}/supplier-sources`
- `PATCH /parts/{inventory_id}/supplier-sources/{source_id}` with `expected_updated_at`
- `DELETE /parts/{inventory_id}/supplier-sources/{source_id}` with `expected_updated_at`

Owner/admin only. Receptionist is read-only. Requests validate tenant ownership before disclosure. Duplicate live source returns `409`; stale version returns `409`; validation returns `422`; absent feature or unsupported context returns generic `404`.

Every POST requires `Idempotency-Key` under the existing durable tenant + operation-family boundary. Preference changes and `inventory.preferred_supplier_id` synchronize atomically.

## 7. Grouped purchase-order preparation

`POST /purchase-orders/batch`

The operation creates one draft PO per supplier in a single transaction. It never submits orders automatically.

Request:

```json
{
  "groups": [
    {
      "supplier_id": "40000000-0000-4000-8000-000000000401",
      "lines": [
        {
          "inventory_id": "10000000-0000-4000-8000-000000000101",
          "ordered_quantity": 3,
          "unit_cost": "15.75",
          "source_id": "41000000-0000-4000-8000-000000000411"
        }
      ]
    }
  ],
  "notes": "Prepared from Needs reorder"
}
```

Response `201`:

```json
{
  "purchase_orders": [
    {
      "id": "20000000-0000-4000-8000-000000000201",
      "po_number": "PO-20260824-0001",
      "supplier_id": "40000000-0000-4000-8000-000000000401",
      "status": "draft",
      "line_count": 1,
      "ordered_quantity": 3
    }
  ],
  "unassigned": []
}
```

Rules:

- caller supplies only assigned groups; unassigned parts remain in the client preparation tray and are excluded from totals;
- PO numbers are allocated by the server under tenant lock and remain unique;
- each source must be active and match both line inventory and group supplier;
- quantity honors source minimum and pack quantity;
- duplicate inventory lines across groups are `422`;
- any invalid group rolls back every draft;
- the request requires durable idempotency; same key and fingerprint replays, changed fingerprint returns `409`;
- concurrent requests cannot allocate the same tenant PO number or create duplicate drafts for one durable request.

Existing single-PO routes remain compatible.

## 8. Navigation and interface contract

Canonical routes:

- `/dashboard/garage/inventory` — Parts & inventory.
- `/dashboard/garage/purchasing` — Purchasing.
- `/dashboard/garage/suppliers` remains a compatible redirect into `/dashboard/garage/purchasing?view=suppliers`.

Parts & inventory:

- one page title and concise operating summary;
- All parts, Needs reorder, and Movement views;
- server-backed search/filter/sort with bounded rendering;
- desktop table + selected-part drawer;
- compact/mobile list + full-width detail transition;
- part image, tenant-logo fallback, then neutral package icon;
- detail sections Overview, Stock, Ordering, History;
- contextual “Prepare purchase order” and “Open in Purchasing” actions;
- no default archived selection and no archived mutation.

Purchasing:

- Purchase orders, Suppliers, Receiving, and Returns & cores views;
- preparation tray groups assigned lines by supplier;
- draft creation reports exact success/failure and retains recoverable input;
- receipt and return mutations preserve v1 single-flight, idempotency, version, and error behavior;
- every commercial or stock action is hidden from read-only roles while state remains readable.

## 9. Theme and accessibility contract

The redesign inherits the authenticated DieselBridge theme system. It does not introduce a detached Inventory theme and does not replace `ThemeContext` with CSS `light-dark()`.

Add shared semantic tokens for the handoff's service-manual language:

- `--parts-paper` — selected-row/action-block field;
- `--parts-paper-text` — foreground on paper;
- `--parts-oxide` and `--parts-oxide-hover` — high-value purchasing action;
- `--parts-rule` — technical divider;
- `--parts-technical-muted` — secondary operating copy.

Each token has light, dark, and high-contrast values under the existing `data-appearance-mode` boundary. Existing product navy, road white, copper, semantic state, and personal accent tokens remain authoritative. Oxide is reserved for purchasing action and never becomes a competing global brand accent.

Requirements:

- normal text contrast at least 4.5:1; large text/UI boundaries at least 3:1;
- every interactive target at least 44 CSS px, or 48 in large density;
- visible focus in all modes and Windows forced colors;
- status is never communicated by color alone;
- selected-row inversion preserves readable links, buttons, and focus;
- no horizontal document overflow at 320, 390, 960, or 1280 CSS px;
- 200% zoom retains every key value and action;
- edit/save/cancel transitions restore or deliberately move focus with announcement;
- dark, light, and high contrast receive identical information and capability.

## 10. Compatibility and rollout

- Existing inventory, supplier, photo, PO, receipt, return, core, and activity routes remain compatible.
- Existing part IDs, supplier IDs, PO IDs, SKU uniqueness, movement history, and WAC remain unchanged.
- The feature gate still fails closed before any protected read.
- No production migration, feature enablement, data rewrite, push, PR, merge, or deployment is authorized by this contract.
- Migration 125 must be additive and downgrade only its own fields/table.
- CSV import, external vendor integrations, attachments, landed cost, counter sales, and automatic PO submission remain deferred.

## 11. Deterministic acceptance fixture

Extend `backend/tests/fixtures/db038_parts_operations.json` with:

- one active part with photo, bin, preferred source, alternate source, reorder need, repair shortage, incoming PO, receipt history, and movement history;
- one active part without a supplier source;
- one archived part with history but no mutation capability;
- two suppliers with different minimum, pack, terms, and lead times;
- one receptionist and one owner/admin path;
- a second tenant reusing visible names/SKUs/source numbers to prove isolation;
- grouped-draft success, duplicate-line failure, invalid-source rollback, idempotent replay, changed-fingerprint conflict, and concurrent number-allocation cases;
- light, dark, high-contrast, 1280, 960, 390, and 320 browser expectations.

## 12. Delivery handoff

Board ID: DB-038

From / To: Product & Delivery Lead -> Architecture & API Contracts -> Backend & Integrations -> Frontend & UX

User outcome: shop staff can understand parts availability and repair demand, prepare supplier-grouped purchasing, receive supply, and trace inventory without leaving a coherent My Shop workflow.

Scope explicitly not completed: CSV import, attachments, vendor integrations, automatic submission, landed cost, counter sales, production migration, rollout enablement, merge, and deploy.

Known risks: populated supplier backfill, duplicate supplier relationships, generated PO-number concurrency, responsive density, selected-row contrast, and stale edit focus.

Branch / environment: `codex/db038-ux-recovery`; local candidate only.

Return condition: any change to stock semantics, negative-stock rules, WAC, tenant authority, durable idempotency, receipt immutability, or automatic submission returns to Architecture and Product before implementation continues.
