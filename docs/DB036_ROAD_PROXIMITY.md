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
