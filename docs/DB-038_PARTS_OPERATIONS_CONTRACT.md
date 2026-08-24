# DB-038 Parts Operations Contract v1

Status: Architecture GO for implementation handoff; Amendment 1 defers purchase-order attachments

Scope: Phase 1 only — activity and demand, purchasing and receiving, vendor returns and cores

Base: `origin/main` at `ca11a4f7ab386b99c5f60a818ba67919876dcaf5`

Intake: `a6fc91016d95e08baa2cbf7e07ffa9bc5eafa128`

## 1. Decision

DieselBridge will extend the existing tenant inventory and repair-order parts model; it will not create a second catalog or stock balance.

- `Inventory` remains the canonical tenant-owned part/SKU and `inventory.stock_quantity` remains the Phase 1 materialized on-hand package balance.
- Every balance change is accompanied in the same database transaction by an immutable movement. The movement history is authoritative audit evidence; it is not an eventually consistent analytics copy.
- Repair-order consumption retains the existing whole-package reservation, shortage override, cost snapshot, and restoration behavior.
- Purchase receipts use moving weighted-average cost (WAC). Receipt unit cost excludes refundable core charges and taxes/shipping not allocated to the line. Phase 1 does not implement landed-cost allocation.
- A vendor stock return decreases on-hand at the item's current WAC and records the expected/actual vendor credit separately. It does not rewind historical WAC.
- A core is a custody bucket, not saleable on-hand inventory. Core obligations originate from a core-bearing repair-order part usage and move through `expected`, `on_hand`, `returned`, or `waived` states.
- No stock-bearing operation may produce a negative balance. No over-receiving is allowed in Phase 1.
- The feature is additive and tenant gated. Counter sales, parts-only invoices/payments, purchase-order attachments, external vendor integrations, AI extraction, and broad reporting remain out of scope.

These choices leave no unresolved purchasing or costing fork requiring Product escalation.

## 2. Source-grounded baseline

| Existing source | Contract implication |
|---|---|
| `backend/app/db/models/inventory.py` — `Inventory` | Preserve tenant SKU, package balance, on-order, reorder point, cost, price, core charge, unit type, location, photo, and placeholder state. |
| `backend/app/db/models/inventory.py` — `PartsUsage` | Preserve repair-order provenance, quantity, cost/price snapshots, reserved package count, and shortage override. |
| `backend/app/api/v1/endpoints/repair_orders.py` — add/update/delete parts | Continue ordered row locks, `ceil` package consumption for fractional units, explicit shortage override, and exact restoration of reserved packages. |
| `backend/app/services/price_build_service.py` — service parts | Continue deterministic inventory lock ordering and skip bundled parts that would make stock negative. |
| `backend/app/api/v1/endpoints/inventory.py` | Existing inventory CRUD, typeahead, photo, and direct receive routes require an explicit compatibility path. The current direct receive operation has no PO, durable idempotency, ledger, or WAC calculation. |
| `backend/app/db/models/supplier.py` and `backend/app/api/v1/endpoints/suppliers.py` | Normalize tenant suppliers without replacing their current IDs or breaking the existing API. |
| `backend/alembic/versions/120_inventory_is_placeholder.py` | Placeholder promotion and historical repair-order links must remain intact. |
| `backend/alembic/versions/121_inventory_canonical_sku_unique.py` and `backend/scripts/merge_duplicate_inventory.py` | Canonical live SKU uniqueness is a prerequisite. No fuzzy SKU/category/vendor merge is authorized. |
| `frontend/src/features/inventory/InventoryPage.tsx` | Preserve existing catalog management while adding the gated operations workspace. |
| `frontend/src/features/garage/MyGaragePage.tsx` | Inventory and Suppliers remain under the canonical My Shop route; no duplicate top-level route or navigation state. |
| `backend/app/middleware/idempotency.py` | Keep HTTP replay behavior, but add durable domain idempotency because the Redis result cache is not a financial/stock record. |

Current inventory and supplier list/detail queries conditionally omit tenant predicates when a principal has no tenant. Phase 1 endpoints must instead require a server-derived tenant before any protected lookup. Existing endpoints touched by the implementation must receive the same hardening; foreign, missing, deleted, disabled, and unlinked resources are all generic `404`.

## 3. Data contract

Migration revision: `124_parts_operations_v1`, directly after `123_inventory_ets_imported_at`.

Every new operational table has `tenant_id NOT NULL`, indexed tenant ownership, `created_at`, `updated_at`, and soft deletion only where stated. Relationships supplied by a caller are validated with tenant predicates before authorization-dependent disclosure. Cross-tenant foreign keys are prohibited by composite tenant/id constraints or equivalent database constraints plus service validation.

### 3.1 Catalog normalization

`inventory_categories`

- `id`, `tenant_id`, `name`, `normalized_name`, `description`, `is_active`, timestamps.
- Unique live `(tenant_id, normalized_name)`.
- Normalization is trim, collapse internal whitespace, and case-fold only. No fuzzy or semantic merge.

`suppliers` additions

- `normalized_name`, `is_active`, `account_reference`, `email`.
- Unique live `(tenant_id, normalized_name)`.
- Existing supplier IDs and fields remain stable.

`inventory` additions

- `category_id` nullable tenant-owned FK.
- `preferred_supplier_id` nullable tenant-owned FK.
- `cost` remains the materialized WAC, `NUMERIC(12,2)`, never negative.
- `stock_version BIGINT NOT NULL DEFAULT 0`; increment on every stock/core-affecting transaction involving the item.
- Existing `category`, `supplier_name`, `supplier_contact`, and `on_order_quantity` remain during compatibility.

`tenants` addition

- `parts_operations_enabled BOOLEAN NOT NULL DEFAULT FALSE`; it is the tenant rollout gate and never grants a role permission.

### 3.2 Purchase orders

`purchase_orders`

- `id`, `tenant_id`, `po_number`, `supplier_id`, `status`, `ordered_at`, `expected_at`, `notes`, `version`, actor/timestamps.
- Status: `draft -> submitted -> partially_received -> received`; `draft|submitted -> cancelled` only when no receipt exists.
- Unique live `(tenant_id, po_number)`.

`purchase_order_lines`

- `id`, `tenant_id`, `purchase_order_id`, `inventory_id`.
- Immutable submitted snapshots: `sku`, `description`, `unit_type`, `unit_cost`, `core_charge`.
- `ordered_quantity INTEGER` in stock packages, `1..999`.
- `received_quantity INTEGER NOT NULL DEFAULT 0`, constrained `0 <= received <= ordered`.
- Draft lines may be edited/deleted. Submitted lines are immutable; corrections use cancellation before receipt or a new PO.

`purchase_receipts`

- `id`, `tenant_id`, `purchase_order_id`, `receipt_number`, `received_at`, `supplier_reference`, `notes`, `received_by_user_id`.
- `operation_family`, `idempotency_key`, `request_fingerprint`; unique `(tenant_id, operation_family, idempotency_key)`.
- Receipts are immutable and never soft-deleted.

`purchase_receipt_lines`

- `id`, `tenant_id`, `purchase_receipt_id`, `purchase_order_line_id`, `inventory_id`.
- `quantity INTEGER`, `unit_cost NUMERIC(12,2)`, `wac_before`, `wac_after`, `balance_before`, `balance_after`.
- A receipt correction is a vendor return or an explicit inventory adjustment; receipt deletion/rewrite is forbidden.

### 3.2.1 Amendment 1 — attachment deferral

Purchase-order attachments are deferred from DB-038 Phase 1 and are not an API, UI, fixture, Security, or QA acceptance requirement for this release.

The repository has no existing private general-object storage boundary to reuse:

- `backend/app/services/cloudinary_service.py` handles hosted images only (`resource_type="image"`) and returns hosted URLs/public IDs.
- inventory and repair-order upload routes validate and publish images through that image-specific service;
- invoice PDF download routes generate bytes on demand and do not persist uploaded documents;
- there is no existing private PDF/object upload adapter, tenant-authorized signed download, provider-neutral storage-key API, or orphan cleanup worker.

Using the image pattern for invoices/packing slips would either exclude PDFs or invent Cloudinary raw/private delivery, retention, signing, and cleanup semantics outside the accepted contract. Purchase documents are supporting evidence, not an input to ordered/received quantities, WAC, stock movements, approvals, demand, or return/core origins, so their absence does not weaken any Phase 1 stock or tenant invariant.

The additive `purchase_order_attachments` metadata table/model already present in the Backend draft may remain empty and unreachable to avoid churn, or Backend may remove it before its implementation commit. Either choice is contract-equivalent for Phase 1 provided there is no attachment route, browser surface, fixture data, stored object, or claim that attachments are supported. A later Phase 1.1 board item must select a private storage provider/adapter and independently contract upload, content validation, malware posture, authorization, idempotency, cleanup, retention, and download behavior before any metadata is written.

### 3.3 Immutable inventory movements

`inventory_movements`

- No update/delete API and no soft delete.
- Fields: `id`, `tenant_id`, `inventory_id`, `bucket`, `movement_type`, `quantity_delta`, `balance_before`, `balance_after`, `unit_cost_snapshot`, `wac_before`, `wac_after`, `source_type`, `source_id`, `destination_type`, `destination_id`, `actor_user_id`, `actor_display_name_snapshot`, `reason_code`, `note`, `idempotency_key`, `occurred_at`, `created_at`.
- `bucket`: `on_hand` or `core_on_hand`.
- Phase 1 movement types: `migration_opening_balance`, `repair_reservation`, `repair_release`, `po_receipt`, `vendor_return`, `vendor_return_reversal`, `core_recovery`, `core_return`, `core_return_reversal`, `legacy_direct_receipt`, `manual_adjustment`.
- `quantity_delta != 0`; `balance_before >= 0`; `balance_after >= 0`; `balance_after = balance_before + quantity_delta`.
- Unique `(tenant_id, idempotency_key)` when non-null.
- Source/destination IDs are never resolved without the movement's tenant predicate.

Repair-order mutations must add movements atomically:

- add/expand parts: negative `repair_reservation` for the packages actually reserved;
- reduce/delete/cancel: positive `repair_release` for the packages actually restored;
- shortage quantity not physically reserved creates no fictional negative movement; its demand remains visible through `PartsUsage.stock_shortage_override` and required-versus-reserved packages.

### 3.4 Returns and cores

`core_obligations`

- `id`, tenant, `parts_usage_id`, `inventory_id`, optional `supplier_id`, whole-package quantity, unit core value snapshot, status, version, actor/timestamps.
- Unique live origin `(tenant_id, parts_usage_id)`.
- Created when a core-bearing `PartsUsage` is committed. Initial status `expected`.
- `expected -> on_hand -> returned`; `expected|on_hand -> waived` requires an owner/admin reason. Removing the originating part usage before recovery moves `expected -> cancelled`; an `on_hand` core blocks deletion of its origin until it is returned, waived, or reversed. A returned, waived, or cancelled obligation is terminal except through a recorded reversal where defined.

`vendor_returns`

- `id`, tenant, return number, supplier, kind (`stock|core`), status (`draft|submitted|shipped|credited|cancelled`), version, dates, reference, notes, actors.
- Draft/submitted may cancel only before a stock movement is posted.
- Shipping posts the physical movement. Crediting records commercial completion but does not change stock.
- A reversal is an append-only event that physically restores the original quantity and links `reverses_return_id`; it never edits the original movement. It is allowed once, owner/admin only, with reason and idempotency key. Stock/core balance is restored, while WAC remains unchanged in both directions.

`vendor_return_lines`

- Stock return: `purchase_receipt_line_id` is required; inventory and supplier must match that tenant-owned receipt origin. Returnable quantity cannot exceed received minus prior shipped/reversed returns.
- Core return: `core_obligation_id` is required and must be `on_hand`; inventory/supplier must match the obligation.
- Records quantity, expected credit, actual credit, current-WAC stock value snapshot, and original origin snapshots.
- Stock return decreases on-hand using current WAC and leaves the materialized WAC unchanged. Core return decreases `core_on_hand` and never changes saleable stock/WAC.

### 3.5 Demand projection

Demand is a read projection, not independently mutable state.

- Repair shortage packages = `ceil(PartsUsage.quantity) - stock_reserved_packages` for non-deleted parts on non-terminal editable repair orders, never below zero.
- Shelf replenishment packages = `max(reorder_level - stock_quantity, 0)`.
- Open supply = remaining submitted/partially-received PO quantity plus the legacy `on_order_quantity` only while that legacy value has not been reconciled.
- Recommended order = `max(repair_shortage + shelf_replenishment - open_supply, 0)`.
- Each summary retains source rows for repair order, part usage, reorder rule, and open PO; the UI must not imply a repair allocation where none exists.
- Placeholder parts are shown as `unlinked` demand and cannot be placed on a PO until promoted to a canonical stocked item.

## 4. API contract

Base path: `/api/v1/parts-operations`. Responses use decimal strings and UTC ISO-8601 timestamps. Collection endpoints use the existing paginated envelope when `paginated=true`; default limit 50, maximum 100.

### 4.1 Read endpoints

- `GET /summary`
- `GET /demand?state=open|covered|unlinked&supplier_id=&search=&skip=&limit=`
- `GET /activity?inventory_id=&source_type=&movement_type=&from=&to=&skip=&limit=`
- `GET /purchase-orders?status=&supplier_id=&search=&skip=&limit=`
- `GET /purchase-orders/{po_id}`
- `GET /returns?kind=&status=&supplier_id=&skip=&limit=`
- `GET /returns/{return_id}`
- `GET /cores?status=&supplier_id=&inventory_id=&skip=&limit=`
- `GET /categories`; `GET /suppliers` remains compatible and gains additive normalized fields.

Example demand item:

```json
{
  "inventory_id": "10000000-0000-4000-8000-000000000101",
  "sku": "DB-OIL-FILTER-01",
  "name": "Oil filter",
  "unit_type": "each",
  "stock_quantity": 1,
  "reorder_level": 3,
  "repair_shortage_packages": 2,
  "shelf_replenishment_packages": 2,
  "open_supply_packages": 1,
  "recommended_order_packages": 3,
  "fresh_as_of": "2026-08-23T14:00:00Z",
  "sources": [
    {"type": "repair_order", "repair_order_id": "30000000-0000-4000-8000-000000000301", "order_number": "TPS-000301", "packages": 2},
    {"type": "reorder_level", "packages": 2}
  ]
}
```

### 4.2 Purchase mutations

- `POST /purchase-orders` — create draft.
- `PATCH /purchase-orders/{po_id}` with `expected_version` — edit draft header/lines.
- `POST /purchase-orders/{po_id}/submit` with `expected_version`.
- `POST /purchase-orders/{po_id}/cancel` with `expected_version` and reason.
- `POST /purchase-orders/{po_id}/receipts` — partial/final receive.

All POST mutation requests require `Idempotency-Key` of 16–128 safe printable characters. Durable scope is tenant + operation family + key. The stored fingerprint includes method, canonical route, authenticated principal, and canonical JSON/body checksum. Same key/same fingerprint replays the original status/body with `Idempotency-Replayed: true`; same key/different fingerprint is `409`.

Receipt request:

```json
{
  "expected_version": 4,
  "received_at": "2026-08-23T14:00:00Z",
  "supplier_reference": "PACKING-8821",
  "lines": [
    {"purchase_order_line_id": "20000000-0000-4000-8000-000000000211", "quantity": 4, "unit_cost": "18.25"}
  ],
  "notes": "Four received; two remain backordered"
}
```

Response `201`:

```json
{
  "receipt_id": "20000000-0000-4000-8000-000000000221",
  "purchase_order_id": "20000000-0000-4000-8000-000000000201",
  "purchase_order_status": "partially_received",
  "version": 5,
  "lines": [{
    "inventory_id": "10000000-0000-4000-8000-000000000101",
    "received_quantity": 4,
    "remaining_quantity": 2,
    "balance_before": 1,
    "balance_after": 5,
    "wac_before": "16.00",
    "wac_after": "17.80"
  }]
}
```

WAC is calculated under lock using Decimal arithmetic:

`round_half_up(((old_on_hand * old_wac) + (received_qty * receipt_unit_cost)) / (old_on_hand + received_qty), 2)`.

If old on-hand is zero, new WAC is receipt unit cost. Intermediate arithmetic uses at least six decimal places; rounding occurs once at persistence. A receipt with no accepted quantity is rejected.

### 4.3 Return/core mutations

- `POST /cores/{obligation_id}/recover` — `expected -> on_hand`, posts `core_recovery`.
- `POST /cores/{obligation_id}/waive` — owner/admin reason required.
- `POST /returns` — create draft from valid origin lines.
- `PATCH /returns/{return_id}` with `expected_version` — draft only.
- `POST /returns/{return_id}/submit|ship|credit|cancel` with expected version.
- `POST /returns/{return_id}/reverse` — owner/admin, once, reason required.

Example stock-return line:

```json
{
  "kind": "stock",
  "supplier_id": "40000000-0000-4000-8000-000000000401",
  "lines": [{
    "purchase_receipt_line_id": "20000000-0000-4000-8000-000000000222",
    "quantity": 1,
    "expected_credit": "18.25"
  }],
  "reason": "damaged_in_box"
}
```

## 5. Transaction, ordering, and failure semantics

Receipt transaction order is mandatory:

1. Derive tenant from the authenticated server principal; reject absent/inactive tenant.
2. Validate schema, quantity/money bounds, key format, and request fingerprint before database locks/writes.
3. Resolve PO, supplier, lines, and inventory with tenant predicates; foreign/missing/deleted return generic `404`.
4. Claim/read the durable idempotency record.
5. Lock PO, then PO lines, then inventory rows sorted by UUID, then relevant return/core rows sorted by UUID.
6. Revalidate version, lifecycle, remaining quantities, origins, balances, and all line calculations. Any failure rolls back the entire request.
7. Insert receipt/return and movement rows, update balances/WAC/versions/status, and store the replay response in one commit.

The same lock order applies to repair-order stock mutations after those mutations are moved behind the shared inventory movement service. No request may lock inventory first and then its parent document.

Concurrency invariants:

- Same receipt key racing twice commits once and both callers obtain the same receipt outcome.
- Different keys racing for the last PO quantity: one commits; the stale/over-receipt request returns `409` with no movement, balance, WAC, status, or version change.
- A repair reservation racing a receipt/return is serialized on the inventory row; neither can observe or create a negative balance.
- A transaction that changes multiple items is all-or-nothing.
- Database commit uncertainty is resolved by reading the durable key on retry, never by issuing an unkeyed second mutation.

## 6. Authorization and non-enumeration

| Capability | Owner | Admin | Receptionist | Mechanic | Fleet manager | Customer/driver | Super admin |
|---|---:|---:|---:|---:|---:|---:|---:|
| Inventory/demand/activity read | yes | yes | yes | no — legacy repair-order typeahead only | no | no | only via explicit tenant support context |
| PO/receipt/return/core read | yes | yes | yes | no | no | no | only via explicit tenant support context |
| Catalog/category/supplier mutation | yes | yes | no | no | no | no | no implicit access |
| PO draft/submit/cancel/receive | yes | yes | no | no | no | no | no implicit access |
| Return/core transition | yes | yes | no | no | no | no | no implicit access |
| Manual adjustment/waive/reversal | yes | yes | no | no | no | no | no implicit access |
| Repair-order part reservation | existing repair-order role rules | existing | existing | assigned/additive existing rules | internal-fleet existing rules | no | no implicit access |

Receptionists may see purchasing state needed to answer shop questions but cannot change stock or commercial documents. Mechanics retain their existing tenant-scoped repair-order part typeahead and mutation behavior, but the new parts-operations API does not expose demand, costs, vendor pricing, purchase orders, returns, or activity to them. Fleet-manager access remains confined to existing internal-fleet repair behavior; Phase 1 does not grant shop purchasing access.

All server queries begin with the authenticated tenant. Known foreign UUID, random UUID, deleted row, wrong parent-child pairing, unlinked origin, and disabled feature have indistinguishable `404` bodies. Role denial for a same-tenant resource is `403` only after the resource has been tenant-scoped. Logs and metrics contain tenant-safe internal IDs but never supplier account references, request bodies, or secrets.

## 7. Validation and errors

- `400`: malformed/missing idempotency key or structurally invalid transition command.
- `401`: no valid authenticated session.
- `403`: authenticated same-tenant principal lacks capability.
- `404`: foreign, missing, deleted, wrong-parent, unlinked, or feature-disabled resource.
- `409`: stale `expected_version`, invalid current lifecycle, key/payload mismatch, request in progress, over-receipt, insufficient stock, already reversed, duplicate normalized name/SKU, or conflicting concurrent write.
- `422`: field validation (non-positive/excess quantity, excessive precision, invalid dates/money).
- `503`: an operational dependency is unavailable before mutation. Database/commit uncertainty returns the standard correlation-safe server error; retry with the same key is required.

Money is `0.00..999999.99`, maximum two decimals, and an order/return line total may not exceed `9999999.99`. Unit cost for a stock receipt must be positive; credits may be zero. Stock package quantities are integers `1..999`. Notes are at most 2,000 characters; references/numbers 100 characters; names 255 characters. Rejected requests—including quantity `1000` or an excessive computed line total—are mutation-free, including timestamps and versions.

## 8. Compatibility, rollout, and rollback

Two gates are required:

- deployment kill switch `PARTS_OPERATIONS_V1_ENABLED`, default false;
- `tenants.parts_operations_enabled`, default false, owner-visible only after platform enablement.

Effective enablement requires both. The browser cannot override either. New routes return generic `404` when disabled.

Compatibility sequence:

1. Deploy migration, models, movement service, and APIs with both gates off.
2. Backfill and verify opening balances. From this point, every stock mutation—including legacy inventory receive and repair-order reservations/releases—must transactionally write a movement.
3. Legacy `GET /inventory`, typeahead, photos, suppliers, and current response fields remain unchanged. New normalized IDs/versions are additive nullable fields.
4. While Phase 1 UI is gated, `POST /inventory/{id}/receive` remains available to owner/admin but uses the shared service and writes `legacy_direct_receipt`; it does not alter WAC because no supplier line cost was supplied. UI shows it as a manual receipt, not a PO receipt.
5. Direct edits to `stock_quantity`, `on_order_quantity`, and `cost` are removed from the new UI. The legacy update API translates stock differences into `manual_adjustment` with a required reason once the tenant gate is on; otherwise its current shape remains temporarily compatible.
6. After all enabled tenants have migrated and no legacy mutation traffic exists for 30 days, remove direct receive/direct balance edits in a separate board item. Do not remove them in DB-038.

Rollback turns off the tenant or deployment gate and returns users to the existing Inventory page. It never deletes movement/PO/return data or reverses stock. Schema downgrade is allowed only before any non-opening operational movement exists; after that, rollback is forward-only via the flag and corrective migration.

## 9. Migration and backfill

Preflight must prove one Alembic head at revision `124_parts_operations_v1`, with the linear prerequisite chain through `121_inventory_canonical_sku`, `122_inventory_ets_retired_at`, and `123_inventory_ets_imported_at`, no live canonical-SKU duplicates, no negative balances/costs, and no orphaned `PartsUsage`/service-part inventory references. Failure aborts before schema/data mutation.

Backfill rules:

- Create one `migration_opening_balance` per live inventory item with nonzero on-hand. Actor is null, reason identifies migration revision, WAC is current `Inventory.cost`.
- Zero-balance items need no fictional movement.
- Preserve `PartsUsage.unit_cost`, reservation fields, placeholders, locations, photos, and canonical SKU survivor IDs exactly.
- Normalize categories from existing nonblank strings only by trim/collapse/case-fold; exact normalized duplicates share a category. No fuzzy recategorization.
- Backfill supplier FK only when the existing supplier string has one unique exact normalized match in the tenant. Ambiguous/unmatched values remain legacy text and appear in a cleanup queue; do not synthesize supplier records from questionable strings.
- Do not create fake POs/receipts for `on_order_quantity`. Mark it legacy-unlinked and include it in open supply until staff reconciles it.
- Verify per tenant: sum opening movement balance equals current on-hand by item; no cross-tenant FK; counts/checksums before and after; repeat dry run produces no changes.

Migration runs separately from feature enablement. A populated production migration requires a backup/restore point and recorded dry-run evidence, but DB-038 does not authorize executing it.

## 10. Presentation contract

One gated Inventory workspace under `/dashboard/garage/inventory` provides:

- Demand: prioritized repair shortage and reorder demand with source traceability and “add to draft PO”.
- Inventory: current catalog/list/detail, balances, WAC, price, location, category, preferred supplier, and item activity.
- Purchase Orders: draft/submitted/partial/received/cancelled lists, detail, remaining quantities, and receiving flow.
- Returns & Cores: origin-linked stock returns and core obligations/transitions.
- Activity: immutable chronological ledger with actor, source, destination, WAC, and balance-after.

Suppliers/categories are contextual management panels; existing `/dashboard/garage/suppliers` remains compatible during transition. There is no invented workflow stage, counter-sale screen, invoice flow, or duplicate catalog.

Desktop uses queue/list + persistent detail where space permits; iPad stacks list/detail; 390/320 use navigable cards and full-width sheets. All critical actions remain keyboard reachable, have visible focus, 44px targets, non-color status text, forced-colors support, and reduced-motion behavior. Tables preserve tabular numeric alignment and never hide SKU, quantity, cost, status, or primary action behind horizontal clipping.

## 11. Shared deterministic fixtures

Create import-safe fixtures under matching backend/frontend `test-fixtures/db038` paths using fixed UUIDs and frozen time `2026-08-23T14:00:00Z`:

- Tenant A Truck Pit Stop and Tenant B Foreign Shop.
- Owner, admin, receptionist, mechanic, fleet manager, customer, and driver in both tenants.
- Exact canonical parts: oil filter (reorder + repair shortage), coolant (fractional usage/package reservation), reman starter (core charge), placeholder/unlinked part, and one foreign-tenant lookalike sharing a display SKU.
- Normalized category and supplier plus ambiguous legacy supplier/category strings.
- Active repair order with shortage override and one fully reserved part.
- Draft PO, submitted PO, partial receipt/backorder, completed PO, and duplicate-key receipt case.
- Expected/on-hand/returned core obligations and draft/shipped/credited/reversed vendor returns.
- Opening, reservation/release, receipt, return, reversal, and legacy adjustment movements with known balances/WAC.

Frontend fixture responses must be serialized from the backend contract fixture or validated against the same schemas; hand-maintained divergent shapes are not accepted.

## 12. Acceptance and negative matrix

Backend must prove on PostgreSQL:

- migration upgrade/backfill/idempotent verification and preflight refusal;
- partial then final receipt, deterministic WAC, PO status/version, balance and movement linkage;
- same-key concurrency exactly once; different-key over-receipt race exactly one winner;
- receipt versus repair reservation/return concurrency never negative;
- multi-line failure rolls back every line, movement, balance, WAC, version, and timestamp;
- repair add/edit/delete/cancel and bundled-service behavior remain equivalent, including fractional package rounding and shortage overrides;
- return/core origins, limits, state transitions, reversal-once rule, and no WAC rewind;
- each role in the authorization matrix;
- foreign versus missing equivalence for every path/body ID and child-parent mismatch, with zero mutation;
- disabled flags, Redis/cache loss, durable replay, commit retry, and correlation-safe errors;
- legacy inventory/typeahead/supplier response compatibility.

Frontend/runtime must prove with identical fixtures:

- demand -> draft PO -> submit -> partial receive -> backorder -> final receive -> activity;
- repair shortage trace back to the real repair order without losing workspace context;
- core recovery -> return shipment -> credit and stock return -> reversal;
- disabled gate renders the unchanged legacy page;
- owner/admin mutation controls, receptionist read-only state, mechanic restricted state, and no surface for other roles;
- desktop, iPad, 390, 320, 200% zoom, keyboard/focus, 44px targets, reduced motion, high contrast/forced colors, long SKU/vendor/reference, empty/loading/stale/error/conflict/offline states;
- rapid/repeated receipt submission cannot produce duplicate optimistic balance or success state.

Independent Security gates tenant/non-enumeration, durable idempotency, concurrency, logs, and role boundaries. Independent QA gates migration fixture behavior, exact browser journeys, responsive/accessibility states, and legacy compatibility. Implementers cannot self-approve either gate.

## 13. Implementation split and return conditions

### Backend & Integrations — accountable first slice

One focused branch/PR from the accepted contract:

1. migration/models/constraints and deterministic fixture;
2. shared inventory movement service used by existing repair-order and legacy receipt mutations;
3. demand/activity, normalized supplier/category, PO/receipt, returns/core APIs;
4. focused PostgreSQL race, tenant, migration, and compatibility tests;
5. both flags default off.

No external vendor calls, production migration, or enablement.

### Frontend & UX — contributing second slice

After API schemas/fixtures are stable, one focused branch/PR:

1. gated workspace within the existing My Shop Inventory route;
2. shared generated/validated types and query keys;
3. demand, PO/receiving, returns/cores, and activity journeys;
4. preserve legacy page and supplier route behind rollback behavior;
5. focused component and Playwright coverage for the matrix above.

### Required delivery sequence

Architecture contract -> Backend implementation -> independent Security -> Frontend integration -> independent QA/Impeccable -> Release verification. Any change to costing, stock units, negative-stock rule, origin requirements, durable idempotency, tenant scope, or counter-sales exclusion returns to Architecture/Product before implementation continues.

DB-038 is not Done at this contract. It returns to Product as Architecture GO and is ready for dedicated Backend & Integrations ownership; no push, merge, migration execution, deployment, tenant enablement, or production data change is authorized by this document.
