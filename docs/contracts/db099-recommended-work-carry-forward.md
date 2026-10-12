# DB-099: recommended work across truck visits

- Version: 1.0.0
- Status: Architecture contract ready for implementation; no implementation or runtime acceptance claimed
- Accountable owner: Backend & Integrations
- Contract owner: Architecture & API Contracts
- Delivery lead: Product & Delivery Lead (DB-101 intake)
- Delivery lane: High risk for the new aggregate read boundary; independent QA and Security review required. No migration, financial mutation, or worker change.
- Source inspected: `91045a6`, 2026-10-12

## 1. User outcome and first-slice boundary

When a truck returns, authorized shop staff can see its unresolved recommended
work from other visits and open the original repair order. Selecting a truck
inside a customer record exposes the same technical recommendations. Staff do
not have to remember which earlier order contains them.

The first slice adds one paginated, read-only staff endpoint and consumes it on
an existing RO or customer/vehicle surface. It may also support a staff-wide
queue. It does not copy recommendations, add priced work, resolve recommendations,
create estimates, send messages, or mutate any source order. An unresolved
recommendation remains attached to its original order with the same ID.

This is one valuable portion of ETS behavior, not full ETS parity. ETS documents
truck-level recommendations persisting into later visits and conversion to work.
Conversion, photos, invoice publication and reversal require separate contracts:
[ETS Recommendations](https://support.easytruckshop.io/en/articles/16515197-recommendations-issues-how-they-work).

## 2. Existing behavior and authorization

`RecommendedService` stores `repair_order_id`, description, priority, optional
estimated cost/notes, `is_resolved` and `resolved_by_repair_order_id`. Its inherited
`deleted_at` exists even though the current delete endpoint hard-deletes rows.
The existing collection at `GET /repair-orders/{order_id}/recommended-services`
reads one order only. Keep all existing request/response and mutation behavior
unchanged.

Existing `RECOMMENDED_SERVICES_ROLES` includes owner, admin, receptionist,
mechanic and fleet manager. It is not safe to reuse that tuple for an aggregate
query without its per-source-order checks:

- `_check_mechanic_order_assignment` requires a mechanic to be assigned to the
  source order, not merely another order for the same truck.
- `_check_ro_access` restricts a fleet manager to source orders with
  `is_fleet_work` or `is_internal`.
- The customer principal uses an exact selected tenant/customer context; a
  vehicle relationship never grants access to a former payer's financial record.

The new endpoint's exact v1 allowlist is `garage_owner`, `garage_admin`,
`receptionist`, behind `get_current_active_user`/`require_role`. These roles already
have shop-wide RO access. `mechanic`, `fleet_manager`, `customer`, `driver`, and
`super_admin` receive the existing generic `403 Access denied`; no tenant means
`400 User must be associated with a tenant`. No platform-wide tenant selector or
permission bypass is introduced. Existing per-order access for these roles remains
unchanged. UI consumers must use the same allowlist and make no request for other
roles.

## 3. Additive route and request

`GET /api/v1/repair-orders/recommended-work`

Register this static route before `/{order_id}` routes. Always return the page
envelope below; this new endpoint does not need the legacy `paginated` switch.

| Parameter | Type/default | Meaning |
|---|---|---|
| `vehicle_id` | optional UUID | Exact canonical local vehicle; never search or merge by VIN/unit text |
| `customer_id` | optional UUID | Current customer/vehicle relationship context, not the source RO's historical payer |
| `context_order_id` | optional UUID | Require `vehicle_id`; verify the order belongs to that exact truck and tenant, then exclude its own recommendations |
| `skip` | integer, default 0, minimum 0 | Offset after all visibility filters |
| `limit` | integer, default 25, range 1..100 | Bounded page size |

Examples:

- RO panel: `?vehicle_id=<truck>&context_order_id=<selected-ro>&limit=25`.
- Customer vehicle panel: `?vehicle_id=<truck>&customer_id=<selected-customer>&limit=25`.
- Optional shop queue: `?skip=0&limit=25`.

Malformed UUID, unsupported pagination values, or `context_order_id` without
`vehicle_id` return `422`. Do not silently ignore an invalid filter.

## 4. Tenant, vehicle and customer predicates

Resolve explicit context IDs using tenant predicates before building the page.
Foreign, missing or soft-deleted explicit vehicle/customer/context-order IDs
return the same `404 Recommended work context not found`. A context RO on a
different vehicle, a cancelled context RO, or a customer/vehicle pair without
the relationship below returns that same `404`. The response must not reveal
which individual ID exists elsewhere.

Every candidate must satisfy all of:

1. `RecommendedService.tenant_id == current_user.tenant_id`,
   `deleted_at IS NULL`, `is_resolved IS FALSE`, and
   `resolved_by_repair_order_id IS NULL`. Excluding inconsistent linked-but-open
   records avoids presenting a row as fresh work when a resolution link exists.
2. Join source `RepairOrder` by both its ID and matching tenant. Require its
   `deleted_at IS NULL` and `status != CANCELLED`.
3. Join `Vehicle` by source `vehicle_id` and matching tenant; require
   `Vehicle.deleted_at IS NULL`. Require the source RO's customer row to exist
   in the same tenant and have `deleted_at IS NULL`; do not return that customer's
   identity or money fields.
4. Apply `vehicle_id` exactly when supplied. A repeated VIN/unit number never
   makes two local vehicle IDs equivalent. Existing deliberate vehicle merging
   remains the only mechanism that moves source history.
5. When `context_order_id` is supplied, exclude `source_order.id == context.id`.
   Do not exclude other source orders merely because they were opened later;
   the UI says "Open recommendations for this truck", not "previous visits".
6. Completed, invoiced and paid source orders remain eligible. `DECLINED` also
   remains eligible: declining a quote does not prove the technical issue was
   resolved. Only cancelled/deleted sources are suppressed in this slice.

Use a tenant-scoped `EXISTS` for current customer linkage, not a multiplying
join. A vehicle is linked to the supplied `customer_id` when either:

- `Vehicle.customer_id == customer_id` (the existing legacy owner pointer); or
- a non-deleted `VehicleCustomerRelationship` has the same tenant, vehicle and
  customer, type `owner` or `operator`, `effective_from <= now`, and
  `effective_to IS NULL`.

Do not treat a `default_payer`-only relationship, ended relationship, future
relationship, or FleetMembership by itself as customer-vehicle access. This
matches the customer vehicles surface's owner/operator meaning while adding
explicit tenant and effective-date guards. Validate the selected customer in
the caller's tenant even when no matching recommendations exist. When only
`customer_id` is supplied, return recommendations for its currently linked
vehicles; an existing customer with no qualifying trucks yields an empty page.

Technical continuity across a change of owner is intentional for these three
shop staff roles. It does not rewrite the source RO's payer or grant the new
customer any portal access. Omit `estimated_cost`, `notes`, source customer
identity/contact, invoice IDs, balances and pricing. Staff can separately open
the source RO through its existing authorization. Recommendation descriptions
are free text and may themselves contain private information, so this endpoint
must remain staff-only even with the reduced response.

## 5. Response and ordering

`200`, `Cache-Control: no-store`:

```json
{
  "items": [
    {
      "id": "00000000-0000-4000-8000-000000000011",
      "description": "Inspect left rear wheel seal leak",
      "priority": "soon",
      "created_at": "2026-09-10T14:00:00Z",
      "vehicle": {
        "id": "00000000-0000-4000-8000-000000000012",
        "unit_number": "031",
        "year": 2022,
        "make": "Freightliner",
        "model": "Cascadia"
      },
      "source_order": {
        "id": "00000000-0000-4000-8000-000000000013",
        "order_number": "RO-0101",
        "status": "paid",
        "created_at": "2026-09-09T14:00:00Z"
      }
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 25
}
```

Vehicle `unit_number`, `year`, `make`, and `model` preserve their stored optional
values; no guessed labels or fabricated IDs. `priority` is the existing enum
`urgent | soon | monitor`. `source_order.status` uses the existing RO enum.
Timestamps retain timezone and are serialized in standard API datetime form.

Order by priority (`urgent`, `soon`, `monitor`), recommendation `created_at ASC`,
then recommendation `id ASC`. Counts and page queries must use identical full
predicates. Count unique recommendation IDs, not joined relationship rows.
Two distinct IDs with identical descriptions remain separate; deduplicate only
by the canonical ID when rendering appended pages. `skip >= total` returns an
empty page with the real total. Offset pagination is a live list, not an immutable
snapshot; a refresh may move rows when someone resolves work.

The endpoint runs bounded page/count queries without per-row source lookups.
GET calls perform no commits, database writes, history events, outbox events,
notifications, stock changes or external-provider work. No idempotency key or
migration is required.

## 6. Frontend contract

- Render each recommendation once with priority, description, recorded date and
  source order number. "Open source order" navigates to the existing
  `/dashboard/repair-orders?selected=<source_order.id>` selection route.
- Keep current-order recommendations in their existing editable section; request
  `context_order_id` so carry-forward rows cannot duplicate that section.
- Do not render Add/Convert/Resolve/Delete controls in the new section. Reading
  or opening a row must not invoke any existing mutation.
- Include tenant, vehicle, customer context, context RO, skip and limit in query
  keys. Pass cancellation signals; changing selected truck/order/customer must
  never flash stale rows. Clear previous-context data immediately.
- Refetch when returning to the source order and after existing recommendation
  mutations. The caller may invalidate the common recommended-work query prefix.
- Distinguish loading, empty, failed and partial-page states. An unavailable
  request must not say there are no recommendations. Include explicit paging
  when `total` exceeds the loaded rows; do not truncate to the first 25 silently.
- Preserve keyboard focus and readable compact layout; source links remain whole
  controls. No customer/driver/fleet-manager/mechanic surface is added in v1.

## 7. Fixtures and acceptance gates

Extend the patterns in `backend/tests/test_db003_recommended_service_tenant_boundary.py`
in a focused `test_db099_recommended_work.py`. Use synthetic entities only:

1. Tenant A, staff owner/admin/receptionist, customer Old and customer New, truck
   X. Paid source RO belongs to Old; later context RO belongs to New. Preserve
   the original source ID, payer and recommendation after reading from New's
   current truck view. Confirm old payer identity/notes/estimates are absent.
2. Tenant A truck Y has the same VIN/unit text as X and an open recommendation;
   it must never enter X's page. Tenant B rows must not enter any A page, even
   when deliberately malformed source/vehicle/customer FKs otherwise match.
3. Include resolved, linked-but-unresolved, soft-deleted recommendations; cancelled
   and deleted source ROs; deleted vehicles and deleted/foreign source customers.
   All are excluded. Include paid, completed and declined sources as positive cases.
4. Seed two active qualifying relationship rows for X; result and total remain
   one recommendation. Test ended/future/default-payer-only/foreign relationship
   rejection and the legacy pointer fallback independently.
5. Test every role: three allowed; mechanic (including context-assigned mechanic),
   fleet manager, customer with multi-shop links, driver and super-admin all 403.
   No authentication follows existing 401 behavior. Missing tenant is 400.
6. Foreign/missing/deleted context IDs, mismatched order/truck and mismatched
   customer/truck yield indistinguishable 404s. Invalid query shapes yield 422.
7. Seed more than one page, tied timestamps/priorities, duplicate descriptions
   with different IDs and a page beyond the end. Assert ordering, count, bounds
   and current-RO exclusion. Empty valid contexts return 200 empty pages.
8. Snapshot recommendations, ROs, labor/parts, settlements and provider outbox
   before/repeated GETs and source selection; verify no stored fields/counts
   change. No stock or websocket/provider effects.
9. Frontend tests cover source navigation, no mutation controls/calls, current-RO
   exclusion, all request context keys, role gating, page transition, request
   failure and rapidly switching trucks before an earlier response returns.
10. Independent QA verifies one synthetic/full-stack signed-in desktop and compact
    journey plus independent Security review of the new aggregate read boundary.
    Synthetic frontend-only preview is useful evidence but does not substitute
    for authenticated API/runtime acceptance.

Runtime at intake is blocked: worktree `backend/.env` is absent, port 8000 is
unbound, and port 5173 belongs to another worktree. Preserve those services and
follow dieselbridge-local-runtime before implementation/local browser QA. Do not
claim full-stack visibility until its alignment and verification complete.

## 8. Related audit findings, outside this slice

**Service-template completion checklist parity is missing.** Service templates
already carry labor duration/rate and parts (`db/models/service.py:27-82`), but
neither Service nor Labor has configurable template checklist definitions or
per-job completion items. `repair_orders.py:2557-2584` completes work based on
assignment/status; `:2916-3017` checks status/pricing/customer authorization, not
template items. The existing checklist is a separate fixed fleet inspection
template (`db/models/fleet.py:27-52`), with its own completion rules
(`api/v1/endpoints/fleet.py:777-788`). It is not a service-template checklist gate.
Design template versioning, copied job-item state, server-side completion rules
and override audit under another item before implementing that feature.

**Profitability defect is confirmed, not absent reporting.** Canonical pricing
sets `total_parts_cost` from `PartsUsage.total_price` and `total_labor_cost` from
customer-charge `Labor.total_cost` (`services/pricing.py:58-89`). Analytics
incorrectly subtracts those retail sums as costs and clamps losses to zero
(`api/v1/endpoints/reports.py:1171-1179`, `:1233-1248`). Real parts cost is
`PartsUsage.unit_cost * quantity`; the existing parts report already uses it
(`reports.py:773-788`). Sublet expense exists as `Labor.vendor_cost`; no labor wage
cost snapshot exists in Labor/User. Repair reporting separately with explicit
missing-cost coverage and meaningful metric labels. Do not invent labor cost,
call an incomplete contribution net profit, or treat a null cost as known zero.

**Receivable aging is an opportunity, not ETS parity.** ETS itself documents no
native aging report: [ETS A/R guidance](https://support.easytruckshop.io/en/articles/16739469-who-owes-me-money-getting-your-a-r-and-building-an-aging-report).
Keep any proposed receivables feature separate from this technical-work queue.
