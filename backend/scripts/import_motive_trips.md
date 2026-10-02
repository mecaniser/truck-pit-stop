# Motive completed trip import

Requires deployed migration `158_fleet_trips`. This operator CLI imports only
completed trips visibly observed in Motive. It does not enable API sync or count
freight loads. Keep source JSON and receipts private and outside Git.

Run from `backend` using the approved environment:

```sh
python -m scripts.import_motive_trips --input /private/trips.json --tenant-id TENANT_UUID --actor-id OWNER_UUID
```

Review dry-run VIN matches. Repeat with `--apply` only when production import is
authorized. One transaction commits the entire batch or nothing; default dry run
writes no rows. Never change membership dates to make a rejected trip importable.

Input shape (synthetic, explicitly timezone-qualified source observations):

```json
{"rows":[{"unit":"101","vin":"1M8GDM9AXKP042788","provider_vehicle_id":"example-101","source_read_at":"2026-10-02T14:00:00-04:00","started_at":"2026-10-02T09:00:00-04:00","ended_at":"2026-10-02T10:00:00-04:00","origin_label":"Example City, NC","destination_label":"Sample City, NC","distance_miles":40,"driving_seconds":3600,"stops":null}]}
```

`stops: null` means not captured. Use `[]` only if the source explicitly says no
stops. Stops use `location_label`, nullable `arrived_at`/`departed_at`, nullable
`idle_seconds`; do not attribute between-trip stops to a trip without evidence.
Never infer geometry or fabricate timestamps. Trip time is the actual journey;
`source_read_at` is when the dashboard was read; server `captured_at` is when saved.

Exact retries with the same tenant/provider vehicle/departure and trip content
are no-ops even if read again later. Changed content conflicts rather than
rewriting history. Receipt identifies the stored trip and created/unchanged
status. Import requires active owner/admin, unique live VIN, and unique current
membership covering departure, arrival, and source read. Existing telemetry,
vehicle, repair and PM records are never written by this importer.

Verify GET `/api/v1/fleet/trips` with the corresponding departure date/timezone,
then open Trips from that truck. Totals describe recorded coverage only. App
rollback can hide Trips while retaining records; do not downgrade the migration
as a routine rollback because that would delete imported trip history.

## Optional trip metrics

Rows may include a nullable `metrics` object:

```json
{"fuel_used_gallons":null,"idle_seconds":0,"fuel_start_percent":80,"fuel_end_percent":null,"estimate_baseline_mpg":6.5,"estimate_baseline_captured_at":"2026-10-02T08:00:00-04:00","estimate_baseline_period":"last_30_days"}
```

Only enter source-verified trip fuel use, idle time and endpoint fuel percentages.
Unknown values stay null, including on legacy records; zero is a known reading.
Percentages cannot establish gallons consumed because refueling and tank capacity
are unknown. Idle time cannot exceed trip elapsed time. Frozen estimation baseline
requires all three fields, positive finite MPG, and a timezone-qualified capture
within the 30 days before `source_read_at`. It is supplied explicitly from that
truck's verified MPG record, never looked up dynamically during reads.

The API returns `trip_mpg = distance_miles / fuel_used_gallons` only for positive
actual gallons. If actual gallons are absent and a baseline exists, it returns
`estimated_fuel_gallons = distance_miles / estimate_baseline_mpg`. Actual zero
suppresses both division and estimated fallback. Estimated fuel never becomes
actual fuel or actual trip MPG. Extremely small divisors that overflow are
rejected during import. The read projection also guards older stored input from
producing nonfinite JSON. These values do not affect PM,
service odometer or 30-day fleet MPG.

Metrics are part of immutable content: changed values on an existing trip cause
a conflict. Missing/null/all-null metrics retain the original no-metrics digest,
so prior exact retries remain safe. Migration 158 includes nullable JSON metrics
before its first deployment; no existing deployed migration is being modified.
