# DB-036 road proximity contract

Owner: Frontend & UX. Contract responsibility: Architecture & API Contracts.
Lane: Standard product (new routing-provider workflow); independent QA before release.

## Acceptance and provider contract

- Origin is the selected truck; destinations are all other coordinate-bearing trucks in the supplied tenant-scoped board. No preselection by aerial distance. Existing observed-time freshness gates apply to both ends; last-known requires explicit opt-in.
- Rank ascending by miles returned on Mapbox fastest driving routes, deterministic ID tie break; show estimated driving duration. This is general driving comparison, not absolute minimum-mile or truck-restriction-aware navigation. Vehicle dimensions/weights are not present in the board contract and must not be invented.
- Browser uses existing public Mapbox token. Send coordinates only (no truck IDs, labels, driver details or Motive credentials) to the same approved Mapbox provider. No persistent route cache, DB writes or new internal endpoints.
- Matrix GET `directions-matrix/v1/mapbox/driving/{coordinates}`: selected source index 0; explicit destination indices; annotations distance,duration. Batch up to 24 destinations plus origin. Null entries mean no route, not zero; never use fallback_speed. All batches must complete before claiming a closest result.
- Directions GET `directions/v5/mapbox/driving/{origin};{closest}` with geometries=geojson, overview=full, steps=false. Draw returned road geometry only, no invented connectors. Geometry failure does not remove valid matrix ranking; expose route-preview failure.
- Invalid/missing token, errors, null routes and empty candidate sets have explicit UI states. Hide previous ranking/geometry immediately when origin, coordinates, eligibility or scope changes. Abort superseded requests; bound requests with a timeout; no auto-retry loop or hidden routing while no origin exists.
- Tests: reversal versus straight-line ranking, correct directed request, multi-batch coverage, ties/zero/null/malformed response, cancellation/late replies, missing token, changed/removed scope and positions, last-known gating, route polyline rather than straight connector, compact UI.

## Runtime boundary

Isolated synthetic frontend on 127.0.0.1:5186; backend 8000 absent and approved backend configuration unavailable. No local production API/DB connection. Real-fleet acceptance remains blocked by 0 of 21 trucks with coordinates, verified in prior receipt. Preview exercises live Mapbox with synthetic coordinates only.

References: https://docs.mapbox.com/api/navigation/matrix/ and https://docs.mapbox.com/api/navigation/directions/

## Motive account clarification

The tenant has an accessible Motive dashboard account; the absent connection record means no direct API integration configured in DieselBridge. Dashboard capture is a supported alternative. Authenticated inspection on 2026-10-04 verified truck 609 has a Copy coordinates action beside its location; the action returned an exact latitude/longitude pair. The dashboard showed 48m 1s since the observation. Exact source age retained; no exact observed_at invented. Private capture is outside committed fixtures under output/proximity-map; no production snapshot submitted. This proves dashboard coordinates are available for at least this truck, not all 21. Manual snapshots with coordinates can supply pins without an API connection.

## Verification receipt — 2026-10-04

- 55 focused tests pass: routing 12, proximity 8, canvas 4, telemetry 22, return context 5, detail 4. TypeScript, production build and explicit changed-file ESLint pass. Added negative regression proves previous road geometry is cleared during recalculation.
- Independent QA agent `road_proximity_qa` reviewed implementation without editing: GO for code and focused automated contract checks; no blocking correctness/privacy findings. Reviewed 54 tests before final additional geometry-clear test; root reran final 55.
- Runtime: branch codex/fleet-road-proximity, base/receipt HEAD40fc2e4b, implementation initially uncommitted; Vite PID9315 serves this worktree frontend on127.0.0.1:5186. Runtime metadata set from branch/HEAD at startup. Default API proxy8000 absent; no backend/.env or database connected. Port5173 belongs to another task and was preserved. Synthetic fixture is intentionally frontend-only.
- Live Mapbox desktop accessibility acceptance:101→2043.9mi/14min; selection307 cleared old rows to Calculating road distances then returned20412.5mi/19min,10114.4mi/22min,40816.8mi/29min, and Route shown. This is directed road routing, not straight-line estimates.
-390px iframe browser acceptance: fresh results present; Include last-known brought610 into first place0.4mi/3min. Selecting610 changed origin with Last known2h ago and returned1010.4mi/4min,2043.8mi/12min,30714.2mi/21min. Controls remained accessible; no production changes.
- Browser automation CDP timed out; native Chrome accessibility actions succeeded. Native screenshot capture returned only a257x160window thumbnail, inadequate for a detailed visual/overflow review. Full-resolution visual review and authenticated real-fleet routing remain pending; do not call the complete release gate done.
- Real Motive account access confirmed separately above. Exact last-known coordinate discovery is available via dashboard; importing verified manual snapshots remains separate from this routing-code change.

## Route contrast and quick-info refinement

Fast UI follow-up on PR468: blue6px road route with10px white casing and repeated forward arrows; side-panel card displays selected→closest IDs, prominent road miles and estimated drive time. Loading clears the card metrics; existing missing-route behavior retained.12affected component/canvas tests and TypeScript/ESLint pass. Native browser verified card at desktop and390px, then selection307→204updated to12.5mi/19min. Same source-aligned frontend PID9315/5186; backend remains absent. Screenshot capture still thumbnail-only; no claim of new full-resolution visual review or production deployment.

## Compact company markers

User-supplied77Cargo reference translated to a red/black SVG wing mark without company text. Matching operating company (fallback board membership/owner) gets the mark beside unit number; other or mixed-company pins remain neutral. Translucent light rectangular badge roughly30px tall,44px transparent target, status dot, blue selection outline and dashed last-known boundary. Preview fixtures explicitly identify as77Cargo; no production identity changes.5canvas tests, TypeScript and ESLint pass. Native Chrome verified six markers with77Cargo company tooltip and preserved nearby-origin selection. SVG served200 from existing5186runtime. Full-size visual capture remains unavailable; user-visible preview updated.

## Stable selection follow-up

Markers are reconciled by sorted group membership, retaining button/badge identity through selection and routing responses. Only changed coordinates move an existing marker; removed or regrouped members replace the affected markers. Camera fits the fleet initially and responds only to explicit Recenter thereafter. Route source clears/updates without marker replacement. Map readiness resets when the map instance changes, including development refresh.27focused tests (7canvas,8proximity,12routing), TypeScript, ESLint and diff checks pass. Native Chrome selection101→307retained all six marker AX identities during loading and after the307→20412.5mi/19min route result. Same source-aligned5186PID9315; screenshot limitations and absent local backend unchanged.

## Alignment correction and single-line truck rows

Root cause of pin/route offset: updating button.className after Marker construction discarded Mapbox's mapboxgl-marker class (absolute positioning). Preserve provider classes and toggle app classes with classList; tests now model Mapbox adding its class and assert survival initially and across selection/results. Truck list rows are single flex lines with unit-corner status dot, hover title/accessibility status name, truncated location, age, road miles and compact driving duration.15affected tests, TypeScript/ESLint pass; native browser confirms six markers and new compact-row content. Detailed rendered alignment review remains limited by native thumbnail capture; no production deployment.

## Opaque markers and overlap callouts

All badge states now use solid white with charcoal text; unrelated markers no longer lower opacity. Clustering uses projected screen overlap (96x56px neighborhood), recomputed after map movement/resize. Each cluster has an offset count billboard, leader and location dot anchored at an actual member coordinate; it does not fabricate an average truck position. Popup exposes each member and last-known status. Zoom can split nearby coordinates while identical coordinates stay grouped.16affected tests, TypeScript/ESLint pass, including screen-overlap grouping, zoom separation, preserved coordinates and no unsolicited camera fit. Native preview verified3-truck cluster101/204/610, member chooser, and610selection preserving last-known eligibility messaging. Full-resolution capture limitation unchanged; no release.

## Polished cluster chooser without map occlusion

PR468 merged the road-routing and route-summary/color work, before subsequent marker/cluster refinements. Branch codex/fleet-cluster-popover starts from current main c1037855 and carries those later commits forward. The chooser is now a rounded white card in the existing side panel (compact view: below map), with status dots, stronger unit text, muted labels, blue keyboard focus and a close control. No floating map popup can hide a truck. Cluster click brings the card into view; member selection dismisses it.

17affected tests, TypeScript/ESLint/diff checks pass. Native Chrome verified cluster101/204/610opens in side panel and204selection closes it. Runtime realigned: frontend5186PID85747, worktree fleet-proximity-map, branch codex/fleet-cluster-popover, startup HEADd45f25f5plus verified edits. No local backend/database configured; synthetic preview with live approved Mapbox only. Full-resolution screenshot limitation unchanged. Not deployed.

## Zoom-first cluster interaction

Cluster click now uses member bounds to ease the camera inward (at least one zoom level, capped18). Nearby distinct positions separate progressively instead of opening a special panel. Identical coordinates or still-overlapping pins at zoom18retain the chooser as a usable fallback. Single-truck selection still never reframes the camera. Persistent click handlers read the latest member positions.17affected tests, TypeScript/ESLint pass. Native browser verified the three-truck group separates204from the closer101/610pair with no card. Clustering is screen-space96x56px and has no effect on road-mile ranking.


### Home overview — 2026-10-04

Frontend & UX / Fast UI, PR469. Initial preview no longer selects101. Production FleetApp already initializes mapFocusId undefined; explicit detail/return selections remain supported. Initial fit and Recenter always bound every located truck. Home and the clickable address move to the geocoded home at zoom15 and Home clears selection. A separate home marker identifies the base.

Address:416 Seaboard Drive, Matthews, NC28104. Mapbox v6 forward geocoding returned an exact address match (number, street, postcode, place and region matched). Temporary coordinates remain in memory. The address is enabled for authenticated tenant_slug truck-pit-stop only, passed as an optional component prop; other tenants do not inherit this base. Preview supplies it explicitly. No tenant data or configuration is written.

Home-to-truck Matrix road miles rank all usable positions, with last-known age labels and missing/unreachable trucks retained after ranked entries. This uses miles along the provider fastest driving routes, not global minimum-mile optimization. No overview Directions geometry is requested. Selected-truck routing and freshness opt-in remain unchanged. Failed home lookup disables Home and retains the full truck list without distances.

Checks:37 tests across canvas, proximity, routing and FleetApp return context pass; TypeScript and affected map/hook/test lint pass. Native Chrome desktop and390px preview show unselected Closest to home, all7fixture trucks and road ordering101(15mi),610(15.1mi,last-known),204(17.8mi), etc. Selecting101 switches to truck comparison; Home clears it back to overview. Camera bounds/Home transitions have focused tests. Screenshot capture remains distorted/thumbnail-only, so no full-resolution visual sign-off is claimed.

Runtime:5186/PID85747 still serves this worktree on codex/fleet-cluster-popover; pre-edit HEAD babde0e4 plus these source edits. HTTP200 and rendered Home/road results verify served source. Backend8000 absent; no approved local database configuration, authenticated full-stack acceptance unavailable. Synthetic data with real Mapbox only. Not merged/deployed.


### Shop priority and search focus — 2026-10-04

Frontend & UX, Fast UI follow-up on PR469. For a selected eligible truck, compare directed shop-to-selected miles with selected-to-nearest-truck miles. Shop wins when nearer or tied, including when no other truck is routable. Recommendation controls summary endpoints, miles/time and Directions origin/destination; nearby rows retain truck comparisons. Stale/absent selected positions retain the existing eligibility rules. Errors in either comparison do not claim a winner; selection/scope changes invalidate recommendation and geometry immediately.

Live provider check found Matrix rejects a single cell with422 InvalidInput. Singleton batches now request destinations0;1, validate both returned entries and discard the self-distance. This also repairs existing one-other-truck and single-truck-home-overview cases.

40focused routing/proximity/canvas tests pass; TypeScript, scoped ESLint and diff checks pass. Native Chrome scenario `tests/proximity-preview.html?scenario=shop-closer` displays Shop→101,1.5mi/7min, blue route, and other trucks at17.2mi/31.2mi/42.8mi. Scenario is explicit synthetic data. Same aligned5186process/worktree; no backend or production mutation. CSS focus-within now outlines the full search label including its icon; inner input outline suppressed. Served stylesheet verified and native search focus exercised; prior screenshot capture limitation persists. Not deployed.


### Production labels and last-known follow-up — 2026-10-04

PR469 was merged and released independently as3a7d459f. Live fleet inspection showed company-prefixed display_unit_number and full reported addresses, with0/21usable coordinate pairs. The preview previously omitted those production-shaped fields.

New branch codex/fleet-map-real-labels uses the raw unit_number for map/list/summary labels, preserving leading zeros and alphanumeric IDs. Map location text extracts city from reported address labels without geocoding street labels into truck positions. Last-known comparison defaults enabled with existing retention and age labels; operators can still restrict to recent positions. Preview now includes company-prefixed display fields and full synthetic street labels to exercise the real shape. Full frontend1071/1071 tests in125files, TypeScript and scoped lint pass. Native local preview verifies raw IDs and city-only rows. Runtime5186/PID19801 serves this worktree from main3a7d459f plus edits; backend absent, no local database configuration. No new full-resolution screenshot claim.

User authorized using existing Motive last-known positions. One historical exact Copy coordinates capture for unit609 was imported via the deployed fleet_telemetry.capture service after dry-run rollback, exact VIN match, unique active membership, tenant, signed-in garage-owner identity and deployment SHA verification. Source observation time remains null; original capture time/source age retained in evidence rather than invented as a live GPS timestamp. Import created one immutable coordinate-only snapshot; no vehicle identity, service mileage, provider connection or repair record changed. Private payload/receipt remain outside Git under output/proximity-map. Production browser confirms609last-known pin and1located/20without coordinates. This is partial data coverage, not a full fleet import. Motive list inspection also shows some vehicles explicitly lack Vehicle Gateway/location data; other available coordinate pairs remain unverified. UI changes are separate from the production capture and await PR release.
