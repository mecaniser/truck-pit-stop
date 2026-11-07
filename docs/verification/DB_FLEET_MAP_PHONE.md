# DB-FLEET-MAP-PHONE

Owner: Frontend & UX. Fast UI lane. Branch: `codex/fleet-map-phone`. [PR822](https://github.com/mecaniser/truck-pit-stop/pull/822).

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

## Release and signed-in acceptance — 2026-11-06

User explicitly authorized finishing verification, merging/deploying and checking the live map. All seven protected CI checks passed on `1332059c` in run42333703160. The scoped diff review found no new contract, auth, tenant, migration or payment behavior. No VERSION/CHANGELOG changes in this focused UI PR.

PR822 squash-merged at2026-11-07T03:30:54Z (Nov6 22:30:54EST) as `1765e3b615f30b97c6acd7417927c7cd3c1b7230`. Railway auto-deployment `accf7b6e-728f-49c1-94f5-4811537ed44b` succeeded on that exact commit. Public www/API build stamps match; readiness reports healthy database/Redis.

Premerge signed-in production candidate stylesheet preview passed320/390/430px and desktop branding/selection. Temporary stylesheet override was removed before deployed-build checks. This was a browser-local style preview, not a claim that candidate JS was deployed before merge.

After deployment, reloaded the signed-in production `/fleet` with **no stylesheet overrides** and actual Mapbox geography/provider rendering:

- 320×740,375×812,390×844,430×932:32px badges, hidden fleet logos,16px search field, document width equals viewport width. Responsive map canvas heights362/403/417px in the corresponding phone views.
- 844×390 landscape and1307×900 desktop: no document overflow; desktop branded presentation retained.
- Expanding the seven-unit cluster reveals every member; selection of609 gives32px badge with red border `rgb(198,40,40)`, matches the detail heading, and routing reaches the closest-road-route state.
- Unit24 without coordinates shows the explicit no-verified-coordinates notice with no fabricated map pin.
- Clear selection and Recenter restore the overview and geographic clusters. Browser console reports zero errors. Browser viewport restored to its original size.
- No fleet/customer records, statuses, payments or settings changed. These are responsive browser checks, not physical-iPhone hardware testing.

Private production screenshot retained only locally at `frontend/output/playwright/fleet-map-phone/production-phone390.png`; excluded from Git. Product item **Done — released and browser verified**, Frontend & UX accountable. Historical local-backend configuration blocker above remains a local environment limitation, not a production acceptance blocker.
