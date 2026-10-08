# DB-036 server dashboard health observations

Architecture handoff, 2026-10-07. Backend & Integrations accountable. Separate
outcome after the Trips worker; no OAuth activation, provider API calls, vehicle
status updates, or fault lifecycle inference. This document records discovery
and the implementation contract, not deployment or import acceptance.

## Verified source UI

Read-only Playwright probes ran inside the existing Trips canary service. Login
used its existing server environment without exporting credentials/session data.
Company `77 CARGO LLC` / `KT8934277` was checked before and after. Settings showed
`(GMT-04:00) Eastern Time - New York`; browser context was also New York.

Route: `https://app.gomotive.com/en-US/#/maintenance/health`. The visible table
headers are VEHICLE OR ASSET, AVAILABILITY, DEFECTS, FAULT CODES, NEXT SERVICE,
then two empty columns. It displayed `Showing 16 of 16`. This is the health
report's inventory, not proof all 22 directory vehicles report health. Missing
vehicles remain source-missing, never healthy or zero.

The text `Fault codes` identifies both a filter and a table header, not a tab.
Find the table row by its observed vehicle-summary href and click its fourth
cell. This opens a read-only vehicle drawer. Its
`[data-testid="section-fault-codes"]` card is headed `Current fault codes`.
Click each grounded `.phx-collapse-item-header` labeled `Show details` before
reading detail content. Initial DOM text included collapsed content; the final
probe explicitly expanded both details and verified `Hide details` with no
zero-height collapsed content.

Final positive fixture, source read `2026-10-07T23:21:43.346Z`: provider vehicle
5971650 / unit 02, exact rendered VIN verified (private evidence), table count 2 and two
expanded cards:

| SPN | FMI | Description | Severity | Network | Source address | First detected | Last observed | Occurrences |
|---|---|---|---|---|---|---|---|---|
| 520216 | 31 | PLC4trucks antilock braking system Communication Circuit Error — Condition Exists | High | J1939 | 11 · Brakes - System Controller | Sep 25, 2026, 5:50 AM | Oct 7, 2026, 6:59 PM | 17 |
| 523013 | 31 | Seat Occupation Sensor Error — Condition Exists | Unclassified | J1939 | 232 | Aug 25, 2026, 7:38 AM | Oct 7, 2026, 6:59 PM | 1 |

Zero fixture at `2026-10-07T23:20:53.361Z`: provider 5971710 / unit 531, exact
rendered VIN verified (private evidence), table count 0 and explicit `No fault codes` inside
`Current fault codes`. This means no current codes reported in that capture,
not overall truck health or resolution of earlier codes.

An earlier source table read showed count 4 for unit 02 while its drawer showed
2 cards; a subsequent independent read showed count 2 and the same 2 cards.
Require stable before/after counts and equality with captured card count; retry
boundedly or mark partial. Never silently discard the discrepancy. VIN rendering
also required an explicit readiness wait; a short fixed wait returned no VIN.

Private evidence (mode 0600) lives outside this checkout at
`/Users/sergio_m1_promax/GitHub/truck-pit-stop/output/motive-trips/`:
`health-expanded-details.json` and its `.cjs` probe; `health-current-cards.json`;
`health-multicode.json`; `health-nav-elements.json`; `health-row-elements.json`.
Do not commit raw probe artifacts; earlier broad drawer probes include unrelated
driver/location text. Production collection must capture only allowlisted
diagnostic fields and identity evidence.

## Storage and write contract

Use an additive dashboard observation model, not `MotiveFault`. The latter
requires OAuth connection/remote vehicle/provider fault ID, nonnull first/last
event timestamps and authoritative open/closed lifecycle status. Its REST
ingestion and mapped read gates are incompatible with dashboard observations.

Minimal new table `fleet_diagnostic_captures`: base ID/timestamps/deletion fields;
tenant, vehicle, fleet_customer and fleet_membership IDs; verified VIN; provider
vehicle ID; source company ID/label; source=`motive_dashboard`; source_read_at;
captured_at; captured_by_user_id; client_request_id; content_sha256; coverage;
explicit_empty; source_scope; codes JSON array. Enforce tenant-safe composite
identity/FK constraints and unique `(tenant_id, client_request_id)`.

Each code stores allowlisted nullable strings: code, spn, fmi, description,
severity, network, source_address, source_status, provider_fault_id; nullable
nonnegative occurrence_count; first_detected_text and last_observed_text;
nullable parsed first_detected_at/last_observed_at; timestamp_precision and
timezone_basis. Preserve leading zeroes in code/SPN/FMI. No provider fault ID
was visible in discovery; leave null. Source status is `Current fault codes`
(the observed section scope), not invented `open`, `closed` or resolved events.

The capture service accepts an explicit tenant/active owner-admin actor and
expected source company configuration, rechecks company verification before and
after, resolves exactly one active tenant VIN and one current fleet membership,
and binds the captured membership ID. Unit number is never the join key.
If an expected fleet customer is configured, enforce it. Membership must cover
source-read time; parsed last-observed intervals must be covered too. First
detected may predate membership: retain it as explicitly source-reported history
of the currently observed code, not as a prior-owner event or attributed onset.
Unknown observation time is allowed only as a current dashboard observation
with verified read-time membership, never as proof of when a fault occurred.

Default dry run, explicit commit, one transaction, tenant serialization, saved
private receipt and replay. Same client request plus same immutable digest is
unchanged; altered payload conflicts. Replaying the identical source file must
not refresh source-read time. Later genuine captures may append observations.
No writes to OAuth tables, existing fault lifecycle, repair/PM, vehicle status,
canonical mileage or aggregate telemetry fault count.

## Timestamp semantics

Source details display minute-only timestamps without a zone suffix. Settings
and browser agree on New York but discovery did not vary browser timezone to
prove the Health component's rendering basis. Preserve literal texts. Until the
adapter's timezone basis is independently verified, parsed instants remain null
with precision `unknown` and timezone_basis `unverified`; display capture time
separately. Do not assume the settings page alone proves a component's timezone.
If later verified, use explicit New York minute intervals; reject ambiguous or
nonexistent DST values and future/reversed intervals. Never invent seconds.
Source-read timestamp means dashboard checked, not latest fault event.

## Collector contract and completeness

Suggested module `backend/scripts/motive_health/collect.cjs` with pure parser
tests. Reuse server login/company/VIN conventions; separate worker state path,
lock, receipt and commit flag. Suggested importer/orchestrator modules:
`import_health.py`, `runner.py`, `run_worker.py` in the same package. Share login
helpers only if this preserves existing worker behavior and tests.

Versioned source envelope: company ID/label, before/after verification booleans,
timezone evidence, start/finish/read timestamps, health directory count and
terminal evidence, complete flag, and per-vehicle provider ID/VIN/count/state/
allowlisted codes. Collector walks the health table through observed visible
links, separately waits for exact VIN on each summary, then returns to the
health row, opens drawer, expands each detail and validates stable source counts.
Require exact headers and unique provider/VIN mappings. Explicit empty requires
count zero plus `No fault codes` in the correct card. A missing card, missing
VIN, failed load or count mismatch is not empty. Missing directory vehicles get
source_missing receipts; unknown unmapped source vehicles get excluded receipts.
Store partial artifacts privately but do not import partial captures as complete.
Never mark absent earlier codes closed or resolve incidents automatically.

## Read API and UI contract

Add `GET /fleet/trucks/{vehicle_id}/diagnostics` under existing Fleet truck-read
authorization, independent of OAuth state. Require current tenant, active truck,
current membership and matching capture membership/customer on every read.
Return source, last_checked_at, coverage (`unknown|partial|complete`),
explicit_empty, source_scope, and latest accepted codes with raw/nullable parsed
timestamps. No capture returns unknown/null/empty, not a healthy zero. Earlier
captures may be returned as `previously_reported` with their check times; absence
from latest capture never means resolved. A failed latest collection should be
visible through worker status/receipt and must not refresh last_checked_at.

Use a truck-detail diagnostic list with SPN/FMI/code, description, severity and
`Dashboard checked` time. Unknown source times are explicit. Do not reuse the
OAuth integration panel's empty-list wording or lifecycle statuses. Board counts,
if later added, must count current captured codes only with explicit capture
coverage and must not silently replace the existing telemetry reading contract.

## Acceptance and release gates

- Positive expanded-card and explicit-zero fixtures above parse without loss.
- Exact VIN/membership and wrong tenant/company/actor/VIN/duplicate rejection.
- Ended/replaced membership prevents old-company reads; unknown observed time
  does not bypass read-time membership checks.
- Missing six directory vehicles, unmatched VIN, partial table and failed drawer
  remain unknown/excluded; no healthy-zero fabrication.
- Stable count validation reproduces 4-versus-2 mismatch as partial/retry.
- No provider ID/event/status invention; missing later row never closes a code.
- Detail expansion verified before collection; no hidden state/API extraction.
- Timestamp uncertainty, DST ambiguity, unknown versus zero occurrence count,
  and repeated source capture retain honest semantics.
- Dry-run no writes; atomic commit; exact replay unchanged; conflicting replay
  fails; uncertain commit recovers by same-payload retry; unrelated-table checks.
- Migration upgrade/rollback safety, independent QA/security, production canary
  receipt and authorized read/UI evidence before calling the worker released.

Do not enable scheduling until the separately authorized health service and
its first dry-run/commit/replay canary are verified. No release gate is satisfied
by this source discovery alone.

## Implementation checkpoint

The source-only canary completed at 2026-10-07 23:30:35 UTC: 16/16 Health
inventory vehicles, 14 captures, 22 current codes and three explicit empty
captures. Unit 26 lacked a VIN; unit 900 used J1708 SID/PID cards. Its verified
five-card source fixture now parses with the original SID/PID code namespace,
null SPN and original FMI. Fresh source-only validation at 23:42:50 UTC captured 15 vehicles and 27 codes, including all five unit-900 cards; three explicit empty captures and only unit 26 unavailable.
No diagnostic data has been written to production.

Private source evidence remains outside Git in `output/motive-trips/`.
Dedicated Railway service: `diesel-bridge-motive-health`
(`4da46413-32b0-429c-9bab-f022ec5e41b7`), volume
`8f1dbc87-e1fa-4022-8111-0cbc117ae667` at `/data`. Configuration references the
existing authorized location worker. `MOTIVE_HEALTH_COMMIT=false`; no schedule.
Deployment `4b0ffc02-d12f-4091-96c1-cda55a4b46fb` runs collection only and never
invokes the importer. Restore the normal start command
`python -m scripts.motive_health.run_worker` after the committed canary.
Target health schedule is hourly at :30, offset from hourly location collection;
activate only after all release gates pass.

Frontend checks: eight related tests, TypeScript and scoped lint passed. CUA
synthetic preview at `http://127.0.0.1:5179/tests/diagnostics-preview.html`
verified reported, explicit empty and unknown states at desktop and 390px width.
Checkout/PID 57620 was verified; no approved local backend configuration exists.
This is synthetic UI acceptance, not authenticated production acceptance.

Independent review findings are fixed: pending commit receipts reconcile under
the worker's exclusive lock before a fresh capture; saving-disabled mode refuses
recovery writes. Authorization locks the actor row, and a PostgreSQL test proves
concurrent revocation waits until transaction release. Seven collector and 34
backend/process tests pass. PostgreSQL full migration 001→162, replay/readback,
composite foreign keys and protected downgrade passed. The real 14-vehicle source
validated offline with all event instants unknown, as required.

Protected CI, production migration 162, current identity dry run, committed
receipt, unchanged replay and authenticated fleet UI verification remain release
gates. Neither source-only success nor a merged PR enables scheduling by itself.

## Release verification (October 7, 2026)

PR #482 merged as `cf05f14a97a508aec7617ddb581adf02a36abaac` after all six
protected checks passed. Web deployment `aec55706-0573-4535-a039-8805b586c916`
succeeded; migration 162 and required constraints were verified read-only.
`/health/ready` reports database and Redis ready.

Worker canary `40100baa-8b21-45a6-9d58-dcfdeec2cd05` matches the merged collector,
runner and diagnostic-service hashes. Fresh source collection checked all 16
Health entries. Its rollback-only dry run validated 15 captures; controlled
commit saved those 15 captures with 27 codes and three explicit-empty checks.
An exact-source replay returned 15 unchanged with identical IDs; all 15 saved
records were verified through the current-membership diagnostics read service.

The source entry for unit 26 has no verified VIN. Seven board entries lack a
verified health capture, including the unmatched unit; these categories overlap
and must not be summed as distinct trucks. Unknown event timestamps remain null,
with original source text and separate dashboard-check time retained. Missing
source data never clears faults or asserts that a truck is healthy.

Final scheduled deployment `bcc62504-5b3d-4d31-af29-1f36d1b72438` succeeded.
Hourly collection at :30 and saving are enabled for the separate service, with
normal `python -m scripts.motive_health.run_worker` entrypoint. First scheduled
execution remains pending. Authenticated browser acceptance awaits user sign-in
after session expiry; server readback is verified, UI acceptance is not claimed.
Private receipts and source data remain on the worker volume and outside Git.
