# DB-036 Motive driver record contract

Owner: Backend & Integrations. Architecture handoff: 2026-10-09.
Risk: high (worker, tenant data, additive migration). Implementation agents are
not independent gatekeepers. Root owns collector and UI-source acceptance.

## Acceptance and identity

Collect driver safety, fuel, coaching and bounded recent safety events from the
rendered Motive driver record. Record only observed values, periods and section
availability. A missing value is null, an explicit zero remains zero. Never invent
risk thresholds from a score. The Safety Score chart's `Coaching` annotation is
not a risk band. Colored bands require verified provider performance ranges. Live source discovery
by the collector owner found `/admin/safety/performance-ranges`: Fair50–84,
Good85–95, Excellent96–100. The collector reads and compares the provider ranges
before/after every run; the importer validates sorted, nonoverlapping source
ranges and the exact derived label, e.g. `Fair (50–84)`. Fair/Good/Excellent map
to the product's red/yellow/green indicators. Scores outside verified ranges
remain neutral; the numeric boundaries are never hardcoded in the application.

A capture requires exact verified company ID/label, stable provider driver ID,
provider vehicle ID, exact VIN, and a current-driver link verified before and
after reading the driver page. Name search does not establish identity. The
capture attaches only to the unique current tenant fleet membership for that
VIN, whose date interval includes collection time, and the worker's explicitly
configured fleet customer. No public write endpoint is added.

Fleet cards currently carry free-text driver names, not DriverProfile IDs.
Projection additionally requires that exact trimmed provider and current local
driver names match, that the local phone/name snapshot remains unchanged, and
that the vehicle's driver assignment revision is unchanged. The revision changes
on driver name/phone edits, including clear/reassign-to-same-name sequences.
Collection time must also be after the latest local assignment change, preventing
a source-read/local-reassignment/import race. The latest complete provider driver
directory is persisted atomically with the run and must still contain exactly
one matching provider-driver/provider-vehicle pair. An empty, missing, unassigned,
changed or ambiguous provider assignment therefore suppresses older scores even
when the local free-text name has not yet been updated.
A name mismatch does not discard the source capture; it prevents attaching its
score to an unverified local label. DriverProfile/custody records are not created
or linked by name. Current source assignment verification remains a time-specific
observation and its checked time is always returned. Stale (>48 hours) is explicit.

## Worker service

`fleet_driver_records.capture(db, tenant_id, actor_id, body, company_label,
company_id, *, apply=False, expected_customer_id=<configured UUID>)` accepts
`DriverRecordCapture` from `app/schemas/fleet_driver_record.py`. The body extends
the content below with `client_request_id`, `vin`, `provider_vehicle_id`,
`provider_driver_id`, `driver_name`, `source_company_id`, `source_company_label`,
`company_verified_before/after=true`, `assignment_verified_before/after=true`, and
an explicit-zone `source_read_at`. Actor must be an active tenant garage admin or
owner. Authorization locks serialize replay; current VIN/member are revalidated.

Dry run returns `would_create` without writing. Apply returns `created` or exact
replay `unchanged`. Same request with changed content/membership is HTTP409.
Source/company/identity mismatch and future collection timestamps are rejected.
The importer must retain immutable request IDs across retries and verify receipt,
readback and replay before commit. Captures do not change driver contacts, fleet
membership, custody, incidents, attribution, repair records or source provider.

## Read API

`GET /fleet/trucks/{vehicle_id}/driver-record` uses existing fleet authorization,
returns `Cache-Control: no-store`, and returns 404 for a foreign tenant, deleted
vehicle/customer or non-current/ambiguous membership. Shape:

```typescript
{
  vehicle_id: string;
  source: 'motive_dashboard';
  availability: 'unknown' | 'available' | 'assignment_unverified';
  record: DriverRecordDetail | null;
}
```

`BoardTruck.driver_record: DriverRecordSummary | null` is additive on the board
and detail's `truck`. Summaries are loaded in three bounded batch queries, with no per-card
HTTP request. Missing/unverified identity returns null. The latest valid-membership
capture is considered first; a newer mismatch must never reveal an older driver.

```typescript
type DriverRecordSummary = {
  capture_id: string; provider_driver_id: string; driver_name: string;
  safety_score: number | null;
  safety_band: 'red' | 'yellow' | 'green' | 'unknown';
  safety_band_label: string | null; safety_period_text: string | null;
  last_checked_at: string; coverage: 'partial' | 'complete'; stale: boolean;
};
type DriverRecordDetail = DriverRecordSummary & {
  safety: {score: number|null; band: 'red'|'yellow'|'green'|'unknown';
    band_label: string|null; period_text: string|null; coaching_label: string|null;
    top_behaviors: {behavior:string;score_impact:number|null}[];
    history: {period_text:string;score:number}[]};
  fuel: {period_text:string|null; utilization_percent:number|null;
    active_time_text:string|null; idle_time_text:string|null;
    metrics:{label:string;value:string;unit:string|null}[]};
  coaching: {status_label:string|null;open_count:number|null;last_coached_text:string|null};
  recent_events: {occurred_at_text:string|null;behavior:string;severity:string|null;
    status:string|null;vehicle_label:string|null;location:string|null}[];
  sections: Record<'safety'|'fuel'|'coaching'|'recent_events', 'available'|'unavailable'|'empty'>;
  unavailable_reasons:string[]; source_timezone:string|null;
};
```

Source timestamps and relative periods remain text unless verified. Recent-event
rows are not a complete history unless pagination completeness is proven; the
collector defaults to partial coverage. Sensitive contact/license details and
raw pages are not returned. Every list/text field is bounded by the schema.

## Migration, compatibility and release

Add immutable `fleet_driver_directory_captures` for complete source assignment
coverage and `fleet_driver_record_captures` with tenant-composite vehicle/customer/member
foreign keys, immutable request uniqueness, source/read-time constraints and
indexes. Add vehicle driver assignment revision/change time and a PostgreSQL trigger so
all name/phone mutation paths invalidate earlier identity snapshots. ORM updates
also advance the revision for isolated SQLite tests. Existing vehicle/API fields
are preserved. Empty-table downgrade is allowed; populated evidence blocks it.

Required evidence: isolated schema/service/route tests, negative tenant/company/
actor/membership/reassignment cases, replay/conflict and neutral missing data;
PostgreSQL migration/constraint/trigger checks; source-verified collector fixtures;
independent Security and QA; desktop/compact popover acceptance. No merge,
deployment, schedule or production imports are authorized by this contract.

Local preflight: codex/motive-driver-records at 5fcff895, no ports5173/8000,
backend/.env and Vite absent. Full local app/browser acceptance remains blocked;
isolated tests are not authenticated runtime evidence.


## Worker document and local evidence

The Python worker lives in `backend/scripts/motive_drivers/`. `runner.run` requires
an explicitly configured fleet customer even for an empty directory. All source
rows and nested readings validate before any write. The v1 document carries the
verified company, before/after flags, timezone evidence, collection start/finish,
complete driver directory count/terminal evidence, `performance_ranges`, and
`drivers`. Directory `complete=true` does not imply complete driver history;
individual record `coverage` stays partial for visible recent rows.

Captured rows include source driver/vehicle IDs, name, VIN, assignment flags and
`DriverRecordContent`. Unavailable rows preserve provider IDs when observed, have
a bounded `reason`, and omit reading fields. Unassigned/no-VIN source does not
create driver metric observations. All complete runs, including zero captures,
retain the assignment directory so they can invalidate old displayed scores.

Dry run writes private local receipt/source/attempt files but no DB rows. Saving
requires `MOTIVE_DRIVER_COMMIT=true` (case-sensitive); state defaults to
`/data/motive-driver`, with `MOTIVE_DRIVER_STATE_DIR` override. Scope requires
`MOTIVE_DRIVER_FLEET_CUSTOMER_ID`, `MOTIVE_SYNC_TENANT_ID`,
`MOTIVE_SYNC_ACTOR_ID`, `MOTIVE_COMPANY_LABEL`, `MOTIVE_COMPANY_ID`.
The wrapper holds an exclusive lock and recovers unresolved immutable attempts
before new collection. Unchanged replay and committed readback verify exact
saved IDs. Receipt counts distinguish retained observations from available UI
projections and local-name mismatches. No schedule is installed by the worker.

2026-10-09 implementation evidence: 101 focused/new plus related diagnostics,
board and custody tests passed on isolated SQLite with Python3.11. New-source
Ruff and `git diff --check` passed. PostgreSQL15 fresh-database full upgrade to
163, empty downgrade/re-upgrade, raw-SQL assignment trigger, composite customer
constraints, preserved unchanged replay and populated downgrade refusal passed.
The expanded PostgreSQL worker pipeline and complete-empty-directory suppression
pass also passed on the final schema.
These are implementation checks, not independent Security/QA approval or live
collection/import/runtime acceptance. No production data was changed.


Independent gate correction (2026-10-09): source validation errors contain raw
Pydantic input values. CLI entry points now return only structured failure codes;
actual subprocess regression tests verify a synthetic private provider sentinel
never appears in stdout/stderr for importer validation or pending receipt parsing.
The locked capture path also refreshes vehicle/member objects before identity
snapshotting so an older caller ORM cache cannot defeat assignment invalidation.

Final targeted rerun after CLI sanitization and locked identity refresh: 54
schema/service/importer/worker/process tests pass; Ruff on all new backend Python
sources and diff integrity pass. Related diagnostics/board/custody regression
previously passed in the 101-test combined run. Private PostgreSQL test databases
created for implementation verification are `driver_records_20261009`,
`driver_records_v2_20261009`, and `driver_records_v3_20261009` inside the existing
local PostgreSQL15 test container; the pre-existing health database was untouched.


Independent gate footer/range correction (2026-10-09): the importer now requires
canonical `Showing N of N` footer evidence, with both numbers equal to the
complete directory's declared and actual row count, including `Showing 0 of 0`.
Contradictory, malformed and trailing text is rejected before any database write.
Provider ranges must match the collector's supported Fair/Good/Excellent order,
red/yellow/green bands, and contiguous 50–100 scale; internal range boundaries
still come from source. Seventeen new negative/empty-directory cases were added.
Final targeted backend/importer/process result: **71 passed**, with Ruff and diff
integrity clean. This supersedes the earlier54-test targeted count.
