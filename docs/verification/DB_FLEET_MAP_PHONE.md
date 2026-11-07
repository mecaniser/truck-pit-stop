# DB-FLEET-MAP-PHONE

Owner: Frontend & UX. Fast UI lane. Branch: `codex/fleet-map-phone`. Draft [PR822](https://github.com/mecaniser/truck-pit-stop/pull/822).

Acceptance: small-screen markers hide fleet branding and show compact unit-number circles; black outline, red selected outline; full long labels retained. Preserve status/last-known information, company-scoped grouping, cluster expansion, GPS anchors and accessible selection. Phone map height and framing suit narrow screens; search does not trigger iOS input zoom. Desktop branding remains unchanged. No API, auth, tenant, migration or data changes.

## Local verification — 2026-11-06 22:22 America/New_York

- 320/375/390/430px browser layout: 32×32px badges, 50% radius, hidden brand images, 16px search font, every synthetic badge within map bounds, document width equals viewport width.
- 844/1440px: existing branded badges retained, no document overflow.
- Actual FleetMap/FleetMapCanvas and production global/fleet/proximity styles rendered with 15 synthetic units and a mock Mapbox projection. Browser pointer selection selects603 with red outline (`rgb(198,40,40)`), keyboard Enter selects600; long unit label remains intact. Screenshot kept locally at `frontend/output/playwright/fleet-map-phone/phone390.png`.
- Provider rendering, real geography/zoom and signed-in backend acceptance are NOT established by this synthetic preview. Routing intentionally returns unavailable in the preview. No provider/customer records accessed or changed.
- 52 focused tests (canvas/layout/label/clustering36, FleetProximity16), changed-source ESLint, controls check, TypeScript and production build pass. Build has existing large-chunk advisory.

## Runtime alignment receipt

- Intended checkout: `truck-fleet-map-phone` worktree, branch `codex/fleet-map-phone`, base `a0ff0092`, task source/board edits dirty during verification.
- Mandatory runtime controller `switch` attempted: blocked by absent approved `backend/.env` (dependencies subsequently installed from lockfile). No configuration or credentials copied; no API process stopped or repointed.
- Existing8000 container belongs to a separate sandbox; frontend5173 unbound during preflight. It was not used to claim acceptance.
- Synthetic-only Vite preview: loopback port5193, route `/output/playwright/fleet-map-phone/index.html`, PID31021, process command and cwd verified at this checkout's frontend, HTTP200. Custom local config has no API proxy and intercepts provider fetches. Source-specific32px badge rendering verified.
- Full local stack: **blocked**. Preview: browser-verified synthetic presentation only. Signed-in Fast UI acceptance remains pending. No merge/deployment authorization in this task.

PR CI and signed-in acceptance remain required before release. Not Done.
