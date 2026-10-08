# DB-036 daily server fuel contract

Backend & Integrations owns the daily worker. This outcome reuses
`FuelDailyImport`, `FleetFuelDaily`, `import_motive_daily_fuel.run_import`, and
`GET /fleet/fuel-daily`. No migration or trip-metric write is required.

## Data boundaries

Driving gallons, idling gallons and source-reported total remain separate
nullable readings. Missing does not mean zero. Source distance and durations
remain report measurements, not reconstructed trip measurements. The worker
never invents or imports an estimate. Existing trip fuel estimates remain a
separately labelled UI measure with their frozen basis.

Report timezone is initially unverified; `source_timezone` stays null. An Eastern
settings page does not prove the report's date boundaries. Each report date's
existing conservative membership interval is UTC midnight minus 14 hours through
the following UTC date at noon. Only dates whose whole interval has ended are
eligible. Default overlap is three completed report dates; `MOTIVE_FUEL_DAYS`
may explicitly request 1–7. A 13:30 UTC daily schedule includes yesterday after
the noon cutoff without inventing the report timezone.

Exact source VIN and provider ID bind to one current active tenant vehicle and
fleet membership covering the entire report-date interval and source-read time.
Existing trip/fuel bindings remain additional identity evidence. Units are
labels, never join keys. Current active owner/admin is rechecked in each
transaction. No membership backdating, OAuth/provider activation, vehicle
updates, or financial data writes are part of this worker.

## Collection and receipt contract

Version 1 envelope includes company ID/label, before/after verification,
settings timezone evidence, start/finish, complete directory count and terminal
evidence, report dates, and every directory vehicle's provider ID/unit/VIN plus
one explicit result for each requested date. The collector verifies the visible
report/date filter and completion before declaring a reported or source-missing
result. Failed or partial reports cannot masquerade as completed readings.
Missing source and unavailable records remain explicit receipt entries.

Before writes, validate the full envelope, requested contiguous completed dates,
unique provider/VIN identities and full vehicle/date accounting. Reported
readings use the strict existing import schema and evidence hashes. Invalid
individual readings, unmapped VINs, membership gaps, and immutable source
revisions are quarantined with reasons while valid rows proceed. A report
coverage failure fails the source gate before any per-row quarantine can hide it.
Existing daily records never change; later different readings do not overwrite
an earlier accepted day. Repeated identical source values retain original
read/capture times and receipt identity.

Default is dry-run. Save immutable normalized rows and source hash before an
explicit atomic commit. Recheck identity/membership, replay the same batch,
commit once, and verify saved IDs/digests and current fleet-fuel read visibility.
Unknown commit outcomes recover from exactly the saved source and normalized
attempt before new collection; no recapture may be used to freshen old data.
Private source, normalized material and receipts never enter Git. A saved
receipt is not a claim of full fleet coverage: report excluded/missing counts.

## Acceptance

- Company/count/date/filter completeness failures stop before writes.
- Tenant, actor, VIN and temporal membership isolation remain enforced.
- Driving/idling readings, explicit zero and missing stay distinct; no estimates
  or frozen trip metrics are altered.
- Same source values replay unchanged; changed source date readings quarantine.
- Dry-run writes nothing; late failure rolls back the whole batch; commit/replay
  and uncertain-outcome recovery retain stable saved record IDs.
- Current-membership API projection verifies saved rows; source gaps remain
  explicit in receipts and the existing partial-coverage API.
- Independent QA/security, protected PR CI, release SHA, fresh source canary,
  receipt and authenticated UI evidence precede a release claim.

Local startup 2026-10-08: branch `codex/motive-daily-fuel`, base `2162a553`;
no approved backend `.env` or local 8000 listener. Parent reported no 5173
listener. Isolated test databases only; no local full-stack visibility claim.

## Verified provider binding

Flat `reports` accounts for every directory provider and requested date.
The rendered Vehicle filter must produce an official Motive report URL with
exact `vehicle_ids`, `start_date`, `end_date`, `report_id=48` and normal report
mode. Each proof retains selected unit, visible date, read time and terminal
evidence; the unit is a display cross-check, never the identity join.
Single-provider reports have exactly one settled row, or zero rows with explicit
empty evidence. A row with no fuel readings is source-missing and never becomes
zero; optional source distance/duration evidence stays private in that case.
The API rechecks normalized current VIN against the saved verified VIN so an
identity edit cannot show another truck's historical fuel.

Parent runtime verification: frontend preview on port 5173, PID 97505, using an
in-memory synthetic API adapter; desktop and 700px source-fuel/overview checked
through CUA, 35 focused frontend tests, TypeScript and scoped ESLint passed.
This is frontend evidence, not production import or a local backend claim.
