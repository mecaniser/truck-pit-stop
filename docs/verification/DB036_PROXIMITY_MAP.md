# DB-036 — Fleet proximity map

2026-10-04. Accountable owner: Frontend & UX. Existing-contract Fast UI lane.
Branch: `codex/fleet-proximity-map`; base `6adc53b72cc98042222795290715ab9d294eecec`.

## Outcome and acceptance

- Clicking a truck selects a comparison origin in the map workspace. Opening
  details is a separate action; FleetApp retains that comparison selection when
  the manager returns to Map.
- Selected pins have a clear outline. Pin border and text status use the existing
  operational status model; speed/stopped state never implies a breakdown.
- Show three nearest eligible trucks, with expansion, straight-line miles,
  operational status, location, and observation age. Connector lines use the
  exact same geographic points; coincident trucks are individually selectable.
- Default eligibility requires valid retained coordinates and an observation
  timestamp within the existing fresh/delayed window (15 minutes, with existing
  future-clock tolerance). Both origin and candidate must qualify. Explicit
  Include last-known permits retained older/undated readings and labels them.
  No road-distance, travel-time, availability or trailer-compatibility inference.
- Unlocated trucks remain searchable/selectable but cannot get fabricated pins
  or distances. Expired data cannot reappear through legacy coordinates.
- Desktop/tablet side panel becomes stacked on small screens. Keyboard selection
  moves focus into the selected summary; clearing returns focus to search.
- Truck details uses the same component and eligibility rules, replacing its
  old independent nearest-list calculation. Read-only existing board scope;
  no auth/API/schema/provider/dependency changes or writes.

## Automated evidence

43 focused tests pass in aggregate:
- FleetProximity: 9 (geographic ranking/ties/zero, stale/unknown/missing/invalid/
  expired/future positions, origin eligibility, expansion, selection/details,
  scope removal, refreshed coordinates, clock aging).
- FleetMapCanvas: 3 (pin interaction and status, coincident selection, exact
  connector coordinates, polling preserves camera, explicit recenter, cleanup,
  renderer-error fallback). Renderer is mocked; these are not basemap proof.
- FleetTelemetry: 22 (existing telemetry/manual-capture semantics plus adapted
  selection/fallback/map lifecycle checks).
- FleetApp.return-context: 5 (including map -> details -> map selection).
- TruckDetailHarden: 4.

Production build passes. TypeScript passes. Strict focused lint passes on new
production code/tests; FleetApp has pre-existing lint debt, so the repository's
baseline-aware changed-source gate passes across all 10 changed TypeScript files.

## Runtime receipt and browser evidence

- Intended checkout: `/Users/sergio_m1_promax/.codex/worktrees/fleet-proximity-map/truck-pit-stop`.
- Preflight controller dry-run refused startup: approved `backend/.env` absent
  and initially no frontend dependencies. Installed locked frontend dependencies
  using npm ci. No backend secrets copied, database migrated, flags changed or
  production API used.
- Existing port5173 PID62713 belongs to the separate Motive workspace. Preserved.
- Isolated frontend: `http://127.0.0.1:5186`, PID61139, Vite command/source cwd
  verified against this worktree; controller branch/SHA environment supplied.
- Preview: `/tests/proximity-preview.html`; HTTP200 and actual changed component
  rendered. Synthetic trucks only; preview calls no backend.
- Default frontend proxy is localhost8000. No backend listener/configuration;
  database/sandbox identity and authenticated readiness cannot be verified.
- No Mapbox token in this checkout. Accessible map-unavailable fallback verified;
  real geographic tiles, actual WebGL pins/lines and live coordinates are NOT
  browser-verified. No new provider/key or credentials were provisioned.
- CUA: selection, three-nearest/expanded list, explicit last-known inclusion,
  separate details and return, search for unlocated truck, Enter selection,
  summary/search focus restoration. Desktop1280, tablet820 and phone390 checked.
  DOM confirms viewport390/document width390 and focused selected summary.
  Temporary viewport reset; preview left open.
- Local screenshot: `output/proximity-map/desktop.jpg` (uncommitted).

Draft PR: https://github.com/mecaniser/truck-pit-stop/pull/467; implementation `92421704`.
The preview process was started at the base SHA; rendered source checks verify
the changed component. Committing did not restart or switch that process.

Status: implementation review candidate. Authenticated full-stack and actual
basemap acceptance remain required before Done. Merge and deployment are not
performed by this task.

## 2026-10-04 follow-up: approved Mapbox and live coordinate coverage

User authorized connecting existing Mapbox configuration and checking actual
fleet coordinates. Reused only the public VITE_MAPBOX_TOKEN from the main
checkout frontend/.env, passed directly into this preview process environment;
no token was printed, committed, newly issued or saved in this worktree. The
process still binds 127.0.0.1:5186 and serves this worktree. Backend remains
unconfigured; preview is intentionally synthetic, not connected to production.

Real Mapbox streets tiles, six coordinate-backed markers (some outside the
comparison bounds), status borders, selected outline and dashed connector lines
rendered in Chrome. Clicked actual map pin204: selection204; nearby101=2.6mi,
307=10.3mi,408=23.2mi. Clicked nearby307: selection307; nearby204=10.3mi,
101=12.7mi,408=12.9mi. These numbers refer only to the labeled synthetic fixture.
Screenshot: output/proximity-map/mapbox-verified.png (local, uncommitted).
Browser CDP access was unreliable; native CUA accessibility, clicks and screenshots
provided the successful browser evidence.

PR467 has since merged as d841cf32 at2026-10-04T22:17:52Z (verified through gh).
The authenticated production Fleet Map exposes the new proximity UI and reports
0located/21without coordinates. A tenant-scoped production read-only database
transaction independently ran the existing board read-model and counted stored
data:21trucks;13manual location labels;8without location;0coordinate pairs;
32telemetry snapshots and0with coordinates;0Motive remote vehicles;0active
Motive connection records. No data, credential, provider or production settings
were changed. Thus no hidden stored coordinates are being dropped by the map.

Usable-coordinate trucks: none. Labels only:77CARGO01,02,03,06,7,77,8,88,W900;
DONTRANS530,531,860;ELIS609. No location:77CARGO022,04,05,077;DONTRANS532,533,HINO;
ELIS603. Names/numbers are coverage identifiers, not geocoded positions.

Actual-fleet pin/proximity acceptance remains BLOCKED on coordinate ingestion
and a connected/mapped provider (or separately authorized verified-coordinate
captures). Renderer suitability and local Mapbox connection are now VERIFIED.
