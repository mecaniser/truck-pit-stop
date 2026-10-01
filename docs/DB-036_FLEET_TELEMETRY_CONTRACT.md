# DB-036 Fleet Board telemetry and geographic map contract

Architecture v1, 2026-10-01. Accountable owner: Backend & Integrations. This is
the follow-up to the full Motive connector: authorized manual dashboard captures
and connector readings become visible on the existing Fleet Board and truck
detail, with a geographic map. It does not authorize production changes or
change the existing provider-account/customer authorization model.

## Scope and ownership

- Backend owns one additive snapshot migration after the actual current Alembic
  head, snapshot model/service/schemas, capture HTTP route, shared board/detail
  telemetry projection, bounded queries and backend tests.
- Frontend owns the manual capture form, board/detail telemetry presentation,
  FleetMap geographic replacement, map dependency declaration and UI tests.
- Root owns the real dashboard capture/identity evidence, board intake and
  release decision. Values and vehicle associations must come from that evidence.
- Architecture owns this contract only. Fresh independent QA/Security reviewers
  review the implementation. Do not treat this design as an approval of code.

## Identity and authorization

GET `/fleet/board` and GET `/fleet/trucks/{vehicle_id}` retain their current
authorization: same-tenant GARAGE_OWNER, GARAGE_ADMIN or FLEET_MANAGER under
`require_fleet_access`. Do not grant customer-portal users shop-wide board access.

Manual capture is restricted to active GARAGE_OWNER/GARAGE_ADMIN in an active
tenant, with trusted Origin checks for cookie mutations. Resolve tenant from the
validated principal. Require exact same-tenant vehicle, selected fleet company
and active FleetMembership. Use `board_membership_customer_id`, not ownership,
billing or an assumed equivalence to `fleet_customer_id`. Staff must explicitly
select the current board company and confirm the full VIN. Normalize VIN by trim
and uppercasing only, then require an exact 17-character match with the canonical
truck VIN; reject absent, malformed, mismatched or ambiguous identity.

Motive company name/ID and Motive truck number are capture provenance only. They
do not authorize a DieselBridge company, modify FleetMembership, create a Motive
OAuth binding or select a tenant. One dashboard account may visibly contain
vehicles belonging to different DieselBridge fleets. Never hardcode a provider
company name to a DieselBridge company or match only by unit number.

Record the exact FleetMembership ID at capture. Reads require that this same
membership remains nondeleted and currently effective. A truck leaving and later
rejoining a company must not inherit a former membership's captured readings.
Known observed_at must also fall within that membership's effective interval.
Unknown observation time is explicitly unknown; its capture time must fall in
the membership interval. Recheck identity and membership inside the transaction.

## Manual capture HTTP contract

`POST /api/v1/fleet/trucks/{vehicle_id}/telemetry-snapshots`

```json
{
  "client_request_id": "UUID",
  "fleet_customer_id": "UUID",
  "vin": "EXACT_VERIFIED_17_CHAR_VIN",
  "observed_at": null,
  "source_age_text": "41s ago",
  "provider_company_label": "Visible Motive company label or null",
  "provider_vehicle_id": null,
  "provider_vehicle_number": "609",
  "location_label": "Location text exactly observed, or null",
  "lat": null,
  "lng": null,
  "speed_mph": null,
  "odometer_miles": null,
  "engine_hours": null,
  "fuel_percent": null,
  "fault_count": null,
  "evidence_note": "Dashboard capture; observation timestamp not displayed."
}
```

This is an immutable journal entry, not PATCH to Vehicle. `source` is always
server-assigned `motive_dashboard_manual`; captured_at and captured_by_user_id
are server-assigned. Never accept a client timestamp as capture time. The form
allows the source observation time to remain blank. Only enter observed_at when
the dashboard identifies a time applicable to these readings; do not interpret
page-opening time, current clock or a GPS-only update time as all metric times.
For genuinely different observed times, submit separate partial snapshots.

All measurement fields are optional/nullable, but require at least one actual
reading (including location_label). Trim text; enforce sensible length limits:
provider_company_label 255, vehicle IDs/numbers 120, location_label 500 and
evidence_note 1000. Reject nonfinite numbers, negative readings, fuel outside
0–100, fractional/negative fault count and invalid coordinates. Coordinates must
be supplied together; ranges lat[-90,90], lng[-180,180]. Zero coordinates and
zero speed are valid measurements when actually observed, never defaults.
Use existing conservative Motive bounds for odometer/hours/speed; no inferred
conversion unless the UI actually shows a known source unit.

observed_at must include a timezone, be no more than five minutes in the future,
and be within the 30-day retention window. Its absence is allowed.
Optional source_age_text (maximum120 characters) records the visible relative
age verbatim; do not subtract it from capture time to fabricate observed_at. A missing
dashboard odometer/engine-hour basis is stored as `dashboard_unspecified`, never
silently labeled calibrated, true, virtual or ECU-derived. No geocoding call is
made from location text and no approximate place coordinate is stored as a truck
position. A map popup or UI data source showing exact vehicle coordinates may
supply them. A link marked Open area with an ll parameter is a viewport center,
not evidence of the vehicle position.

Return 201 on first creation, 200 for an identical client_request_id retry:

```json
{
  "id": "UUID",
  "vehicle_id": "UUID",
  "fleet_customer_id": "UUID",
  "source": "motive_dashboard_manual",
  "observed_at": null,
  "captured_at": "UTC ISO timestamp",
  "captured_by_user_id": "UUID"
}
```

Unique `(tenant_id, client_request_id)` plus canonical submitted-body digest.
Reuse with different content returns409. Forbid cross-user replay disclosure:
an existing entry is returned only after reauthorizing its vehicle/company and
requiring the original submitting actor. Foreign/missing/ended membership and
vehicle/company IDs return uniform404; disallowed role403; invalid values422;
VIN mismatch409 with stable `vehicle_identity_mismatch`. Use safe no-store JSON
errors; do not echo raw request bodies. No edit/delete route in this scope.

## Storage and retention

New `FleetTelemetrySnapshot` stores tenant_id, vehicle_id, fleet_customer_id,
fleet_membership_id, verified_vin, request ID/digest, source, observed_at,
captured_at, actor, source_age_text, provider provenance, allowlisted measurements and note.
Composite tenant+vehicle/company FKs must reject cross-tenant references;
membership validation covers all four identities. Index tenant+vehicle+captured_at
and the retention timestamp. Entries are append-only except retention purge.

Retain dashboard snapshot data for30 days from captured_at and suppress reads
after that bound even if purge is late. Known source readings older than30 days
are also excluded. Do not require MOTIVE_ENABLED or OAuth credentials for manually
authorized captures. Scheduled purge must run while provider collection is off.
Keep real dashboard values and identity worksheets out of committed source/tests;
use synthetic regression fixtures and private evidence for actual captures.
No existing Motive fixture tables are repurposed and no production migration is
performed as part of offline verification.

## Shared read projection

Add nullable `telemetry` to BoardTruck, returned identically by both board and
truck detail. Build it in one service after membership/account context has been
attached, on both projection and legacy-builder paths. Read bounded sets for the
returned vehicle IDs; no provider HTTP and no per-truck SQL requests on board GET.

```typescript
type ReadingProvenance = {
  source: 'motive_api' | 'motive_dashboard_manual' | 'manual_location';
  observed_at: string | null;
  captured_at: string | null; // server receive/capture time, not observation
  freshness: 'fresh' | 'delayed' | 'stale' | 'unknown';
  snapshot_id: string | null;
  source_age_text: string | null;
}
type NumericReading = ReadingProvenance & {
  value: number;
  unit: 'mph' | 'mi' | 'h' | 'percent' | 'count';
  basis: 'calibrated' | 'virtual' | 'dashboard_unspecified' | null;
}
type LocationReading = ReadingProvenance & {
  lat: number | null; lng: number | null;
  label: string | null;
}
type FleetTelemetry = {
  location: LocationReading | null;
  speed: NumericReading | null;
  odometer: NumericReading | null;
  engine_hours: NumericReading | null;
  fuel: NumericReading | null;
  fault_count: NumericReading | null;
  motion: 'moving' | 'stopped' | 'unknown';
}
```

`null` means no admissible measurement; do not emit a zero-valued reading merely
to satisfy a schema. Provenance belongs to each reading, so a new position cannot
make yesterday's odometer or faults look fresh. Label API received_at as captured
or received, never as the vehicle observation time. Fault synchronization time
may show a confirmed snapshot timestamp but must not be claimed as fault onset.

For each field choose the latest admissible known observed_at; ties prefer
Motive API, then latest captured_at, then stable snapshot ID. If no known-time
candidate exists within retention, choose the newest unknown-time manual capture.
This policy prevents a newly opened dashboard from defeating a known source
observation; manually captured values with unknown time remain usable and labeled
Captured / observation time unknown. Missing fields do not erase another valid
source's reading. Raw dashboard labels such as Yard are preserved as reported
location text only, never treated as operational repair status or exact geometry.

API candidates must pass the connector's existing configured/allowlisted active
connection, generation, explicit vehicle binding, observed-time and current
exact-company FleetMembership checks. A manual capture in a different fleet
cannot relax those checks. Disconnect/ended membership suppresses API readings;
manual snapshots remain independently governed by their recorded membership.
Prefer true API odometer/hours when supplied; otherwise a virtual API reading is
allowed with `basis: virtual`. Never label that fallback calibrated. Fuel is null
unless an actual approved source supplies it. API fault_count is the count of
known open faults only when the connection's fault snapshot is recently checked;
do not derive truck fault count from shop warning lights or incidents.

Freshness uses observed_at: <=5 min fresh, <=15 min delayed, then stale within
retention. Unknown observed_at yields unknown, even when captured just now.
Motion is moving/stopped only for a fresh speed reading; zero means stopped and
missing/stale/unknown-time speed means unknown. No inferred parked state.

Existing canonical `odometer`, status, PM inputs/projections, warning_lights,
incident counts and work orders stay unchanged. Add a distinct reported-mileage
display instead of overwriting service-mileage inputs. Never let location speed
or a dashboard status move a truck between repair columns.

## Existing last_* location compatibility

Load Vehicle.last_location_at alongside legacy last_* values. A legacy manual
location with a timestamp can be a lowest-priority `manual_location` candidate,
with captured_at=last_location_at and observed_at=null. Untimestamped legacy text
may be displayed as an explicitly undated manual note in detail, but not a map
pin or current-location claim. Expired legacy values must not reappear when a
newer source becomes unavailable.

Frontend board/map/detail location presentation must consume telemetry rather
than silently fall back to raw top-level lat/lng. Existing top-level location
fields may remain for compatibility, but the changed UI must not use them as
current positions. In particular remove the TruckDetail `speed ? mph : parked`
logic and title Current location when the reading is stale/unknown. Nearby
distances use validated geographic coordinates from the same selected location
reading and are labeled straight-line, last-known when applicable.

## Geographic map

Reuse the existing approved Mapbox integration and `VITE_MAPBOX_TOKEN`. The
current lockfile already installs mapbox-gl3.18.0 through search-js; if importing
it directly, declare that installed compatible version as a direct frontend
dependency and preserve a reproducible lockfile. Do not create a key, copy
credentials or add a second provider. Use a real geographic Mapbox base map and
required attribution, with exact longitude/latitude points and fitted bounds.

Replace the schematic roads, fixed yard and golden-angle fake positions in
FleetMap. Unknown coordinates produce **no pin**. Show those trucks in a clickable
Location unavailable list, including their actual location text/provenance where
present. Preserve all trucks even if none can be mapped. Text alone must not
trigger geocoding. Same-location trucks can share a cluster or selectable list;
never move their coordinates to spread markers. Offscreen trucks are brought into
bounds rather than clamped to an arbitrary edge.

Pin/list popup shows unit/company, source, observed/captured time, freshness and
reported speed; operational repair status can appear separately. Stale/unknown
observations are visibly last-known, never animated as currently moving. If map
token or WebGL/network/style is unavailable, retain the accessible truck list and
show Map unavailable. Do not substitute the schematic or a fake yard pin.
Do not put VINs, driver names, tokens or other sensitive fields into map provider
URLs. Markers and captions use safe text DOM, not unescaped popup HTML.

## Required acceptance evidence

- Actual capture worksheet/evidence verifies each VIN and selected existing
  board-membership company; no unverified 603/609/company inference.
- Valid partial snapshot with unknown observation time, actual zeros, exact
  timestamps, coordinate-pair validation, bounds and replay/conflict behavior.
- Rejected wrong role/tenant/company/VIN, ended/replaced membership and denied
  customer-portal board access; no canonical mileage/status/PM writes.
- Field-level latest selection, API/manual ties, missing fields, null times,
  stale/expired observations, API disconnect and legacy timestamp fallback.
- Projection and legacy-builder board paths and truck detail return the same
  normalized telemetry; bounded query count does not grow with truck count.
- Real geographic positions, missing-coordinate list, exact coincident points,
  far-apart bounds, no token/error fallback, safe captions and correct motion.
- Desktop/mobile browser interactions for capture, board/detail, map/list
  selection and source/freshness labels; fixture evidence is identified as such.
- Additive PostgreSQL upgrade/downgrade, focused regression tests, independent
  auth/tenant security review and QA. Live authenticated runtime, actual data
  writes, merge/deployment and provider approval remain separately evidenced.

## Repository evidence

- `backend/app/api/v1/endpoints/fleet.py`: existing Fleet roles, membership-backed
  board, `_build_board_truck`, projection path and current last_* reads.
- `backend/app/schemas/fleet.py`: BoardTruck compatibility fields.
- `backend/app/db/models/vehicle.py`: last_location_at and manual location fields.
- `backend/app/db/models/motive_oauth.py`: existing normalized API telemetry.
- `frontend/src/features/fleet/FleetMap.tsx`: schematic/fabricated missing pins.
- `frontend/src/features/fleet/TruckDetail.tsx`: existing parked fallback.
- `frontend/src/components/MapboxAddressInput.tsx` and frontend lockfile: existing
  Mapbox token convention and installed geographic renderer.

### Capture fleet selection clarification

The selected board truck fixes the capture company to its explicit
`board_membership_customer_id`. Show `board_membership_company_name` beside the
truck VIN; require staff to enter the full VIN verified in Motive and press Save.
This is the explicit selected fleet confirmation; an arbitrary company dropdown
is not required. Do not infer company from the owner or operating authority
header. Missing board membership disables capture.
