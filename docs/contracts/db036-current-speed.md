# DB-036: current speed with Motive location

Date: 2026-10-15. Architecture & API Contracts handoff. Backend & Integrations
is accountable for the outcome; Frontend & UX owns presentation. Worker changes
use the high-risk lane, including independent QA/Security and release evidence.

## Outcome and compatibility

Collect available speed during the existing verified Motive location visit.
Show a speed as current only when its own trusted observation is at most five
minutes old. Missing speed, missing timestamp, and old speed cannot establish
that a truck is moving or stopped. No new database column, public endpoint,
response property, storage volume, or provider account is required.

Existing `TelemetryCapture.speed_mph` and `FleetTelemetry.speed` carry the value;
`observed_at`, `observed_precision`, and the existing freshness contract carry
its provenance. Keep per-field selection: newer location must never refresh the
age of a previously saved speed. Do not rewrite historical snapshots.

## Collector document

`backend/scripts/motive_sync/collect.cjs` may extend each `located` row with:

```json
{
  "speed_mph": 0,
  "speedText": "0 mph",
  "speedReason": null,
  "precision": "minute",
  "observed_at": null,
  "observed_minute_start": "2026-10-15T13:45:00Z",
  "observed_minute_end": "2026-10-15T13:46:00Z"
}
```

These are additive producer fields, not new public API fields. The real row
continues to require the existing company, provider vehicle, VIN, coordinates,
raw timestamp, timezone and source-read evidence. Older documents without speed
remain valid. Numeric speed must be finite, not a Boolean, and within the
existing 0–250 mph schema bound. Accept explicit zero; do not infer zero from
`Stationary`, `Parked`, an engine state, blank text, or missing data. Do not
interpret a road speed limit, an average trip speed, or an unrelated reading as
current vehicle speed. Only an unambiguous displayed mph value is accepted;
unsupported units or ambiguous values remain unavailable.

The speed selector and its relationship to the location observation must be
grounded in the actual visible Motive vehicle Live UI before implementation.
The collector must bind the displayed speed to the same verified VIN, provider
route and source observation as the coordinates. Read it before and after the
existing timestamp/coordinate stability check. A changing speed, source time,
coordinates, route or VIN must never be combined across attempts. Reuse bounded
whole-observation retries; never copy speed from a failed attempt into a later
location. Stable missing/ambiguous speed must not prevent a valid location from
being collected: use null/omission and a bounded reason instead.

When the observation timestamp cannot be verified, retain raw speed text as
evidence if useful, but omit the numeric speed from this collector import. Do
not timestamp speed with `sourceReadTime`, server time, or an elapsed label.
Known but old observations may remain historical evidence and must not be
presented as current. Minute precision remains the half-open interval
`[minute_start, minute_end)`; it must not become an invented exact second.

Suggested bounded reasons are `speed_unavailable`, `speed_ambiguous`,
`speed_invalid`, `speed_unit_unsupported`, and `speed_timestamp_unavailable`.
Reasons are operational receipt data, not text to expose in the fleet UI.

## Import, ordering and immutable replay

`import_locations.py` currently compares only coordinates in `disposition` and
queries only coordinate-bearing history. A same-interval location-only row is
therefore `unchanged` even if the new source contains speed. Conversely,
`fleet_telemetry.capture` rejects overlapping minute location captures. Do not
solve this by loosening the existing location overlap guard.

Plan location and speed independently under the existing tenant serialization:

| Source and prior field evidence | Field disposition |
| --- | --- |
| Missing/invalid speed | No speed write; preserve historical speed and its time |
| No prior speed, valid known observation | Add speed |
| Strictly newer non-overlapping observation | Add speed, including explicit zero |
| Same interval and same speed | Unchanged; no refreshed timestamp or extra snapshot |
| Same interval and different speed | Conflicting observation; do not overwrite |
| Older speed observation | Older; do not replace current speed |
| Different overlapping minute/exact intervals | Overlapping observation; do not order by capture time |
| Prior speed has unknown time | Preserve it unless the new interval starts strictly after its capture time |

An equal-valued overlapping but different interval is still ambiguous. Compare
against speed-bearing history, including speed-only supplements, independently
of location history. Only intervals that overlap or follow the proposed interval, or unknown-time
readings not provably earlier by capture time, count toward the 1,000-row safety
bound. Strictly earlier disjoint history cannot hold this update. Do not rely on
a retention job or count all lifetime rows, which would eventually stop updates.

For the important transition from an old location-only collector: if the same
location interval/coordinates are unchanged but speed is admissible, create an
immutable **speed-only** capture with `lat`, `lng`, and `location_label` omitted.
It carries the same observation interval and exact identity evidence. This
adds the missing field without duplicating or altering the location. A newer
location and admissible speed may be captured together. An independently held
field must not accidentally be included in the payload for another field.
If location itself conflicts, retain that report; any independently admissible
speed must still meet all source stability and identity checks.

The capture service must prevent an overlapping minute speed capture from
bypassing importer planning: same tenant, vehicle and membership; live prior
speed rows; reject when either speed interval has minute precision and the
intervals intersect. Keep the existing immutable request replay check ahead of
this guard. Preserve legacy exact-time manual capture semantics (existing
tests intentionally permit multiple exact readings); the collector importer
still rejects equal exact-time conflicting speeds before capture.

Each field subset has a deterministic request ID derived from its full immutable
payload. Replay checks run before deciding that its fields are now unchanged;
a recovered speed-only supplement must return the same saved snapshot. Old
documents must retain their old request IDs: do not add `speed_mph: null`, null
speed evidence, or a new evidence version to the legacy location-only digest.
Request-body mismatch remains `request_conflict`; interval rejection remains
`overlapping_observation_interval`. No existing snapshot is updated in place.

`execute_pass` must verify the fields actually written. Speed-only capture
requires the selected speed snapshot/value/observation to match, not a new
location snapshot ID. Combined capture verifies both fields. Preserve dry run,
commit, fresh-connection receipt readback and unchanged replay evidence.

## Tenant and source boundaries

Keep the company identity checks before/after collection and complete-directory
proof. The exact VIN/provider route must stay stable throughout capture. The
importer still requires the configured active tenant and owner/admin actor,
unique exact tenant VIN, unique current same-tenant fleet membership, and
membership coverage of source read time and the complete observation interval.
Provider company naming does not reassign app fleet membership: truck 609 stays
in Elis. Do not infer a driver match, enable a new fleet, or cross tenants to
fill an apparent gap. No client-supplied frontend freshness grants write access.

## Driver identity read resilience

The October 15 driver run failed with `vehicle_identity_changed`; the retained
log does not distinguish a genuinely different VIN from a missing second VIN
render. Treat that root cause as unconfirmed until fresh diagnostics establish
it. The driver collector may retry a null VIN read at most twice after the
initial attempt. Each attempt uses the existing fresh-document reader with the
same exact provider route. Do not retry a non-null mismatching VIN, an ambiguous
VIN or a changed source. The [Oct16 timeout amendment](db036-driver-timeout-retry.md)
permits only TimeoutError within that same three-read budget; every other reader
exception remains immediately fatal. Exhausted mixed timeout/null reads retain
ui_timeout and cannot become ordinary missing-VIN rows.

An initially absent VIN after all three attempts remains the existing
`vin_unavailable` row. After a known initial VIN, every non-null verification
must exactly equal it; any different VIN immediately fails the whole collection
as `vehicle_identity_changed`. Three null verification reads fail the whole
collection as `vehicle_identity_unavailable`. In both cases `complete` remains
false, so no partial import or replacement of prior successful records is
permitted. Keep complete-directory, company, assignment, tenant and importer
guards unchanged. No schema, public API or fleet mapping changes are required.

Retry/failure diagnostics may identify the provider driver/vehicle ID, unit,
before/after-summary phase and bounded attempt number. Do not log VINs, raw
provider content, credentials or exception messages outside the safe reason
allowlist. Focused fixtures must prove null-to-same recovery, bounded persistent
null behavior, immediate mismatch rejection even if a later read would match,
and propagation of source/ambiguity errors without retry.

## Frontend presentation

Add one shared current-speed selector used by both visible speed values and
`truckMotion`. It must require a retained numeric mph reading, a valid explicit
`observed_at`, an accepted source, finite value in range, and freshness at most
five minutes using the existing observation-time clock. Preserve the existing
five-minute future tolerance; values beyond it are unknown. For minute
precision, calculate age from the interval start, conservatively. Capture time
and location time are never substitutes for speed observation time.

Apply it to `TelemetrySummary` (card/map summary), `TruckTelemetryValue` (detail)
and all other current-speed renderers found by repository search. `0 mph` remains
visible when fresh and produces stopped; a positive fresh value produces moving.
Stale/delayed/unknown speed must not be a current numeric speed or current motion
indicator. Omit the current speed control or show a short unavailable state.
If historical speed is retained in a separate detail, label it explicitly as a
past reading with its own time. The existing 30-second clock must age an open
view out of the current state without requiring a reload. Do not change the
availability or ages of location, odometer, fuel or other independent fields.

## Required focused fixtures and ownership

- Backend owner: `motive_sync/collect.cjs`, its collector tests,
  `import_locations.py`, `test_motive_sync_import.py`, the speed overlap section
  of `fleet_telemetry.py`, and focused telemetry/actual-PostgreSQL tests.
  Prove explicit zero, unavailable/ambiguous/wrong-unit/non-finite speed,
  changing speed between reads, VIN/route changes, unknown timestamps, old
  documents, same-minute location-only supplementation, unchanged replay,
  conflicting/overlapping speed, older speed, independent field preservation,
  and foreign tenant/VIN/membership rejection.
- Frontend owner: `telemetry.ts`, `TelemetrySummary.tsx`,
  `TruckTelemetry.tsx`, and their existing focused component tests.
  Prove 12-day-old and capture-only speed absent from current UI; fresh zero
  and positive values; exact five-minute boundary and expiry while open;
  invalid/future timestamps; recent location with unavailable speed; desktop
  and compact layout. Keep real travel-history speeds outside this change.
- Parent/coverage owner: independently reconcile complete Motive vehicle and
  driver directories with approved fleet memberships and current projections.
  Distinguish provider-no-score, unassigned driver, absent VIN, no gateway,
  stale telemetry, and collector omission; source counts alone do not prove
  that every app truck or driver is synced. Any coverage implementation beyond
  this existing identity contract returns for contract review.

## Release acceptance

Require focused tests, protected CI, independent QA/Security, successful Web and
the existing location worker deployments with exact source/image evidence,
and a fresh captured/imported/replayed production observation. Browser acceptance
covers current versus old speed on desktop and compact fleet surfaces. A job
that is green but collected no trustworthy speed is not current-speed success.
If Motive supplies no timestamped speed for a truck, the correct result remains
unavailable; do not use repeated collection to manufacture freshness. Roll back
the worker on identity, conflicting-observation, replay or projection failure;
retain the frontend stale-speed suppression independently where safe.
