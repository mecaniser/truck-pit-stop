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
