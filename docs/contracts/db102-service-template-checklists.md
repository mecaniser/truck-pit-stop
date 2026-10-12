# DB102 — Service-template checklists and job completion

Status: Architecture contract for implementation, 2026-10-12. Product & Delivery
Lead owns the board; Backend & Integrations is the accountable implementation
owner. This is the high-risk lane because it adds persisted records and a
completion gate. Independent QA and Security reviewers must not be the contract
author or implementing agents.

## User outcome and acceptance

An owner/admin defines ordered tasks on a service template. Applying that service
to a work order takes an immutable copy of those tasks. The assigned mechanic or
authorized staff can check and reopen tasks, with their identity and the server
time recorded. Required tasks must be finished before the work is submitted for
review or finalized. Optional tasks do not block completion.

1. An administrator can save, reorder, edit, and remove up to 50 template tasks;
   each has a nonblank label and an explicit Required switch, on by default.
2. A newly applied service receives independent unchecked task copies. Editing
   the template later changes future applications only. Reapplying an existing
   service must not reset its tasks or retrofit historical jobs.
3. The work-order editor, mechanic job detail/expanded job, and fleet work-order
   detail expose the same persisted progress. A full reload preserves checks.
4. Required incomplete tasks stop **every supported completion path** before
   timers, points, notifications, invoices, PM advancement, incident resolution,
   or status changes. The message explains the remaining count and opens the
   checklist. Completing the tasks allows the existing completion workflow.
5. Existing orders without snapshots retain their current behavior. This is not
   a retrospective inspection requirement. Customer-facing documents, prices,
   invoices, provider settings, and historical service notes are unchanged.
6. Cross-tenant, unassigned-mechanic, customer/driver, deleted-record, stale-write,
   frozen-order, and concurrent-completion cases have negative tests.

No DOT certification, attachments, signatures, per-task billing, per-service
technician assignment, bulk check-all, waiver, or compliance claim is introduced.
This is one checklist per applied labor/service line, regardless of its billed
quantity; labels describe the work the technician must verify for that line.

## Existing source and integration boundaries

Baseline inspected: `91045a625f89d84221aaf8ed74d1cdc7d92438b6`.

| Existing behavior | Required hook |
|---|---|
| `backend/app/db/models/service.py`: Service is the catalog/template; parts are ServicePart rows | Add template JSON and checklist revision to Service; do not put tasks in description or internal_notes |
| `backend/app/services/price_build_service.py:273`: `add_flat_service_line` creates a Labor carrying `source_service_id`; reapply updates that existing line | Snapshot only in the new-line branch, in the same transaction; preserve snapshots in the existing-line branch |
| The same service's `add_repair_operation_line` routes `service:<uuid>` through `add_flat_service_line` | Covered by the canonical helper; do not create a second snapshot |
| `repair_orders.py`: legacy POST `/{order_id}/labor` can create Labor with `source_service_id` | Snapshot on creation here too, after scoped source validation |
| `fleet.py`: `_set_wo_pm_services` reseeds Labor; deprecated `add-service` also creates Labor | Snapshot all genuinely new service applications; preserve snapshots for retained PM services when their labor IDs are replaced |
| `repair_orders.py`: mechanic `complete-work`, `admin-complete-work`, `approve-completion`, generic PUT status | Invoke the shared gate under the order row lock before side effects |
| `fleet.py`: POST `/work-orders/{ro_id}/complete` has its own finalization path | Invoke the same gate before completion, invoicing, PM advancement, and incident changes |
| `PriceBuildService.remove_line` and legacy DELETE `/{order_id}/labor/{labor_id}` hard-delete Labor | Archive snapshots first and preserve their history; removed scope no longer gates completion |
| `ServicesManagementPage.tsx` owns staff template editing | Add the template checklist editor here, not the customer `ServicesPage.tsx` |
| `RepairOrdersPage.tsx` sets `showLegacyPriceEditor = false`; current new-order creation applies selected services through `price-build/flat-service` | Mount the checklist in the active editor and retain canonical application. Do not interpret historical `internal_notes.selected_services` as a new execution snapshot |

Template lookup APIs currently serve customer booking as well as staff. Keep the
new checklist definition endpoints staff-only instead of appending internal task
text to every existing ServiceResponse. Existing service read authorization
defects must not be inherited by the new endpoints.

## Persistence and migration

Add migration `165_service_checklists` after `164_motive_driver_journal` (reconcile
the revision number if main advances before implementation).

On `services`:

- `checklist_template`: JSONB in PostgreSQL / JSON variant in SQLite; non-null,
  default empty array. The application always replaces the whole value with a
  freshly validated ordered list, never relies on in-place JSON mutation.
- `checklist_version`: integer, non-null, server/application default 0.
- Each template entry: `{id: UUID, label: string, required: boolean}`. IDs are
  server-generated for new entries and stable across edits/reordering. A client
  may retain a current entry ID, never insert an arbitrary foreign/unknown ID.

New `repair_order_checklist_items` model/table, using BaseModel timestamps:

- `tenant_id`, `repair_order_id` are non-null foreign keys; the order FK uses
  ON DELETE CASCADE for a true parent purge. Normal RO deletion is soft deletion.
- `labor_id`: nullable FK to Labor, ON DELETE SET NULL. `labor_id_snapshot`:
  non-null UUID of the original application, no cascading source FK.
- `source_service_id_snapshot`, `source_template_item_id`,
  `source_template_version`: immutable provenance values, not live joins.
- `service_name_snapshot`, `label`, `required`, `position`: immutable snapshots.
- `is_completed`: non-null false; `completed_at`, `completed_by_user_id`,
  `completed_by_name`: nullable server-written completion evidence. Name is a
  display-name snapshot; do not fall back to exposing an email address.
- `version`: positive integer, initially 1, incremented on each actual state
  change. `removed_at`: nullable timestamp for scope removal.
- Index `(tenant_id, repair_order_id, removed_at, position, id)` and `labor_id`;
  unique `(labor_id, source_template_item_id)` for active attachment. Checks for
  nonnegative position, positive version, nonempty bounded labels, and matching
  completion boolean/evidence nullability.

User IDs in evidence are snapshots, not cascading user relationships, so renames
or account removal cannot erase attribution. A removed labor line must not erase
checklist evidence. The gate/read joins must additionally verify that the live
Labor has the same tenant and order and is not soft-deleted; never trust child
tenant_id alone. Missing/malformed source joins cannot widen access or count as
another order's completed work.

Use existing `RepairOrderHistoryEvent` for append-only events:
`checklist_created`, `checklist_completed`, `checklist_reopened`, and
`checklist_scope_removed`. Store actor ID/name, checklist item ID as entity_id,
server time, and the snapshotted service/task text. A same-state no-op creates no
event. Because the current order-detail serializer also returns history to
customers, explicitly exclude these four internal event types from customer
history responses. New checklist endpoints deny customer/driver access entirely.

No data backfill: every pre-migration order starts with zero checklist rows.
Downgrade removes only the new table/columns, but destroys newly recorded task
evidence; use application rollback with additive schema retained after adoption,
not an automatic destructive downgrade. Rollout order is migration, backend,
then frontend. Check migration upgrade on a clone at 164 and verify one head.

## API contract

Use schemas in `backend/app/schemas/service_checklist.py`, shared business rules
in `backend/app/services/service_checklist.py`, and thin endpoints. Existing
`services.py` and `repair_orders.py` routers may host the routes. No provider,
worker, notification, or external API dependency is needed.

### Template definition

`GET /api/v1/services/{service_id}/checklist`

Read roles: garage_owner, garage_admin, receptionist, mechanic, fleet_manager.
Require an explicit tenant. Select Service by both ID and current tenant, with
deleted_at null. An inactive service remains readable/editable by its own staff;
normal application still requires an active service.

```json
{
  "service_id": "11111111-1111-4111-8111-111111111111",
  "version": 2,
  "items": [
    {"id": "22222222-2222-4222-8222-222222222222", "label": "Verify drain plug is secure", "required": true},
    {"id": "33333333-3333-4333-8333-333333333333", "label": "Record filter brand", "required": false}
  ]
}
```

`PUT /api/v1/services/{service_id}/checklist`

Write roles: garage_owner and garage_admin only. Request:

```json
{
  "expected_version": 2,
  "items": [
    {"id": "22222222-2222-4222-8222-222222222222", "label": "Verify drain plug is secure", "required": true},
    {"label": "Check for leaks with the engine running", "required": true}
  ]
}
```

Return the GET shape with server IDs and new version. Require 0–50 entries;
trim labels and require 1–300 characters; reject duplicate IDs, unknown IDs,
extra fields, invalid types, and negative expected_version with 422. Labels may
repeat because distinct physical checks can share text. Array order is the task
order. Empty array explicitly removes the future template's tasks.

Lock the Service row and compare expected_version. Mismatch: 409
`"This checklist changed. Reload it before saving."`. Exactly unchanged content
at the expected version is a no-op and preserves version. Otherwise replace JSON
and increment version atomically. A retry with an old version returns 409 and
never overwrites another author's changes. Do not silently retry mutations.

The existing service editor can save base service details and checklist in two
explicit API steps, but must retain unsaved checklist edits and state a partial
failure accurately. For a new service, create the service first, then save its
checklist with expected_version 0; a failed second step leaves the editor open
on the created service, so retry cannot create a duplicate service.

### Work-order checklist

`GET /api/v1/repair-orders/{order_id}/checklist?skip=0&limit=100`

Return flat ordered items, grouped by service application in the frontend:

```json
{
  "items": [{
    "id": "44444444-4444-4444-8444-444444444444",
    "labor_id": "55555555-5555-4555-8555-555555555555",
    "service_name": "Oil service",
    "label": "Verify drain plug is secure",
    "required": true,
    "position": 0,
    "is_completed": false,
    "completed_at": null,
    "completed_by": null,
    "version": 1
  }],
  "total": 1,
  "skip": 0,
  "limit": 100,
  "summary": {"total": 1, "completed": 0, "required": 1, "required_remaining": 1},
  "can_update": true
}
```

Completed `completed_by` is `{ "id": "<actor UUID>", "name": "Casey Mechanic" }`
and completed_at is UTC ISO 8601. Paging uses skip >=0 and limit 1–100; order by
labor creation/id, then item position/id. Summary/total count the entire active
scope, not the current page. No archived rows are included; removal and prior
state remain in staff order history. Zero rows returns an empty page and zero
counts, not an error. Set Cache-Control: no-store.

Roles: owner/admin/receptionist can read same-tenant orders; mechanic must be the
order's currently assigned mechanic; fleet_manager must additionally satisfy
the existing fleet order scope (`is_fleet_work` or `is_internal`). All source,
order, task and live labor predicates use the selected request tenant. Customer,
driver, super_admin and other roles get 403. No tenant gets 400. Missing,
cross-tenant or deleted order/item gets generic 404. Same-tenant but unassigned
mechanics/non-fleet orders for fleet_manager get 403 without task data.

`PATCH /api/v1/repair-orders/{order_id}/checklist/{item_id}`

```json
{"is_completed": true, "expected_version": 1}
```

Return the updated item plus the full-scope summary and can_update. Same read
roles can write subject to assignment/fleet scope. The order must be in_progress
or pending_review, not deleted/cancelled/finalized, and must have no active
financial/pricing lock. An on-hold in_progress job may record an already
performed check; this does not resume its timer. Draft/quoted/approved/assigned/
acknowledged states are read-only until work starts. Completed/invoiced/paid are
read-only. Return 409 `"Checklist changes require an open work order."` for
state/lock failure. Read response can_update is computed with exactly these rules.

Acquire the repair-order row lock first, then load/validate the target task and
live labor under that same tenant/order. Re-check mechanic assignment after the
lock. Compare expected_version; mismatch is 409 `"This task changed. Refresh the
checklist and try again."`. Same state at current version is a no-op preserving
actor/time. A change to true records current authenticated actor and server time;
false clears current completion evidence, increments version, and appends a
reopen event retaining the old evidence in history. Clients cannot supply actor,
time, label, required flag, source IDs, or order/tenant IDs in the body.

## Snapshot, lifecycle, and concurrency rules

- One shared snapshot helper accepts the already validated tenant, locked order,
  new Labor row, Service's whole JSON/version, and optional authenticated actor.
  Flush the new line before creating tasks. Templates with no tasks produce no
  checklist rows. Snapshot and labor/parts application commit or roll back
  together. Automation-originated PM creation records an explicit system actor
  label, never pretends a mechanic performed a task.
- Read the template JSON/version as one Service row value; concurrent template
  save yields either the old complete revision or the new complete revision.
  Avoid mixed revisions and avoid holding a Service lock while acquiring an
  order lock. Template PUT locks only Service; order operations lock RO first.
- Reapplying an existing line, changing price/hours/quantity, or recalculating
  does not resnapshot. This includes historical lines without any tasks, and
  new lines whose original template had zero tasks. No retroactive task creation.
- Legacy Labor update may not change `source_service_id` on an existing line
  with checklist snapshots: 409 `"Remove this service and add the replacement
  to change its checklist."`. Ordinary description/hour/rate edits preserve the
  execution snapshot. New Labor with source_service_id always snapshots.
- Fleet PM reseeding must map retained services' old/new Labor rows while the RO
  is locked and reattach existing task rows unchanged (including an empty prior
  snapshot). Only newly selected services obtain current template tasks. Removed
  services are archived. This is important even in draft: an older draft must
  not unexpectedly inherit a template revision. A no-change PM selection cannot
  duplicate tasks. Reject an ambiguous duplicate old service-line mapping with
  409 rather than attach another line's history arbitrarily.
- Line deletion archives tasks (`removed_at`, detach labor_id) and records scope
  removal in the same transaction. Existing line edit/delete permissions remain;
  checklists do not create a new mechanic permission to remove required work.
  Re-adding a removed service is a new unchecked application of the current
  template. The old snapshot/history remains retained.
- Cancel or soft-delete the whole order: retain task rows unchanged and freeze
  writes. Restore uses the existing status workflow and restores the same
  progress. Existing internal-order reopen (and invoice void returning to review)
  does not automatically erase checks; authorized staff can explicitly uncheck
  a task to require rework. No new reopen route or finalized-customer bypass.
- Template deactivation/removal does not affect existing snapshots. No joins to
  current template text are used when displaying or gating historical work.
- Legacy `internal_notes.selected_services` is a historic pricing envelope, not
  executable task scope. Do not backfill it, rewrite it, or infer completion from
  it. The currently enabled template application paths above are required.

Use `SELECT ... FOR UPDATE OF repair_orders` (not unqualified joined locking)
for task updates, line changes and completion. For routes already taking the
tenant financial lock, retain that lock before RO; checklist writes take only RO
and never acquire the tenant lock afterward. Generic RO PUT must acquire the RO
row lock too, so status/assignment changes serialize with checklist writes.

The completion guard runs on all four explicit completion routes and on generic
RO PUT when changing status to pending_review/completed/invoiced/paid. It counts
required unchecked active snapshots through tenant-matched live Labor. If any
remain, return 409 with a **string** detail, preserving existing toast contracts:

`"Complete the 2 required checklist tasks before finishing this work order."`

The frontend refreshes/opens the checklist on this 409; it does not turn failure
into an optimistic completed state. The server gate always evaluates the entire
order, even if the client has only loaded the first checklist page. After the
guard passes, retain every existing authorization, financial, role and status
check. No unchecked optional task is a blocker. Zero snapshots is a no-op gate.
Completion versus uncheck must serialize: uncheck first prevents completion;
completion first freezes further task changes. The block leaves timers, points,
status, invoice count, notifications, PM mileage/date and incident state intact.

## Frontend implementation

Create `frontend/src/features/service-checklists/` with shared types/query keys,
template editor, and work-order checklist component. Owner/admin editor sits
inside `features/dashboard/ServicesManagementPage.tsx`. Show task label, Required,
up/down reorder and remove controls; no drag-only interaction. Compact labels and
whole button text must stay on one line. Use the app's Lucide chevron if collapsed.

Use the same order component in `PriceBuilderPanel.tsx` (read-only at finalized
states), `MechanicPortalPage.tsx` full detail and expanded job, and
`FleetPriceBuilderPanel.tsx`/fleet detail where that shell owns the order actions.
Avoid two mounted copies in the same order shell. A clear header shows
`Checklist · 3/5` and `2 required remaining`; list completion actor/time beside
checked tasks, with optional tasks visibly marked. Hide an empty checklist
section without suppressing loading/error states. No customer-portal rendering.

Keep mutations pessimistic, disable only the pending task, and use item version
from the last confirmed response. 409 refreshes the scope and requires a fresh
operator action; do not automatically apply their stale check. React Query keys
include tenant ID, order ID and pagination, and mutations invalidate that order's
checklist and relevant detail/history. A tenant/order switch cancels or ignores
prior responses. Loading/error must never render the entire job as cleared.
Use a visible Load more control for more than 100 rows; the header continues to
use full summary counts. Completion buttons may show the remaining-task hint,
but the server remains authoritative (including mechanic quick Job Done).

## Shared fixtures and gates

Use synthetic tenants A/B, owner A, admin A, receptionist A, assigned mechanic A1,
unassigned mechanic A2, fleet manager A, customer A, driver A and owner B. Template
T-A has two required tasks and one optional; T-B has identical labels under a
different tenant. Orders: active customer A assigned A1; active unassigned A;
active internal fleet A; pending_review A; frozen A; historical A without
snapshots; and order B. No test invokes live payment or messaging providers.

Backend proof must cover:

- Definition save/reorder/remove/empty, ID validation, 50/51 and 300/301 limits,
  authorization, foreign service lookup, optimistic template conflict.
- Every application hook; independent jobs; current version copied; old label,
  required flag, ordering and progress remain after template edit/deactivate;
  existing-line reapply, zero-task original and historical reapply create nothing.
- Fleet PM retained/added/removed/no-change reseed, no duplicate snapshots, and
  ambiguous duplicate source mapping rejection with no partial mutation.
- Assigned mechanic check/uncheck attribution; same-state no-op; stale version;
  assignment change while editing; final/initial/cancelled/deleted states; payload
  spoofing, role restrictions and corrupted child tenant/order/labor joins.
- Each completion route and generic status transitions block required incomplete
  tasks with zero side effects; allow optional incomplete, complete required, and
  historical no-snapshot cases. Existing completion financial checks still apply.
- PostgreSQL two-session completion/uncheck race, template update conflict and
  line-delete/check race; serialized order and no deadlock. SQLite tests alone
  cannot establish row-lock behavior.
- Both line deletion paths retain history and remove the blocker; re-add creates
  fresh tasks; RO cancel/delete/restore and internal reopen preserve evidence.
- Customer detail does not expose new checklist event text/actor; all new routes
  deny customer/driver access. Paging summary cannot be bypassed at 101+ tasks.

Focused frontend proof: template add/reorder/save/conflict/partial save failure;
task states, actor/time, failed mutation, stale tenant/order, pagination and
server completion rejection. Build, TypeScript, and changed-file lint required.
Runtime acceptance: create a synthetic template, apply to a synthetic order,
edit the template and verify the old job stays unchanged, start work, check tasks
as assigned mechanic, reject premature completion, finish required tasks,
complete through review, and verify frozen/read-only state. Repeat the affected
compact/mobile interaction and one fleet PM carry-forward/reseed flow. Record
exact branch, ports, migration, fixtures and screenshots without customer data.

Implementation evidence is not independent approval. Fresh QA and Security
reviewers inspect this diff and reproduce important negatives before release.
CI/PR, merge and production release are separate board states. Post-release
canary uses a permitted synthetic/nonfinancial job or read-only existing
snapshots; no real invoices, customer sends or historical changes are authorized
by this contract.

## Handoff

- Board ID: DB102.
- From / To: Architecture & API Contracts → Backend & Integrations + Frontend & UX.
- Scope completed: source-grounded contract and failure/compatibility fixtures.
- Scope not completed: migration, API/UI implementation, checks, independent
  gates, runtime acceptance, PR, merge or deployment.
- Material decision resolved: required tasks block completion; optional tasks do
  not; old jobs are grandfathered; no waiver or automatic reset; one checklist
  per applied line, not per billed quantity.
- Next action: implement on its own branch/worktree with mandatory local-runtime
  alignment; keep DB102 separate from DB098/DB099/DB100.
- Return condition: a discovered application/completion path cannot preserve the
  same snapshot and gate semantics, or implementation needs a contract change.
