# DB-110 operation execution contract

2026-10-13 · Architecture & API Contracts · implementation handoff v1

Board owner: Backend & Integrations. Product & Delivery Lead coordinates frontend,
runtime integration, independent QA and independent Security. This is a high-risk
lane because it changes persistent execution state, mechanic access and timer
attribution. It does not authorize production migration, merge or deployment.

## Decision and acceptance

Use **one responsible technician per operation** in this increment. An operation
is an existing, nondeleted `Labor` row, not a new copy of the priced service. Keep
`RepairOrder.assigned_mechanic_id` as the order lead. Assigning/reassigning an
operation never changes that lead, starts a timer, allocates historical time,
alters billed/book hours, or marks work complete. Multiple technicians may work
on different operations on one order concurrently. A technician still has at
most one active timer across operation work, general order work and miscellaneous
work. A later crew model requires a separate allocation contract.

The complete journey is staff assignment → operation appears in the assigned
technician's portal → explicit technician timer → required checklist → explicit
operation completion → all applicable operations and required tasks complete →
existing whole-order review/finalization. Individual completion never finalizes
the order, issues an invoice, awards full-order points, or resolves its source
recommendation. Existing DB-107 provenance and resolution remain order-based.

Required acceptance includes two technicians, a distinct order lead, a legacy
operation, a service checklist, a converted recommendation and a second tenant;
all controls and errors must work at desktop, 390px and 320px in the actual UI.

## Source findings that the implementation must address

- `db/models/labor.py` already has `mechanic_id`, but existing manual-labor creation
  also sets it to the adding mechanic. It is not evidence of completed work.
- `mechanic_time_service.start_session` is currently RO-only, rejects any second
  timer on the same RO, and auto-holds the previous RO when one technician switches.
  That order-wide auto-hold is wrong while another technician is still working.
- Mechanic job discovery/detail, photos and service checklists currently rely on
  the order lead. Helpers need deliberately scoped discovery and execution access,
  not blanket pricing/customer/whole-order authority.
- `_compute_book_hours_for_orders` currently credits every labor hour on any timed
  order to that mechanic. Helpers would duplicate book credit unless filtered.
- `complete-work` stops only the lead's timer, swallows failures, and subtracts the
  sum of technician minutes from wall time to infer hold time. Concurrent workers
  require a shared, atomic completion helper and interval-union wall coverage.
- Canonical labor removal is a hard delete; fleet PM reseeding replaces retained
  labor rows. Assignment/completion/time history must survive those paths.

## Additive data model and compatibility

Use migration `168_operation_execution`, descending from the combined
`167_merge_checklist_conversion` head. Verify the actual graph before choosing
the revision ID; never create a second accidental head.

On `Labor`, reuse `mechanic_id` for the current responsible technician and add:

| Field | Contract |
| --- | --- |
| `execution_status` | Nullable string constrained to `pending` or `completed`; null is explicitly legacy/untracked. |
| `execution_version` | Nonnegative integer, initially 0; increment once per real assignment/completion/reopen change. |
| `completed_at` | UTC timestamp, populated exactly when completed. |
| `completed_by_user_id`, `completed_by_name` | Actor FK and immutable display-name snapshot. Completion actor can be staff; do not imply it was the assigned technician. |

Existing rows retain null execution status and existing mechanic references; no
backfill claims they were completed. New non-sublet rows use `pending` across
manual labor, flat service, operation search, recommendation conversion and fleet
PM creation. Use explicit constructor/default handling and migration ordering so
the new default does not backfill historical rows. Existing null rows enroll in
tracking on explicit assignment or completion. The UI calls their state
`Not tracked`; null is never shown as completed. Completion guard ignores only
legacy/untracked and sublet rows. Sublet is externally supplied work: do not offer
an internal technician timer or enroll it automatically; existing RO-level review
still governs its acceptance. Standalone parts create no synthetic operation.

On `MechanicTimeSession`, add nullable `labor_id` FK (`ON DELETE SET NULL`) plus
immutable `labor_id_snapshot` and `labor_description_snapshot`. An attributed
session is still `session_type=repair_order` and retains its real RO ID. Enforce
that attribution requires a repair-order session and a matching tenant/order/
active labor row at start. Snapshot fields survive later removal; no copying of
durations to a second session table. Existing sessions remain unallocated with
all new fields null. Keep the existing partial unique active-mechanic index.
Include attribution in timer audit snapshots and manager/session read output.

Add internal order history events for assignment, completion, reopen and removed
scope with actor and before/after evidence. Filter them from customer histories,
as DB-102 already does for checklist events. Do not append private technician
execution metadata indiscriminately to shared customer `LaborResponse` payloads.

## API contract

New authenticated routes live under `/api/v1/repair-orders/{order_id}`:

| Method and suffix | Body | Result |
| --- | --- | --- |
| `GET /operations` | None | Current operation page below. |
| `PUT /operations/{labor_id}/assignment` | `{ "mechanic_id": "uuid-or-null", "expected_version": 0 }` | Refreshed operation page. Null explicitly unassigns but never disables tracking. |
| `PUT /operations/{labor_id}/completion` | `{ "is_completed": true, "expected_version": 1 }` | Refreshed operation page. False explicitly reopens. |
| `POST /operations/{labor_id}/timer/start` | `{ "expected_version": 1 }` | Refreshed operation page after explicit self-start. |
| `POST /operations/{labor_id}/timer/stop` | `{ "expected_version": 1, "session_id": "uuid" }` | Refreshed operation page after stopping that exact session. |

Example page (numbers are raw seconds, not billed hours):

```json
{
  "items": [{
    "labor_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "description": "Inspect steering linkage",
    "mechanic_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "mechanic_name": "Technician Two",
    "status": "pending",
    "version": 1,
    "completed_at": null,
    "completed_by": null,
    "tracked_seconds": 600,
    "active_session": null,
    "required_tasks_remaining": 1,
    "can_assign": true,
    "can_complete": false,
    "can_reopen": false,
    "can_start_timer": false,
    "can_stop_timer": false
  }],
  "summary": {
    "tracked": 2,
    "completed": 0,
    "remaining": 2,
    "legacy_untracked": 1
  },
  "order_status": "in_progress",
  "is_order_lead": false
}
```

Use one bounded projection query for assignments/actors and one aggregate session
query, not one query per row. Return all current operations for a staff/lead
workspace (the parent already loads all its labor lines); a helper receives only
their assigned operation rows. Mechanic-safe payloads contain no customer contact,
vendor cost, invoice or recommendation financial details. A helper's summary is
their visible scope, never a misleading whole-order completion promise. Staff and
lead summary covers the whole order. Missing/error responses must retain existing
operation content with a visible retry, not display false zero/all-complete.

`tracked_seconds` is the sum of real, nondeleted session intervals with the same
tenant, order and operation snapshot, including elapsed active time at a single
server `now`. General order time remains visibly unallocated; never distribute it
by billable hours. `active_session` identifies the actual session and its owner.
For legacy/untracked operations, return `tracked_seconds: null`, not zero. For a
tracked operation with a successfully loaded session aggregate but no attributed
sessions, zero means `No tracked time`; it does not claim the work took zero time.
Missing/failed aggregates must remain unavailable rather than defaulting to zero.
After mutation refresh the order, operations and checklist state and invalidate
mechanic jobs/timer queries. Broadcast only after successful commit.

Unknown cross-tenant/order/removed references return 404; unauthorized roles or
another same-tenant technician's operation return 403; malformed input returns
422. Version, stage, hold, required-task, active-timer and frozen-order conflicts
return 409 with actionable text. Stale writes never silently overwrite a newer
assignment/completion. Same-state requests at the current version return 200
without another event. A lost-response retry with the old version returns 409;
the UI reloads canonical state, preserving safe single application. Starting an
already-running exact operation returns its current session rather than inserting
a duplicate; stop requests carry the exact session ID so a delayed request cannot
stop a replacement timer. Validation precedes side effects.

## Authorization and lifecycle

- All lookups require exact tenant, RO and active child identities. Technician
  choices require same-tenant, active, nondeleted `UserRole.MECHANIC`. Assignment
  does not create, invite or activate people. Preserve an inactive historical
  technician's display evidence; offer only active valid replacements.
- Owner/admin/receptionist can assign and record operation completion/reopen on
  editable shop work. Fleet manager has the same abilities only on permitted
  internal/fleet work. A mechanic can complete/reopen and time only an operation
  assigned to themselves. The order lead may read the whole job but does not gain
  authority to execute another technician's operation merely by being lead.
- Assignment is allowed in existing editable pre-work and in-progress stages,
  including held work. Reassignment of a completed operation requires explicit
  reopen first. Reassignment/removal with an active linked timer returns 409 and
  asks to stop it; it never closes or reattributes another person's time silently.
- Start and completion require order `in_progress`, not held, not frozen/deleted,
  pending execution and required tasks complete for completion. Explicit staff
  completion may handle an unassigned operation, recording the staff actor; this
  does not invent technician time. Timer start requires a real assigned mechanic.
- Reopen is allowed during in-progress or pending review, before financial lock.
  Reopening during pending review atomically returns the order to in-progress and
  clears `work_completed_at`; start no timer. Clear current completion fields but
  retain the prior actor/time in history. A required checklist task cannot be
  reopened under a completed operation: return 409 requiring operation reopen
  first. Optional tasks do not prevent completion.
- Helper mechanics appear in `my-jobs`, job detail and assigned-work discovery
  through a tenant-scoped active-assignment EXISTS alongside order-lead access.
  Identify `is_order_lead`; do not show helpers whole-order acknowledge/start/
  hold/resume/complete controls. Existing lead actions retain their authorization.
  Helper operation/checklist execution does not broaden pricing, customer,
  recommendation conversion, notes, photos or general RO write permissions.
  Use the new reduced projection instead of relaxing the generic RO access guard.
- Checklist read/write authorization admits helpers only for their active assigned
  labor rows; lead/staff retains full read scope. Write permission still checks
  the exact task's labor assignment. All filters and counts use the same scope.

## Time and order consistency

1. Extend the existing session service with optional operation attribution. An
   exact same operation start reuses its running session. Switching between two
   operations on the same RO closes the previous session and opens the next at
   the **same timestamp**. Switching from general-order time to an operation also
   closes/opens; never relabel the old interval. Retain attendance/break policies.
2. One technician may switch to another RO without holding other technicians'
   work. Only preserve legacy auto-hold when no other active same-RO session
   remains and the switcher is its lead; operation helpers never auto-hold the
   whole order. Same-RO operation switches never hold it. An explicit lead hold
   stops every active session on that RO atomically; resume clears hold and may
   start only the caller's general-order timer under the existing lead flow.
3. Completing an operation stops only active sessions linked to that operation,
   at its completion timestamp. Do not stop an unrelated operation, general-order
   timer or another job merely because it belongs to the same technician. Never
   swallow a timer failure then commit completion. Reassignment retains historic
   session technician ownership, durations and snapshots.
4. All whole-order completion paths call one operation guard alongside the
   checklist guard **before** status, invoice, points, notifications, incident or
   recommendation side effects. Guard every tracked pending operation. On success
   stop all active sessions whose tenant and RO match, and stamp tracked totals
   atomically. Apply to generic PUT forward transitions, `complete-work`,
   `admin-complete-work`, `approve-completion`, and fleet `complete-work-order`.
   Quote/invoice helpers must not introduce a bypass. Cancellation/deletion also
   stops every matching timer without completing operations; restoration does
   not resume timers or falsely complete pending work.
5. RO `actual_tracked_minutes` represents summed person-time and may exceed wall
   time when two mechanics work concurrently. Derive idle/hold approximation from
   wall time minus the **union** of active technician intervals, not their sum.
   Do not describe that approximation as a complete hold-event ledger.
6. Keep booked hours separate. Filter `_compute_book_hours_for_orders` by tenant
   and mechanic: each current labor line credits its explicit assignee once;
   unassigned/legacy scope credits only the order lead. Never give every helper
   all order hours. Historical order-note fallback applies only to the lead and
   only where canonical labor is absent. This remains a booked-scope estimate,
   not actual labor, payroll or additional operation-level points. Existing
   order-level points remain awarded only through existing whole-order flow.
7. Existing manager timer control may accept optional `labor_id`, with its
   existing mandatory reason. Validate assignee, tenant, status/hold/completion in
   the shared service; generic manager start must not bypass these checks. No new
   implicit manager timer action is required in the operation assignment UI.

## Concurrency, source changes and migration proof

Use the existing tenant financial transaction lock first on paths combining
operation/timer changes and order state, then RO row lock, then labor/child rows.
All active timer writers must serialize for that tenant before reading/switching
the active session. Do not acquire a blocking lock in reverse order; take the
tenant lock before any order write lock in affected creation/removal/PM paths.
Refresh ORM state after locks. Keep the partial unique active-mechanic constraint
as a final safeguard and map contention to retryable conflict, not a 500. Never
commit inside a helper. DB-level two-session tests are required; SQLite cannot
prove these races. Ensure clock-out, break, manager stop/edit/delete and midnight
maintenance cannot resurrect or overwrite sessions ended by operation completion.
Execution version increments on assignment/completion/reopen, not merely elapsed
time. Timer changes are instead serialized transactionally, validate the fresh
operation version/state inside the lock, and use exact session identity for stop.
Thus a stale assignment cannot race a newly started timer: after taking the lock
it must observe that active timer and return 409 before changing the assignee.

Material work-scope changes (description, hours, source or line type) to a completed
tracked operation require explicit reopen first. Price-only rate changes need not
reopen it. Legacy `LaborCreate/Update.mechanic_id` must validate the same assignment
contract; it cannot remain an unvalidated bypass. An explicit assignment change
in legacy PUT must route through the guarded assignment service or return 409
instructing the caller to use the versioned operation route.

Removal must preserve timer attribution snapshots and internal history and remove
the line from completion scope without pretending it was completed. Active timers
block removal. Fleet PM reseeding should retain the existing labor identity for a
retained service whenever execution tracking exists, updating allowed cost fields
in place; do not manufacture a new pending operation or transfer historical timer
identity to different work. Required checklist snapshots and DB-107 source links
stay intact. Removed PM services use the same guarded removal path.

Migration proof: populated legacy rows retain null status/unchanged time and totals;
new operation rows default pending; attributed sessions satisfy FK/check constraints;
hard deletion retains snapshot identity; downgrade tested on an isolated DB, never
the user's populated preview. Deployment rollback should roll application code
back while retaining additive columns/data; a destructive downgrade would lose
execution evidence and requires separate release authority.

## Implementation surfaces and regression fixtures

Backend changes center on `db/models/labor.py`, `db/models/mechanic_time.py`, a new
`services/operation_execution.py` and schemas, `services/mechanic_time_service.py`,
`services/service_checklist.py`, `services/price_build_service.py`, and endpoints
`repair_orders.py`, `mechanics.py`, `dashboard.py`, `fleet.py`. Review timer
maintenance for shared locking and source projections/history privacy. Existing
pricing/customer response shapes remain compatible; new execution projection is
internal-only. Every operation creation and hard-removal callsite is in scope.

Reuse fixtures/regressions in:

- `test_service_checklists.py`, `test_service_checklists_postgres.py`.
- `test_mechanic_time_service.py`, `test_mechanic_job_scope.py`.
- `test_repair_order_finalization.py`, `test_fleet_workflows.py`,
  `test_internal_fleet_repairs.py`, `test_fleet_pm_mileage.py`.
- `test_db107_recommendation_conversion.py` and its PostgreSQL race suite.
- `test_price_build_service.py`, `test_db003_price_mutation_tenant_boundary.py`,
  `test_db003_read_tenant_boundary.py`, `test_fleet_manager_price_build_access.py`.

Add focused tests for: A-lead/B-helper discovery and strict task scope; inactive/
wrong-role/cross-tenant assignee; foreign order/labor/session; null/zero/legacy
states; assignment without a timer; stale assignment/completion; double-click
start; delayed stop against a replacement session; same-RO and other-RO switch;
parallel helpers; required-task completion/reopen; completion preserving unrelated
timer; order hold/finalization/cancel/delete closing all matching timers; failure
rollback; manager timer bypass; line removal and retained PM reseed; material scope
edit after completion; no duplicate booked-hour credit; sum person-time versus
union wall coverage; every whole-order completion entry point; customer projection
privacy; recommendation linkage unchanged. PG races include assign-vs-start,
complete-vs-start, hold/finalize-vs-start, remove-vs-start, same-mechanic two starts,
and required-task reopen-vs-operation completion.

## Handoff

From Architecture & API Contracts to Backend & Integrations / Frontend & UX.
Scope completed: repository-grounded contract and implementation/test map only.
Scope not completed: product implementation, browser acceptance, migrations run,
independent gates and release. Environment: focused
`codex/operation-technician-workflow`; combined preview 5174/API8001 remains
parent-owned with the existing synthetic DB preserved. Return to Architecture if
an implementation needs to weaken a gate, reassign historical time, add multiple
assignees, or widen helper access beyond this reduced operation workflow.
