# DB-107 — Tracked recommendation-to-operation conversion

Status: Architecture-approved implementation contract, 2026-10-12. Backend & Integrations accountable;
Product & Delivery Lead coordinates. Source branch `codex/recommendation-conversion`
is stacked on PR505. Local preview intentionally remains the combined branch on
5174/API8001. This contract authorizes no merge, production migration, or deployment.

## Outcome and boundaries

A shop staff member adds previously recommended work to the current truck's repair
order without copying away its origin. The operation links to the recommendation
and original order. Repeated clicks, retries, and concurrent requests produce one
operation. Removal/cancellation is visible and requires a deliberate replacement;
an old retry never resurrects work. Conversion is **not completion** and must not
change recommendation resolution, order status, payments, or authorization.

Allowed actors are the existing cross-order recommendation roles:
`garage_owner`, `garage_admin`, `receptionist`. Customer, driver, mechanic and
fleet-manager callers do not gain cross-order access through this endpoint.
All lookups, including target/source customer, truck, and conversion
joins, require the current tenant. Missing and foreign-tenant identities share a
404. Do not accept a tenant, source description, source order, vehicle, actor, or
resolution state supplied by the client. Duration and displayed rate are explicit
operator inputs, validated as described below.

## Existing behavior that constrains this change

- `RecommendedService` is an unresolved source-order note. DB099 reads open notes
  on the exact truck, excludes the current source order, and has a reduced
  three-role staff projection. Preserve its source/tenant/customer joins.
- Existing labor/service operations are `Labor` rows; there is no separate
  operation aggregate. Parts use `source_line_id` or `source_service_id` grouping.
- Labor duration is finite 0.01–999.99 hours at up to two decimal places. A zero-hour
  placeholder is invalid; a guessed hour or copied estimated cost is unacceptable.
- `PriceBuildService.add_flat_service_line` resets an existing row of the same
  template. Template mapping is deliberately deferred from DB107. This endpoint
  creates one manual operation; it never applies/reset a template or its parts.
- Existing line deletion physically deletes `Labor`; repair-order deletion is
  restorable soft deletion, and cancellation retains at least the labor history.
- The combined preview includes DB100 checklist snapshot/archive hooks and schema
  revision `165_service_checklists`; the source base currently ends at164. Preserve
  those hooks when integrating. Manual conversion does not create checklists or
  interact with template snapshots.

## Durable data

Add `recommendation_conversions`, with standard UUID/timestamps and:

| Field | Contract |
| --- | --- |
| tenant_id | Required tenant FK |
| recommendation_id | Required source recommendation FK; no delete cascade |
| source_order_id | Required original RO FK; no delete cascade |
| source_order_number | Immutable display snapshot |
| source_description | Immutable recommendation description snapshot |
| source_priority | Immutable priority snapshot |
| vehicle_id | Required truck FK at conversion time |
| target_order_id | Required destination RO FK; no delete cascade |
| target_order_number | Immutable display snapshot |
| target_labor_id | Required immutable UUID identifying the created labor row |
| request_id | Client UUID for one logical submit |
| request_hash | Canonical hash of recommendation, target, duration, rate and replacement ID |
| hours, hourly_rate | Immutable validated numeric creation inputs, for retry comparison |
| created_by_user_id | Server actor FK |
| superseded_at | Nullable; set only by an explicit successful replacement |
| superseded_by_conversion_id | Nullable self FK for the replacement |

`target_labor_id` is an audit reference, deliberately not a cascading labor FK:
existing hard line deletion must leave the exact original UUID in the record.
Existence/state is determined by a tenant-and-order-scoped join. Unique indexes:
`(tenant_id, request_id)`, `(tenant_id, target_labor_id)`, and partial unique
`(tenant_id, recommendation_id) WHERE superseded_at IS NULL`. Retain all superseded
rows. Do not mutate provenance fields during ordinary labor/template editing.
No client write schema accepts these provenance fields.

The source recommendation cannot be physically deleted once any conversion exists:
return409 `recommendation_has_conversion` with a useful message; resolving it is
still supported. Unconverted delete behavior is unchanged. Source order soft
removal retains snapshots and underlying recommendation; operation provenance
remains visible but its source navigation is marked unavailable if not accessible.

## Write API

`POST /repair-orders/{target_order_id}/recommended-work/{recommendation_id}/convert`

Request:

```json
{
  "request_id": "a1111111-1111-4111-8111-111111111111",
  "hours": "1.25",
  "hourly_rate": "145.00",
  "replaces_conversion_id": null
}
```

Required duration follows `validate_labor_hours`: finite0.01–999.99 at up to two
decimal places. Required hourly rate is finite0–99,999,999.99 at up to two decimals,
matching Numeric(10,2); reject precision loss, negative or non-finite values.
Initialize the form to the tenant's existing customer labor rate. Customer-order
staff may explicitly adjust that rate like ordinary labor editing. For an internal
order the displayed/submitted rate must match the canonical customer-vs-internal
rate policy; a stale policy rate returns409 `pricing_changed`, never silently
changes the user's reviewed price. No estimated cost is converted to hours/rate.
The preview total is the explicitly entered hours × rate, with canonical monetary
rounding used by normal labor. Description comes from the source recommendation.
Create a normal manual operation, avoiding repair-operation memory, estimate
providers, template reuse, inventory or checklist side effects. No `service_id`,
quantity, or other mode is accepted in this request.

Return201 for a newly created conversion,200 for replay/already-linked exact
conversion. The response is independent of the large price-build response:

```json
{
  "conversion": {
    "id": "b1111111-1111-4111-8111-111111111111",
    "recommendation_id": "c1111111-1111-4111-8111-111111111111",
    "source_order": {
      "id": "d1111111-1111-4111-8111-111111111111",
      "order_number": "QA-PRIOR-VISIT",
      "available": true
    },
    "source_description": "Inspect steering play",
    "target_order": {
      "id": "e1111111-1111-4111-8111-111111111111",
      "order_number": "QA-CURRENT-VISIT",
      "status": "in_progress",
      "available": true
    },
    "labor_id": "f1111111-1111-4111-8111-111111111111",
    "state": "active",
    "created_at": "2026-10-12T18:00:00Z",
    "can_replace": false,
    "can_resolve": false
  },
  "replayed": false,
  "warnings": []
}
```

Warnings use the existing `{code,message,line_id}` shape; this plain-operation
path ordinarily returns an empty list.
Invalidate/refetch price-build, selected-order details/totals, labor/parts,
recommended-work, source recommended-services, and checklist queries. Do not
optimistically invent a labor row before receiving the exact returned identity.

## Transactions, replay and concurrent calls

1. Authorize the role/tenant before any disclosed data. Acquire existing
   `lock_tenant_financials` before financial/order row locks, coordinating with
   cancellation/deletion/restore/finalization. Its busy result remains retryable.
2. Locate `(tenant_id, request_id)`. Same canonical hash returns the original
   conversion's **current** derived state without writes, even if its line was
   later removed, its target cancelled, or it has since been superseded. A reused
   UUID with a different hash is409 `idempotency_key_reused`.
3. Lock the target order, then the source recommendation (`FOR UPDATE`). Reload
   and validate tenant/truck/source state inside the transaction. Target must be
   present, nondeleted, editable under canonical status/lock rules, and its
   `source` must not be `easy_truck_shop_import`. Source recommendation and source
   order/customer/truck must be current and nondeleted/noncancelled for a **new**
   conversion. Source and target trucks must match. Same-source-order conversion
   is permitted where exposed; DB099 aggregate continues to exclude it normally.
4. Recheck request replay after locking. If an unreplaced conversion exists on
   this target and request duration/rate matches its creation input fields, return
   it200 without changing values; if its input differs,409 `already_converted`.
   A live conversion on a different target is always409 `already_converted` with
   its safe projection. UI navigates to that operation instead of adding again.
5. Removed/cancelled/deleted-target recovery requires the exact current
   `replaces_conversion_id` and a **new** request UUID. Without it return409
   `replacement_confirmation_required`; stale/foreign replacement IDs return409
   `conversion_changed` (no foreign detail). Validate the old state again under
   the financial lock and appropriate target locks. Only the current unresolved
   recommendation can be replaced. Mark prior row superseded and insert new row
   atomically with the new work. Any failure rolls both changes back.
6. Insert work and conversion, recompute totals through existing logic, and add
   one ordinary repair-order history event explaining the source order. Commit
   once. No nested service commit, notification/provider call, or completion write.
   Unique constraints are a final backstop; on a race re-query the winning
   conversion under tenant scope and return replay/conflict, never500.

Recommendation update/delete acquires the recommendation row lock so a concurrent
resolution or deletion cannot race a new conversion. Keep lock ordering consistent;
source update/delete do not lock an unrelated target order after this row lock.

## State, recovery and resolution

Derived `state` precedence: `superseded`, `target_deleted`, `target_cancelled`,
`operation_removed`, `active`. Completed/invoiced/paid targets remain `active`
linked history; they do not automatically make a recommendation resolved.
`can_replace` is true only for the current unresolved conversion in
removed/cancelled/deleted state. No replay or GET writes a state transition.

Cancelling or soft-deleting a target does not erase its link or silently make a
new operation elsewhere. UI states why the existing operation is unavailable and
offers an explicit “Add again”/“Add to this order” confirmation with the prior
conversion ID. A removed operation can be recreated on the same editable order.
If an old order is restored/reactivated after its conversion was superseded while
its old labor row still exists, reject restoration/reactivation with409
`superseded_recommendation_work` and the current safe target link. The operator
must use the current work record. Do not permit two executable operations by
restoring stale work. Apply this guard to restore and status transitions from
cancelled/deleted to actionable states, including applicable override paths.
Restoration before replacement is allowed and makes the same link active again.

Resolution remains explicit using the existing source recommendation PATCH. For a
converted recommendation, setting `is_resolved:true` must reference its current
conversion target in `resolved_by_repair_order_id`, and that target must still
contain the operation and be completed/invoiced/paid (not cancelled/deleted).
Otherwise409 `converted_work_not_completed`. `can_resolve` reflects this rule;
Converted resolution-field edits are restricted to the same three staff roles;
nonstaff errors never include conversion metadata. Existing unconverted manual
resolution is unchanged. Resolved state and completion-order reference cannot be
cleared independently; clearing the reference requires explicit reopening. Reopening a recommendation
clears `resolved_by_repair_order_id`; it retains its historical conversion and
therefore does not create a duplicate. Source deletion remains blocked after
resolution because provenance is still required.

## Read projections and UI

Add optional `conversion` to DB099 `RecommendedWorkItem` and to staff
`RecommendedServiceResponse`; null means never converted. Show the current/latest
conversion, including unavailable states; unresolved converted notes stay in the
open recommendations list with an “Added to #…” state and target link, not a
second Add button. Preserve DB099 pagination, exact vehicle scoping, minimized
nonfinancial projection and cross-role cache guards.

Staff price-build summary also adds `recommendation_hourly_rate` (canonical
customer/internal policy rate) and `can_convert_recommendations` (role, editable
status and ETS guard). Other roles receive null/false. The form fails closed
unless can_convert_recommendations is explicitly true.

Expose optional `recommendation_source` on **staff price-build labor lines**:
`conversion_id`, `recommendation_id`, `source_order {id,order_number,available}`,
`description` snapshot, and `state`. This is server-projected, never editable.
Show an understated “From recommendation · #source” link on the operation and the
original recommendation description when the operation has been renamed. The information survives description/rate/hour edits and reload.
Do not broaden customer/mechanic/fleet cross-order read contracts: only populate
this projection for the existing three staff roles, and do not accidentally expose
it through ordinary customer repair-order detail serialization.

The compact conversion UI is attached to the recommendation and names the current
truck/order. Hours starts blank; the actual tenant rate and calculated amount are
visible, and the staff member can edit the customer-order rate. Confirmed submit is disabled while pending, keeps its UUID on an
unknown/failing outcome, retains inputs on error, and offers a retry. Cancel or
opening the form writes nothing. Changed input after an unknown result must first
reconcile the original request; do not reuse its UUID with a different payload.
Success reveals/focuses the exact new operation using `?operation=<labor UUID>`.
Source navigation uses `?recommendation=<source recommendation UUID>` and opens the
original note read-only even when the source order is completed/invoiced/paid; do
not make historical source work editable to show it. Source/target navigation
preserves Shop Work queue context. Error/conflict actions offer the already-created record.
Desktop remains dense;390/320px controls must wrap as whole buttons,44px touch
targets, no horizontal overflow, focus/keyboard/Escape and complete labels.

## Error envelope

Use `HTTPException(detail={"code":...,"message":...,"conversion":...})` for new
structured errors; omit conversion except when accessible and useful. Frontend
accepts legacy string detail from existing price-build/template errors.

| Status | Codes / meaning |
| --- | --- |
|401/403| Existing authentication/role denial |
|404| `recommendation_not_found`, `target_not_found`, `context_not_found`; foreign IDs are indistinguishable |
|422| Shape/UUID validation; invalid exact duration/rate; extra fields rejected |
|409| `recommendation_resolved`, `vehicle_mismatch`, `target_not_editable`, `target_ets_managed`, `pricing_changed` |
|409| `already_converted`, `idempotency_key_reused`, `replacement_confirmation_required`, `conversion_changed` |
|409| `recommendation_has_conversion`, `converted_work_not_completed`, `superseded_recommendation_work` |
|existing retryable lock error| Preserve financial lock busy semantics; retry same request UUID |

## Acceptance evidence required

- Backend real DB integration: plain creation, correct hours/rate/total, provenance
  reload, resolution unchanged, source link after description edits, no template/
  inventory/checklist mutation; valid customer rate override and internal policy guard.
- PostgreSQL concurrency (not SQLite): same UUID replay, two different UUIDs same
  recommendation/target, two target orders concurrently, conflicting payload,
  lost response retry. Exactly one current link/operation; no duplicate totals,
  history event; no inventory/checklist mutation. Rejects leave no partial work.
- Isolation: foreign recommendation/source/target/truck/replacement/key
  and forged optional fields; disallowed roles; malformed source joins; no PII or
  wrong-tenant projection in errors. Same truck with historical customer ownership
  is permitted when existing DB099 source access is valid.
- Lifecycle: normal and price-build line deletion preserve provenance; old retry
  cannot recreate; explicit replacement creates one new operation; cancellation/
  soft-delete state, replay, replacement and superseded restore/reactivation
  guard; ordinary restore before replacement; converted source delete rejection;
  explicit resolution only after real completed work and correct target.
- Frontend focused tests: linked state/no Add, immutable source, manual validation,
  rate/total preview, pending duplicate clicks, retry UUID and inputs,
  stale context cannot populate a different order, same queue navigation,
  failure/conflict recovery, disallowed role and finalized/ETS target guards.
- Signed-in actual desktop and390/320px browser: create tracked manual work,
  reload and source/target navigation; attempt duplicate; remove/re-add and
  cancellation recovery; finish test work then explicit resolution. Check totals,
  warning/error visibility, keyboard actions, focus, touch sizing and overflow.
  Synthetic isolated local fixtures only; retain/remove according to parent QA
  cleanup plan. Viewport evidence does not claim physical phone testing.
- Independent Security and QA gates after implementation, then protected CI.
  Do not mark Done without authorized merge/deploy evidence.

## Migration and rollback

One additive migration creates the conversion table/indexes; no backfill guesses
links between existing notes and similarly worded labor. Existing responses add
nullable fields and preserve old clients. Source Alembic currently has164 while combined preview has165. Approved graph:
source additive `166_recommendation_conversion` has down_revision
`164_motive_driver_journal`, retaining one focused source head. Combined preview
alone receives an explicit merge revision joining `165_service_checklists` and
`166_recommendation_conversion`. Verify both source and preview heads. Later
integration of the independent checklist branch requires that explicit merge;
record this prerequisite in release evidence. Do not apply two unmerged heads to
production. Parent owns preview schema integration/restart.

Run upgrade/downgrade/upgrade only on a disposable database and verify real
PostgreSQL unique-index semantics. Apply only an additive upgrade to authorized
local preview after preserving current fixtures/config. Rollback is application
code rollback while **retaining** the additive conversion schema/evidence. A
production downgrade after adoption would destroy provenance and needs separate
explicit authorization. Stop rollout on tenant leakage, duplicate line/stock
mutation, lost provenance, unexpected pricing or failed lifecycle guards.

## Handoff

Board ID: DB-107. From Architecture & API Contracts to Backend/Frontend.
Scope completed: contract and repository evidence only; no implementation edits,
no browser/runtime changes. No unresolved product ambiguity: conversion schedules
work, explicit resolution confirms completion, replacement is deliberate.
Next action: implement approved source/preview migration ancestry and code against
these response fixtures and acceptance cases. Return any contract deviation to
Architecture before silently changing lifecycle or pricing behavior.
