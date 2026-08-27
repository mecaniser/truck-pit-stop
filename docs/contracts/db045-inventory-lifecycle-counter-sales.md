# DB-045 Inventory Lifecycle, Audit, and Counter Sales Contract

**Contract version:** 1.0.2 (frozen)
**Board item:** DB-045
**Accountable implementation owner:** Backend & Integrations
**Contract owner:** Architecture & API Contracts
**Frontend contributor:** Frontend & UX
**Required independent gates:** Security & Tenant Isolation, QA & Regression, Release & Reliability
**Branch:** `codex/db045-inventory-lifecycle-counter-sales`
**Required base:** the merged DB-044 `origin/main`
**Frozen base/HEAD at contract authoring:** `cb09d157a1e2635d53847539ca3e7ffa9bfb7965`
**Delivery shape:** one branch, one integrated pull request, one exact candidate SHA
**Risk lane:** high risk (payments, stock, tax, migrations, tenant authorization)
**Status:** frozen before implementation

## 1. Purpose and non-goals

DB-045 delivers one repair-first Inventory release containing:

1. An append-only, tenant-safe Part Activity index and truthful historical backfill.
2. A selected-part lifecycle hub plus a global Activity view, filter contract, CSV export, and lifecycle summary.
3. Secondary staff-operated counter sales using dedicated sale records, reservations, manual tenders, Stripe Connect, and QuickBooks Payments.
4. Partial returns/refunds, QuickBooks Accounting synchronization, receipts, and additive reporting.

The release is not separable into a publicly enabled “Phase 1” and “Phase 2.” Activity writers, migrations, backfill reconciliation, counter-sale models, provider integration, UI, authorization, reporting, and feature gates land in the same integrated PR. The counter-sales workflow remains inaccessible until the rollout gates in section 18 pass.

The following remain out of scope:

- customer self-checkout, guest payment links, or customer-portal sales;
- vehicles or repair orders as requirements for a counter sale;
- partial, split, deposit, pay-later, or accounts-receivable tenders;
- arbitrary part attachments, cross references, cycle counts, or managed category taxonomy;
- converting counter sales into repair orders, repair invoices, `Payment`, or `PartsUsage` records;
- reconstructing overwritten historical part fields, costs, or prices;
- production charges/refunds during acceptance without separate Product authorization;
- non-USD currencies.

## 2. Existing-contract preservation

DB-045 is additive unless this contract explicitly says otherwise.

- Existing repair invoices, invoice payments, repair-order reporting, and `PartsUsage` remain repair-order-only.
- Existing purchase orders, receipts, cores, vendor returns, repair usage, and inventory movements remain authoritative domain records. Activity is their immutable searchable index, not their replacement.
- `GET /api/v1/parts-operations/activity` remains available with its current parameters, pagination behavior, serializer, role behavior, and movement-only meaning. Existing clients must receive no renamed fields or new required parameters.
- Existing `available_packages` and inventory `stock_quantity` continue to mean physical on-hand stock. DB-045 adds held and available-to-sell projections; it does not silently redefine existing values or sort semantics.
- Existing `/api/v1/parts-operations/parts`, Inventory routes, provider flows for repair invoices, and QuickBooks invoice synchronization retain their response and state semantics.
- Existing repair metrics must not acquire synthetic counter-sale repair orders or invoices.

The new UI renames the visible selected-part **History** tab and global **Movement** view to **Activity**. Older URLs and the legacy movement endpoint remain compatible; the new UI reads the new Activity APIs.

## 3. Feature gates and capability rules

### 3.1 Activity foundation

Activity storage and mutation-side event writing are installed with the migration and are not controlled by the counter-sales flag. New Activity read routes continue to require the existing Parts Operations deployment and tenant gates and the existing active-tenant rules.

Writers must append Activity events for relevant successful mutations even when counter sales are disabled. This prevents a new historical gap between deployment and tenant rollout.

### 3.2 Counter sales

Counter sales require all of the following:

1. deployment setting `COUNTER_SALES_ENABLED=true`;
2. active tenant with `counter_sales_enabled=true`;
3. existing Parts Operations deployment and tenant gates enabled;
4. the tenant's latest Activity backfill run has status `verified` for the deployed payload version;
5. the caller has an allowed role;
6. the requested tender is configured and healthy for that tenant.

Both new counter-sales gates default to false. Feature-off, foreign-tenant, missing, soft-deleted, and unsupported-tenant resources return the same generic `404` response. Disabled tender rails are omitted from capabilities and return a safe provider-not-configured error if called directly.

The existing Parts summary response receives only this additive capability object:

```json
{
  "capabilities": {
    "counter_sales": false,
    "counter_sale_tenders": []
  }
}
```

The UI shows the quiet **Parts sales** utility only when `counter_sales` is true. Parts remains the default Inventory experience; no Shop-menu or application-level navigation item is added.

## 4. Authorization and tenant isolation

All authorization is derived from the authenticated server principal. No request-body tenant, actor, role, or provider-account identifier is trusted.

| Capability | Owner | Admin | Receptionist | Other roles |
|---|---:|---:|---:|---:|
| Read Activity/lifecycle/export | yes | yes | yes | no |
| Read counter sales/receipts | yes | yes | yes | no |
| Create/edit draft at catalog price | yes | yes | yes | no |
| Checkout at catalog price | yes | yes | yes | no |
| Override line price | yes, reason required | yes, reason required | no | no |
| Cancel draft | yes | yes | no | no |
| Create/retry return or refund | yes | yes | no | no |
| Enable tenant gate/provider | release-authorized operation | release-authorized operation | no | no |

`super_admin` is not implicitly entitled to tenant data. It follows the repository's explicit support-context contract, if any, and otherwise receives the same denial as an unrelated role.

Every table carries `tenant_id`. Parent/child and part references use composite tenant-aware foreign keys or equivalent database constraints so a child cannot point across tenants. Every query begins with the server-derived tenant predicate. IDs from another tenant, missing IDs, deleted parts/customers, or objects disabled by a feature gate return a generic `404` without disclosing existence. Role failures on an otherwise enabled tenant return `403`.

Exports, receipt PDFs, email delivery, provider callbacks, and source deep links repeat the same tenant and role checks. Provider webhooks derive the tenant from a verified connected-account/provider mapping and stored attempt metadata, never from an unverified payload field alone.

## 5. Immutable Part Activity model

### 5.1 `part_activity_events`

The migration adds an append-only PostgreSQL table with:

- `id UUID` primary key;
- `tenant_id UUID` and `inventory_id UUID`, both required;
- `category VARCHAR(32)` using the fixed values `catalog`, `stock`, `repairs`, `purchasing`, `returns`, `sales`;
- `event_type VARCHAR(80)` from the vocabulary below;
- `occurred_at TIMESTAMPTZ`, `recorded_at TIMESTAMPTZ`;
- `correlation_id UUID` shared by every event/domain mutation produced by one command;
- `source_type VARCHAR(48)`, `source_id UUID`, and nullable `source_number_snapshot VARCHAR(120)`;
- nullable `actor_id UUID`, plus required `actor_name_snapshot VARCHAR(255)` (`System` for system/backfill events);
- nullable `reason_code VARCHAR(80)` and `note TEXT`;
- `origin VARCHAR(24)` with `live`, `baseline`, or `backfill_snapshot`;
- `payload_version SMALLINT`, initially `1`;
- `idempotency_key VARCHAR(255)`;
- `before_values JSONB` and `after_values JSONB` containing a schema-whitelisted map of typed scalar values;
- nullable `stock_snapshot JSONB`, `money_snapshot JSONB`, `payment_snapshot JSONB`, and `source_snapshot JSONB` using the schemas below.

Required uniqueness and indexes:

- unique `(tenant_id, idempotency_key)`;
- newest-first `(tenant_id, occurred_at DESC, id DESC)`;
- `(tenant_id, inventory_id, occurred_at DESC, id DESC)`;
- filter indexes for category/event type, actor, source type/source id;
- PostgreSQL text-search index over safe actor, reason, note, source number, part-name/SKU snapshots.

Database triggers reject `UPDATE` and `DELETE` for this table. There is no update, delete, or soft-delete API. Corrections are represented by later events. Alembic downgrade drops the guard trigger before the empty table in disposable verification databases; populated production data is never rolled back by destructive downgrade.

### 5.2 Snapshot schemas

`before_values` and `after_values` may contain only documented part or source fields and JSON scalar values. Dates use RFC 3339 strings; money uses fixed-decimal strings; quantities are integers for whole-package stock and decimal strings only for legacy repair usage.

`stock_snapshot` version 1:

```json
{
  "physical_on_hand": 12,
  "held_for_checkout": 2,
  "available_to_sell": 10,
  "delta": -1,
  "bucket": "on_hand",
  "stock_version": 8
}
```

`money_snapshot` version 1 may contain `currency`, cost/WAC before/after, list price, charged price, discount, item subtotal, tax, service fee, total, refund allocations, and cost basis. Every amount is a string with two decimal places and currency is always `USD`.

`payment_snapshot` version 1 may contain tender family, attempt/refund state, safe provider object identifier, brand/last-four when returned by a provider, and a scrubbed failure code. It must never contain tokens, client secrets, raw card/bank values, provider credentials, full provider payloads, or sensitive error messages.

`source_snapshot` version 1 may contain the human-readable number/title and source-specific safe summary. Response `href` values are computed server-side from `source_type` and `source_id`; callers cannot persist arbitrary URLs.

### 5.3 Event vocabulary

The initial fixed vocabulary is:

- Catalog: `part.created`, `part.baseline`, `part.identity_changed`, `part.category_changed`, `part.location_changed`, `part.unit_changed`, `part.photo_changed`, `part.reorder_level_changed`, `part.cost_changed`, `part.selling_price_changed`, `supplier_source.created`, `supplier_source.updated`, `supplier_source.preferred_changed`, `supplier_source.removed`.
- Stock: `stock.adjusted`, `stock.received`, `stock.repair_reserved`, `stock.repair_released`, `stock.counter_sale_completed`, `stock.counter_sale_returned`.
- Repairs: `repair_usage.added`, `repair_usage.changed`, `repair_usage.removed`, `repair_usage.current_snapshot`.
- Purchasing: `purchase_order.created`, `purchase_order.updated`, `purchase_order.submitted`, `purchase_order.cancelled`, `receipt.recorded`, `receipt.current_snapshot`, `core.status_changed`, `core.current_snapshot`.
- Returns: `vendor_return.created`, `vendor_return.submitted`, `vendor_return.shipped`, `vendor_return.credited`, `vendor_return.cancelled`, `vendor_return.reversed`, `vendor_return.current_snapshot`.
- Sales: `counter_sale.created`, `counter_sale.updated`, `counter_sale.awaiting_payment`, `counter_sale.payment_succeeded`, `counter_sale.payment_failed`, `counter_sale.completed`, `counter_sale.cancelled`, `counter_sale.return_requested`, `counter_sale.refund_succeeded`, `counter_sale.refund_failed`, `counter_sale.return_completed`, `counter_sale.late_success_refunded`.

One business command uses one correlation ID. A sale command affecting several parts writes one event per affected part with the same correlation ID and source sale/attempt/return. The API may visually group adjacent correlated events, but it does not collapse or discard them.

### 5.4 Atomicity and no-op rules

Each successful local domain mutation and its Activity events commit in the same database transaction. A failure rolls both back. Provider calls are not made while database locks remain open: the local pending transition is committed first, the provider call occurs, and the confirmed local finalization plus events/movements/outbox commit atomically in a new transaction.

Normalized catalog/source updates whose before and after values are identical write no Activity event. The idempotency record may still store the successful replay response. Stock/financial commands with zero quantity or zero amount fail validation and write nothing.

## 6. Backfill and reconciliation

### 6.1 Backfill-run state

`part_activity_backfill_runs` records `tenant_id`, payload version, cutoff time, state (`running`, `failed`, `reconciled`, `verified`), batch cursor, source counts, inserted/replayed counts, per-source checksums, duplicate count, error summary, and timestamps. Only the command/release process updates this operational table; it is not an audit event and has no product mutation API.

### 6.2 Command behavior

The implementation provides a command equivalent to:

```text
python -m app.commands.backfill_part_activity \
  --tenant-id <optional> --batch-size 500 \
  [--dry-run] [--verify-only]
```

It must:

1. take a tenant-scoped advisory lock and process tenants independently;
2. capture a high-water cutoff after live writers are deployed;
3. use keyset batches and bounded transactions;
4. append one explicit `part.baseline` snapshot for every non-deleted part as of the cutoff;
5. append one event per existing `InventoryMovement`, preserving its occurrence time and snapshots;
6. append truthful current-state snapshots for legacy repair usage, receipt lines, vendor-return lines, and core obligations existing at the cutoff;
7. label baseline/backfill origin and never present current snapshots as reconstructed historical changes;
8. use deterministic keys shared with live projection writers, for example `inventory_movement:<id>:v1`, so races and reruns cannot duplicate events;
9. continue safely after an interrupted batch;
10. reconcile eligible source counts, event counts, unique keys, tenants, deleted rows, and checksums before marking the run `verified`.

Live events after the cutoff are already written by the mutation path and are excluded from the source cutoff counts. A safe rerun inserts zero duplicates and produces the same reconciled counts. Counter sales cannot be enabled for a tenant until the latest payload-version run is `verified`.

## 7. Activity and lifecycle APIs

All paths below are under `/api/v1/parts-operations`.

### 7.1 Query contract

`GET /activity-events` accepts:

- `inventory_id` (optional UUID);
- `category` (optional fixed category);
- `event_type` (repeatable optional value);
- `actor_id` (optional UUID);
- `source_type` and `source_id` (optional, source ID requires source type);
- `search` (optional normalized text, 2-200 characters);
- `from` and `to` (optional RFC 3339 UTC instants; inclusive lower, exclusive upper);
- `cursor` (optional opaque cursor);
- `limit` (default 50, range 1-100).

Default ordering is `(occurred_at DESC, id DESC)`. The opaque base64url cursor encodes schema version, the last tuple, and a SHA-256 fingerprint of all normalized filters. A malformed cursor or one reused with different filters returns `400`. The query fetches `limit + 1`; immutable rows make pages stable. No offset pagination is exposed.

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "inventory_id": "uuid",
      "category": "stock",
      "event_type": "stock.adjusted",
      "occurred_at": "2026-08-26T00:00:00Z",
      "correlation_id": "uuid",
      "origin": "live",
      "actor": {"id": "uuid-or-null", "name": "Alex"},
      "reason": {"code": "count_correction", "note": "Shelf count"},
      "before": {"stock_quantity": 5},
      "after": {"stock_quantity": 7},
      "stock": {},
      "money": null,
      "payment": null,
      "source": {
        "type": "inventory_movement",
        "id": "uuid",
        "number": "MOV-100",
        "href": "/dashboard/garage/inventory?activity=uuid"
      }
    }
  ],
  "next_cursor": "opaque-or-null"
}
```

`GET /activity-events/export.csv` accepts the identical filters except `cursor` and `limit`. It streams the same newest-first result set and columns: occurrence time, category, event type, part SKU/name, actor, reason/note, typed before/after JSON, physical/held/available stock, delta, WAC, list/charged price, tax, fee, tender/status, source type/number/deep link, origin, correlation ID. Spreadsheet-formula-leading text is escaped. Export is capped at 50,000 rows; a larger result returns `413` with instructions to narrow filters. No provider secrets or internal tokens appear.

### 7.2 Part lifecycle summary

`GET /parts/{inventory_id}/lifecycle-summary` returns lifetime aggregates from authoritative source records, not inferred reconstructed history:

```json
{
  "inventory_id": "uuid",
  "as_of": "2026-08-26T00:00:00Z",
  "repairs": {"units_used": "12.00", "repair_order_count": 5, "last_used_at": null},
  "purchasing": {
    "units_received": 20,
    "receipt_count": 3,
    "units_returned_to_vendor": 2,
    "open_core_obligations": 1
  },
  "sales": {
    "units_sold": 6,
    "units_returned": 1,
    "net_units": 5,
    "gross_item_revenue": "300.00",
    "discounts": "10.00",
    "refunds": "50.00",
    "net_item_revenue": "240.00",
    "last_sold_at": null
  },
  "activity": {"event_count": 31, "last_event_at": null}
}
```

Deleted/foreign/missing parts return generic `404`. The summary uses completed sales and completed returns only.

## 8. Counter-sale data model

All monetary columns use `NUMERIC`/fixed-decimal values and application `Decimal`; binary floats are prohibited. Currency is constrained to `USD`. Mutable aggregates use explicit optimistic `version` integers. No sale, line, attempt, return, refund, or reservation has a destructive public delete path.

### 8.1 `counter_sales`

Required fields include tenant-scoped unique sale number; status; version; optional existing customer; immutable buyer name/email/phone snapshots; currency; tenant tax-rate and service-fee-rate snapshots; list subtotal, charged subtotal, discount, tax, fee, and total; created/updated/completed/cancelled actors and timestamps; and safe accounting-sync status/reference fields.

Anonymous walk-ins are valid. A vehicle is never accepted or required. Sale numbers are allocated under a tenant-scoped lock and do not disclose global volume.

State transitions are exactly:

```text
draft -> awaiting_payment -> completed -> partially_returned -> returned
  |              |
  -> cancelled   -> draft (definitive payment failure or safe release)
```

Completed sales are never voided or edited. A manager reversal is a full audited return/refund. Failed attempts remain attached to the returned draft.

### 8.2 `counter_sale_lines`

Each line stores tenant, sale, part, whole-package quantity, SKU/name/unit/category snapshots, unit cost, catalog/list price, charged price, discount, override reason/actor when applicable, item subtotal, tax allocation, fee allocation, total, and cost total. Quantities are positive integers. Lines become immutable once checkout starts; returning to draft after a failed payment may unlock lines under a new sale version, while retaining attempt snapshots.

Receptionists may submit only current catalog selling price. Owner/admin price changes require a non-empty 3-500 character reason and are recorded in both the line and Activity. A missing or non-positive catalog selling price blocks checkout unless owner/admin supplies a valid override and reason.

### 8.3 `counter_sale_reservations`

Reservations store tenant, sale line, part, quantity, state (`held`, `consumed`, `released`, `expired`), expiration (15 minutes), hold/release/consume timestamps and reason, and version. Only `held` quantities count as held-for-checkout. A reservation changes no physical stock.

For every part projection:

```text
physical_on_hand = Inventory.stock_quantity
held_for_checkout = SUM(active held reservation quantity)
available_to_sell = MAX(physical_on_hand - held_for_checkout, 0)
```

The parts API adds `physical_on_hand_packages`, `held_for_checkout_packages`, and `available_to_sell_packages`; legacy `available_packages` remains physical on hand.

### 8.4 Payment attempts and provider deliveries

`counter_sale_payment_attempts` stores tenant, sale, tender, state (`created`, `pending`, `succeeded`, `failed`, `cancelled`, `compensating_refund_pending`, `compensated`), full amount, request fingerprint/idempotency key, safe provider intent/charge/reference IDs, provider request ID, safe provider status/failure code, attempt number, reconciliation timestamps, and actor.

`counter_sale_provider_events` is an append-only deduplication ledger containing provider, external event ID, event type, safe payload hash, received/processed timestamps, processing state, and safe error summary. `(provider, external_event_id)` is unique. Raw provider payloads, tokens, client secrets, and credentials are not persisted.

Exactly one tender settles the full sale. Tender values are `stripe`, `quickbooks_payments`, `cash`, `check`, `ach`, `zelle`, `external_terminal`, `fleet_reference`, and `other`.

### 8.5 Returns and refunds

`counter_sale_returns` stores tenant, sale, version, state (`pending_refund`, `refund_failed`, `completed`), aggregate item/tax/fee/refund amounts, actor, reason, timestamps, and correlation ID.

`counter_sale_return_lines` stores the original sale line, positive whole quantity, required 3-500 character reason, disposition (`restock` or `damaged`), deterministic item/discount/tax/fee/cost allocations, and processed unit ordinals.

`counter_sale_refunds` stores return, original payment attempt, tender, state (`pending`, `succeeded`, `failed`), amount, safe provider refund/reference ID, idempotency/fingerprint, attempt count, safe failure data, and timestamps.

Pending, failed-but-retryable, and completed returns claim their unit ordinals so another return cannot exceed the remaining quantity. A failed refund is retried on the same return/refund record; it does not create a new stock or money claim.

## 9. Price, tax, fee, and refund arithmetic

All calculations occur on the server with `Decimal`, USD cents, and round-half-up only at the documented allocation boundary.

1. `line_list = catalog_price * quantity`.
2. `line_charged = charged_unit_price * quantity`.
3. `line_discount = line_list - line_charged`.
4. `sale_charged_subtotal = SUM(line_charged)`.
5. `sale_tax = round_cent(sale_charged_subtotal * tenant_tax_rate_snapshot / 100)`.
6. Stripe and QuickBooks Payments use the current checkout service-fee rule and tenant service-fee snapshot. Manual tenders have fee `0.00`.
7. `sale_total = sale_charged_subtotal + sale_tax + sale_fee`.

Tax and fee cents are allocated to lines by charged subtotal using largest remainder; ties resolve by stable line UUID. Each line's item/tax/fee cents are then distributed over ordered unit ordinals using quotient plus stable earliest-ordinal remainder. A partial return consumes the next unreturned ordinals and refunds exactly their stored item, tax, and fee allocations. Therefore return order and retry count cannot change the total refund, and all line allocations always sum to the sale totals.

The refund ceiling is the original confirmed sale total less completed or claimed return allocations. Refunds go to the original rail when supported. Restock disposition posts inventory only after refund success; damaged disposition never increases on hand. Manual refunds require owner/admin confirmation plus a safe reference/note and complete atomically with the return. Provider refund failure creates no inventory movement.

## 10. Checkout, concurrency, and provider finalization

### 10.1 Lock and transaction order

Every mutating endpoint requires `Idempotency-Key` (16-128 safe characters) and expected aggregate version where applicable. A durable idempotency family stores normalized route, tenant, principal, aggregate, request fingerprint, response status/body, and correlation ID. Same key/same fingerprint replays; same key/different fingerprint returns `409`.

Checkout uses this order:

1. validate gates, role, idempotency, DTO, tender, and provider capability;
2. lock the sale and lines;
3. lock referenced Inventory rows in ascending UUID order;
4. lock active reservations for those parts in ascending UUID order;
5. recompute physical, held, and available-to-sell values inside the transaction;
6. create 15-minute holds, freeze snapshots/totals, create an attempt, and move the sale to `awaiting_payment`;
7. commit before any provider network call;
8. invoke the provider with a provider idempotency/request ID derived from the local attempt;
9. finalize through one shared idempotent service used by synchronous responses, webhooks, and reconciliation.

If availability is insufficient, the whole checkout fails with `409`, no hold is created, and no provider is called. This ordering plus row locks must prove no oversell under concurrent checkout.

### 10.2 Completion

Confirmed provider amount, currency, connected account/merchant, metadata sale ID/tenant, and status must match the frozen attempt. Finalization re-locks the sale, reservations, and parts in the same order. In one transaction it:

- marks the attempt succeeded and sale completed;
- consumes reservations;
- decrements physical stock with one immutable `counter_sale` InventoryMovement per line;
- appends per-part sale/stock Activity events;
- writes the QuickBooks Accounting outbox event;
- stores the immutable receipt snapshot and optional receipt-email outbox event.

A replay observes the completed transition and returns its stored result without double stock, money, Activity, or outbox rows.

### 10.3 Failure, expiry, and late success

A definitive payment decline/failure releases the holds, records the failed attempt/event, and returns the sale to editable `draft`. An unknown/timeout result remains `awaiting_payment`; it is reconciled and must not release stock.

The expiry worker claims expired reservations safely, checks the provider state first, then:

- finalizes a provider-confirmed success;
- releases only a provider-confirmed failure/cancellation;
- retains the hold and raises a retryable operational alert for unknown state.

If a provider success is discovered after a reservation was safely released, the system does not decrement inventory or complete the sale. It automatically initiates an idempotent full compensating refund, marks the attempt accordingly, appends `counter_sale.late_success_refunded`, and raises an operational alert. The tenant gate does not permit negative inventory as recovery behavior.

### 10.4 Provider-specific rules

- **Manual:** cash, check, ACH, Zelle, external terminal, fleet reference, or other. Required reference rules are tender-specific. Completion is local and synchronous; service fee is zero.
- **Stripe Connect:** staff-side Elements uses the tenant connected account. The server creates the PaymentIntent with exact amount/currency and signed metadata, returns `client_secret` only in the immediate response, and never stores it. Signed webhooks and retrieval reconciliation call the shared finalizer.
- **QuickBooks Payments:** the browser sends only the one-time token. It is used once and never stored/logged. The server uses the local attempt-derived `Request-Id`; timeout retries reuse it. Charge retrieval/reconciliation calls the shared finalizer.

Provider credentials, OAuth tokens, payment tokens, raw card/bank data, webhook secrets, and raw payloads never enter application logs, Activity payloads, exports, receipts, or database business rows.

## 11. Counter-sales APIs

All routes are under `/api/v1/parts-operations/counter-sales`. Mutation endpoints require `Idempotency-Key`; sale/return mutations also require `expected_version`.

Version 1.0.1 adds the exact response and browser-provider handshake below. This is a pre-implementation additive clarification only; it changes no state, authorization, money, stock, or rollout decision from version 1.0.0.

| Method and path | Purpose | Success |
|---|---|---|
| `GET /` | cursor list; filters status, customer, text, from/to | `200` |
| `POST /` | create draft with optional buyer/customer and lines | `201` replayable |
| `GET /{sale_id}` | full sale, lines, totals, attempts, return summary | `200` |
| `PATCH /{sale_id}` | edit draft buyer/lines | `200` |
| `POST /{sale_id}/checkout` | reserve and initiate/finalize one full tender | `200` manual/completed or `202` provider pending |
| `POST /{sale_id}/cancel` | owner/admin cancel draft | `200` |
| `POST /{sale_id}/payment-attempts/{attempt_id}/reconcile` | explicit safe reconciliation | `200` or `202` |
| `GET /{sale_id}/returns` | list return/refund records | `200` |
| `POST /{sale_id}/returns` | owner/admin create partial/full return | `201`, `200`, or `202` |
| `GET /{sale_id}/returns/{return_id}` | read return/refund | `200` |
| `POST /{sale_id}/returns/{return_id}/retry-refund` | retry same failed refund claim | `200` or `202` |
| `GET /{sale_id}/receipt.pdf` | branded immutable receipt PDF | `200 application/pdf` |
| `POST /{sale_id}/receipt/email` | idempotent optional email delivery | `202` |

### 11.1 Frozen sale response and action vocabulary

`GET /{sale_id}` and every sale mutation return `CounterSaleResponse` directly, except checkout which wraps it as described in section 11.2. Decimal values are strings with two decimal places. Nullable properties are present as `null`; response producers do not rename or omit fields based on tender.

```json
{
  "id": "uuid",
  "sale_number": "CS-1001",
  "status": "draft",
  "version": 1,
  "customer_id": null,
  "buyer_name": null,
  "buyer_email": null,
  "buyer_phone": null,
  "currency": "USD",
  "list_subtotal": "0.00",
  "charged_subtotal": "0.00",
  "discount_amount": "0.00",
  "tax_amount": "0.00",
  "service_fee_amount": "0.00",
  "total_amount": "0.00",
  "lines": [{
    "id": "uuid",
    "inventory_id": "uuid",
    "sku": "AIR-FLT-001",
    "name": "Air Filter - Primary",
    "unit_type": "each",
    "quantity": 1,
    "returned_quantity": 0,
    "remaining_returnable_quantity": 1,
    "unit_cost": "46.25",
    "list_unit_price": "65.00",
    "charged_unit_price": "65.00",
    "discount_amount": "0.00",
    "item_subtotal": "65.00",
    "tax_amount": "0.00",
    "fee_amount": "0.00",
    "total_amount": "65.00",
    "price_override_reason": null,
    "physical_on_hand": 31,
    "held_for_checkout": 0,
    "available_to_sell": 31
  }],
  "payment_attempts": [{
    "id": "uuid",
    "tender": "stripe",
    "state": "pending",
    "amount": "65.00",
    "failure_code": null,
    "safe_status": "requires_confirmation",
    "created_at": "2026-08-26T00:00:00Z"
  }],
  "returns": [],
  "allowed_actions": ["edit_draft", "checkout", "cancel"],
  "created_at": "2026-08-26T00:00:00Z",
  "updated_at": "2026-08-26T00:00:00Z",
  "completed_at": null,
  "cancelled_at": null,
  "accounting_sync_status": "not_queued",
  "receipt_email_status": null
}
```

The finite `allowed_actions` values are `edit_draft`, `checkout`, `cancel`, `reconcile_payment`, `download_receipt`, `email_receipt`, `create_return`, and `retry_refund`. The server computes them after applying feature gate, tenant, role, aggregate state, provider state, and remaining-returnable-quantity rules:

- `draft`: owner/admin/receptionist receive `edit_draft` and `checkout`; owner/admin also receive `cancel`.
- `awaiting_payment`: allowed staff receive `reconcile_payment`; no sale or line edit is allowed.
- `completed` or `partially_returned`: allowed staff receive receipt actions; owner/admin receive `create_return` only while quantity remains returnable; owner/admin receive `retry_refund` when any attached return is `refund_failed`.
- `returned`: allowed staff receive receipt actions only.
- `cancelled`: no action.

`GET /` returns `{"items": [CounterSaleListItem], "next_cursor": "opaque-or-null"}`. A list item contains `id`, `sale_number`, `status`, `buyer_name`, `buyer_email`, `total_amount`, `line_count`, `tender`, `created_at`, and `completed_at`.

### 11.2 Checkout and provider capability handshake

The Parts summary capability is exactly:

```json
{
  "capabilities": {
    "counter_sales": true,
    "counter_sale_tenders": ["stripe", "quickbooks_payments", "cash"],
    "counter_sale_providers": {
      "stripe": {"available": true, "stripe_account_id": "acct_safe_or_null"},
      "quickbooks_payments": {
        "available": true,
        "token_url": "https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens"
      }
    }
  }
}
```

When counter sales are disabled, `counter_sales` is false, tenders are empty, and provider entries are present with `available=false` and nullable fields set to `null`. Provider availability is tenant-safe, contains no credential, and reflects configured healthy sandbox/production mode. QuickBooks requires no browser app ID in the current integration: the staff browser posts card data directly to the returned Intuit `token_url`, receives `{ "value": "opaque-one-time-token" }`, immediately clears the form, and sends only that value as `payment_token` in checkout. The token is accepted only for `quickbooks_payments`, is excluded from request logs, and is never persisted.

`POST /{sale_id}/checkout` returns:

```json
{
  "sale": {"...": "CounterSaleResponse"},
  "payment": {
    "attempt_id": "uuid",
    "tender": "stripe",
    "state": "pending",
    "client_secret": "ephemeral-or-null",
    "stripe_account_id": "acct_safe_or_null",
    "reconcile_url": "/api/v1/parts-operations/counter-sales/uuid/payment-attempts/uuid/reconcile"
  }
}
```

Only a Stripe pending response may contain `client_secret`; it is returned once and never stored or echoed by later reads. Stripe browser flow calls checkout first, initializes connected-account Elements with `stripe_account_id`, and calls `stripe.confirmPayment({elements, clientSecret, redirect: "if_required"})`. Browser success is not authoritative. A signed webhook normally calls the shared finalizer; the browser may then POST the returned `reconcile_url` to converge immediately. There is no client `finalize` endpoint and no browser-supplied provider status. Reconcile retrieves provider state and returns the current `CounterSaleResponse` (`200` terminal, `202` still indeterminate).

QuickBooks Payments tokenizes first, then calls checkout once with `payment_token`; the server uses the attempt-derived `Request-Id` and returns the same checkout envelope. Manual tenders return the envelope with terminal sale state and null provider fields. Clients render `sale.status`, `payment.state`, and `allowed_actions`; they never infer completion merely because confirmation or token submission returned without an error.

Create/update line DTO:

```json
{
  "inventory_id": "uuid",
  "quantity": 2,
  "charged_unit_price": "45.00",
  "price_override_reason": "Manager match"
}
```

`charged_unit_price` and its reason are omitted for catalog pricing. The server ignores no pricing field silently.

Checkout DTO:

```json
{
  "expected_version": 3,
  "tender": "stripe",
  "payment_token": null,
  "manual_reference": null,
  "receipt_email": "buyer@example.com"
}
```

`payment_token` is accepted only for QuickBooks Payments and is excluded from request logging. Stripe returns an ephemeral client secret; manual tender requires its applicable reference. The full frozen sale response contains `physical_on_hand`, `held_for_checkout`, and `available_to_sell` line projections, exact decimal-string totals, allowed actions, safe provider recovery state, and no secret fields.

Return DTO:

```json
{
  "expected_version": 5,
  "lines": [
    {"sale_line_id": "uuid", "quantity": 1, "reason": "Customer return", "disposition": "restock"}
  ],
  "manual_refund_reference": null
}
```

## 12. Error and response semantics

All errors use the repository-standard safe detail envelope and stable machine-readable code where supported. Raw provider errors are scrubbed.

- `400`: malformed cursor, invalid filter combination, malformed idempotency key.
- `402`: definitive payment decline; sale is restored to draft and holds are released.
- `403`: authenticated role lacks authority on an enabled, resolved tenant workflow.
- `404`: feature disabled, missing/foreign/deleted resource, inaccessible source/customer/part, or wrong tenant.
- `409`: optimistic version/state conflict, insufficient available-to-sell stock, duplicate/mismatched idempotency key, claimed refund quantity, provider amount/account/status mismatch, or unsafe reservation transition.
- `413`: export exceeds 50,000 rows.
- `422`: invalid quantity, money, tax/fee, tender payload, override/reason, disposition, or refund ceiling.
- `424`: requested provider rail is not configured/healthy.
- `503`: provider result is indeterminate/unavailable; hold remains and response identifies safe reconciliation, never a retry that may double charge.

Provider-pending work returns `202`, not a false completed response. Clients must render the server state and allowed actions rather than infer completion from HTTP submission success.

## 13. QuickBooks Accounting and receipt outbox

Completed counter sales enqueue `quickbooks.counter_sale.sync.v1`; completed returns enqueue `quickbooks.counter_sale_return.sync.v1` in the existing durable `ProviderOutboxEvent` system. Idempotency is based on tenant, event type, aggregate ID, and payload version.

- Sale event creates a QuickBooks **Sales Receipt**, not an Invoice, with immutable buyer/line/tax/fee snapshots.
- Return event creates a **Refund Receipt** linked by stored local/provider references.
- Anonymous buyers use one deterministic per-tenant walk-in QBO Customer. The resulting QBO customer ID is stored on the tenant QuickBooks connection; concurrent creation is locked/idempotent.
- Existing customer QBO references are reused only after tenant-safe validation.
- Outbox retry/dead-letter behavior never repeats local stock or payment transitions.

Receipt PDFs are rendered from the completed sale snapshot, including tenant branding, receipt/sale number, completion time, buyer when supplied, item/tax/fee/total, tender-safe reference, and return/refund summary. Optional emails use a separate durable `counter_sale.receipt.email.v1` outbox event. They never expose cost, margin, internal notes, or provider secrets.

## 14. Reporting contract

Existing Sales, Parts Margin, Tax, customer profitability, and dashboard reports gain additive counter-sale source aggregation while preserving repair-only measures and response fields. New/extended fields distinguish `repair` and `counter_sale`; no counter sale creates a repair invoice/order.

Reporting recognizes only completed sales and completed returns, using `completed_at` in the tenant's reporting date boundary:

- gross item sales: completed charged line subtotal;
- discounts: catalog/list less charged line amount;
- refunds: completed returned item allocation;
- net item sales: charged subtotal less completed item refunds;
- net tax: collected tax less completed returned tax allocation;
- net service fees: charged provider fee less completed returned fee allocation;
- units: sold quantity less completed returned quantity;
- COGS/margin: sold cost basis is reversed for `restock` returns but not for `damaged` returns;
- customer profitability: linked customers only; anonymous walk-ins remain in aggregate reports and never create a synthetic DieselBridge Customer.

Failed/pending/cancelled sales, reservations, attempts, and returns do not affect financial reports. QBO sync state does not change reporting recognition.

## 15. Frontend contract

Canonical route: `/dashboard/garage/inventory/sales`.

- Parts stays the default Inventory route.
- A quiet **Parts sales** utility opens sale history; sale history owns the primary **New counter sale** action.
- A selected part exposes **Sell part** only in contextual overflow, not as another dominant inspector button.
- Selected-part **History** becomes **Activity** and uses the part-scoped new endpoint.
- Global **Movement** becomes **Activity** and uses the global endpoint with filters, stable pagination, source deep links, and CSV export.
- Checkout supports part search, the existing shared quantity stepper component, optional customer lookup/buyer snapshots, manager override with reason, totals, tender selection, provider pending/failure recovery, receipt, and owner/admin returns.
- The UI displays physical, held, and available-to-sell stock separately and never promises stock based only on stale client state.
- Allowed actions come from server state/role. Disabled or pending actions remain explainable and keyboard reachable.
- Accessibility requires semantic controls, labels/errors, focus restoration, live provider-state announcements, 44px targets, theme support, and containment at desktop, 1280, 960, 390, and 320 widths.

Frontend DTOs preserve decimal amounts as strings. Dates are UTC RFC 3339 values formatted at display time. Provider client secrets/payment tokens live only in provider SDK memory and are cleared on completion/navigation.

## 16. Migration and rollback

The implementation adds one intentional Alembic revision directly after the sole DB-044 main head. It creates:

1. `part_activity_events` and immutability guards;
2. `part_activity_backfill_runs`;
3. `counter_sales`;
4. `counter_sale_lines`;
5. `counter_sale_reservations`;
6. `counter_sale_payment_attempts`;
7. `counter_sale_provider_events`;
8. `counter_sale_returns`;
9. `counter_sale_return_lines`;
10. `counter_sale_refunds`;
11. required tenant counter-sales and QuickBooks walk-in-customer fields;
12. composite tenant foreign keys, unique constraints, checks, and indexes.

Upgrade must be safe with both feature flags off and must not perform an unbounded data backfill inside Alembic. Backfill is the explicit batched command after deploy.

Downgrade is exercised only on a fresh disposable PostgreSQL database. It refuses or is operationally prohibited once Activity or sale rows exist. Production rollback means disabling the global and tenant counter-sales gates, stopping workers, preserving tables/events, and rolling application code forward or back compatibly; it never deletes audit/financial history.

Schema preflight, model metadata, migration graph, and fresh upgrade/downgrade/upgrade must agree on one head.

## 17. Verification matrix for one exact candidate SHA

All results attach to one unchanged candidate SHA. A change to migrations, authorization, money/stock logic, provider finalization, event payloads, or API contracts invalidates affected gates.

### 17.1 Database and Activity

- one Alembic head; upgrade/downgrade/upgrade on fresh PostgreSQL;
- database update/delete guard proves Activity immutability;
- event/domain atomic rollback and successful atomic commit;
- every listed mutation emits the correct actor, reason, before/after, correlation, source, and safe snapshots;
- normalized no-op writes no event;
- batched baseline/source backfill, interruption resume, safe rerun, counts/checksums, no duplicates, cutoff-race coverage, and cross-tenant reconciliation;
- migration/backfill contains no provider or production mutation.

### 17.2 Tenant, role, and read contracts

- active own-tenant owner/admin/receptionist positives;
- role negatives, foreign tenant, nonexistent, deleted, both disabled gates, and generic-404 parity;
- source/customer/part body-reference isolation;
- stable cursor traversal during concurrent inserts, invalid/filter-mismatched cursor, filter combinations, search, date boundary, export parity/cap/formula escaping;
- unchanged legacy movement endpoint fixtures.

### 17.3 Stock, money, and state

- concurrent checkouts for the same parts prove no oversell and deterministic locks;
- whole-package and positive-money checks;
- physical/held/available projections and unchanged legacy physical field;
- 15-minute expiry with confirmed failure, success, and unknown provider states;
- definitive failure returns to draft; duplicate/late webhook and reconciliation are idempotent;
- late success after release produces one compensating refund, no stock decrement, and one alert;
- tax/fee cent rounding and stable line/unit allocation;
- receptionist catalog-price enforcement and owner/admin override reason;
- full and partial returns, claimed quantities, refund ceiling, restock versus damaged inventory, failed/retried refunds, and no double money/stock.

### 17.4 Providers, accounting, reporting, and UI

- Stripe Connect sandbox Elements charge, signed duplicate webhook, retrieval reconciliation, refund, mismatch, and redacted logs;
- QuickBooks Payments sandbox tokenized charge, timeout/idempotent retry, reconciliation, refund, and redacted logs;
- every manual tender family and required reference behavior;
- QBO sandbox Sales Receipt, deterministic walk-in customer, Refund Receipt, durable retry/dead letter, and no duplicate provider documents;
- printable branded PDF and idempotent email outbox;
- Sales, Parts Margin, Tax, customer profitability, and dashboard source/netting checks, including damaged-return COGS behavior and repair-metric non-contamination;
- component and Playwright journeys for part/global Activity, create/edit/checkout, every tender family, provider recovery, receipt, partial/full return, permissions, keyboard/focus, themes, and responsive containment.

### 17.5 Independent gates

Security independently reviews tenant authorization, generic 404s, feature gates, price/refund authority, webhook signatures, connected-account mapping, provider tokens/credentials, exports, CSV injection, logs, receipt/email data, and payment metadata.

QA independently verifies the exact candidate identity, focused automated suites, fresh PostgreSQL behavior, provider sandboxes, UI journeys, and unchanged legacy contracts. Release verifies protected CI, exact-SHA GO, merge identity, deployment, migration, backfill reconciliation, configured workers/webhooks, and target-tenant gate state.

## 18. Rollout and sign-off

The required order is:

1. DB-044 is merged and its production/runtime evidence is recorded.
2. DB-045 branch is created from freshly fetched resulting `origin/main`; this contract is frozen before parallel implementation.
3. Implement one integrated candidate with both new feature gates false.
4. Obtain focused owner evidence, independent Security GO, independent QA GO, protected CI, and exact-SHA Release GO.
5. Merge the one PR and deploy the exact merge candidate with counter sales still disabled.
6. Run migration/schema preflight, deploy Activity writers/workers, and execute tenant-scoped dry-run/backfill/reconciliation. A failed tenant remains disabled.
7. Verify Stripe and QuickBooks sandbox/provider/webhook/outbox readiness. No real customer charge/refund occurs without separate Product authorization.
8. Enable the global gate only after system readiness, then enable the explicitly approved target tenant only after its verified backfill and provider configuration.
9. Verify production read-only/runtime behavior, gate state, worker health, Activity counts, provider/outbox health, and absence of stock/payment/reporting regressions.

DB-045 is Done only after the board records the owner, frozen contract impact, exact candidate/merge/deploy identity, focused checks, migration/backfill reconciliation, Security/QA/Release GO, target-tenant gate result, and production runtime evidence. Any unresolved provider, stock, tenant, refund, reporting, migration, or runtime defect keeps it out of Done.

## 19. Frozen implementation decisions and external dependencies

The following are frozen and are not implementation-time product choices:

- dedicated counter-sale aggregates, never repair-order/invoice reuse;
- immutable per-part Activity index with database update/delete guards;
- exactly one tender, provider-backed or manual, settling the sale in full;
- 15-minute holds with provider-aware expiry and compensating refund on late success;
- server-side Decimal tax/fee/refund allocation and whole-package quantities;
- owner/admin-only price override and returns/refunds;
- QBO Sales Receipt/Refund Receipt through the durable outbox;
- parts-first navigation with secondary `/inventory/sales` utility;
- both counter-sales gates off by default and tenant enablement only after verified backfill.

External acceptance dependencies are not permission to weaken the contract. Stripe Connect test credentials/webhook signing, QuickBooks Payments sandbox scopes, QuickBooks Accounting sandbox access, and configured email/PDF dependencies must be available to complete their required gates. If any are unavailable, the candidate may remain implemented behind disabled gates but DB-045 cannot receive release sign-off or target-tenant enablement.
