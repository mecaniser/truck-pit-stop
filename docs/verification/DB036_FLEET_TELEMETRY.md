# DB-036 manual telemetry and Fleet Board verification

2026-10-01. Accountable owner: Backend & Integrations. Implementation follows
`docs/DB-036_FLEET_TELEMETRY_CONTRACT.md` on `codex/db036-motive-sandbox`.

## State

Implementation and offline verification passed. The existing draft PR #443 contains
the prerequisite Motive integration and this follow-up. Independent offline QA
and application security are GO; see the separate independent review record.
This follow-up is not deployed, and no production telemetry snapshot has been
submitted. Authenticated runtime and actual configured basemap acceptance remain
blocked by missing approved configuration.

## Automated checks and review

- Frontend owner: 36 focused tests (17 telemetry, 13 board, 3 detail, 3 navigation), TypeScript,
  targeted ESLint and normal production build passed.
- Backend owner:36 tests passed with disposable PostgreSQL enabled:22 new
  capture/projection tests and14 existing fleet-board/projection regressions.
  Coverage includes same-request concurrent retries, wrong VIN/tenant/membership,
  no-store redacted errors, origin rejection, zero/null readings, field ordering,
  legacy/projection/detail parity and bounded SQL snapshot selection.
- Root final normal frontend production build passed after the synthetic-token
  bundle check, replacing temporary synthetic build artifacts.
- Independent UI review caught map recreation on the 30-second age tick; the
  frontend owner corrected the lifecycle and added regression coverage.
- Root migration preflight: full empty PostgreSQL 15 chain through 153 passed.
  First new 154 attempt failed because its parent named `153` rather than the
  actual revision `153_motive_full_scope`; returned to Backend for correction.
  After correction, 153→154→153→154 passed. Snapshot model columns match the
  migrated table exactly; composite membership FK and request uniqueness exist.
  Independent backend/security gate passed:176 distinct backend cases and37
  frontend cases, including the existing Motive PostgreSQL regressions.

## Runtime preflight

At intake the intended worktree was clean at `e009acb4`. Frontend port 5173 and
backend port 8000 were unbound; frontend proxy targets `127.0.0.1:8000`.
The runtime controller dry-run blocked on missing approved `backend/.env`.
No application configuration, shared database, or existing services were changed.
Authenticated full-stack local acceptance is therefore blocked. Synthetic
component/browser fixtures and an explicitly disposable PostgreSQL instance
provide separate offline evidence; they do not establish production readiness.

## Dashboard identity observations

The operator checked the two requested trucks in the authenticated Motive and
DieselBridge interfaces. Both full VINs match. Provider unit numbers, model years,
company labels and DieselBridge card headings alone are not sufficient identity
or membership evidence. Actual VINs, readings and locations are kept outside the
repository and synthetic tests.

One truck has dashboard telemetry; the other currently reports that a Vehicle
Gateway must be added to see location/telematics. That message establishes
unavailable dashboard data, not whether a physical device is installed.
No empty snapshot or invented zero measurement may be imported for that truck.

The available dashboard reading exposes a relative age, not an absolute source
timestamp. Preserve that text and leave observation time unknown. An Open area
map URL exposes a viewport center, not a verified vehicle coordinate. No map pin
is justified by that URL or a highway/ZIP label. Refresh readings before an
eventual production import instead of treating this discovery capture as current.

## Owner synthetic browser evidence

2026-10-01 17:38–17:40 UTC: temporary Vite fixture served the actual changed
FleetBoard, TruckDetail, TelemetryCapture and FleetMap from the intended worktree.
Listener PID 30982, port 5173 and source working directory were checked, with HTTP
200 for the fixture. Its visible banner identified synthetic data; Axios used an
in-memory adapter, with no application backend or production connection.

- Desktop board and detail displayed a manual location, reported mileage and
  speed with observation-time-unknown captions, separately from service mileage.
- Saving a synthetic partial capture refreshed truck detail, preserved zero
  speed and service mileage, and left motion unknown for an unknown source time.
- Map fallback retained both selectable trucks without invented pins. The
  absent Mapbox token was visibly reported. Actual provider basemap rendering
  remains unverified until an approved configured runtime is available.
- At 390px width, map list and capture form were usable; selecting a list truck
  opened its detail, and a wrong VIN submission produced the expected rejection.
  Viewport override was reset after inspection.

Temporary harness files were removed and the exact fixture Vite PID 30982 was
gracefully stopped after rechecking its source path. The temporary browser tab
was closed; user-owned Motive and DieselBridge tabs were preserved.
After independent tests finished, the dedicated disposable PostgreSQL container
was stopped and automatically removed. Existing application services and volumes
were not modified.

These checks establish frontend interactions against synthetic responses only;
they do not exercise HTTP authorization or durable database persistence.

## Import workflow after release

1. Read the authorized Motive truck dashboard and verify its full VIN against
   the selected DieselBridge truck.
2. Confirm the selected active board membership company. Operating authority,
   owner and invoice recipient may be different companies.
3. Open the manual capture form. Enter only the displayed readings and units.
   Leave coordinates and observation time blank when they are not available.
4. Save once, then verify the board and detail show the reported readings with
   their manual source and time labels. An unknown-time speed must not imply
   live motion. The map may show a location-unavailable list entry.
5. Verify service mileage, maintenance projections and repair status are
   unchanged. Repeat for other verified trucks that have actual readings.

Manual captures are point-in-time work. They do not establish a recurring scrape
or an active Motive API connection.

## Release and rollback boundaries

Required before release: focused automated checks, migration verification,
independent QA/security review and the applicable runtime/release gates. Provider
approval is needed for live OAuth collection, not for this separately authorized
manual capture path. Keep live collection disabled until its separate gates pass.

If board reads, tenant isolation or capture authorization regress, stop new
captures and roll back application code. Preserve snapshot rows for diagnosis;
do not use a destructive migration downgrade on production as a routine rollback.
The existing canonical vehicle/service fields are not overwritten by snapshots.
