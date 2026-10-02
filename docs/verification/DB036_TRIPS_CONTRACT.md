# DB-036 Trips contract v1

Architecture & API Contracts · 2026-10-02 · branch `codex/fleet-trips`.

## Outcome and ownership

Backend & Integrations is accountable for persistent, tenant-scoped Motive trip
history. Frontend & UX consumes the contract below. Product & Delivery owns the
board and source collection. A fresh reviewer independently gates QA/security.

The Trips sidebar destination sits below Maps. Truck detail offers View trips,
carrying the truck selection and a return path. Trips supports fleet-wide or
truck-specific date filtering, aggregate figures, and expandable stop details.
Trip counts are driving journeys, never confirmed freight loads. These are
recorded trips; importing several observed trips does not establish complete
fleet coverage for a day.

## Read API

`GET /api/v1/fleet/trips`

Query:

- `start_date`, `end_date`: required ISO calendar dates, inclusive, ordered;
  maximum 31 calendar days.
- `timezone`: optional IANA name; defaults to the authenticated tenant timezone.
  Invalid names return 422. It is echoed so display and filtering agree.
- `vehicle_id`, `fleet_customer_id`: optional UUID filters.
- `limit`: default 50, range 1–100; `offset`: default 0, nonnegative.

Convert the start date's local midnight and the day after the end date's local
midnight independently to UTC. Select trip departures in that half-open
interval. This handles 23/25-hour DST days. A trip crossing midnight belongs to
its departure date; its entire recorded mileage is included once. Never prorate
trip mileage using clock time.

Response example (synthetic):

```json
{
  "items": [{
    "id": "10000000-0000-0000-0000-000000000001",
    "vehicle_id": "20000000-0000-0000-0000-000000000001",
    "unit_number": "101",
    "fleet_customer_id": "30000000-0000-0000-0000-000000000001",
    "fleet_name": "Example Fleet",
    "started_at": "2026-10-02T13:00:00Z",
    "ended_at": "2026-10-02T14:00:00Z",
    "origin_label": "Example City, NC",
    "destination_label": "Sample City, NC",
    "distance_miles": 40.0,
    "driving_seconds": 3600,
    "stops": [],
    "captured_at": "2026-10-02T20:00:00Z",
    "source": "motive_dashboard_manual"
  }],
  "summary": {"trip_count": 1, "distance_miles": 40.0, "driving_seconds": 3600},
  "total": 1,
  "limit": 50,
  "offset": 0,
  "timezone": "America/New_York",
  "start_date": "2026-10-02",
  "end_date": "2026-10-02"
}
```

`summary` covers the full authorized filter result, before pagination. Order
items by departure descending, then ID descending for stable ties. `total`
equals `summary.trip_count`. No matches returns 200 with empty items and zero
totals; this means no recorded trips, not proof the truck did not move.

Each stop is `{location_label, arrived_at, departed_at, idle_seconds}`; unknown
times or idle are null. `stops: null` means not captured; `[]` means the source
explicitly showed no stops. Stop times are timezone-aware instants. Never assign
between-trip stops to a trip without source evidence of that relationship.

## Authorization and isolation

- Use existing Fleet read roles and active authenticated user/tenant checks.
- Every join constrains tenant, live vehicle, live fleet customer and membership.
- Trips store the exact membership captured at import. Reads require that same
  membership to remain active now, and departure/arrival to lie inside its
  effective interval. A later membership cannot expose an earlier member's data.
- Import requires one unique active membership covering both trip endpoints and
  the source capture time. Do not backdate memberships to accept rejected trips.
- Missing, deleted, cross-tenant or inaccessible explicit truck/company filters
  return indistinguishable 404. Unauthorized role returns 403; unauthenticated
  returns 401. Invalid dates/limits/timezone return 422. Error details contain no
  source payload, database connection strings or other tenants' existence.
- Responses are `Cache-Control: no-store`; no provider credentials enter the API.

## Persistent model

Add `fleet_trip_snapshots` using BaseModel. Required fields:

- Tenant, vehicle, fleet customer and membership UUIDs; captured-by user UUID.
- `verified_vin` (17), `provider_vehicle_id` (120), provider unit (120).
- `source` = `motive_dashboard_manual`, `source_read_at`, server `captured_at`.
- `started_at`, `ended_at` timezone-aware timestamps.
- `origin_label`, `destination_label` (each max 500).
- `distance_miles` finite 0–100000; `driving_seconds` integer 0–2678400.
- `stops`: nullable JSON list, max 100 validated stops; labels max 500,
  nullable timestamps, nullable finite nonnegative integer idle seconds.
- `request_digest` SHA256 and stable identity/dedup key.

Composite foreign keys follow `FleetTelemetrySnapshot`: tenant+vehicle,
tenant+customer, and tenant+vehicle+customer+membership. Unique identity is
tenant + provider vehicle + departure instant. Index tenant/departure and
tenant/vehicle/departure. Database checks cover nonnegative finite bounds,
arrival strictly after departure, and driving time no greater than elapsed time
(no rounding tolerance is currently applied).
Boolean numeric values and NaN/Infinity are rejected before database insertion.

Completed trips only: arrival cannot be after source capture, and capture cannot
be in the future. Reject naive timestamps; the collector resolves the source's
display timezone explicitly. Do not infer observation dates from relative age.
No arbitrary 30-day telemetry expiry is applied to persistent trip history.
This feature neither extends telemetry retention nor deletes existing records.

## Import CLI

`backend/scripts/import_motive_trips.py --input FILE --tenant-id UUID --actor-id UUID`
defaults to dry run; explicit `--apply` enables an atomic transaction. Input is
`{"rows": [...]}` with each row containing `unit`, `vin`,
`provider_vehicle_id`, `source_read_at`, `started_at`, `ended_at`,
`origin_label`, `destination_label`, `distance_miles`, `driving_seconds`,
and optional `stops`.

Use strict extra-field rejection, normalized exact VIN validation and unique
live VIN match inside the selected tenant. Require active owner/admin and active
tenant, following the MPG importer. Validate the complete batch and all temporal
membership rules before commit. Lock tenant/vehicle/membership as needed to avoid
concurrent identity changes. Invalid or ambiguous rows abort the whole batch
with a safe error. No automatic best-effort skipping or unit-number-only match.

Repeated source reads of the same trip must not create extra trips. Compute
payload digest from normalized trip content excluding recapture time/operator;
same identity and same digest is a no-op, while changed content is a conflict
requiring a reviewed correction. Include membership and VIN in validation, and
recheck current authorization even on replay. Reject duplicate identities within
one input file. Database uniqueness enforces concurrency safety.

Receipt identifies each resolved truck, source trip, created/no-op and stored row
ID, plus whether the batch committed. Dry run creates no records. Preserve all
vehicle fields, PM targets, repair history and existing telemetry snapshots.
Private source files and receipts stay outside Git. No public write endpoint,
saved Motive password, or pretend OAuth synchronization is introduced.

## Frontend and geometry

Show a compact Recorded trips / miles / driving time summary, city-to-city rows,
departure/arrival times, and expandable stops. Keep capture date/time in the expanded row footer, without internal provenance prose.
Dates use the requested IANA timezone, echoed in the response.
Do not render a reconstructed road route or coordinate pins from city labels;
route geometry can appear only after a later contract adds actual provider
coordinates. Plain city-to-city route text satisfies this initial data shape.
Loading, retryable error, no trips recorded, and no stop details states are
distinct. New date/truck queries cannot leave the previous truck's results
visible under the new filter. Navigation is touch-usable and preserves return
context without expanding the truck page into another data table.

## Required gates and rollback

Tests cover normal imports, retries/conflicts, duplicate VIN, foreign tenant,
wrong role, deleted identities, ended/replaced membership, trip before membership,
cross-midnight trips, DST boundaries, reversed dates, invalid timezone, nonfinite
numbers, totals across pagination, empty results and unchanged vehicle/telemetry.
Migration upgrades and downgrades only the new table; rollout is additive and
old clients remain compatible. App rollback hides the new surface while retaining
stored trips; destructive migration downgrade is not a routine rollback.
Live collection/import and deployment need separate accurate release evidence;
mocked UI acceptance never proves imported production data.
