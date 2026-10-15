# DB132 / P1 — parts markup matrices: intake contract

Architecture preparation completed 2026-10-15; moved into canonical intake after R1/DB131 production closure. Source baseline `7b3dc4b30a52e6880580f1511716afc38dbd1ba2` has the identical application tree as the reviewed preparation baseline21546789. Accountable implementation owner: Backend & Integrations. Product & Delivery Lead owns scope. Application implementation has not started; contract acceptance and negative cases below precede code, and independent gates remain required. This document does not activate pricing policy or authorize guessed shop markups.

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

Feature ships inactive: no matrix is seeded and no default is chosen for a real
shop. New behavior begins only when its owner/admin selects a default. Deployment
does not constitute authority to invent markups or change customer agreements.

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
  active names unique case-insensitively. Identity is ID, not name. No hard delete.
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
  event type, reason and bounded private before/after JSON. Include nullable typed
  FK columns for matrix, inventory, parts usage or counter line as applicable;
  same-tenant composite constraints on referenced persisted identities. This
  audit must work with parts-operations/counter-sale flags disabled. Private
  owner/admin event reader supports bounded entity-filtered pagination.

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
and nullable `pricing_matrix_revision_id UUID`; FK `(tenant_id,revision_id)`
references the revision's unique `(tenant_id,id)`. Add `(tenant_id,id)` uniqueness
where needed on PartsUsage for audit linkage. Matrix revision identity must not
exist only inside JSON: JSON cannot enforce the promised composite tenant FK.
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

Use one additive migration after R1's actual head. Null snapshots/floors and false
fixed flag preserve all existing data. Production rollback leaves columns and
revisions in place; reverse migration only on disposable test databases after
dropping new app code. DB constraints/composite FKs prohibit cross-tenant links.

## API contract

Namespace `/api/v1/parts-pricing` independent of activating counter-sale or parts
operations feature flags. No new flag is required: absence of a matrix and all
part policies unset preserves legacy defaults.

* `GET /matrices?include_archived=false` returns bounded metadata/current revision
  to owner/admin only. The same allowlist applies to matrix details/revision
  history, private configuration audit and draft-matrix `/preview`. Other staff
  use sanitized contextual resolution, not the matrix-rule endpoint.
* `POST /matrices` accepts name and complete validated bands; creates revision1,
  never silently makes it default. Use the normal request UUID/idempotency pattern
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

Architecture reviewed `/tmp/db132-backend-handoff.md` and
`/tmp/db132-frontend-handoff.md` against current source on 2026-10-15. The following
resolves their open contract items; it does not authorize early implementation.
No genuinely unresolved product decision remains within P1's selected scope.

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

`POST /api/v1/parts-pricing/resolve` body has `context` and `plan` (extra fields
forbidden). All decimal quantities/prices are strings; maximum100 resulting parts
per command,100 unique inventory IDs and30 services; reject excess before queries.
If an existing route has a stricter bound, keep that bound. Do not split a bundle
into separate commits to evade a limit.

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
plans; one canonical planner runs for preview and mutation. Request route adapters
add `pricing_preview_fingerprint` to part-add, service-apply, PM-replace, fleet-create
and counter-create/replace bodies. Exact expected sale version remains mandatory
on sale edits. The deprecated callable fleet staging/service endpoints use these
same semantics; a hidden UI is not a safe pricing bypass.

Safe response has `schema_version`, `pricing_preview_fingerprint`,
`confirmation_required`, `plan_kind`, `lines` keyed by client/component/retained
line identity, source categories, ordinary permitted customer prices, warnings,
canonical totals and an `availability` result. Fleet projection returns the
opaque fingerprint, permitted whole-work totals and safe scope warnings, without
unit costs, line prices, rates, rules or markup. Management-only details may enrich
this response through an explicit owner/admin schema, never a raw snapshot spread.

Fingerprint is an opaque keyed digest (not a decodable JWT/plain hash exposing
low-entropy cost inputs). Bind tenant, authenticated actor, authorized context and
bill-to/internal status, normalized plan/quantities, default generation, selected
matrix revision, current part cost/catalog/policy values and pricing versions,
service composition/component identities/quantities, canonical labor inputs needed
for bundle totals, and all retained line identities/price versions/saved amounts.
Use one consistent policy resolution per preview/transaction. Bind money-semantic
inputs, not unrelated names/notes or global inventory updated_at. Stock_version
alone is excluded: a stock-only change does not mean the price changed.

At mutation, reauthorize and reconstruct the plan under locks, compare keyed
fingerprint and all expected versions. Managed additions, explicit new-line
manual/stock intent, or an existing submitted fingerprint require matching
confirmation. Missing fingerprint when confirmation is required returns409
`pricing_preview_required`; mismatch returns409 `pricing_preview_changed` with a
fresh safe projection. Never interpret a stale catalog-supplied amount as manual
consent. Unmanaged/default legacy adds with no fingerprint remain compatible;
all new UI uses preview. If policy activates between an old client's request and
commit, the now-managed action fails for missing confirmation instead of charging
an unconfirmed amount. Internal default adds stay compatible; supplied differing
internal prices reject with `internal_price_fixed` rather than being ignored.

An unchanged retained-line quantity update needs its existing version/stock guard,
not fresh catalog pricing. No original snapshot is resolved during confirmation.
A manual new-line amount requires explicit `pricing_intent:"manual"` plus reason;
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

- Management details: applied matrix name/revision, rule/basis/cost/floors,
  margins, original/current price and audit reason; explicit schema only.
- Ordinary shop workflow (authorized receptionist/mechanic, plus owner/admin's
  regular row): `{origin_source, current_source, managed, default_unit_price,
  charged_unit_price, can_override, pricing_version}` and opaque confirmation
  fingerprint where applicable. Origin categories are matrix/fixed/catalog/
  ad_hoc/internal/legacy_unknown. Legacy NULL snapshot is `legacy_unknown`, not
  invented Catalog provenance. Display only prices the existing audience is
  permitted to see. No rule body, actual cost, minimum derived from cost, matrix
  identifier/name, markup/margin or private actor/note in this new projection.
- Fleet workspace keeps its existing whole-work total/quantity presentation; no
  new per-line pricing/rate fields, override controls, raw provenance or rule names.
  It can accept a changed safe total/scope or cancel after a preview conflict.
- Customer/public/portal and invoice/quote/receipt documents keep only existing
  customer-facing charges. New provenance is entirely absent. The shared
  `_build_parts_usage_response` must take explicit audience or use separate schemas;
  do not add raw snapshot through its generic customer-facing use. Audit existing
  `unit_cost` emission there and suppress it for customer/public audiences as
  part of this serializer boundary; do not widen inventory reader authorization.

Private detail or thresholds must not leak through409/422 bodies, logs, generic
history notes, websockets or idempotent replay. Restricted price-floor failures
use `price_below_minimum` plus an actionable safe message; only owner/admin may
receive the numeric threshold. Existing inventory read rights are preserved, but
are not a grant to new matrix data. Clear tenant/role-sensitive frontend caches
on identity changes; query keys include context/plan and authenticated scope.

### 7. Contract closure and mandatory regression additions

Backend handoff's eight omissions and frontend role/schema questions are resolved
above. Preserve both handoffs as source/integration maps; when wording differs,
this refined contract is authoritative. No production policy activation, guessed
markup, account terms or premature C1 behavior is authorized.

Add acceptance for service/PM retain/remove/re-add identity, ambiguous legacy
mapping, NULL-cost historical preservation, minimum-with-no-matrix, cost-floor-only
no-effect, fixed-with-no-matrix, snapshot-managed=false, default ABA, preview missing/
changed/bundle composition, stale generic inventory write, internal price tamper,
external fleet PM unit_cost, lifecycle/tenant-negative snapshots, raw response
privacy, role change before idempotency replay, quantity/manual/bulk CAS and late
bundle rollback. Test matrix configuration/audits with parts-operations disabled.
Test PO WAC versus attach and competing template changes on actual PostgreSQL.
No tests were executed during this contract-only refinement; passing results must
be produced during implementation and independent acceptance.


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

Runtime after R1 Done and local-runtime preflight: create draft matrix, preview,
activate only in synthetic permitted test scope, attach standalone/bundled part,
edit quantity/price, revise matrix, show old line stable/new line updated, fixed/
floors/clear/archive behavior, save/reload/conflict; read-only historical quote
comparison. Light/Night desktop1280+,320/390portrait,740×400landscape. One workspace
scroll, compact rows, 44px touch targets, keyboard/Escape/focus, error retains draft.
Never issue real quotes, complete real counter sales or change real default rates
for QA without authority. Use synthetic fixtures and restore test configuration.

High-risk financial/migration lane: approved contract, independent QA/Security,
real migration/concurrency tests, protected CI, schema/release identity and
production changed-journey evidence before DB132/P1 is Done. Parent chooses owner
split after R1 release; suggested backend owns all backend/migration/tests and
frontend owns matrix settings/part-policy/price-picker/provenance and tests.

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
