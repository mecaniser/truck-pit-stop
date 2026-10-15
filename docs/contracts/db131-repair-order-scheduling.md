# DB-131 / R1: repair-order scheduling contract v1

Status: **Architecture approved for implementation, 2026-10-15.** This is a
contract approval, not a QA/security or release approval. DB-131 was unoccupied
in the board and contracts at intake. Backend & Integrations is accountable;
Product & Delivery Lead owns prioritization and the release decision.

## Outcome and boundaries

Staff can set a planned start and promised finish on an existing repair order,
see those dates without expanding a large panel, and find all overdue work.
Dates survive save, reload, navigation, hold/release and ordinary order edits.
The schedule does not start work, complete work, alter timers or reserve capacity.

No bay/resource calendar (S1), booking changes, invoice due dates, notifications,
customer promises sent externally, invoice/quote snapshots, financial mutation,
automatic schedule changes or new timezone settings. Optional dates during new
order creation can follow later; this release edits the saved order.

Existing evidence: `RepairOrder` has actual work timestamps but no planned dates;
`Tenant.timezone` already stores an IANA shop timezone (default
`America/New_York`). The ledger uses `RepairOrderReadModel` and a legacy fallback;
dashboard queues use their own `RecentOrder` serialization. These paths must not
silently omit a saved schedule.

## Data and rollout

Add nullable `scheduled_start_at` and `promised_finish_at` to `repair_orders`,
both `DateTime(timezone=True)`. Store UTC instants, never browser-local strings.
Both existing and newly imported rows default to NULL. Do not infer planned dates
from creation, invoice due date, appointment, imported notes or actual work.
Add a database check permitting either NULL but requiring finish > start when
both exist. Add an index suitable for tenant + promised-finish filtering;
`(tenant_id, promised_finish_at, id)` with `promised_finish_at IS NOT NULL` is
sufficient. Do not include a volatile `now()` predicate in an index.

Use a new Alembic revision after the actual current head; do not modify historical
migrations. Roll out schema before code. An application rollback leaves the
nullable columns and audit history intact. Downgrade is for disposable migration
tests only after schedule writes; a production rollback must not discard dates.

For this small extension, avoid rebuilding/backfilling the entire JSON projection:
read the two schedule columns from `RepairOrder` using a tenant-qualified 1:1
join alongside the bounded projection payload. Apply the same canonical source
predicate to count and rows. The existing legacy path reads them directly.
This preserves existing projection search/quote/invoice behavior and avoids
persisting a time-dependent `is_overdue` value. Source joins must match both
`repair_order_id` and `tenant_id`; no per-row lookups or unbounded payload fetches.

## Access and lifecycle

Schedule GET: existing shop-staff roles plus mechanics already authorized for
that exact order. Schedule PATCH: garage owner, garage admin, receptionist and
fleet manager. Preserve existing fleet-manager internal/fleet-work scope and
mechanic order/operation assignment scope; do not broaden existing list access.
Reject customer/driver/public access. Reject another tenant or deleted order
with 404. Role denial occurs before lookup, with 403.

Schedules are editable for nondeleted, unreleased orders in draft, quoted,
declined, approved, assigned, acknowledged, in_progress or pending_review.
Completed, invoiced, paid, cancelled and vehicle-released orders are read-only;
return 409 on writes. A pricing/quote lock alone is not a schedule lock: these
dates cannot alter money or an already-sent authorization. Hold does not lock the
schedule and does not move the promise. Reopening/restoring retains the saved
dates; staff deliberately reschedule if needed.

Schedule fields and audit events are staff-only in this release. On pre-existing
generic RO responses to customer/nonstaff readers, omit or null the new dates and
force `is_overdue=false`. Hide the new event type in the same history paths that
hide internal operation/hold events. An allowed mechanic can read, not edit.

## Endpoints

`GET /api/v1/repair-orders/{order_id}/schedule` returns:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "timezone": "America/New_York",
  "scheduled_start_at": "2026-10-16T12:00:00Z",
  "promised_finish_at": "2026-10-16T21:00:00Z",
  "scheduled_start_local": "2026-10-16T08:00",
  "promised_finish_local": "2026-10-16T17:00",
  "scheduled_start_fold": null,
  "promised_finish_fold": null,
  "updated_at": "2026-10-15T18:00:00.123456Z",
  "is_overdue": false,
  "can_edit": true
}
```

Unset instants/local strings/folds are NULL. Fold is NULL for ordinary times and
0/1 for an existing instant in a repeated clock hour. `timezone` is the current
validated `Tenant.timezone`, not the browser timezone. An invalid configured zone
returns a clear 409 `schedule_timezone_invalid`; do not silently schedule in a
different zone. The existing default covers valid legacy tenants.

`PATCH /api/v1/repair-orders/{order_id}/schedule` takes a complete schedule pair:

```json
{
  "expected_updated_at": "2026-10-15T18:00:00.123456Z",
  "timezone": "America/New_York",
  "scheduled_start_local": "2026-10-16T08:00",
  "promised_finish_local": "2026-10-16T17:00",
  "scheduled_start_fold": null,
  "promised_finish_fold": null
}
```

Both local keys are required but nullable; NULL explicitly clears that date.
Fold keys are optional nullable integers 0/1. A fold requires its date. Reject
unknown fields. `expected_updated_at` is a required timezone-aware timestamp;
compare exact UTC instants, not formatted strings or millisecond-rounded values.
`timezone` must exactly match the shop's current configured zone, otherwise 409
`schedule_timezone_changed` and require a fresh GET. No client-selected shop zone.
Success returns the same schedule response shape, with the fresh order version.

Validation: exact `YYYY-MM-DDTHH:mm`, valid calendar/time, no offset or seconds in
wall-time input. Either date alone is legal. If both are present, resolved finish
must be strictly after start. Past dates are legal: staff may record a missed
promise, and overdue status makes that visible. Empty text is normalized to NULL
by the UI, not accepted as a date by the API.

### Timezone and DST

Resolve wall time on the backend using `zoneinfo.ZoneInfo` and UTC round trips
for fold=0 and fold=1. A time with no valid round-trip is nonexistent: 422
`schedule_time_nonexistent`, naming the field. Never normalize a spring-forward
02:30 into 03:30. If both candidates are valid and different, require an explicit
fold; 422 `schedule_time_ambiguous` includes the affected field and two choices
with fold, UTC instant and UTC offset. The editor then presents “First 1:30 AM
(UTC−04:00)” / “Second 1:30 AM (UTC−05:00)”. No silent earlier/later choice.
For an unambiguous time, NULL or fold=0 is valid; reject inappropriate fold=1.

Changing the shop timezone later changes display, not stored instants. The
dialog reloads after a timezone conflict before saving; it must not silently
reinterpret the draft. No frontend timezone-conversion dependency is required:
format display with Intl and send the typed wall-time string unchanged.

### Transaction, concurrency and errors

Reuse the existing tenant workflow lock order and exact-tenant RO row lock used
by staff holds, then enforce role/scope, lifecycle and `expected_updated_at`.
Do not apply pricing `editable()` wholesale, because quote locks are unrelated.
Validate/resolve the whole pair before mutation. Persist both fields, a strictly
advancing order `updated_at`, and one history event in a single transaction.

An unchanged pair returns 200 without changing version or adding an event, after
the expected version and lifecycle checks. A stale write, including an uncertain
retry of a successful write, returns 409 `schedule_changed`. Frontend reloads
the saved pair for comparison; never silently overwrite or auto-retry with a
new version. This provides duplicate-safe effects without a new idempotency table.
Use no Redis idempotency key for this PATCH; normal session authorization and
version checks must run on every attempt.

Other 409: `schedule_locked` for a read-only lifecycle. Validation failures are
422, including `schedule_finish_before_start` (equal also invalid). For domain
errors use `{ "detail": { "code": "...", "message": "...", "field": "..." } }`;
omit field if not relevant. Auth/missing-order errors retain existing conventions.
No 4xx may leave a partial update or audit event.

Audit `event_type="schedule_changed"`, label “Schedule updated”, actor identity
and name, JSON detail containing previous/current UTC pairs and configured zone.
Expose through existing staff history. After commit, broadcast an existing RO
update with `send_to_customer=false`, `notify_status_change=false`; invalidate
staff list/detail/dashboard queries. Do not email, SMS or emit a status change.

## Lists, overdue filtering and summaries

Add optional UTC schedule fields, `schedule_timezone` (IANA string or NULL), and
computed `is_overdue` to staff RO
list/workspace/detail responses and existing staff dashboard order-row responses.
Defaults for older clients/fixtures are NULL/false. Resolve the timezone once per
tenant/request and reuse it across rows; do not call the schedule endpoint for
each queue row. Display timestamps using this explicit zone rather than browser
local time. An invalid zone yields NULL and the editor's explicit configuration
error; it must not silently fall back for writes. Dashboard schema, row selects
and serializers must carry the fields; no new dashboard lane or KPI is required.

The single shared overdue predicate, evaluated against one UTC `now` per request:

* promised finish exists and is strictly before now;
* not soft deleted and `vehicle_released_at IS NULL`;
* status is draft, quoted, approved, assigned, acknowledged, in_progress or
  pending_review.

Declined, cancelled, completed, invoiced and paid are excluded. Hold does not
exclude overdue work. `work_completed_at` alone does not exclude pending_review:
the shop still has quality review outstanding. A reopen can become overdue again.
At exact promised finish the order is not overdue until time advances beyond it.

Add `overdue: bool = false` to GET `/repair-orders`, `/status-counts` and
`/value-summary`. True is supported only for existing staff readers; return 403
for customer/nonstaff attempts. All paths apply the same predicate, tenant/role,
customer, vehicle, search and deleted rules BEFORE count, total value and paging.
`deleted=true&overdue=true` returns zero rows/count/value (and retains the existing
deleted-view role restriction). A terminal status plus overdue likewise returns
zero. Status-counts retain their existing meaning: each status count under the
other applied filters, and `all` is their sum. Preserve search semantics.

Default false keeps existing ordering. True sorts by `promised_finish_at ASC,
id ASC`, including legacy fallback, so the most overdue jobs appear first with a
deterministic tie-break. Preserve pagination envelope, skip/limit cap and normal
response shape. Do not filter only loaded pages, fetch every row to count, or
silently use the bounded dashboard queue as the complete overdue set. Counts and
results are live across requests; no snapshot token or new pagination scheme.

## UX and shared acceptance fixture

One compact “Schedule”/date summary control near the existing order header/work
details opens a small shared editor. Display “Start” and “Promised finish” with
shop timezone in the editor, plus Clear per field, Save, Cancel and a named close
button. Escape cancels, focus returns to its trigger; failed saves retain input.
Make pending saves visibly pending and prevent duplicate submits. Do not add an
always-expanded form, second content scroller or taller fixed footer.

Show promised finish and textual Overdue cue in the queue without replacing its
company total or multiplying row height. Show start as secondary detail where
space permits. Color supplements text. A discoverable “Overdue” filter uses the
server contract and URL `overdue=true`; preserve it on detail close/reload/Back.
Switching from a dashboard-origin bounded queue to “All overdue work” explicitly
clears `queue` and uses the full ledger. Search/customer context remains intact.
Reset paging on filter changes and invalidate counts/value/list after a save.
Refetch overdue results on focus and at most every 60 seconds while visible so
crossing a deadline becomes discoverable without manual reload.

Fixture now: `2026-10-16T22:00:00Z`, shop `America/New_York`, browser timezone
`America/Los_Angeles`. Order A in_progress with start12:00Z/finish21:00Z is overdue
and displays 8 AM/5 PM shop time. Order B same promise, pending_review, is overdue.
Order C same promise, completed, is not overdue. Order D held in_progress is
overdue. Order E no finish is not overdue. Order F belongs to another tenant and
is never returned. Tie-break/pagination fixture has >25 matching rows; search and
customer filters reduce both count and value across all pages.

DST fixtures: New York `2026-03-08T02:30` is rejected; `2026-11-01T01:30`
requires fold, mapping to05:30Z (0) or06:30Z (1). A browser in Los Angeles must
produce the same stored instants as one in New York. Ordinary timestamp roundtrip,
clear-one/clear-both, past-date, reversed/equal pair, stale version, timezone
change, unknown role, wrong tenant, released/deleted/finalized and held-order
cases are required. Invalid writes leave money/status/timers/invoice dates intact.

Runtime acceptance uses signed-in Light and Night Shop at desktop1280+, phone
390/320 portrait and740×400 landscape: set/save/reload/edit/clear/cancel/Escape,
overdue search and multi-page count/value consistency, conflict recovery and
customer/order return. Mobile evidence is browser emulation unless physical
hardware is actually used. Verify readable controls, no horizontal overflow,
44px mobile hit targets, desktop density and one workspace content scroller.

## Ownership split and gates

Backend & Integrations owns model/migration, schedule schemas/service/routes,
role/tenant/lifecycle/DST/concurrency, history masking, source enrichment,
dashboard row serialization, filter/count/value/fallback and backend tests.
Suggested new files: `schemas/repair_order_schedule.py`,
`services/repair_order_schedule.py`, focused schedule tests and one migration.
Existing backend RO/dashboard/model files are exclusively backend-owned.

Frontend & UX owns `frontend/src/types/index.ts`, shared schedule editor and
formatting/presentation helpers, `RepairOrdersPage.tsx`,
`RepairOrdersLedger.tsx`/presentation helpers, dashboard row type consumption and
focused tests. No API/model edits. Proceed against the exact fixture above;
contract changes return to Architecture. Parent integrates both owners' work.

Migration/tenant boundary requires high-risk lane gates proportionate to this
scope: real PostgreSQL migration upgrade/rollback-on-empty and concurrent-write
proof; independent QA and Security reviewers who did not direct/implement it;
protected PR CI, schema/deploy readiness and actual production theme/device
journey evidence. No owner self-approves those independent gates. Board/backlog
R1 becomes Done only after required release evidence, not after this contract or
passing component tests. P1 remains the next selected outcome.
