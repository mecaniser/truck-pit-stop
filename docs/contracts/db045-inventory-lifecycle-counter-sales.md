# DB-045 Inventory lifecycle and manual counter sales contract

- Version: 1.1.0
- Status: Re-frozen after Product scope reduction
- Accountable owner: Backend & Integrations
- Branch: `codex/db045-inventory-lifecycle-counter-sales`
- Reshape base: `0980555dba6bfc4556074c3df1c7833c972c772f`
- Currency: USD only
- Delivery lane: High risk

## 1. Product boundary

DB-045 remains a repair-first Inventory release. It delivers:

1. an append-only Inventory Activity foundation;
2. a selected-part lifecycle hub;
3. a small, secondary workflow for occasional staff-recorded walk-in part sales.

Parts remains the default Inventory experience. Parts sales is reached through the quiet Inventory utility or a selected-row contextual action. It is not a top-level Shop destination and it is not a general-purpose POS.

### Deferred from DB-045

The following are intentionally removed and require separate Product-approved items:

- Stripe Connect counter-sale checkout, webhooks, or reconciliation;
- QuickBooks Payments charges, refunds, or settlement reconciliation;
- QuickBooks Accounting Sales Receipt or Refund Receipt synchronization;
- payment-provider retry, dead-letter, compensation, or recovery workers;
- expiring stock reservations or late-provider-success compensation;
- provider refund orchestration;
- emailed counter-sale receipts;
- counter-sale dashboard, Tax, Parts Margin, Sales, or customer-profitability integration;
- split tenders, partial payments, pay later, accounts receivable, guest payment links, and customer-portal checkout.

Existing repair-invoice Stripe, QuickBooks, email, outbox, and reporting behavior is outside DB-045 and must remain unchanged.

## 2. Immutable Activity foundation

`part_activity_events` is an append-only, tenant-scoped index. Product APIs cannot update, delete, or soft-delete events. The database prevents update and delete.

Each event records:

- tenant, part, category, event type, occurrence time, correlation ID, and idempotency key;
- source type, source ID, source number snapshot, and safe deep link;
- actor ID and actor-name snapshot;
- reason code/note and payload version;
- typed before/after, stock, money, payment, and source snapshots when applicable;
- origin: `live`, `baseline`, or `backfill`.

Categories are Catalog, Stock, Repairs, Purchasing, Returns, and Sales.

Relevant existing Inventory mutations append their event in the same transaction. No-op catalog/source updates append no event. Existing authoritative records remain authoritative; Activity is a searchable immutable projection.

## 3. Backfill and rollout gates

The idempotent batched command writes:

- one explicit baseline snapshot for every non-deleted part;
- one event for each existing inventory movement;
- truthful current-state snapshots for legacy repair usage, receipts, vendor returns, and core obligations.

It never claims to reconstruct overwritten historical values. Deterministic idempotency keys make interrupted runs and reruns safe. Reconciliation records counts, checksums, duplicates, and tenant identity. A tenant cannot use Parts sales until its latest payload-version backfill is verified.

Parts sales requires both:

- global `COUNTER_SALES_ENABLED`;
- tenant `counter_sales_enabled`.

Both default disabled. Disabled, foreign, deleted, and unreconciled tenants receive the same generic not-found response.

## 4. Lifecycle interfaces

All routes are under `/api/v1/parts-operations`.

- `GET /activity-events`
- `GET /activity-events/export.csv`
- `GET /parts/{id}/lifecycle-summary`

Activity filtering supports part, category, event type, actor, source, text, and half-open date range. List and CSV export use the same normalized filter contract. List pagination is stable cursor pagination. CSV fields are spreadsheet-injection safe.

The selected-part History tab is renamed Activity. The global Movement view is renamed Activity. Overview, Stock, and Ordering remain.

The lifecycle summary includes repair usage, purchasing/receipts/vendor returns/cores, manual counter-sale units/revenue/returns, and Activity count/last occurrence. The existing movement endpoint remains backward compatible.

## 5. Manual counter-sales domain

### 5.1 Roles and buyer

Garage owner, garage admin, and receptionist may create and complete a sale. Only owner/admin may:

- override catalog price, with a required reason;
- cancel a draft, with a required reason;
- record a return.

A sale may link an existing same-tenant customer or use immutable optional buyer name, email, and phone snapshots. Anonymous walk-ins are valid. A vehicle is never required.

Foreign, deleted, placeholder, archived, or cross-tenant records are unavailable through the same generic boundary behavior.

### 5.2 State model

Sale states:

`draft -> completed -> partially_returned -> returned`

A draft may transition to `cancelled`. Completed sales are never destructively voided.

There is no awaiting-payment state. A checkout either commits the complete manual sale atomically or leaves the draft and stock unchanged.

### 5.3 Pricing and tender

- Quantities are positive whole packages.
- Catalog selling price is the default.
- Receptionists cannot override catalog price.
- Owner/admin overrides require a reason.
- Tenant sales tax is snapshotted on the sale.
- Exactly one manual tender settles the entire sale: cash, check, ACH, Zelle, external terminal, fleet reference, or other.
- An optional external reference may be recorded.
- There is no DB-045 card-provider fee.

Each line snapshots part identity, unit, unit cost, list price, charged price, discount, tax, total, and deterministic per-unit allocations for return calculations.

### 5.4 Stock safety and checkout

Checkout:

1. validates gate, role, tenant, optimistic version, and idempotency key;
2. locks all part rows in deterministic ID order;
3. verifies every requested quantity against physical on-hand;
4. records one succeeded manual tender record;
5. decrements physical on-hand using `counter_sale` inventory movements;
6. appends sale-completion Activity events;
7. stores the printable receipt snapshot;
8. commits the complete sale in one database transaction.

No reservation rows or background expiry worker exist. Held-for-checkout is always zero and available-to-sell equals physical on-hand for this bounded workflow. Concurrent checkout cannot oversell because stock is checked while rows are locked.

### 5.5 Returns

Owner/admin may return any remaining quantity. Every line requires:

- a reason;
- `restock` or `damaged` disposition.

A restocked return posts `counter_sale_return` inventory movements. A damaged return does not increase on-hand. The recorded return calculates the original deterministic item and tax allocation and may store an external refund/reversal reference. DB-045 does not execute or reconcile money movement. Repeating the same idempotency key cannot duplicate stock, Activity, or return records.

## 6. Counter-sales interfaces

All paths are under `/api/v1/parts-operations`.

- `GET /counter-sales`
- `POST /counter-sales`
- `GET /counter-sales/{sale_id}`
- `PATCH /counter-sales/{sale_id}`
- `POST /counter-sales/{sale_id}/checkout`
- `POST /counter-sales/{sale_id}/cancel`
- `GET /counter-sales/{sale_id}/returns`
- `POST /counter-sales/{sale_id}/returns`
- `GET /counter-sales/{sale_id}/returns/{return_id}`
- `GET /counter-sales/{sale_id}/receipt.pdf`

Mutations use optimistic `expected_version` where applicable and require `Idempotency-Key`. The key is bound to tenant, principal, route, and canonical payload. Reusing a key with a different request conflicts.

There are no provider webhook, payment-attempt reconciliation, refund retry, or receipt-email endpoints in DB-045.

## 7. Frontend placement and behavior

Canonical route: `/dashboard/garage/inventory/sales`.

- Parts remains the default Inventory workspace.
- `Parts sales` opens sale history and owns the primary `New counter sale` action.
- A selected ledger row may expose `Sell part` through contextual overflow.
- Draft creation supports part search, the shared QuantityStepper, optional customer lookup, manager price override, and buyer snapshots.
- Checkout shows item/discount/tax/total, one manual tender, optional external reference, and one completion action.
- Completed sales expose printable receipt and, for managers, audited return entry.
- Provider checkout, provider recovery, accounting sync, email receipt, and refund-retry UI must not render.
- Keyboard, focus return, 44px controls, theme behavior, and responsive containment are required.

## 8. Migration and downgrade

Migration 127 creates the Activity/backfill/idempotency tables, tenant feature gate, manual counter-sale tables, succeeded manual tender records, and completed manual-return tables. It does not add provider, reservation, accounting-sync, service-fee, or email-receipt structures.

Fresh PostgreSQL upgrade, downgrade, and re-upgrade must keep one Alembic head. Downgrade must refuse when immutable Activity or counter-sale financial/audit rows exist rather than silently destroy records.

## 9. Focused verification

One exact candidate SHA must pass:

- Alembic single-head and fresh disposable PostgreSQL upgrade/downgrade/re-upgrade;
- append-only trigger and cross-tenant FK checks;
- idempotent backfill rerun and reconciliation;
- disabled gate, unauthorized role, foreign/deleted record, and generic-not-found cases;
- Activity atomicity, no-op, actor/reason, stable cursor, and CSV filter parity;
- manual checkout success, idempotency, version conflict, and concurrent no-oversell;
- receptionist price restriction and manager override reason;
- cancel draft;
- partial/full, restock/damaged, ceiling, and duplicate return cases;
- receipt PDF;
- focused components and Playwright for Activity, sale draft, manual checkout, receipt, and return across supported themes and widths;
- changed-source lint, production build, compile, and diff checks;
- independent Security review for tenant authorization, exports, idempotency, stock, and refund authority;
- fresh independent QA on the exact candidate.

Provider sandbox journeys and broad counter-sales reporting suites are explicitly not DB-045 acceptance because those product seams are deferred.

## 10. Release boundary

Prior CI, Security, QA, and Release evidence for the provider-heavy candidate is historical after this material contract change.

No merge, deployment, migration, backfill, target-tenant gate enablement, or production mutation occurs until:

1. the reduced candidate is committed and pushed under Product authority;
2. protected PR CI passes on that exact SHA;
3. fresh independent Security and QA return GO on that exact SHA;
4. Release returns exact-SHA GO;
5. Product authorizes merge and the separately controlled production rollout.

Production sign-off requires migration/backfill reconciliation, deliberate target-tenant gate enablement, and read-only/runtime verification. No real financial transaction is required or authorized by this contract.
