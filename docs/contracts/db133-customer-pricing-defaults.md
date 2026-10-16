# DB133 / C1 — customer pricing defaults

Architecture contract, 2026-10-16. Accountable owner: Backend & Integrations.
Product & Delivery Lead owns scope, board and release sequencing. Source baseline:
`195c7f3af7a4ea59552ff58daedd5a63308d0f7e` on `codex/customer-pricing-defaults`
(application `70530bda`, including P1 and its UI correction).
Read [C1 readiness](../verification/DB133_CUSTOMER_PRICING_READINESS.md),
[P1 contract](db132-parts-pricing-matrix.md), and
[the ordered tracker](../ETS_PARITY_TRACKER.md) together with this document.

Product accepted this lean contract after P1 production closure and mandatory C1
local-runtime preflight on2026-10-16UTC. This is implementation authorization, not
QA, release approval or Done. No real account
agreement, rate or matrix assignment is created by this contract.

## Outcome, approved decisions and limits

Owner/admin can set an optional agreed customer labor rate and/or select a parts
matrix in Customer → Business settings → Pricing. New external work for that exact
bill-to account automatically uses its terms. Staff can distinguish the default
from an explicit override. Subsequent account/shop changes never rewrite saved
work or issued documents.

**User-approved on 2026-10-16 UTC:** NEW external orders, including external fleet
PM/staged work, use customer agreed labor rate first, otherwise shop billing rate.
Existing orders retain saved rates. This deliberately replaces the current
external fleet PM/staged/deprecated fallback to the internal labor rate for new
C1 external orders; it is not an incidental refactor. Internal work keeps its
existing internal/customer-rate preference and does not adopt account agreements.

Resolved defaults:

- Both account fields start NULL. NULL means inherit shop policy for FUTURE order
  intake, not free labor, no markup, or retroactive clearing of old terms.
- A customer selects a matrix identity; each new order pins its current immutable
  revision. New C1 orders also pin the actual inherited shop rate/revision, or an
  explicit catalog mode if the shop has no matrix. Unset is not a later live lookup.
- An order policy stays fixed for new additions to that order too. There is no
  job-wide refresh/reprice action. Individual authorized overrides remain possible.
- Retained labor rates and all P1 part snapshots remain unchanged on hours/quantity
  edits, service/PM reapply, auto-recalculate, assignment, completion, reopen and
  restore unless the user explicitly edits the price through the existing allowed
  lifecycle. This applies to legacy retained lines as well as C1-created lines.
- Legacy/imported orders are not backfilled with today's account policy. A newly
  added line on a legacy order uses the established route's shop/internal default,
  never the customer's newly configured agreement. Imported edit guards remain.
- Buyer change on an editable counter draft preserves existing line prices;
  the existing buyer selection selects its policy for future lines only, using
  the existing P1 preview/version checks and no additional confirmation dialog.

Include existing standard/quick/contextual/fleet intake, service/book/manual labor,
recommendation conversion, P1 parts insertion paths, optional enabled counter sales
and narrow pricing-aware customer merge safety. Exclude credit limits/terms,
deposits, service-specific agreements, effective dates, bulk repricing, payroll,
resource scheduling, provider/tender changes, new counter-sale activation, tax-rule
changes, outreach and full financial-identity merge. Quotes/invoices/receipts stay
snapshot consumers. No invented production rates or policy activation.

## Current source and reusable components

- `Customer` has tax-default CAS but no pricing agreement; generic customer PUT
  permits customer self-service. Pricing fields must not be added to generic
  writable CustomerCreate/CustomerUpdate or portal payloads.
- Business settings is currently a private disclosure inside
  `CustomerTaxExemptionControl.tsx`, with separate payments permission. Extract a
  reusable disclosure without making tax controls visible to new roles.
- P1's `parts_pricing_rules.PricePolicy` and `resolve_price` already accept a
  revision. `parts_pricing.selected_policy` currently selects only the live shop
  default; `parts_pricing_planner.build_plan` selects it only for genuine additions.
  Extend policy selection, not P1 pricing math/retained identity/stock handling.
- Labor defaults are duplicated in PriceBuild, recommendation conversion, direct
  RO labor, fleet PM/legacy/staged writers and P1 preview totals. They must consume
  one policy helper. Service reapply currently overwrites hourly_rate and turns
  auto_recalc on; that must not erase an existing override under this contract.
- Current merge reassigns operational rows then physically deletes the losing
  customer. Financial FKs can roll back with generic 400; Invoice.billed_customer_id
  is a historical UUID without a customer FK. C1 adds only a fail-closed deletion
  guard for its own policy-bearing/referenced identities; generic financial merge
  correctness remains a separately recorded pre-existing issue.

## Additive data model

Refresh the actual migration head after P1 closure; do not reserve a revision
number in advance. No pricing or money backfill.

1. Customer adds `pricing_labor_rate NUMERIC(10,2) NULL`,
   `parts_price_matrix_id UUID NULL`, `pricing_version BIGINT NOT NULL DEFAULT 0`,
   `pricing_updated_at TIMESTAMPTZ NULL`, `pricing_updated_by UUID NULL`.
   Matrix reference uses a composite FK `(tenant_id,parts_price_matrix_id)` to
   P1 matrix `(tenant_id,id)`. NULL and a positive rate are distinct; no zero
   sentinel. These are future-default configuration, not job financial records.
2. RepairOrder adds nullable server-owned `pricing_policy_snapshot JSON` and
   `pricing_matrix_revision_id UUID NULL`, with composite same-tenant revision FK.
   A snapshot includes its own UUID and schema_version. It is immutable after
   creation; no generic update schema accepts it. Internal and legacy rows remain
   NULL; their established internal preference fields remain authoritative.
3. CounterSale adds the same nullable snapshot and typed revision FK. New draft
   captures a policy; an explicit eligible buyer change may replace the draft's
   policy for future additions and append an event. Per-line original snapshots
   never change. Completed sale policy is immutable. Legacy sale snapshot stays
   NULL unless an explicit buyer selection change creates its first future policy.
4. Labor adds nullable immutable `pricing_snapshot JSON` and nullable
   `pricing_source` constrained to `default` or `manual`. The snapshot records
   snapshot_id/schema_version, originating order-policy snapshot ID (nullable),
   default rate/source at attachment and initial observed intent. The live
   hourly_rate remains the charge; later authorized rate edits update the factual
   source and append audit evidence in the existing locked write. NULL means
   unknown legacy origin. No new labor CAS protocol, mandatory reason or extra
   confirmation is introduced. Do not reuse execution_version for pricing or
   backfill a false legacy default. Historical customer UUIDs are not live FKs.
5. Add `account_pricing_events`: immutable event ID/tenant, entity_type
   (`customer_policy`, `labor`, `counter_policy`), original
   entity UUID, original customer ID/name snapshot when relevant, order/sale IDs
   when relevant, actor ID/name/role, timestamp, command correlation, applicable
   before/after versions, optional reason and bounded server-generated evidence.
   Labor events record observed before/after rate/source under the existing write
   lock; they do not invent a version or imply stronger concurrency than the route.
   Retain typed nullable
   same-tenant matrix/revision FKs where referenced. Entity/customer/labor origin
   UUIDs are historical references, not live FKs that block legitimate removal.
   No cascading deletion or SET NULL mutation of audit evidence. Validate all
   live objects against the authenticated tenant before appending an event.

Index tenant plus original snapshot customer_id for RepairOrder/CounterSale policy
references, excluding NULL snapshots, so the narrow merge guard does not scan a
tenant's entire work history. An expression index is sufficient; no live customer
FK or new financial identity table is required.

Reuse P1's unflagged PartsOperationIdempotency primitives under `c1_*` operation
families. No second generic receipt subsystem, policy worker or cron job. The
customer-policy event's schema/tenant/ID/version lets an order snapshot retain
source-policy evidence; version 0 is explicitly unconfigured
and needs no fabricated event. Include the event ID when a configured policy is
captured. A nonzero version whose matching evidence cannot be verified is 409
`account_pricing_unverified`, not a silent fallback.

The immutable order snapshot is exactly:

```ts
type Money = string; // finite, exactly two decimals in responses
type MatrixRef = { id: string; revision_id: string; revision: number; name: string };
type OrderPricingSnapshot = {
  schema_version: 1;
  snapshot_id: string;
  captured_at: string; // UTC ISO8601
  customer_id: string; // original exact bill-to, historical evidence
  customer_name: string;
  customer_pricing_version: number;
  customer_policy_event_id: string | null;
  labor: { source: 'customer' | 'shop'; rate: Money };
  parts: {
    source: 'customer' | 'shop';
    mode: 'matrix' | 'catalog';
    matrix: MatrixRef | null;
    shop_default_generation: number | null;
  };
};
```

Counter snapshots omit labor and have two explicit identity variants. A linked
customer keeps the exact account identity above; a walk-in has no customer identity:

```ts
type CounterPricingSnapshot =
  | (Omit<OrderPricingSnapshot, 'labor'> & { captured_for: 'counter_sale' })
  | (Omit<OrderPricingSnapshot,
      'labor' | 'customer_id' | 'customer_name' | 'customer_pricing_version' |
      'customer_policy_event_id' | 'parts'> & {
      captured_for: 'counter_sale';
      customer_id: null;
      customer_name: null;
      customer_pricing_version: 0;
      customer_policy_event_id: null;
      parts: {
        source: 'shop';
        mode: 'matrix' | 'catalog';
        matrix: MatrixRef | null;
        shop_default_generation: number;
      };
    });
```

For a walk-in, use the actual shop matrix revision or explicit catalog mode if no
shop default exists, and capture the current P1 shop-default generation (including
zero). Do not create a customer, account policy or customer-policy event. Free-text
buyer name/contact remains in existing sale/receipt fields; it is not fabricated
account provenance. A counter-policy event may still record the actual sale's
policy transition with NULL customer identity. Skip customer lookup/locking and
customer-reference merge checks for this NULL identity; normal tenant/sale/P1
checks still apply. The linked-account-only pricing-preview endpoint is not called
for a walk-in; existing P1 counter_draft preview supplies its pricing confirmation.

For either variant, the JSON revision ID must match its typed column; matrix mode
requires both and catalog mode requires both NULL. Validate these invariants on
write, with schema checks/tenant FKs where applicable. Never trust a browser-supplied
snapshot. P1 parts keep their own attachment cost, fixed policy and floor snapshots;
the order snapshot does not freeze inventory WAC or part-specific policy before a
part is attached.

## Dedicated customer configuration API

Namespace `/api/v1/customers`. Configuration GET/PUT/history are tenant owner/admin
only, matching P1 matrix authority. No payments permission is newly required for
pricing and no tax permission is broadened. Role check precedes tenant-scoped live
customer lookup; foreign/deleted account is 404. A house/internal-price identity
(as defined by uses_internal_fleet_pricing, not merely one Boolean) is readable
as ineligible and cannot receive an agreement.

```ts
type CustomerPricingValues = { labor_rate: Money | null; parts_matrix_id: string | null };
type CustomerPricingPolicyResponse = {
  schema_version: 1;
  customer_id: string;
  version: number;
  configured: CustomerPricingValues;
  effective: {
    labor: { source: 'customer' | 'shop' | 'internal'; rate: Money | null };
    parts: { source: 'customer' | 'shop' | 'internal'; mode: 'matrix' | 'catalog' | 'internal'; matrix: MatrixRef | null };
  };
  can_edit: boolean;
  ineligible_reason: 'internal_account' | null;
  updated_at: string | null;
};
type CustomerPricingWrite = {
  expected_version: number;
  labor_rate: Money | null;
  parts_matrix_id: string | null;
  reason: string;
};
type CustomerPricingHistoryResponse = {
  schema_version: 1;
  items: Array<{
    id: string;
    version: number;
    before: CustomerPricingValues;
    after: CustomerPricingValues;
    actor_user_id: string | null;
    actor_display_name: string | null;
    reason: string;
    occurred_at: string;
  }>;
  next_cursor: string | null;
};
```

- `GET /{id}/pricing-policy` returns CustomerPricingPolicyResponse, without any
  database initialization. An internal account has effective internal modes,
  rate/matrix NULL and can_edit=false; do not suggest an external rate for it.
- `PUT /{id}/pricing-policy` accepts CustomerPricingWrite and returns the same
  envelope with 200. Both nullable values are required: omitted is invalid, not
  an accidental clear. Reject extra fields. Rate is strictly positive, finite,
  at most two decimals and fits NUMERIC(10,2). Reason trims to 3–500 characters.
  Referenced matrix must be active and in the same tenant. NULL matrix inherits
  shop; there is no new per-account disable-matrix toggle in C1.
- PUT requires `Idempotency-Key` header using P1's existing validation; UI sends
  one UUID per logical save, reusing it only for uncertain retries. Missing/invalid
  key retains the existing 400 carrier error. After role reauthorization, exact
  replay returns its original response without duplicate events. Different payload
  under the same key is 409 `idempotency_conflict`.
- Under locks, compare expected_version before deciding no-op. Unchanged pair
  returns current version and no event; a real change increments version once,
  updates actor/time and appends event/receipt in the same transaction. Never
  independently save the rate then fail the matrix selection.
- `GET /{id}/pricing-policy/history?limit=25&cursor=...` returns the history envelope;
  limit 1–100, version/ID descending. Opaque cursor binds tenant/account/filter.
  Invalid cursor is 400 `invalid_cursor`. Require the same live tenant-scoped
  customer lookup as policy GET; C1 prevents deletion of a policy-bearing loser.
  Historical UUIDs in audit evidence never grant access to another live entity.

Matrix list/detail APIs remain P1 owner/admin-only. Archive adds an active-customer
assignment guard: any live customer referring to that matrix blocks archive with
409 `matrix_assigned_to_customer`. Clear/reassign future defaults first. Historical
order/counter/part references alone do not block archive; pinned historical revision
loads must not use P1 selected_policy's active-default check. No matrix hard delete.

## Intake preview, safe projections and creation precondition

`GET /{customer_id}/pricing-preview?vehicle_id=...&pricing_presentation=shop|fleet`
provides source-aware intake confirmation, not configuration or authorization.
Use existing RO creation roles. Fleet managers must supply a vehicle and pass the
same exact vehicle/payer scope checks as fleet creation; specifying another tenant
or unrelated customer never grants scope. Shop users can preview an in-scope payer
before selecting a vehicle. A non-NULL token vehicle must match the creation
vehicle exactly; NULL binds only the customer, and creation still independently
validates vehicle/payer scope. New UI refreshes preview after selecting a vehicle.
Mechanics, customers/public and drivers gain no new account-setting endpoint.

```ts
type IntakePricingBase = {
  schema_version: 1;
  customer_id: string;
  vehicle_id: string | null;
  expected_pricing_policy: string; // opaque keyed digest, not decoded account data
  policy_kind: 'external' | 'internal';
};
type ShopIntakePricing = IntakePricingBase & {
  projection: 'shop';
  labor: { source: 'customer' | 'shop' | 'internal'; rate: Money | null };
  parts: { source: 'customer' | 'shop' | 'internal'; mode: 'matrix' | 'catalog' | 'internal' };
};
type FleetIntakePricing = IntakePricingBase & {
  projection: 'fleet';
  agreement_applies: boolean;
};
```

Default presentation is shop for authorized shop staff, fleet for fleet managers.
A shop owner/admin may request fleet; a fleet manager cannot upgrade to shop.
No projection includes matrix IDs/names/rules, cost, margins or private reasons.
Owner/admin configuration is the separate endpoint above. Fleet preview carries
no labor rate or component money; P1 staged-work preview provides the authorized
whole-work total when actual work is selected. Do not fetch a shop/private endpoint
to populate a fleet form. Internal preview rate is NULL until existing vehicle
preference context supplies the unchanged internal workflow's permitted total.

Add optional `expected_pricing_policy` to standard RO create, fleet new/PM creation
and quick-create request adapters. These adapters also accept optional
`pricing_presentation: "shop" | "fleet"`, with the same role-based default and
downward-only restriction as preview; use an existing P1 field where already
available. New UI echoes its preview projection so conflict responses match it.
Token binds authenticated tenant/actor,
customer ID/version/event, effective labor amount/source, chosen revision/catalog
mode/default generation, internal classification, applicable vehicle context and
presentation. Relevant effective shop-rate changes also change the token; customer
CAS and P1 generation already detect their own ABA cases. Do not bind unrelated
notes, names or global timestamps. Recompute from locked authoritative values.

If supplied and mismatched, reject 409 `account_pricing_changed` with a fresh safe
intake preview. Preserve customer/truck/work fields and require explicit retry.
Legacy authorized clients without a precondition still capture the current server
policy; they cannot send an alternative snapshot/rate/revision. New C1 UI uses the
precondition whenever it has displayed account terms. A server default must not
be treated as an intentional manual override just because a client echoed it.

For quick-create, resolve the actual account from normalized phone first, under
existing access/identity rules. It must not use a different selected customer's
token. A supplied mismatch rolls back newly staged customer/vehicle/relationships;
otherwise capture the actual account's terms and return the resulting order source.
Do not add a new ambiguous phone-to-account choice or change quick-create semantics.

### Signed originating-call reservation recovery

Reuse existing PartsOperationIdempotency storage under operation_family
`c1_call_reservation`; no new receipt table, provider protocol or outbound action.
The server computes the key from a keyed, domain-separated digest of authenticated
tenant ID, actor ID and the opaque originating_call_reference token. The key is not
the browser's mutable intake Idempotency-Key. Never store or log the raw token,
provider secret, full request body or browser-supplied attribution in this mapping.
The request fingerprint additionally binds the actual selected customer_id and
vehicle_id. It deliberately excludes current pricing token/rate so an explicit
pricing-conflict retry can reuse its known-success reservation.

The internal completed receipt body is exactly:

```ts
type CallReservationReceipt = {
  schema_version: 1;
  tenant_id: string;
  actor_id: string;
  customer_id: string;
  vehicle_id: string;
  repair_order_uuid: string;
  elis_opportunity_id: string;
  callrail_call_id: string;
  recorded_at: string; // local UTC receipt time, not asserted provider event time
};
```

These are validated provider response fields plus validated local identity bindings,
not caller-controlled attribution. Store an internal 200 completed receipt, never a
serialized RO/price response. Normal endpoint responses still apply the current
safe projection and authorization rather than replaying a cached response body.

Required ordering and transaction boundaries:

1. Before lookup/replay, perform current authenticated tenant/role/call-intake
   eligibility and actual customer/vehicle access checks. A receipt never grants
   new scope. Acquire P1's existing per-key transaction advisory serialization,
   then refresh/inspect the scoped receipt. A different customer/vehicle binding
   conflicts using the existing call-intake identity-conflict behavior; never
   rebind the receipt or disclose the earlier account/vehicle IDs.
2. If a completed mapping exists, validate its tenant/actor/bindings and load the
   reserved order by UUID plus tenant. If that order exists, apply current order
   authorization and existing deleted/lifecycle visibility guards; verify its
   actual customer_id, vehicle_id and provider attribution against the receipt.
   Return the authorized order with its ORIGINAL snapshot before comparing today's
   agreement. Never revive deleted work, silently select another order or recreate
   an inaccessible order. If the reserved order does not yet exist, reuse the
   mapping and continue the final capture without another provider reserve.
3. Without a mapping, prevalidate any displayed pricing precondition before the
   existing provider reserve call. Only a validated successful provider response
   may become a completed mapping. Bound the call with existing timeouts and keep
   serialization limited to this reservation key; do not hold broad tenant,
   customer, order, inventory or financial locks across network I/O.
4. Durably commit this reservation evidence in its own narrowly owned transaction
   before final locked policy capture/order creation. This transaction may contain
   only reservation evidence and read checks, not staged customer/vehicle/order,
   relationship, stock, pricing or payment mutations. Do not accidentally commit
   pending ORM changes from an outer request. The intake adapter owns this explicit
   boundary; normal pricing helpers still do not commit.
5. Begin/revalidate the normal final C1 intake transaction, using the reserved UUID,
   current authorization/actual identities and displayed pricing precondition.
   Another request may already have created that order after the receipt commit:
   refresh and replay it with the same original-order checks before inserting.
   Complete order, snapshot, work and normal intake receipt atomically. A pricing
   409 or other final-work rollback retains the known-success reservation mapping;
   retry preserves the UUID and does not reserve again after that mapping exists.

A crash, network loss or DB failure after provider success but BEFORE the mapping
is durably saved remains an ambiguous provider outcome. C1 cannot guarantee zero
repeated provider calls or exactly-once external execution in that interval. Keep
the existing bounded provider error/retry semantics and authority checks; do not
fabricate a success receipt, invent a new UUID or claim a DB rollback undid the
external reservation. No new provider recovery endpoint, queue, notification or
customer send is introduced. This is known-success recovery only.

P1 fleet_create preview binds the candidate account policy and its total. Its
mutation uses that same captured policy for order creation and parts/labor planning,
not a second live selection after confirmation. Standard create-then-service wizard
retains its successfully created order ID before attachments; cancellation/conflict
only affects pending attachments, as P1 specifies. No create-loop on a price error.

## Policy selection and immutable calculation

Implement one customer/intake capture helper and one existing-order policy reader.
Use them in all three constructors: create_repair_order, quick_create_repair_order,
and fleet._spawn_internal_ro (despite its name, it creates external work too).
Every caller of the fleet helper, including PM scheduling, receives the same policy.
Snapshot, revision FK, order, initial work, stock/relationship changes and the normal
intake idempotency receipt belong to the owning transaction/savepoint. No helper
commit. The separately durable call-reservation evidence above is the sole explicit
exception; it never commits these work/pricing mutations.

Precedence for NEW C1 external orders:

1. Labor: positive configured customer rate; otherwise current Tenant.labor_rate.
2. Parts policy: customer's selected matrix current revision; otherwise current
   shop revision; otherwise explicit catalog mode. Capture the source and version.
3. For a newly attached part, P1 fixed catalog bypass, actual-cost protection,
   pricing basis floor, minimum selling price and explicit authorized override
   retain their established precedence. Account terms cannot weaken those floors.
4. Persist a policy even when both customer defaults are NULL, so a subsequent shop
   or customer update cannot silently change that new order's intended terms.

For a saved C1 order, load its exact same-tenant immutable revision by ID, including
an archived matrix's retained revision. Never call the live selected_policy helper
as fallback for a malformed/missing reference; return 409 account_pricing_unverified.
Explicit catalog mode passes an empty PricePolicy and never adopts a newer default.
Parts still snapshot current actual inventory cost and part policy on each genuine
attachment. P1 retains saved price/cost/floors for retained lines. Its price digest
binds the order policy snapshot ID/revision for new lines, not today's customer
version/default generation; retained-only plans still have no live-policy dependency.

For snapshot-NULL legacy orders, new lines use the pre-C1 route default and P1 live
shop policy for genuine new parts, without consulting account overrides. Retained
labor uses its own saved rate in every path, even if auto_recalc_enabled is true;
hours may recalculate under existing provider/service rules, but money does not
adopt today's Tenant rate. A new C1 policy is not inferred from a legacy line's rate.
No imported order read/add/reopen operation backfills a policy.

Internal orders ignore external account configuration, use the existing
bill_labor_at_customer_rate snapshot for new work and actual cost for new parts.
Retained internal rates/prices remain saved. No changes to time tracking, technician
cost, operation completion, invoice prohibition or internal permission boundaries.

### Labor writer and override contract

Route all seven genuine labor creation sites plus their previews/default readers
through the common helper: PriceBuild service and repair-operation insertion;
recommendation conversion; ordinary direct labor; fleet PM, deprecated service and
staged labor. Vendor/sublet amount rows are explicitly excluded from hourly policy.
Use the same helper for P1 service/PM/fleet total previews, recommendation suggested
rate, recalculation and legacy shop quick-add defaults.

New automatic labor stores the resolved default/rate/source once. Retained service
or PM reapply preserves hourly_rate, pricing_snapshot/source and manual-intent
state. It may change allowed hours/reservation/scope, but cannot reset a manual
line's auto_recalc_enabled to true merely because a template was reapplied.
Recalculate preserves a retained rate while applying existing approved hour rules;
assignment/recommendation/checklist/execution identities remain intact.

Keep the existing authorized rate-edit flow. Make direct LaborCreate.hourly_rate
optional, matching recommendation creation, and accept optional intent on these
creation adapters:

```ts
type LaborPriceIntent = {
  hourly_rate?: Money; // omission asks for the server's applicable default
  pricing_intent?: 'default' | 'manual';
};
```

- New UI omits untouched default hourly_rate, or explicitly sends intent=default;
  the server resolves the order's pinned default even if an old displayed shop rate
  is echoed with explicit default intent. A user-edited rate sends manual intent
  and the actual permitted amount. A default is not a price floor.
- Existing authorized clients supplying an amount without intent retain their
  explicit-rate behavior. A different amount is a factual manual choice; an equal
  amount alone cannot establish manual intent and is recorded as default unless
  the caller explicitly marks manual. Do not reject ordinary authorized edits or
  require a typed reason just because C1 adds source tracking.
- Explicit manual requires an amount and the existing rate-edit role. Mechanics
  retain their existing server-forced default and cannot acquire override authority
  by sending intent or a different rate. Keep current internal/fleet guards.
- Existing LaborUpdate and PriceBuildLineUpdate requests remain compatible: changed
  authorized hourly_rate is manual and adds before/after/source audit in the same
  locked transaction. Hours-only and supplied-but-unchanged rate edits do not invent
  a manual action. No new expected_pricing_version, rate-confirmation dialog or
  hourly-edit version requirement is introduced.
- Use existing order/labor locking and lifecycle/completion guards. Audit records
  the actual transition after acquiring the lock. A concurrent edit retains the
  route's existing serialized update behavior; C1 does not claim new stale-form CAS
  for labor. A later reapply/recalculation must preserve the rate actually saved.
- The origin snapshot remains immutable. Current manual source follows an observed
  edit or explicit creation intent, not comparison with today's customer/shop rate.
  A legacy retained line has unknown default until facts exist; editing its rate
  records current manual intent but does not manufacture a historical default.
- Retained manual-rate protection cannot be defeated with auto_recalc_enabled=true.
  This flag continues to control provider/service hour recalculation; reapply and
  recalculate cannot use it as an implicit price reset. No new default-reset action
  or whole-order repricing feature is added in C1.

The existing legal monetary bounds/zero-price staff controls are preserved;
positive account-default validation does not prohibit an already-authorized manual
zero-price exception. No new discount authority is added. Recommendation conversion
keeps its source linkage, replace-confirmation and idempotency; replay returns the
original operation/rate rather than re-resolving changed account terms.

## Safe persisted responses

Add `pricing_policy` to authenticated shop RO creation/detail/price-build responses
only; quick-create returns the actual resolved account source through this field:

```ts
type ShopOrderPolicy = {
  schema_version: 1;
  snapshot_id: string | null;
  mode: 'captured' | 'legacy' | 'internal';
  labor: { source: 'customer' | 'shop' | 'legacy' | 'internal'; rate: Money | null };
  parts: { source: 'customer' | 'shop' | 'legacy' | 'internal'; mode: 'matrix' | 'catalog' | 'legacy' | 'internal' };
};
type SafeLaborPricing = {
  source: 'customer' | 'shop' | 'internal' | 'legacy_unknown';
  current_source: 'default' | 'manual' | 'legacy_unknown';
  default_hourly_rate: Money | null;
  charged_hourly_rate: Money;
  can_override: boolean;
};
```

Shop LaborResponse adds `pricing: SafeLaborPricing`; legacy default is NULL when
unknown. Owner/admin and ordinary shop rows use this safe projection; no full
account/order snapshot, matrix name/ID, actor reason or cost is spread into generic
responses. Optional compact labels are Account / Shop / Fixed / Manual; exact matrix
names/rules stay in owner/admin configuration. Preserve P1 `origin_source` categories
for parts; add an optional safe `policy_source: customer|shop|internal|legacy` within
the authorized shop part pricing object only when factual. Do not change origin
from matrix/fixed to Account and lose the distinction between policy and calculation.

Legacy/internal ShopOrderPolicy uses NULL labor rate where no historical order
default exists; it must not label today's live rate as an old captured agreement.
Fleet responses do not acquire new labor version, rate, matrix/provenance or override
controls. Existing P1 part versions stay as they are. Fleet whole-work totals remain
the pricing confirmation surface. Customer/public/portal/history documents and
quote/invoice/receipt serializers omit all new internal fields; existing charged
money remains. Reauthorize idempotent replay and key frontend caches by tenant/user,
customer/order, presentation and relevant version; clear on identity changes.

## Counter-sale default and buyer change

Reuse P1 counter_draft planning and saved line identity. New customer draft captures
that customer's parts policy; new walk-in draft uses the NULL-identity snapshot
variant above and captures the actual shop matrix/catalog policy. All
pricing/checkout feature flags, manager-only override rules, tax, payment, receipt
and return accounting remain unchanged. No feature activation is part of C1.

Same buyer plus later account edit does not repin a saved draft. Changing the buyer
on an editable existing draft captures the selected buyer's current policy for
future lines. This also covers linked account → walk-in and walk-in → linked
account; clearing the buyer captures the current shop policy with NULL identity,
while retained lines remain unchanged. P1 preview binds candidate buyer (including
NULL)/policy version/revision, saved sale
version and retained line prices; existing expected_version and
pricing_preview_fingerprint remain the request's concurrency carriers. Reuse P1's
review on changed totals; no keep_existing_line_prices flag, extra acknowledgment
or additional buyer-confirmation modal is required.

Keep all retained charges/cost/provenance, append a counter-policy event with
before/after policy identity and apply the new policy only to genuinely added lines,
atomically. A compact source notice makes the future default visible; existing
saved prices stay unchanged. Buyer-name/email edits without customer-ID change do
not repin. Completed sale/receipt/returns never consult account pricing. Legacy
drafts without buyer change keep P1 behavior. No new sale-version system is added.

## Customer merge: narrow C1 deletion guard

No full financial identity merge or financial-writer remediation is part of C1.
Preserve current export/ETS mapping and existing merge safeguards. Before moving
any rows, acquire the two customer locks in sorted UUID order and refresh the
loser's policy state. Return 409 `customer_pricing_merge_locked` if the losing
customer has any of:

- pricing_version > 0, configured pricing fields or account-policy audit history,
  including a previously configured agreement subsequently cleared;
- an immutable C1 order or counter policy snapshot whose original customer_id is
  that identity, including cancelled, completed and deleted owning records.

This conservative guard protects all C1 source evidence without a winner/loser
policy choice, new merge aliases or deleting historical policy. A configured winner
with an untouched, unreferenced loser is not blocked by this C1 guard. The existing
merge path and its safeguards still decide that operation. No extra merge request
fields or merge configuration UI are introduced. Error text explains which account
must be retained; it does not promise a financial identity transfer.

C1 configuration/intake/counter capture must hold the same live customer lock while
checking or creating first C1 policy references. Thus a losing-customer delete cannot
race successfully with its first C1 policy/reference. Merge must revalidate both
identities after waits; do not follow a deleted customer UUID or silently substitute
another account. This concerns C1 writes only, not payment/invoice/import writers.

Known pre-existing risk, outside this outcome: generic merge can fail on finance FKs
and Invoice.billed_customer_id is not FK-protected. This contract does not assert
that legacy unconfigured customer merges preserve all financial identity or fix
those broader races. Record that separately for identity/merge intake. Do not change
financial creators, rewrite financial ownership or broaden C1 into B1/payment terms.

## Locking, errors and compatibility

C1 configuration/intake and P1-integrated pricing writes authorize first and retain
P1's tenant/idempotency-before-entity ordering where those locks already apply.
After those locks, use sorted customer locks, then order/sale and existing policy/
matrix/service/inventory ordering. Refresh after waits. A configuration command
needs no order lock; saved-order attachments do not reread live customer defaults.
Merge takes its sorted customer locks before existing mutations; it does not add a
new tenant-wide financial workflow. Do not acquire a tenant lock after a customer
lock in a C1 command; helpers must not introduce an inverse order.

Existing labor updates keep their established order/labor locking. Policy helper
reads for immutable saved orders do not request customer locks. Preserve P1 PO/WAC
ordering; never add a late tenant lock to a receipt already holding PO/inventory
locks. No new pricing helper commits. No broad lock is held over user think-time.
Use the established Tenant lock for coherent new-order capture with existing shop
settings writes; do not rewrite financial creators or reviewed-import workflows.
Originating-call reservation recovery uses only the bounded per-key receipt
transaction above; its known-success commit precedes final-work locks.

Domain errors use FastAPI typed JSON; 403 role denial and 404 missing/foreign active
subject do not reveal account terms. 422 handles malformed/out-of-range/unknown
fields. The explicit new conflict carriers are:

```ts
type PricingConflict = {
  detail: {
    code: 'customer_pricing_conflict' | 'internal_account_pricing' |
      'matrix_archived' | 'matrix_assigned_to_customer' |
      'account_pricing_unverified' | 'idempotency_conflict';
    message: string;
    field?: 'labor_rate' | 'parts_matrix_id' | 'expected_version';
  };
};
type IntakeChangedConflict = {
  detail: {
    code: 'account_pricing_changed';
    message: string;
    preview: ShopIntakePricing | FleetIntakePricing; // same authorized projection
  };
};
type CustomerMergePricingConflict = {
  detail: {
    code: 'customer_pricing_merge_locked';
    message: string;
  };
};
```

`customer_pricing_conflict` message: “These pricing settings changed. Refresh them
while keeping your draft.” `account_pricing_changed` message: “The account pricing
changed. Review the current defaults before creating the order.” Merge message:
“This customer has saved pricing history. Keep this customer as the retained
account, or leave the accounts separate.” Do not include another account's details,
policy IDs or a private reason in merge errors. Config conflict does not overwrite
the draft; the owner/admin may separately refetch its authorized policy endpoint.

Preserve P1 errors for its existing preview/parts/CAS paths. Restricted errors,
logs, generic notes/websocket events and replay bodies must not expose private
rates/rules/matrix identity. Validation or version failure makes no partial policy,
order, labor, stock, core, audit or financial mutation. UI never retries changed
prices automatically or reports success before a saved response.

## UI, migration and release acceptance

One Business settings disclosure contains independent Pricing and Tax sections.
Pricing uses optional rate, “Use shop default” matrix choice, current-source preview,
Save/Cancel, compact on-demand History within Pricing and a short future-work-only
note. History uses the defined paginated endpoint, not permanent main chrome.
Keep existing tax eligibility and
fixed customer footer. Matrix selection reuses P1's owner/admin list/editor links.
Forms preserve their drafts on error/conflict; a failed fetch never masquerades as
an unset agreement. No permanent large rate card, extra workspace scroller or fleet
per-line money display. Preserve directory search/Back/customer/vehicle return state.

Migration adds nullable policies/snapshots, typed tenant-safe revision references,
versions and audit storage only. Existing rates/prices/costs remain untouched.
Verify upgrade, legacy NULL compatibility and disposable downgrade/upgrade against
PostgreSQL. Production rollback retains data. Once C1 snapshots/configuration exist,
rolling back to P1-only code must pause affected new-work creation or keep the C1
policy reader compatible; do not silently fall back to different charges. Record
that operational rollback boundary in the release receipt.

Shared fixture: shop labor 145, shop matrix A revision 1. Account One labor 125 and
matrix B revision 2; Account Two unset. New external order One captures 125/B2;
Two captures 145/A1, including external PM/staged routes. Change One to 135/A2:
old order still uses 125/B2 for new work, new order uses 135/A2. Revise/archive B
after removing active customer assignment: old order still uses B2. Clear One:
future orders inherit current shop policy. Existing pre-C1 order with a saved 110
labor line retains 110 on hours/reapply/recalculate; no account snapshot appears.

Required focused evidence before independent gates:

- Exact configuration/preview envelopes, role/tenant/internal-account negatives,
  NULL versus zero, finite/precision/bounds, inactive/foreign matrix, no-op, stale
  CAS, ABA, idempotent replay and role-change-before-replay.
- Every constructor and seven labor writers use the expected policy; preview equals
  attachment. Actual external PM/staged fallback change is asserted explicitly.
  Internal preference combinations remain unchanged. Sublet remains amount-based.
- Customer/shop/matrix updates cannot change old order policy or retained labor/
  parts; saved manual overrides survive service/PM reapply and recalculation.
  Authorized manual edits without new reason/CAS friction, omitted default versus
  explicit amount, mechanic tamper, unknown legacy origin, recommendation
  idempotency and quantity/assignment/completion/restore independence are exercised.
- P1 fixed/minimum/cost protection, archive/current-customer guard, archived pinned
  revision use, legacy NULL orders/drafts and imported financial snapshots remain.
- All-new and retained counter drafts, buyer-change future-policy capture, stale preview,
  unchanged buyer contact edit, checkout and return snapshot invariance.
- Merge refuses a policy-bearing/referenced loser, including cleared policies and
  completed/deleted C1 records; both accounts remain unchanged. A configured winner
  does not unnecessarily block an untouched loser. Existing merge guards remain.
- Real PostgreSQL races: two account saves; account/matrix/shop-rate changes versus
  intake; policy change versus fleet staged preview; merge versus first C1 policy,
  order or counter reference and reverse-pair merge; manual labor edits versus
  reapply/completion. Assert actual rollback and saved-rate preservation. Do not
  claim new labor stale-form CAS or broader financial-merge race guarantees.
- Signed call reservation: precondition failure before reserve; known-success
  mapping plus final pricing409 retry without another reserve; concurrent same-key
  submissions; existing-order replay after agreement change; changed customer/
  vehicle/actor/tenant/role and inaccessible/deleted order negatives; no raw token
  persisted/logged. Simulate ambiguous provider/commit failure and preserve the
  documented limit rather than asserting exactly-once external calls.
- Standard create-then-attach conflict/cancel retains one order identity and original
  policy. No duplicate relationship/stock effects or customer sends during recovery.

Actual runtime journeys in Light and Night Shop on desktop 1280+, portrait 390/320
and landscape 740×400: configure synthetic terms, create exact-account work,
attach service/parts/recommendation, manually edit the rate, reload, change agreement,
verify old/new separation, conflict recovery, customer/search/Back and merge guard.
Counter flow only in already-authorized synthetic enabled scope. Verify readable
source/error labels, stable focus/Escape, 44px mobile targets, one scroll region and
desktop density. Restore synthetic configuration; never change real agreements or
issue real quotes/invoices/payments merely to verify C1.

High-risk finance/tenant/migration lane: independent Security and QA by fresh
nonimplementing agents, protected final-revision CI, exact merge/deployment/schema,
service health and actual production changed-journey acceptance. Root updates
board/tracker/receipt at each gate. No C1 Done or advancement to M1 without those
receipts and no unresolved required follow-up.

## Ownership and exact implementation map

Backend & Integrations owns all backend/migration/tests for this one outcome:

- New `db/models/customer_pricing.py`, `schemas/customer_pricing.py`,
  `services/customer_pricing.py`, and a narrow `services/customer_merge_guard.py`.
  Register models/router as required; endpoints may live in a dedicated
  `api/v1/endpoints/customer_pricing.py` to avoid widening generic customer writes.
- Customer/RepairOrder/Labor/CounterSale models and corresponding explicit schemas;
  next migration after the actual released P1 head.
- `api/v1/endpoints/repair_orders.py`: standard/quick intake, direct labor add/edit,
  source summaries and existing constructor/recommendation response adapters.
- `api/v1/endpoints/fleet.py`: `_spawn_internal_ro`, PM and new-order callers,
  PM/legacy/staged labor and creation preview consistency. Preserve P1 route-path
  fingerprint distinction and no-reservation legacy service semantics.
- `services/price_build_service.py`: service/book writers, retained reapply, rate
  audit and recalculation; `services/recommendation_conversion.py` plus schemas.
- `services/parts_pricing.py`, `parts_pricing_planner.py`, `parts_pricing_rules.py`
  and schemas only for context selection, safe source field and account archive
  guard; reuse P1 price math. `services/counter_sale_service.py` and its endpoint
  for buyer-change future-policy capture with existing preview/receipt behavior.
- `api/v1/endpoints/customers.py` only for the narrow C1 merge guard. No invoice,
  settlement, credit, payment or import writer changes. Quotes/invoice/receipt
  serializers are regression/privacy targets, not live account-calculation paths.

Frontend & UX owns all frontend types/queries/components/tests:

- Extract Business settings from CustomerTaxExemptionControl; add a compact
  CustomerPricingControl in the customer detail/form host without tax-role changes.
- Shared customer-pricing types/query hooks matching the exact envelopes; existing
  P1 matrix options remain manager-only.
- RepairOrdersPage, PriceBuilderPanel, recommendation conversion UI, FleetModals,
  FleetPriceBuilderPanel and intake hooks: safe source/default/intent, existing
  preview/CAS,
  retained created-order identity and fleet projection.
- CounterSalesWorkspace future-policy source notice; CustomerFormModals safe merge
  conflict message; shared Labor/RO/Counter types and focused workflow tests.

Architecture owns any cross-layer contract correction; no silent divergence of
field names or policy precedence. Product owns scope/board and release decisions.
No material product decision remains open: the external fallback was explicitly
approved. If implementation reveals a genuinely different money/ownership policy,
return it to Product before changing behavior. Routine wiring, projections,
locking and negative-case completion do not require another user approval.
