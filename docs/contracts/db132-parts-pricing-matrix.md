# DB132 / P1 — parts markup matrices: approved implementation contract

Architecture approved 2026-10-15 after R1/DB131 and DB137 production closure.
Implementation intake baseline: `fc92c7b9944a0d07db80399b9f6e1eda13840b87`, branch
`codex/ets-parts-pricing-matrix-implementation`. DB137 changed only the repair-order
queue toolbar and its tests/styles from the reviewed P1 application baseline.
Accountable implementation owner: Backend & Integrations. Product & Delivery Lead
owns scope and sequencing. Accepted wire, retained-line and deletion-compatible
audit clarifications are integrated below; no product decision remains open.
This is contract approval, not implementation, test, release or production evidence.
It does not activate pricing policy or authorize guessed shop markups. Independent
QA/Security and the release evidence below remain required.

## Outcome and smallest coherent scope

An owner/admin creates a named cost-band markup matrix, previews examples and
deliberately makes it the shop default. New customer-chargeable parts receive a
consistent price in every existing attachment path. Staff see where that price
came from and can make an authorized manual override. Part cost floors, minimum
sale prices and fixed catalog prices have distinct labels and semantics.

Include ordinary RO parts, parts bundled with a service, external fleet-managed
RO parts and new counter-sale lines. Internal fleet parts remain at actual cost.
No automatic rewrite of catalog selling prices, existing RO parts, existing
counter-sale lines, quote revisions, invoices, imported ETS records, receipts,
payments, taxes, discounts already granted, reservations or stock units. No
catalog-wide “apply/reprice” job. C1 customer pricing is a separate next item.

Feature ships inactive: no matrix is seeded, no default is chosen and no part
policy is configured for a real shop. Matrix pricing begins when its owner/admin
selects a default; explicitly configured part minimum/fixed rules also apply
without a default as defined below. Deployment does not constitute authority to
invent markups or change customer agreements.

## Evidence and source semantics

The approved audit P1/C1 rows and sanitized REA evidence are in:
`docs/ETS_PARITY_BACKLOG_2026-10-15.md` and
`docs/verification/ETS_PARITY_BACKLOG_REA_2026-10-15.json`.
REA evidence ID `ev_dd23a222a269441d5ac9d228ea05477633c66a9e63b0579e43c598ee795c82ee`
includes the observed matrix form and its cost-floor/fixed-price controls. This
is capability evidence, not a claim that vendor backend validation was tested.

Official ETS help (fresh read 2026-10-15):
https://support.easytruckshop.io/en/articles/11664125-using-the-parts-price-matrix
describes markup on WAC, optionally using a higher **cost basis floor**; locking
sales price skips the matrix. Customer matrix overrides the shop default. These
are different from a minimum selling price. It also documents historical failures
after deleting a matrix: DBN should archive and snapshot instead.

DBN already snapshots `PartsUsage.unit_cost`, `unit_price` and `list_price`;
quantity edits preserve price, quotes snapshot charged values, and finalization
locks financial work. `discount_limits.py` protects actual cost, while the direct
part-add route currently accepts a staff-supplied price without the same floor
check. Use one resolver/validator for new pricing behavior rather than adding
another inconsistent check in each UI.

## Product decisions (resolved by Product & Delivery Lead)

1. **Markup, not margin.** Cost × (1 + percent / 100). Display a separate margin
   preview where meaningful; never label 50% markup as 50% margin.
2. **Pricing cost floor** is a minimum basis before markup. It does not change
   WAC, inventory valuation, recorded actual unit cost or profit accounting.
3. **Minimum sale price** is an optional hard minimum for the charged unit price
   of new externally billed lines. Existing actual-cost protection still applies.
   It is snapshotted on attachment and respected by manual price edits, “stock”
   mode and additional discount capacity. No below-minimum override in P1.
4. **Fixed catalog price** means “skip matrix and use this part's saved selling
   price”, not “staff can never edit the job line.” Existing authorized staff can
   override a line above its effective minimum with a reason. This label avoids
   confusing it with invoice finalization locks.
5. Matrix changes affect only newly attached lines; line snapshots do not resolve
   through mutable rules later. A quantity-only edit never adopts current WAC,
   current matrix, current part floor or a different catalog price.

Product & Delivery Lead confirmed both distinct optional fields on 2026-10-15:
pricing cost floor before markup and hard minimum selling price for new managed
external lines, both unset by default. Fixed catalog pricing skips the matrix but
does not block an authorized line override above the effective minimum. This is
within the user's selected minimum-price/locked-price scope; no clarification is
pending. Do not invent a below-minimum permission system. No real-shop pricing
policy activation or guessed markup is authorized by preparation of this contract.

## Definition of managed pricing

A new external catalog attachment is P1-managed only if a matrix is selected for
that context, `fixed_sales_price=true`, or `minimum_sale_price IS NOT NULL`.
A minimum applies without any default matrix. A pricing-cost floor alone has no
effect without an applied matrix, and does not make an otherwise unset catalog
line managed. Fixed pricing bypasses the matrix but remains managed. Record this
boolean in the immutable attachment snapshot; a non-NULL JSON snapshot by itself
never makes an old or unmanaged line subject to new minimum rules.

All-unset/no-matrix catalog defaults preserve current default-price behavior;
explicit overrides keep existing actual-cost protections. A freshly recorded
unmanaged snapshot does not retroactively reject an unchanged historical charge.
Internal and explicit ad-hoc contexts remain distinct from managed external catalog
pricing. Clear-default means catalog pricing plus any independently configured
fixed/minimum policy; it is not a global switch that disables those part policies.

## Exact pricing precedence

The backend shared resolver returns a suggested/default unit price plus an
immutable provenance object. Every insertion caller uses it; browser prices are
never authoritative defaults.

1. Financially locked/finalized order or noneditable counter sale rejects mutation
   before pricing. Existing staff, mechanic assignment and fleet scope stay intact.
2. An internal RO is priced at actual inventory cost; ignore matrix, cost-basis
   floor, minimum selling price and fixed-catalog policy. No markup or customer
   discount is inferred. Preserve the truck's separate labor billing preference.
   A new internal request supplying a different price is rejected; never silently
   ignore money supplied by a caller or permit accidental markup.
3. Explicit new ad-hoc line pricing remains an explicitly entered/manual workflow.
   Do not matrix-price a placeholder whose zero cost represents “not supplied.”
   Validate its supplied cost and sale price and record ad-hoc provenance.
4. For a normal external catalog line, if `fixed_sales_price=true`, use current
   saved `Inventory.selling_price` as the default. Skip matrix/cost-basis floor.
5. Otherwise select an explicit matrix revision provided by the calling pricing
   policy, or the shop default current revision. P1 supplies only shop default;
   C1 later supplies a customer/order policy revision. Never accept an arbitrary
   cross-tenant revision from a browser or choose a matrix by untrusted name.
6. If a revision exists, `basis = max(actual_cost, pricing_cost_floor or 0)`.
   Find its unique band and compute `basis × (1 + markup_percent / 100)` using
   Decimal, rounding once to cents with ROUND_HALF_UP. Apply minimum sale price
   after markup. A band always exists for finite nonnegative valid basis.
7. With no matrix, use the saved catalog selling price. Do not mutate it. Legacy
   no-matrix/no-policy lines preserve existing behavior; validate explicit new
   overrides against current actual-cost protection.
8. For a P1-managed default, `effective_minimum = max(actual_cost,
   minimum_sale_price or 0)`. Fixed/catalog values below it return an actionable
   error requiring correction or an explicit valid override, never silently raise
   a protected fixed price. Matrix results naturally respect cost; raise to the
   configured minimum if needed and show that basis in preview.
9. An authorized explicit override becomes charged price only after finite,
   nonnegative, currency precision, range and effective-minimum validation. Its
   default/list price remains the resolved suggestion, so savings are meaningful.
   Mechanics cannot override; their supplied price must equal server default.

Negative, NaN, Infinity, invalid precision or overflow never become a zero price.
Inventory cost is presently NOT NULL; malformed/missing actual cost blocks matrix
resolution rather than guessing. Existing legacy lines with missing cost retain
their money, and existing restrictions on new discounts remain. A known zero
cost is valid: a positive cost-basis floor or minimum can price it. With zero basis,
no positive minimum and a positive catalog price, fall back to catalog with
`source=catalog_zero_cost` and a warning; never accidentally make a stocked part
free. If neither a usable suggestion nor permitted manual price exists, return
`part_price_required`. Display margin as unavailable for uncertain cost.

Core deposits, purchase freight/tax, surcharge and sales tax are not marked up by
the matrix; it acts only on the part's billable unit price. Fractional quantities
use existing units and canonical total rounding; do not fix P6 stock accounting
inside this release.

## Matrix rules and schema

Concrete additive storage:

* `parts_price_matrices`: id, tenant_id, current_revision integer, current name,
  archived_at/by, metadata version, created/updated actor. Unique `(tenant_id,id)`;
  active names unique case-insensitively. Trim names; require 1–100 characters.
  Identity is ID, not name. No hard delete.
* `parts_price_matrix_revisions`: id, tenant_id, matrix_id, revision integer,
  name snapshot, validated band JSON, created_at/by. Unique `(tenant_id,id)` and
  `(tenant_id,matrix_id,revision)`; composite same-tenant matrix FK. Immutable.
  Name/rules change appends a revision; archive changes only matrix metadata.
* `parts_pricing_policies`: one row per tenant, `default_matrix_id NULL`,
  `generation BIGINT NOT NULL DEFAULT 0`, updated_at/by. Composite same-tenant
  matrix FK. This is the only default pointer; derive `is_default` in responses.
  Every actual default switch/clear/restore selection increments generation,
  including A→B→A and NULL→A→NULL. True no-op selection does not increment.
* `parts_pricing_events`: append-only tenant-scoped configuration and line-price
  audit, actor/time, entity type/id, command correlation, old/new version,
  event type, reason and bounded private before/after JSON. Durable matrix,
  revision, inventory, counter-sale and counter-line references use nullable typed
  same-tenant composite FKs. Historical PartsUsage identity is a deliberate
  non-FK reference because operational usage rows can be physically removed;
  the deletion-compatible audit contract below is authoritative. This audit
  works with parts-operations/counter-sale flags disabled. Its private owner/admin
  reader supports bounded tenant/entity-filtered pagination.

Reuse existing `PartsOperationIdempotency` and its unflagged find/begin/complete
primitives with new `p1_*` operation families; they are durable infrastructure,
not authorization. Do not call `require_parts_operations_enabled` for P1 config.
Fingerprint includes tenant, actor, route and exact validated payload. Reauthorize
before replay; never replay a formerly privileged body after a role change. A
same-key different payload is409. Configuration and mutations save their audit,
receipt and data atomically. No new receipt subsystem is necessary.

Inventory adds `pricing_cost_floor NUMERIC(10,2) NULL`, `minimum_sale_price
NUMERIC(10,2) NULL`, `fixed_sales_price BOOLEAN NOT NULL DEFAULT false`, and
`pricing_version BIGINT NOT NULL DEFAULT 0`. Existing selling_price is fallback/
fixed value. NULL is unset, not0. Version increments for actual cost, selling-price
or policy changes, including WAC changes; stock-only or unrelated metadata changes
do not increment it. Inventory creation starts its first real pricing version.

PartsUsage and CounterSaleLine add nullable server-owned `pricing_snapshot JSON`
and nullable `pricing_matrix_revision_id UUID`; FK
`(tenant_id,pricing_matrix_revision_id)`
references the revision's unique `(tenant_id,id)`. Matrix revision identity must
not exist only inside JSON: JSON cannot enforce the promised composite tenant FK.
There is no live audit-to-PartsUsage FK or new usage uniqueness solely for one.
No FK cascade deletes a referenced revision or price audit. Snapshot includes an
immutable generated snapshot UUID/schema, managed boolean, source, applied matrix
revision/name/band when used, default generation, actual cost and known-cost flag,
cost floor/basis, minimum/effective minimum, fixed flag, catalog/default/original
charged price and initial override actor/reason. Amounts are strings. No fabricated
backfill for existing rows. Fixed/catalog-only lines have NULL applied revision.

PartsUsage additionally gets `pricing_version BIGINT NOT NULL DEFAULT 0` for line
CAS and optional `source_component_id UUID` for a service-part identity snapshot.
That component id is not an FK to a mutable/deletable ServicePart; record identity
without cascading history loss. Counter lines use their existing sale version as
transaction CAS; retain line IDs. Original snapshots never change after creation.
Current charged price and append-only price events form the override overlay;
current source label derives from the latest price action, not mutation of origin.
Reads/finalization use saved values, never the live resolver.

Example rules: `[0.00,25.00)` =>100%, `[25.00,100.00)` =>50%,
`[100.00,infinity)` =>30%. Schema uses `{ min_cost, max_cost, markup_percent }`;
max is NULL only on the last band. 1–30 bands, sorted, first min=0, each next min
equals previous max, strictly increasing limits, last max=NULL. No gaps/overlaps
or silently reordered rows. Label upper bound “under” in UI to make boundaries
clear. Use monetary bounds to2 decimals and percentage to2 decimals,0–10000;
money/result fits existing NUMERIC(10,2). High percentages are allowed but preview
shows their actual price; no guessed markup defaults.

Use one additive migration after the refreshed current Alembic head. Null snapshots/floors and false
fixed flag preserve all existing data. Production rollback leaves columns and
revisions in place; reverse migration only on disposable test databases after
dropping new app code. DB constraints/composite FKs prohibit cross-tenant links.

### Deletion-compatible append-only audit identity

Existing ordinary part removal physically deletes
PartsUsage (`repair_orders.py`, remove-part endpoint); service removal does the same
(`PriceBuildService._restore_service_parts`). A restrictive audit FK would break
those workflows, while cascade/SET NULL would delete or mutate audit evidence.
Do not convert operational parts to tombstones solely to retain an audit pointer.

`parts_pricing_events` therefore stores:

- Immutable server-generated event ID, tenant_id, entity_type/entity_id, event type,
  actor/time, correlation key and old/new version as already specified.
- For `entity_type=parts_usage`, entity_id is the original PartsUsage UUID and is
  intentionally **not a live FK**. A bounded immutable identity snapshot records
  the original usage ID, repair-order ID/number, inventory ID, source service/line/
  component IDs when present, and immutable pricing snapshot UUID/schema. Names,
  quantity, original actual-cost evidence, default/charged amounts and the relevant
  prior/next values are included in the existing bounded private before/after
  evidence. The snapshot is evidence, not a new authorization-bearing association.
- Nullable typed matrix, revision, inventory, counter-sale and counter-line columns
  retain composite same-tenant FKs where applicable. The same-tenant revision FK
  on every live PartsUsage/CounterSaleLine remains required. Nothing cascades to
  delete/alter price audits or revisions. CounterSaleLine can keep its audit FK:
  current draft replacement soft-deletes removed rows and retains their identities;
  P1 reconciliation preserves IDs for retained rows and soft-deletes actual removals.

Do not add `(tenant_id,id)` uniqueness to PartsUsage solely for an audit FK. It
may remain if an independent verified tenant constraint needs it; the live
usage-to-revision composite FK does not itself require usage uniqueness. Audit rows
use tenant+entity_type+entity_id indexes for bounded private reads, not live joins.

Only the server creates event identities, tenant IDs and snapshots. At append time,
load/lock or use the already locked live row and verify that usage, order, inventory
and any referenced pricing revision belong to the authenticated tenant. Assert any
supplied in-process object IDs agree with those validated objects. No public request
accepts an audit entity ID, snapshot or tenant to persist. Price mutation and its
audit append remain one transaction; removal appends its final evidence before the
existing physical deletion in that same transaction. Retry/idempotency must not
append a second removal event. Existing history/activity entries remain unchanged.

This is a deliberate database-integrity exception for a physically removable
operational identity, not an exception to tenant checks: matrix/revision/inventory/
counter references continue to be constrained by the database, and the historical
usage reference is verified at creation. An audit reader must first authorize its
owner/admin tenant scope. A historical entity UUID never authorizes a current
usage/order lookup, reattachment or price mutation; any navigation performs the
normal tenant-scoped live lookup and may report that the source was removed. Audit
rows remain readable without a surviving usage row; no fallback cross-tenant join.

Required PostgreSQL tests: create and override a usage, remove it directly and by
service removal, then verify deletion succeeds and prior plus final audit rows are
byte-for-byte intact; verify replay creates no duplicate audit. Assert cross-tenant
live-row append is rejected and durable composite FKs reject foreign revisions/
inventory/counter identities. Verify a foreign historical UUID cannot bypass the
audit reader scope or authorize a live lookup. Counter draft retain/remove tests
must prove retained IDs stay stable, removed lines stay soft-deleted, and their
prior price events remain intact. No new audit-retention/financial-history feature
or application-wide soft-delete rewrite is part of P1.

## API contract

Namespace `/api/v1/parts-pricing` independent of activating counter-sale or parts
operations feature flags. No new flag is required: absence of a matrix and all
part policies unset preserves legacy defaults.

* `GET /matrices?include_archived=false` returns bounded metadata/current revision
  to owner/admin only. The same allowlist applies to matrix details/revision
  history, private configuration audit and draft-matrix `/preview`. Other staff
  use sanitized contextual resolution, not the matrix-rule endpoint.
* `POST /matrices` accepts name and complete validated bands; creates revision1,
  never silently makes it default. Use the required Idempotency-Key header defined below
  so double submission does not create two matrices.
* `PUT /matrices/{id}` accepts name/bands and expected metadata version; appends
  a revision atomically. Stale version409, unchanged data no-op200. Reject archived
  edits until restored. No in-place update of revision rows.
* `GET /default` returns `{matrix_id, generation}` to owner/admin.
* `PUT /default` accepts `matrix_id` or NULL and `expected_generation`. Use the
  policy generation above; expected identity or matrix revision alone cannot
  detect ABA. Lock, compare and update atomically. Foreign/archived matrix fails;
  clearing does not disable independent part minimum/fixed policies.
* `POST /matrices/{id}/archive` / `/restore` require expected version. Cannot archive
  the active default until deliberately clearing/replacing it. Future C1 active
  references similarly require replacement. Historical line references do not
  block archive and remain readable. Append the dedicated parts-pricing audit;
  archival is metadata only and cannot delete historical price evidence.
* `POST /preview` evaluates proposed draft bands against ≤20 supplied sample cases
  or ≤50 exact tenant inventory IDs. This is read-only, bounded, no stock or catalog
  writes. Draft samples may show hypothetical costs but cannot alter authoritative
  usage. Return before catalog/current suggestion, proposed price, gross profit,
  markup and margin, selected band/source/floor and warnings.
* `POST /resolve` quotes a complete, typed mutation plan in an authorized exact
  RO, new-fleet-draft or counter-sale context. The concrete schema/fingerprint
  contract below covers standalone and service bundles; inventory IDs alone are
  not enough to confirm a service price. It performs no persistence/stock writes.
* `GET /inventory/{id}/pricing-policy` and `PATCH /inventory/{id}/pricing-policy`
  are owner/admin only. PATCH accepts `expected_pricing_version`, optional three
  policy fields and optional selling_price; omitted means unchanged, NULL clears
  an optional floor. Include version in manager inventory detail. Generic catalog
  cost/selling-price writes use the same lock and expected_pricing_version when
  changing money. Missing version returns409 `pricing_version_required`; old
  non-price metadata writes remain compatible. WAC receipt is an existing locked
  source mutation, so it increments price version without a UI pricing CAS.

New policy fields and raw immutable snapshot are not added indiscriminately to
shared inventory/customer types. Exact role projections are defined below. Quotes,
invoices, receipts, public notes/events and portal payloads keep charged values only.

All writes: role check before lookup, tenant+active record scoped lookup,404 for
foreign IDs,409 version/default/archive/preview conflicts,422 bounds/gaps/cost/
floor errors. Configuration owner/admin only. RO manual overrides retain existing
PRICE_BUILD_EDIT_ROLES (fleet manager scoped), with a human reason for manual
pricing or a named audited List/Stock intent as defined below. Counter sales retain manager-only override and
existing reason rule. No customer, driver or mechanic configuration writes.

### Exact configuration envelopes and version names

All routes below are under `/api/v1/parts-pricing` and owner/admin-only. No request
accepts tenant, actor, timestamps, revision IDs or server-generated versions except
the explicitly named expected-version fields. UUIDs are strings, timestamps UTC
ISO8601, `Money` is a two-decimal string and percentages are decimal strings.
Unknown request fields are rejected. These are new P1 schemas, not global changes
to existing inventory or counter-sale envelopes.

```ts
type MatrixBand = { min_cost: Money; max_cost: Money | null; markup_percent: string };
type MatrixSummary = {
  id: string;
  name: string;
  version: number; // metadata CAS, starts at 1
  current_revision: number; // immutable rules/name revision, starts at 1
  current_revision_id: string;
  is_default: boolean; // derived from tenant policy, not a stored second pointer
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};
type MatrixDetail = MatrixSummary & { bands: MatrixBand[] };
type MatrixListResponse = { schema_version: 1; items: MatrixSummary[]; next_cursor: string | null };
type MatrixDetailResponse = { schema_version: 1; matrix: MatrixDetail };
type MatrixRevision = {
  id: string; // immutable revision UUID
  matrix_id: string;
  revision: number;
  name: string;
  bands: MatrixBand[];
  created_at: string;
  created_by_user_id: string | null;
};
type MatrixHistoryResponse = { schema_version: 1; items: MatrixRevision[]; next_cursor: string | null };
type MatrixCreateRequest = { name: string; bands: MatrixBand[] };
type MatrixUpdateRequest = MatrixCreateRequest & { expected_version: number };
type MatrixArchiveRequest = { expected_version: number };
type DefaultResponse = { matrix_id: string | null; generation: number };
type DefaultUpdateRequest = { matrix_id: string | null; expected_generation: number };
type InventoryPricingPolicy = {
  inventory_id: string;
  pricing_version: number;
  actual_unit_cost: Money | null;
  actual_cost_known: boolean;
  selling_price: Money;
  pricing_cost_floor: Money | null;
  minimum_sale_price: Money | null;
  fixed_sales_price: boolean;
};
type InventoryPricingPolicyResponse = { schema_version: 1; policy: InventoryPricingPolicy };
type InventoryPricingPolicyPatch = {
  expected_pricing_version: number;
  selling_price?: Money;
  pricing_cost_floor?: Money | null;
  minimum_sale_price?: Money | null;
  fixed_sales_price?: boolean;
};
type PricingAuditEvent = {
  id: string;
  entity_type: 'matrix' | 'default_policy' | 'inventory' | 'parts_usage' | 'counter_sale_line';
  entity_id: string; // default_policy uses the authenticated tenant UUID
  event_type: string; // server-owned action name; never interpreted as executable UI
  occurred_at: string;
  actor_user_id: string | null;
  actor_display_name: string | null; // no email or new user-directory access
  correlation_id: string;
  old_version: number | null;
  new_version: number | null;
  reason: string | null;
  snapshot_id: string | null;
  changes: Array<{ field: string; before: string | null; after: string | null }>;
};
type PricingAuditResponse = { schema_version: 1; items: PricingAuditEvent[]; next_cursor: string | null };
```

- `GET /matrices?include_archived=false&limit=50&cursor=...` returns
  MatrixListResponse. Limit is 1–100. Sort by normalized name then ID; the opaque
  cursor binds tenant, filter and last sort keys. An invalid/mismatched cursor is
  400 `invalid_cursor`; no silent return to page one. This is live list paging,
  not a historical snapshot; refetch page one after configuration mutations.
- `GET /matrices/{id}` returns MatrixDetailResponse, including archived matrices
  in the authenticated tenant. POST create returns the same envelope with 201;
  PUT edit and POST archive/restore return that envelope with 200. A true no-op
  returns the same version/revision and creates no duplicate revision/event.
- `version` changes on actual name/band/archive/restore mutation. Name/band changes
  also append `current_revision` and set its new `current_revision_id`.
  Archive/restore does not create a rules revision. Selecting/clearing a default
  changes only policy generation, not the selected matrix's metadata version.
- `GET /matrices/{id}/revisions?limit=50&cursor=...` returns MatrixHistoryResponse,
  newest revision first with ID as tie breaker. Each history item includes its
  full immutable bands; no additional revision-detail endpoint is needed.
- GET and PUT `/default` both return exactly DefaultResponse; there is no extra
  `data`, `default` or `policy` wrapper. No policy row yet means NULL/0 on GET,
  without initializing data. PUT uses DefaultUpdateRequest.
- GET and PATCH `/inventory/{id}/pricing-policy` return the same
  InventoryPricingPolicyResponse. Patch uses InventoryPricingPolicyPatch. Unknown
  placeholder cost is NULL/false in this response, not an invented known zero.
  Cost editing continues through the existing catalog pathway; this PATCH does
  not introduce a new actual-cost mutation. Omitted fields stay unchanged.
- `GET /events?entity_type=...&entity_id=...&limit=50&cursor=...` requires both
  entity filters, uses the private tenant scope and returns PricingAuditResponse.
  Limit is 1–100; order occurred_at/ID descending. Its opaque cursor binds the
  tenant/entity filters. `changes` is an explicit allowlisted display projection
  of the event's stored before/after evidence, not arbitrary model serialization:
  scalar values are formatted strings and band lists are canonical JSON strings.
  Never include unrelated model fields, secrets or full actor records. The reader
  works after a usage is physically removed; historical UUIDs are not live access
  grants. Full matrix rules are available in the revision history above.

All configuration writes require the `Idempotency-Key` HTTP header. UI generates
one fresh UUID per logical action and reuses it only for retries of that action;
there is no request-body `idempotency_key`/`request_id` alias. Reuse the existing
`validate_idempotency_key` carrier validation (16–128 printable ASCII characters;
UUID is the UI convention). Missing/invalid header is the existing 400 validation
error. Apply it to matrix create/update/archive/restore, default PUT and inventory
pricing-policy PATCH, before mutation. GET, `/preview` and `/resolve` do not need
an idempotency key. Request payload plus route/actor/tenant determine replay;
unchanged retry returns the original status/envelope without repeating its audit.
Reauthorization precedes replay. Current-policy reads use GET, not an old receipt.

Configuration errors use `{detail:{code,message}}` (apart from existing carrier
validation and standard field-validation 422). Exact conflicts are
`matrix_version_conflict`, `default_generation_conflict`, `pricing_version_conflict`,
`matrix_name_conflict`, `matrix_archived`, `matrix_is_default` and
`idempotency_conflict`. They do not return an implicit replacement object or retry
instruction: the UI preserves the draft, refetches the applicable GET and offers
an explicit retry with the fresh expected version and a new logical-action key.
Foreign IDs remain 404; all matrix writes keep the existing owner/admin boundary.

### Exact draft-matrix sample preview

`POST /preview` is private hypothetical analysis and never a mutation confirmation.
It takes exactly one discriminated source of cases, plus the proposed bands:

```ts
type DraftSample = {
  sample_key: string; // unique per request, 1–80 characters
  label?: string; // optional display label, at most 120 characters
  actual_unit_cost: Money | null; // NULL means unknown, never zero
  catalog_unit_price: Money | null;
  pricing_cost_floor?: Money | null;
  minimum_sale_price?: Money | null;
  fixed_sales_price?: boolean; // omitted means false
};
type MatrixPreviewRequest =
  | { mode: 'samples'; bands: MatrixBand[]; samples: DraftSample[] }
  | { mode: 'inventory'; bands: MatrixBand[]; inventory_ids: string[] };
type DraftPriceEvaluation = {
  status: 'priced' | 'blocked';
  unit_price: Money | null;
  source: 'matrix' | 'fixed' | 'catalog' | null;
  pricing_basis: Money | null;
  effective_minimum: Money | null;
  band: MatrixBand | null;
  gross_profit: Money | null; // unit price minus known actual cost, not pricing basis
  markup_percent: string | null; // realized (price-cost)/cost, unavailable at cost 0
  margin_percent: string | null; // realized (price-cost)/price, unavailable at price 0
  warnings: Array<{ code: string; message: string }>;
  errors: Array<{ code: string; message: string }>;
};
type MatrixPreviewResponse = {
  schema_version: 1;
  currency: 'USD';
  current_default: DefaultResponse;
  cases: Array<{
    sample_key: string; // supplied sample_key or inventory UUID
    inventory_id: string | null;
    label: string;
    actual_unit_cost: Money | null;
    actual_cost_known: boolean;
    catalog_unit_price: Money | null;
    current: DraftPriceEvaluation;
    proposed: DraftPriceEvaluation;
  }>;
};
```

Samples require 1–20 unique keys; inventory mode requires 1–50 unique in-scope IDs.
Supplying both sources, invalid bands, malformed money, duplicates or bounds fails
422 before resolution. An unknown/foreign inventory ID fails the whole request
with 404, without returning partial foreign metadata. Response cases retain request
order. Inventory cases use current authoritative cost/catalog/part-policy values;
sample cases use supplied hypothetical values, optional floors default to NULL,
and an omitted label displays sample_key. Inventory labels use the part name.
Neither mode accepts an internal flag or creates an attachment.

`current` evaluates the existing shop default and `proposed` evaluates the submitted
bands against the same case's fixed/floor rules. Neither evaluation alters stock,
catalog or policy. Fixed pricing skips both matrices. An unpriceable valid case
returns status=blocked, unit_price/gross_profit/markup/margin NULL and explicit
errors; other valid cases remain visible. Unknown cost never becomes zero.
Structural request errors still use 422. A known zero-cost catalog fallback is
source=catalog plus its warning. Percent outputs round HALF_UP to two decimals;
selected band markup remains separate from realized markup/margin. This endpoint
returns no pricing_preview_fingerprint and cannot be submitted as confirmation.

## Snapshot and existing-feature integration

Resolve once per genuinely new insertion, under the explicit lock order below;
load rule revision once per transaction, not per bundled item. Rule/default writers
use the same ordering to avoid a half-old/half-new service package. Preview is not
an authorization token. Stock mutation, rule snapshot, part activity and money
totals commit atomically; validation failure rolls the whole action back.

Quantity-only updates keep price, actual cost, list price and original rule
snapshot. Manual price changes append audit detail and an override overlay without
erasing original rule provenance. Changing a part's fixed/floor values or current
matrix does not edit prior lines. “List” returns to the original line's resolved
default; it does not rerun today's matrix. “Stock” remains an explicit user action
using original actual-cost snapshots. If a P1 minimum forbids stock price, reject
the whole requested bulk change with actionable affected part names; never partly
apply it or ignore the minimum. Discount capacity uses max(snapshot actual cost,
snapshot minimum sale price) for managed=true lines; legacy snapshot-null and managed=false lines retain
existing cost logic. Do not retroactively invalidate granted discounts merely by
setting a new catalog policy.

Retain existing line IDs/cost/list/charged price/provenance during counter draft,
service reapply and PM reseeding. The detailed reconciliation contract below applies
before any destructive replacement. Only genuine additions resolve current policy.
Preserve checkout gates, idempotency, unit return allocations and completed receipt
snapshots. Do not activate counter sales in any tenant.

Existing RO `unit_price` requests must mean explicit override, not stale browser
catalog suggestions. The main picker normally omits unit_price, except “stock”
mode; update it to use the preview and display “Shop matrix / Fixed / Catalog /
Manual” plus charged amount. Ad-hoc explicit pricing remains explicit. Bundled
service price preview must include the same resolved part amounts used by attach;
do not advertise the old catalog total and charge the matrix total after click.

## Resolved engineering decisions after handoff review

Architecture reviewed the backend/frontend integration handoffs and accepted
wire clarifications against the current source on 2026-10-15. Their durable
preparation copies are under
`/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/`.
This canonical contract resolves their open items and is authoritative for P1
implementation. No product decision remains open within the selected scope.

### 1. Retained service, PM and counter-line identity

`PriceBuildService.add_flat_service_line` currently calls `_restore_service_parts`
on reapply, and fleet `_apply_pm_services_to_ro` deletes/reseeds source parts. Both
would erase price history. Replace this only for **retained** components with a
plan-first reconciliation; actual service removal still releases its stock and
archives/deletes according to existing rules.

Match within exact tenant/RO/parent Labor/source service. New bundle rows set
`source_line_id`, `source_service_id` and snapshot `source_component_id`. Prefer
an exact component match if inventory identity agrees. A component ID recreated
in a template does not itself mean the physical line was removed from the job:
use the unique retained `(parent service operation, inventory_id)` fallback when
unambiguous. Historical rows without parent/component IDs can use unique
`(tenant,order,source_service_id,inventory_id)`. Duplicate candidate mappings or
duplicate inventory components that cannot be assigned uniquely return409
`bundle_identity_ambiguous` before mutation; never guess or combine paid amounts.

A retained component preserves its usage ID, actual unit_cost, default/list price,
charged unit price, immutable snapshot, revision FK, price overlay and reservation
identity. Reapplying quantity changes only quantity, reservation delta and derived
line total; it does not resolve against current policy or change its price. Resolve
new template components only. Removing a component releases only its actual
reservation; a later deliberate re-add is a genuinely new attachment. Preserve
existing checklist/execution/recommendation identity of retained parent Labor.
Do not use P1 to change retained labor-rate/recalculation behavior.
Pricing unification is not a stock-accounting rewrite: retain each established
route's reservation behavior and record the actual reserved package count on new
rows (including0 when that route made no reservation). Never infer a legacy PM
reservation from billed quantity and then create a phantom stock release. Retained
unchanged quantity does not touch stock. For a changed/removed legacy component
whose actual reservation cannot be established from existing evidence, reject
that stock-changing action for review rather than guess; do not rewrite unrelated
legacy fallback behavior or migrate historical inventory during P1.

Counter draft requests add optional `sale_line_id` for retained rows. Match exact
sale/tenant/line first and validate inventory agrees. Existing clients without it
may match the already-unique inventory ID. Unknown/foreign/stale retained IDs fail,
never fall back to insertion. Preserve all old line snapshots/IDs; quantity or buyer
change alone is not repricing. Explicit charge equal to the saved charge is a no-op,
not a manual override measured against today's catalog. Resolve only newly added
inventory IDs. Preserve unit-allocation identity; recompute allocations only when
a deliberate quantity/price change changes totals. C1 buyer pricing remains deferred.

Plan all additions/retentions/removals and validate all amounts, stock actions and
version guards first. Existing service helpers that commit (`recalculate_order`)
need a transaction-owned no-commit seam. One bundle command commits once: part
snapshots, stock/core changes, scope, audits, totals and request receipt. A late
failure cannot leave an earlier component or parent operation committed.

### 2. Exact contextual preview and confirmation

`POST /api/v1/parts-pricing/resolve` accepts:

```ts
type ResolveRequest = {
  context: RepairOrderContext | FleetDraftContext | CounterSaleContext;
  plan: PartsAddPlan | ServiceApplyPlan | PmReplacePlan | FleetCreatePlan | CounterDraftPlan;
  pricing_presentation?: 'shop' | 'fleet';
  include_management_details?: boolean; // default false; preview only
};
```

Context/plan bodies are specified below. Presentation metadata is outside the plan.
Extra fields remain forbidden. Money/quantity values remain decimal strings.

Effective presentation is server-derived from the authenticated user and requested
presentation; it is not a permission grant or inferred merely from `is_internal`:

- Fleet manager defaults to `fleet` and is forced to `fleet`, even when requesting
  `shop`. Existing fleet/vehicle/order scope must independently pass. A forged
  `shop` value never returns shop money or management data.
- An authorized shop owner/admin/receptionist/mechanic defaults to `shop`; an
  explicit `fleet` request is a downward projection. Thus an owner viewing the same
  RO in the fleet panel can receive the fleet projection without creating a new
  authorization surface. Existing assignment/sale roles still govern access.
- `include_management_details=true` requires owner/admin. A nonmanager gets 403;
  the flag never upgrades their response. Combining true with effective `fleet`
  returns 422 `management_details_not_available_in_fleet`. A fleet panel sends
  false/omits it. Counter-sale context permits shop presentation only; requesting
  fleet there returns 422 `presentation_not_supported`.
- Customer, public, driver and unauthorized contexts remain forbidden. No caller
  supplied tenant/user/role or internal flag is accepted.

Mutation adapters accept optional `pricing_presentation` with the same downward
rules, alongside `pricing_preview_fingerprint`; they do not accept the management
flag. Use effective presentation for new P1 summaries and error previews. Existing
outer mutation response contracts are not gratuitously renamed: attach the P1
summary through explicit audience-aware schemas. In authenticated shop PartsUsage
and counter draft-line responses, the new field is `pricing: SafePrice`; legacy
rows derive `legacy_unknown` without inventing a snapshot. Fleet and customer/public
serializers omit this field. No raw pricing snapshot is spread into a generic
PartsUsage response. The fingerprint belongs to the preview/confirmation envelope,
not each saved line; existing outer response shapes otherwise remain compatible.

Maximum 100 resulting parts per command, 100 unique inventory IDs and 30 services;
reject excess before queries. If an existing route has a stricter bound, keep it.
Do not split a bundle into separate commits to evade a limit.

Context discriminators:

- `{kind:"repair_order", repair_order_id}` for existing shop/fleet RO work;
- `{kind:"fleet_draft", vehicle_id, bill_to_customer_id:null|UUID}` for staged
  new fleet work. Server resolves exact vehicle relationship/bill-to access and
  internal/external status; no caller-controlled `is_internal` authority;
- `{kind:"counter_sale", sale_id:null|UUID, customer_id:null|UUID,
  expected_sale_version:null|integer}`. Existing sale must be editable and in scope.

Plan discriminators:

- `parts_add`: `lines:[{client_key,inventory_id,quantity,source_line_id?,
  source_service_id?,pricing_intent:"default"|"manual"|"stock",
  unit_price?,price_override_reason?}]` (standalone or existing-operation parts).
- `service_apply`: `service_id,quantity` for the exact canonical service-apply path.
- `pm_replace`: ordered `service_ids` for existing PM selection/reseeding.
- `fleet_create`: ordered `service_ids`, staged `part_lines` as above, and the
  existing staged labor inputs when present. Their unchanged canonical labor math
  is included in the quoted overall work total; this does not add labor policy.
- `counter_draft`: full `lines:[{sale_line_id?,inventory_id,quantity,
  pricing_intent,charged_unit_price?,price_override_reason?}]` so retained rows
  can be distinguished from genuine additions. Retained values default to saved.

Use the existing endpoint request schema as the normalized inner input to these
plans; one canonical planner runs for preview and mutation. Part-add, service-apply,
PM-replace, fleet-create and counter-create/replace adapters add the fingerprint
and optional presentation metadata defined above. Exact expected sale version
remains mandatory
on sale edits. The deprecated callable fleet staging/service endpoints use these
same semantics; a hidden UI is not a safe pricing bypass.

The exact shop/fleet response schemas, private management projection and error
envelopes appear in “Exact privacy projections” below. Use those schemas for
preview and mutation conflicts; generic snapshots are never response objects.

At mutation, reauthorize and reconstruct the plan under locks, compare keyed
fingerprint and all expected versions. Managed catalog additions, explicit new
catalog-line manual/stock intent, or an existing submitted fingerprint require
matching confirmation. Genuine ad-hoc creation without an existing inventory/SKU
identity uses the explicit entered-price exception below. Missing fingerprint
when confirmation is required returns 409
`pricing_preview_required`; mismatch returns409 `pricing_preview_changed` with a
fresh safe projection. Never interpret a stale catalog-supplied amount as manual
consent. Unmanaged/default legacy adds with no fingerprint remain compatible;
all new catalog UI uses preview. If policy activates between an old client's request and
commit, the now-managed action fails for missing confirmation instead of charging
an unconfirmed amount. Internal default adds stay compatible; supplied differing
internal prices reject with `internal_price_fixed` rather than being ignored.

An unchanged retained-line quantity update needs its existing version/stock guard,
not fresh catalog pricing. No original snapshot is resolved during confirmation.
A manual new catalog-line amount requires explicit `pricing_intent:"manual"` plus
reason;
a bare `unit_price` equal to server default is compatible, while a differing bare
amount returns `price_intent_required` (mechanic receives403). This closes old
browser “catalog suggestion” ambiguity without a silent price change.

Existing service shortage behavior can omit a bundled component with a warning.
Preview must disclose that exact included/omitted scope and matching total. At
commit, changed availability that changes the included plan returns409
`bundle_availability_changed` with a new explicit scope preview, not a fake pricing
conflict or surprise partial bundle. Ordinary insufficient stock keeps the existing
stock guard/explicit shortage override. Neither stock case silently reprices a line.
Do not change fractional stock unit semantics or revive unrelated P6 work.

Generic service catalog prices remain labeled catalog estimates. Context preview
uses the **actual existing attach math** (hours × applicable rate), not service
serializer `base_price` behavior when those differ. Fixing that separate labor
semantics discrepancy is outside P1; do not alter labor charges merely to make an
old catalog total match. An exact contextual preview replaces the estimate before
final Apply and must match the resulting canonical total.

#### Existing create-then-attach UI adapters

The shop new-order wizard in `RepairOrdersPage.tsx` currently creates the order
before sequentially applying selected flat services. Preserve that created order
identity before starting pricing previews. Once creation succeeds, retain its ID
and presentation plus each selected service's pending/applied/failed state; a price
409, cancelled confirmation or attach error must never rerun order creation.

Preview each pending service against that exact existing RO with service_apply,
show its confirmed whole-order result, then attach using the matching fingerprint
and one stable logical-action idempotency key. Keep already applied operations and
per-service warnings. Retry only the failed/pending service with the existing RO;
if attachment outcome is uncertain, replay the same attachment key before treating
it as a new action. A deliberate changed price/plan after a confirmed conflict uses
a new action key. Do not blindly reapply completed services or discard entered work.

Cancelling remaining service confirmation opens/returns to the already-created
order and clearly says which services were not added. It does not delete that
order, undo successful components or call creation again. The final success/error
message distinguishes order creation from service application; preserve existing
customer/search/return navigation. This is recovery of the existing two-step flow,
not a new draft-order, booking or all-services atomic-creation feature.

Fleet creation and PM staging in `FleetModals.tsx` use the existing fleet_draft /
fleet_create or existing-order / pm_replace plan as applicable. They preview the
whole staged work before their single create/reseed command, carry its fingerprint
and reuse that command's idempotency key on uncertain retries. Changed total/scope
requires explicit confirmation with the original modal selections preserved. The
server's atomic command and receipt retain the resulting order ID, so retry cannot
create a second order. Existing schedule/vehicle payload and lifecycle semantics
remain unchanged; P1 does not introduce booking policy.

#### Read saved pricing and bulk concurrency token

Persisted authenticated-shop PartsUsage and counter draft-line JSON both use the
exact property `pricing: SafePrice`. Do not call it pricing_summary/provenance or
return raw pricing_snapshot. Legacy rows use origin_source=legacy_unknown and
known saved prices; their pricing_version is the current usage version (or NULL
for counter lines). `can_override` is false when actor/lifecycle forbids mutation.
Public/fleet/receipt serializers omit pricing as specified above.

Existing shop `GET /repair-orders/{id}/price-build` and every mutation returning
PriceBuildSummaryResponse add `parts_pricing_fingerprint: string | null` at the
top level. It is the server-computed opaque bulk CAS token for all active parts,
including the empty set; use NULL for a read-only/noneditable order. This is not
pricing_preview_fingerprint. `ShopPreview` also returns the same token for an
existing editable RO and NULL for fleet_draft/counter contexts. Fleet/public
projections omit it. The frontend reads the price-build summary it already loads,
then sends the token as `expected_parts_fingerprint` for a bulk pricing-mode change
(or discounts command that requests a parts-pricing-mode change). A missing token
is 409 `parts_pricing_fingerprint_required`; changed saved line set/version/amount
is 409 `parts_pricing_conflict`. Refetch price-build while preserving user intent;
never silently retry. Ordinary discount-only edits keep their existing contract.
Bulk responses contain the new token; existing single-line response shapes do not
need an extra envelope just to carry it, and the UI refreshes the summary after them.

For a retained RO line's owner/admin management popover, use the existing resolve
endpoint with the following read-only inspection request; no new endpoint or plan
kind is introduced:

```json
{
  "context": { "kind": "repair_order", "repair_order_id": "<existing-order-id>" },
  "plan": { "kind": "parts_add", "lines": [] },
  "pricing_presentation": "shop",
  "include_management_details": true
}
```

`parts_add.lines=[]` is supported by `/resolve` for an existing repair_order only.
Return the current saved active part rows as retained lines, whole-order saved
canonical totals, confirmation_required=false and requested ManagementDetails.
The popover selects the row by parts_usage_id and uses the matching line_key in
management.lines. No snapshot is created, no current parts policy/WAC is resolved,
no stock is moved and no lifecycle transition occurs. default_generation is NULL.
Read-authorized locked/completed orders may use this inspection; can_override is
false and the bulk token NULL. Deleted orders keep their existing unavailable-panel
behavior. Never use this read-only exception to bypass mutation lifecycle checks.
Empty parts_add on fleet_draft or a mutating add route is 422 `empty_parts_plan`.

Counter draft management uses `/resolve` with context counter_sale and counter_draft
containing its current saved active lines (sale_line_id, inventory_id, quantity and
pricing_intent=default), plus the current expected_sale_version and explicit
include_management_details=true. Default intent on a retained counter row means
keep its saved current charge, not reset to list or today's catalog. This unchanged
retained-only inspection requires no new policy resolution and returns false
confirmation_required. No writes occur; real draft mutations still require CAS.
No new completed-receipt management endpoint or counter checkout change is added.

#### Fingerprint dependencies for retained versus new lines

The fingerprint is an opaque keyed digest, not a decodable JWT or plain hash that
reveals low-entropy cost inputs. Current part cost/catalog/policy values apply only
to genuinely added catalog components, never all rows in a retained bundle. Bind
money-semantic inputs, not unrelated names/notes or global inventory updated_at.

Always bind authenticated tenant/actor, authorized context/internal/bill-to state,
normalized plan/quantities, effective pricing_presentation, stable component keys,
source composition relevant to the plan, lifecycle/material edit guards, and the
expected existing RO-line or sale versions. Management visibility is excluded from
the money fingerprint; it is reauthorized separately and cannot be decoded from it.

For genuinely new catalog lines, additionally bind current relevant inventory
pricing values/versions, chosen matrix revision and default generation (including
ABA). Load one coherent policy for those additions in the transaction. For removed
or retained lines, bind only saved IDs/quantity intentions, immutable snapshot
identity/applied revision, original cost/default/current charge, overlay and line
version (or sale CAS). Do **not** resolve their current catalog/WAC/floor/matrix,
or bind unrelated current default generation merely because the snapshot once
used that matrix. Current inventory is still read for actual stock validation;
that does not replace saved financial inputs.

A retained-only service/PM reapply or counter draft edit therefore has no live
parts-policy dependency. A new catalog price/WAC/floor/default cannot invalidate
its existing price confirmation. Source composition changes, explicit quantity,
current saved charge/version, lifecycle state and actual availability can still
conflict. Existing canonical labor math may re-evaluate labor during service
reapply; bind those genuine labor inputs exactly as the existing attachment path
does. This clarification does not freeze or change labor semantics under P1.

For mixed bundles, current policy inputs apply only to new components; retained
components retain saved inputs. A live policy change can require confirming the
new lines, but never silently reprices the retained lines. No new additions means
no live parts policy resolution. Confirmed parts identity removal/re-add remains a
new attachment under the existing contract, not a way to rewrite retained history.

Stock-only version changes are excluded from price fingerprints. If availability
changes included/omitted scope, return the existing `bundle_availability_changed`
response with explicit updated scope; otherwise the normal stock/quantity guard
applies. Unknown legacy reservation evidence never creates a phantom release.

Required tests: retained-only preview→change matrix/default/WAC→attach uses the same
saved prices without spurious price conflict; mixed plan conflicts only for a new
line policy change; changed retained line version still 409; composition/availability
changes remain visible; cost snapshots and counter-sale IDs stay unchanged.

#### Ad-hoc creation before an inventory identity exists

Current `add_ad_hoc_part_to_repair_order` creates a placeholder then delegates to
ordinary part-add; a genuine new item has no inventory_id to send to `/resolve`.
This genuinely new-item workflow is the explicit exception to catalog preview
confirmation; it still validates and records the entered price atomically.

- A new ad-hoc request whose normalized SKU matches **no existing tenant inventory
  row**, or supplies no SKU, remains an explicit entered-price workflow. It does
  not require a catalog pricing_preview_fingerprint and does not add a new resolve
  plan. Validate supplied name, quantity, price, optional cost and all existing
  role/lifecycle/source references before creating a placeholder. Preserve missing
  cost as unknown in the usage snapshot (unit_cost NULL, known-cost=false), not an
  invented known zero because Inventory's placeholder storage needs 0.
- This explicit initial ad-hoc price is not a catalog override: record actor and
  `ad_hoc_price_entered` evidence, without inventing a manager-only configuration
  permission or demanding an override reason for establishing a new part's price.
  Preserve existing authorized ad-hoc additive roles, including assigned mechanics.
  Subsequent price changes follow the normal existing-line edit roles/CAS rules.
- Internal work still requires a supplied known actual cost and charges that cost;
  reject missing cost or differing price (`ad_hoc_cost_required` /
  `internal_price_fixed`). No matrix/fixed/minimum policy is inferred for a genuinely
  new placeholder. Existing actual-cost/manual validation remains authoritative.
- Acquire tenant/context locks and idempotency protection before placeholder
  insertion. Placeholder, usage, cost-known provenance, stock exception, audit and
  totals commit once. A rejected line leaves no orphan placeholder. Replay of the
  same logical request returns the same created result, not another ADHOC SKU.

If SKU lookup finds existing inventory, it is **not** the no-existing-SKU exception.
Before any new placeholder or line write, return 409
`catalog_match_requires_preview` with safe matched inventory identity and message.
The UI retains the draft, loads ordinary parts_add preview for that exact inventory
and context, and requires confirmation. It then submits the ordinary catalog part
route; supplied differing price needs authorized manual intent/reason, and a
mechanic must accept the server default. Existing placeholder exclusions and
unknown-cost rules still apply in that resolver; matching a placeholder is not
permission to matrix-price unknown zero cost or invent known expense.

For an internal matched catalog item, preview shows the permitted whole-work total
and normal internal-cost default; the user's draft amount is never silently ignored.
Handle concurrent same-SKU creation as the same safe conflict after rollback and
reload, not an unexplained unique-index 500. Revalidate tenant/SKU identity under
locks. Foreign/deleted records do not supply a price or leak identity.

This exception applies only to genuinely new ad-hoc creation; ordinary managed
catalog additions retain mandatory confirmation. No additional inventory creation
surface, automatic promotion, historical backfill or C1 policy is introduced.

### 3. Default generation, locks and inventory coordination

All P1 writes: active tenant/role authorization, then tenant financial lock, then
idempotency serialization/replay, order or sale lock when present, pricing policy
and matrix metadata locks, and sorted inventory row locks. If an operation needs
service/template locks, take them before inventory consistently in both preview
mutation planning and template editing. Re-read/refresh records after waiting on
locks (`populate_existing` or explicit refresh); eager-loaded Inventory objects
from before locking are not authoritative. Policy writers acquire tenant lock
first even if they need only a matrix or part. Do not lock inventory and later
request the tenant lock as staged fleet creation currently can.

Read previews do not hold locks across user think time. Mutation revalidates
service composition under a consistent transaction; source service edit paths
must acquire the same parent service lock before changing components, so a raced
composition cannot escape fingerprint checking. Do not introduce a preview token
as a substitute for the role/lifecycle guard.

PO receipt already locks PO/lines then sorted inventory and never needs the
pricing tenant lock. Retain that path; it can update WAC and inventory pricing
version under its existing inventory lock. Never add a late tenant/policy lock to
it. P1 attachment holds tenant then waits on inventory; the receipt must finish
without requesting tenant/order/policy locks. Include this wait-order case in real
PostgreSQL tests. Stock-only movement with unchanged WAC does not increment pricing
version; actual WAC changes do. Catalog/policy writes use tenant then inventory and
require pricing-version CAS. An old generic inventory form cannot overwrite a
new fixed price or floor using its stale selling-price field.

Default generation solves default A→B→A and NULL→A→NULL, even when eventual price
is identical. Matrix rule/name updates also have immutable revision and metadata
CAS. Preview detects those relevant revisions; a rename that changes only the
human display still remains auditable by revision, not mutable snapshot text.
Archive never invalidates existing line identity, and cannot be active default.

### 4. Explicit price edits, CAS and audit

RO part PATCH adds `expected_pricing_version`, `price_action:"manual"|"list"|"stock"`
and `price_override_reason` (trimmed3–500 characters for manual). A changed price
without explicit action/version is409 `price_intent_required` or
`pricing_version_required`; unchanged supplied price is no-op. Quantity-only
changes preserve money/provenance and increment line version when state changes.
New UI sends version for all updates; legacy quantity-only clients retain current
behavior. A combined quantity/price edit validates both before any stock write.
Stale version409 preserves the user's draft; no retry that overwrites a later edit.

Manual price action retains existing PRICE_BUILD_EDIT_ROLES and order/fleet scope.
Mechanics cannot override. Counter overrides retain manager-only authorization and
existing3–500-character reason. Internal new pricing cannot be marked up; existing
legacy money is not silently corrected by read/quantity/reapply. For an internal
explicit reset use its original known cost, not current inventory cost.

List/Stock are explicit named actions: server records standard reasons
`restore_original_default` / `use_original_cost` and any optional operator note.
Do not demand repetitive typed explanations for these unambiguous preset actions.
Manual input always needs a human reason. List restores original snapshot/list
price; Stock original unit_cost. Validate original managed minimum and all existing
floor/discount constraints. Unknown original cost follows existing legacy guards;
never fabricate it from matrix rules.

Bulk mode requests add `expected_parts_fingerprint` of ordered active line IDs,
versions and saved prices plus explicit `mode` and optional note. Prevalidate all
lines and existing discounts, then apply every change atomically and append one
command audit with per-line before/after records. Reordering unchanged display
rows does not affect the canonical sorted fingerprint. Bulk rejection names safe
part identities but does not expose hidden actual-cost-derived thresholds.

Counter drafts continue to require `expected_version` on the whole sale. Retained
line manual edits require explicit action/reason; sale CAS protects them, so an
extra redundant line version is unnecessary. The authoritative default, origin
snapshot, applied revision ID and first charged price remain immutable. Each price
event records actor, intent/reason, old/new charge and price/sale version. Current
`Manual` source is an overlay. List reset clears the overlay with an event, not by
erasing the prior override or rewriting its original snapshot.

Enforce Numeric limits on both unit result and quantity × price **before mutation**.
Keep HALF_UP for resolved unit prices and canonical existing line/order rounding.
Counter-sale charged price remains strictly positive; RO zero-price rules remain
as currently authorized. Aggregate discount capacity uses summed effective floors;
P1 does not add a new per-line allocation of order discounts.

### 5. External fleet bundled prices and actual expense

Resolve from `ro.is_internal`, not entry route, `is_pm`, a fleet role or service
category. `_apply_pm_services_to_ro`, deprecated `add_service_to_work_order`, staged
`new_work_order` and regular PriceBuild all call the same resolver/planner.
New external fleet catalog parts—including PM/non-PM service bundles—use the shop
policy. New internal parts use actual inventory cost. **Every new PartsUsage stores
actual `unit_cost` explicitly in either case.** A price matrix basis/floor never
becomes that expense. Preserve existing fleet labor-rate preference separately.
Existing rows with NULL cost are left unknown; reapply is not a historical-cost
backfill. Retained line snapshots/charges survive policy changes on both routes.

### 6. Exact privacy projections

No new permission system in P1. New management APIs and full draft/line pricing
details are limited to tenant GARAGE_OWNER/GARAGE_ADMIN, matching current catalog
write authority. Matrix rule readers are not generalized to every RO editor.
The server derives the effective presentation as specified above; an owner can
request the fleet projection, but a fleet manager cannot request shop visibility.

Ordinary shop workflow exposes only the SafePrice fields below. No rule body,
actual cost, cost-derived minimum, matrix ID/name, markup/margin or private actor/
note is added to that projection. Fleet keeps only whole-work money, identities,
quantities and availability, without new per-line prices/rates/override controls.
Customer/public/portal and invoice/quote/receipt documents keep existing
customer-facing charges; new provenance is entirely absent. The shared
`_build_parts_usage_response` must take an explicit audience or use separate
schemas. Audit existing unit_cost emission there and suppress it for customer/
public audiences as part of this boundary; do not widen inventory authorization.

Private detail or thresholds must not leak through 409/422 bodies, logs, generic
history notes, websockets or idempotent replay. Restricted price-floor failures
use `price_below_minimum` plus an actionable safe message; only owner/admin may
receive a numeric threshold. Existing inventory read rights are preserved, but
are not a grant to new matrix data. Clear tenant/role-sensitive frontend caches
on identity changes; query keys include context/plan and authenticated scope.

#### Exact response fields

```ts
type Money = string; // finite decimal, exactly two fractional digits
// Source snapshots use decimal strings at their validated source precision;
// user-facing response money above uses cents.
type Quantity = string;
type OriginSource = 'matrix' | 'fixed' | 'catalog' | 'ad_hoc' | 'internal' | 'legacy_unknown';
type CurrentSource = OriginSource | 'manual';
type PriceDisposition = 'added' | 'retained' | 'removed' | 'omitted';
type SafeWarning = {
  code: string;
  message: string; // audience-safe; no cost/rule/threshold in restricted messages
  line_key: string | null;
  inventory_id: string | null;
};
type LineIdentity = {
  line_key: string; // request client_key, stable component key, or usage/sale-line key
  inventory_id: string;
  parts_usage_id: string | null;
  sale_line_id: string | null;
  source_service_id: string | null;
  source_line_id: string | null;
  source_component_id: string | null;
  disposition: PriceDisposition;
  name: string;
  unit_type: string;
  quantity: Quantity; // planned quantity; removed line uses its saved quantity
};
type LineAvailability = {
  state: 'available' | 'shortage' | 'not_stocked' | 'unknown';
  requested_packages: number | null;
  available_packages: number | null;
  reserved_packages: number | null;
  included: boolean;
};
type SafePrice = {
  origin_source: OriginSource;
  current_source: CurrentSource;
  managed: boolean;
  default_unit_price: Money | null;
  charged_unit_price: Money | null;
  line_total: Money | null; // quantity × charged price before order discount/tax
  pricing_version: number | null; // existing RO usage version; null for new/sale rows
  can_override: boolean; // exact actor, context and lifecycle, not merely editable RO
};
type ShopPreviewLine = LineIdentity & {
  availability: LineAvailability;
  pricing: SafePrice;
};
type FleetPreviewLine = LineIdentity & {
  availability: LineAvailability;
};
type PreviewAvailability = {
  state: 'ready' | 'requires_stock_acknowledgement' | 'partial_bundle';
  omitted_line_keys: string[];
};
type ShopRepairTotals = {
  kind: 'repair_order';
  parts_subtotal: Money;
  labor_subtotal: Money;
  labor_discount_amount: Money;
  order_discount_amount: Money;
  repair_total: Money; // canonical resulting repair charge; excludes checkout fees/tax
};
type FleetRepairTotals = {
  kind: 'repair_order';
  repair_total: Money;
};
type CounterTotals = {
  kind: 'counter_sale';
  list_subtotal: Money;
  charged_subtotal: Money;
  discount_total: Money;
  tax_total: Money;
  total: Money;
};
type PreviewBase = {
  schema_version: 1;
  plan_kind: 'parts_add' | 'service_apply' | 'pm_replace' | 'fleet_create' | 'counter_draft';
  pricing_preview_fingerprint: string;
  confirmation_required: boolean;
  currency: 'USD';
  expected_sale_version: number | null;
  availability: PreviewAvailability;
  warnings: SafeWarning[];
};
type ShopPreview = PreviewBase & {
  projection: 'shop';
  parts_pricing_fingerprint: string | null; // existing editable RO bulk CAS only
  lines: ShopPreviewLine[];
  totals: ShopRepairTotals | CounterTotals;
  management: ManagementDetails | null;
};
type FleetPreview = PreviewBase & {
  projection: 'fleet';
  lines: FleetPreviewLine[];
  totals: FleetRepairTotals;
  // management, parts_pricing_fingerprint, pricing and component money are absent
};
```

Totals describe the **resulting whole order/draft sale**, not merely added parts.
For a new fleet draft they describe the complete staged work. Call the canonical
existing total calculators, including already granted discounts and canonical
counter-sale tax. Shop line_total is a unit-price illustration, not an allocation
of aggregate discounts/tax; omit per-unit return/tax allocations from previews.
A removed/omitted line may show its saved/resolved illustrative price in shop view,
but `included=false` and it does not contribute to resulting totals. Fleet never
receives the `pricing` object or parts/labor subtotals. Names/quantities/availability
remain safe scope information. Do not use omission as zero-priced fulfillment.

Legacy snapshot-null origin is `legacy_unknown`; its saved list/default amount may
still be shown when known. A known zero-cost fallback maps to workflow source
`catalog` plus an audience-safe warning, while its detailed reason stays internal.
For counter lines, existing sale version is the CAS authority; do not invent an
independent price version. New lines have no persisted usage/sale IDs until attach.
Use stable logical line_key for preview matching; do not require allocating rows.

`ManagementDetails` is an explicit private object, not a full snapshot:

```ts
type ManagementDetails = {
  default_generation: number | null; // current policy only if new catalog lines resolve
  lines: Array<{
    line_key: string;
    snapshot_id: string | null;
    actual_unit_cost: Money | null;
    actual_cost_known: boolean;
    pricing_cost_floor: Money | null;
    pricing_basis: Money | null;
    minimum_sale_price: Money | null;
    effective_minimum: Money | null;
    fixed_catalog_price: boolean;
    catalog_unit_price: Money | null;
    matrix: {
      id: string;
      revision_id: string;
      revision: number;
      name: string;
      band: { min_cost: Money; max_cost: Money | null; markup_percent: string };
    } | null;
    override: { reason: string; actor_id: string; occurred_at: string } | null;
  }>;
};
```

Only a requested owner/admin shop preview sets management non-NULL. Safe regular
workflow rows never include its data, even when the current owner could open the
separate price-detail editor. Existing inventory-read rights do not confer this
new management projection. Management timestamps are server UTC ISO8601 strings.
For retained-only plans, default_generation is NULL; per-line management values come
from saved evidence. Do not load current policy just to fill this optional display.

Errors keep FastAPI's existing detail envelope:

```ts
type PreviewConflict = {
  detail: {
    code: 'pricing_preview_required' | 'pricing_preview_changed' | 'bundle_availability_changed';
    message: string;
    preview: ShopPreview | FleetPreview;
  };
};
```

Mutation conflict previews always have management=null in shop view, or management
absent in fleet view. Preserve entered draft/quantities; accepting refresh is an
explicit user action, never silent retry. Other errors use `{detail:{code,message}}`
with safe line/inventory identities only where already authorized. A retained row
CAS conflict is `pricing_version_conflict`; the UI refetches its saved summary while
preserving the typed edit rather than accepting an unrelated live catalog quote.

#### Shared response fixture

Existing external RO has one retained part: quantity 2, original default 40, current
manual price 35, line version 4. Current inventory selling price 999 is irrelevant to
that retained charge. Adding a genuinely new part quantity 1 resolves to 30 from
current policy. No labor, discounts or tax: resulting parts/repair total 100.

Shop preview returns retained line pricing default 40.00/charged 35.00/total 70.00,
source origin=matrix/current=manual/version 4, and new line default/charged 30.00,
total 30.00/version NULL. Both stable keys appear; management=NULL by default.
Fleet preview of the same order returns the same identities/quantities and only
repair_total 100.00, with no pricing/management objects. Owner explicitly requesting
management in shop view receives the private per-line details. Mechanic requesting
management receives 403. Fleet manager requesting shop still receives fleet.

### 7. Contract closure and mandatory regression additions

Backend/frontend handoff omissions, wire/projection questions, retained-only
fingerprint semantics and physical-removal audit compatibility are resolved above.
Preserve the handoffs as source/integration maps; when wording differs, this
canonical contract is authoritative. No production policy activation, guessed
markup, account terms or premature C1 behavior is authorized.

Add acceptance for service/PM retain/remove/re-add identity, ambiguous legacy
mapping, NULL-cost historical preservation, minimum-with-no-matrix, cost-floor-only
no-effect, fixed-with-no-matrix, snapshot-managed=false, default ABA, preview missing/
changed/bundle composition, stale generic inventory write, internal price tamper,
external fleet PM unit_cost, lifecycle/tenant-negative snapshots, raw response
privacy, role change before idempotency replay, quantity/manual/bulk CAS and late
bundle rollback. Test matrix configuration/audits with parts-operations disabled.
Test PO WAC versus attach and competing template changes on actual PostgreSQL.
Also test downward presentation selection and private management rejection,
new ad-hoc no-SKU creation and existing-SKU/raced-SKU confirmation, retained-only
policy/WAC changes without false conflicts, mixed-bundle genuine-new-line
conflicts, and physical usage removal with intact append-only audit evidence.
These tests must assert the exact response schemas and atomic behavior above.
Also assert configuration envelopes/version names and idempotent replay, sample
preview unknown/zero-cost cases, retained read-only management lookup, and bulk CAS
token return/refresh/missing/stale behavior without widening any role or mutation
lifecycle boundary. New-order wizard tests must assert that pricing cancellation,
409/error and retry retain one created RO and never reapply successful services;
fleet staged retry must retain one command/order identity. No tests were executed during this contract-only refinement;
passing results must be produced during implementation and independent acceptance.


## C1 extension seam

Shared resolver takes a resolved pricing-policy object and inventory values;
policy selection is a separate helper. P1 selection is shop default. C1 can add
customer matrix assignment and snapshot its matrix revision/labor rate on a new
order, then pass that explicit revision ahead of shop default without rewriting
math or attaching live customer references to historical money. Customer/account
changes never update existing line snapshots. C1 needs a separate explicit policy
for new lines on an already-open order; do not silently decide that in P1.

No service-category override, per-category matrix, quantity discount, promotion,
margin mode, price ending/rounding rule, multi-currency or bulk catalog reprice in
P1. They are not necessary to close this selected outcome.

## Fixtures and required tests

Rules above: actual20/floorNULL =>40; actual25=>37.50; actual100=>130.
Actual50/floor75 =>112.50 while actual cost snapshot stays50. Actual20/minimum50
=>50. Fixed catalog45 with actual20 ignores matrix and floor; minimum50 makes that
fixed default invalid and requires correction, not silent reprice. New manual35
with actual20/minimum30 succeeds (reason recorded),29.99 fails. Internal actual20
is20 regardless of all those catalog flags. Actual0/floor10=>20; actual0/no floors
with catalog12 falls back12 with warning. Ad-hoc missing cost never feeds matrix.

Boundary tests: every band edge, fractional amounts/quantities, 0%, high markup,
half-cent rounding, output overflow, malformed/nonfinite/negative values, gaps,
overlaps, missing final band, >30bands, unknown fields, no matrix and archive.
Cross-layer tests: direct part, bundle, external fleet and counter paths agree;
internal remains cost; quantities/list restore never reprice; explicit stock/
discount guard is atomic; quote snapshot/invoice/receipt unchanged after revision,
archive, catalog/WAC change and read/reload. New line uses new default; old line
does not. Validate retained counter-draft lines after revision/default changes.

Tenant/role negatives: foreign matrix, part, RO, customer context and preview;
mechanic tamper; receptionist rule writes; fleet boundary; archived default;
customer must not see cost/provenance. PostgreSQL races: same matrix edit, default
switch, archive vs resolution, receipt WAC update vs attachment, two attachments,
and optimistic preview mismatch. Verify actual transaction rollback/no stock
effect after price failure, not just isolated resolver values.

Runtime after the current branch local-runtime preflight: create a draft matrix,
preview,
activate only in synthetic permitted test scope, attach standalone/bundled part,
edit quantity/price, revise matrix, show old line stable/new line updated, fixed/
floors/clear/archive behavior, save/reload/conflict; read-only historical quote
comparison. Light/Night desktop1280+,320/390portrait,740×400landscape. One workspace
scroll, compact rows, 44px touch targets, keyboard/Escape/focus, error retains draft.
Never issue real quotes, complete real counter sales or change real default rates
for QA without authority. Use synthetic fixtures and restore test configuration.

High-risk financial/migration lane: approved contract, independent QA/Security,
real migration/concurrency tests, protected CI, schema/release identity and
production changed-journey evidence before DB132/P1 is Done. The final ownership
split below applies; the mandatory local-runtime preflight precedes application
implementation and local browser QA.

## Final role and file ownership

Backend & Integrations is the single accountable DB132 implementation owner and
owns all backend integrations together. Do not split competing constructor fixes
among multiple backend writers or release config before all paths are covered.

Backend files (exclusive ownership; paths repository-relative):

- New `backend/app/db/models/parts_pricing.py`,
  `backend/app/schemas/parts_pricing.py`,
  `backend/app/services/parts_price_resolver.py`,
  `backend/app/services/parts_pricing_policy.py`,
  `backend/app/api/v1/endpoints/parts_pricing.py`.
- `backend/app/db/models/__init__.py`, `inventory.py`, `inventory_lifecycle.py`
  (paths under models for the latter two); next additive Alembic revision chosen
  only after actual migration head is refreshed.
- `backend/app/api/v1/router.py`; endpoints `inventory.py`, `repair_orders.py`,
  `fleet.py`, `inventory_lifecycle.py`, `services.py`, `parts_operations.py`;
  `backend/app/schemas/repair_order.py`.
- Services `price_build_service.py`, `counter_sale_service.py`, `discount_limits.py`,
  `parts_operations_service.py`, plus the narrow affected existing response schema
  projection. Quotes/invoices/receipts are regression targets; no live resolver is
  added to their finalization/history paths.
- New focused tests for rules/routes/writers/PostgreSQL races plus existing price
  build, ad-hoc, discount, inventory lifecycle, fleet, quote/invoice snapshot suites.

Verified application insertion coverage: PartsUsage in repair_orders ordinary add
(ad-hoc delegates here); PriceBuildService service attach; three fleet constructors
(PM reseed, deprecated service attach, staged direct parts); CounterSaleLine draft
constructor. There are no other `PartsUsage(`/`CounterSaleLine(` application writer
sites in the reviewed source. Import scripts are intentionally not repriced.
Retained service/PM/counter reconciliation and legacy ambiguity rejection remain
defined above; no caller may bypass those retained-identity rules.

Frontend & UX exclusively owns:

- New `frontend/src/features/parts-pricing/` schemas/types, query keys, resolution
  hook, matrix/part-policy editors and source presentation; no duplicate price math.
- `frontend/src/features/inventory/InventoryPage.tsx`,
  `PartsInventoryWorkspace.tsx`, `CounterSalesWorkspace.tsx`,
  `inventoryLifecycleTypes.ts` (the latter three in the same inventory directory).
- `frontend/src/features/repair-orders/PriceBuilderPanel.tsx` and
  `frontend/src/features/repair-orders/RepairOrdersPage.tsx` (new-order wizard);
  `frontend/src/features/fleet/priceBuild.ts`, `FleetPriceBuilderPanel.tsx` and
  `FleetModals.tsx` (the latter two under the same fleet directory);
  `frontend/src/types/index.ts`; affected focused tests and scoped feature styles.
- Reuse both existing inventory Settings entry points. A settings link is optional
  and must open the same editor, not a separate configuration surface. Preserve
  DB137 compact-toolbar files unless a demonstrable integration conflict requires
  parent coordination. Fleet panel explicitly requests fleet presentation.

Architecture owns schema/fixture consistency and contract amendments; return any
unresolved cross-layer incompatibility here rather than silently picking different
fields on each side. Product owns board/tracker, scope and sequencing. Fresh
independent Security/QA reviewers own authorization, privacy, race and changed-UI
acceptance gates; implementers or agents directing implementation do not self-sign
those gates. Release owns protected CI/merge/deploy evidence after authorization.

## Exact source map (current integration checkout)

* `backend/app/db/models/inventory.py`: Inventory cost/selling price and
  PartsUsage unit_cost/unit_price/list_price snapshots; no matrix/fixed/floor.
* `backend/app/api/v1/endpoints/inventory.py`: inventory schemas, admin-only
  catalog writes and `_append_catalog_changes`; existing selling price editor.
* `backend/app/services/parts_operations_service.py`: `apply_inventory_movement`
  and `receipt_wac`; WAC changes cost, not catalog selling price.
* `backend/app/api/v1/endpoints/repair_orders.py`: `add_parts_to_repair_order`,
  `add_ad_hoc_part_to_repair_order`, `update_parts_quantity`,
  `_apply_parts_mode`, `_load_pricing_order_for_update`, `_build_parts_usage_response`.
* `backend/app/services/price_build_service.py`: `_part_unit_price_for` and bundled
  PartsUsage creation; second external pricing path requiring shared resolver.
* `backend/app/api/v1/endpoints/fleet.py`: PM reseeding and deprecated service
  attachment currently use cost and omit unit_cost; staged creation direct parts
  distinguish internal/external. All must use one consistent resolver/retention path.
* `backend/app/api/v1/endpoints/services.py`: catalog base-price summary differs
  from canonical attach labor math; source template component mutations currently
  need a shared parent-service lock to serialize bundle composition reads.
* `backend/app/services/discount_limits.py`: `part_cost`, `proposed_part_price`,
  `discount_limits`, `validate_discounts`; explicit bulk/list/cost floor logic.
* `backend/app/api/v1/endpoints/quotes.py`: `_quote_snapshot` stores actual charged
  part values. No live matrix lookup belongs here.
* `backend/app/services/counter_sale_service.py`: `create_or_replace_draft`,
  `_tenant_parts`, `price_sale`, `serialize_line`; current replacement behavior.
* `backend/app/api/v1/endpoints/inventory_lifecycle.py`: SaleLineInput and
  SalePatchInput, counter-sale role/feature gates and idempotent checkout.
* `backend/app/db/models/inventory_lifecycle.py`: CounterSaleLine snapshots,
  immutable receipt/return allocations and PartActivityEvent composite tenancy.
* `frontend/src/features/inventory/PartsInventoryWorkspace.tsx`: existing
  SellingPriceInput already supports typing price or markup percentage; extend
  with policy controls, do not replace/reimplement its useful manual entry.
* `frontend/src/features/inventory/CounterSalesWorkspace.tsx`: draft adaptation,
  manual override payload, line total preview and sale display.
* `frontend/src/features/repair-orders/PriceBuilderPanel.tsx`: addPart omits price
  except stock mode, catalog/typeahead currently labels saved `selling_price` as
  “list”, per-line manual edit and bulk discount/pricing-mode controls.
* Focused tests: `test_price_build_service.py`, `test_discount_cost_floor.py`,
  `test_discount_cost_floor_postgres.py`, `test_ro_pricing_discounts.py`,
  `test_db045_inventory_lifecycle.py`, `test_inventory_catalog_activity.py`,
  `test_fleet_manager_price_build_access.py`, PriceBuilderPanel and inventory tests.
