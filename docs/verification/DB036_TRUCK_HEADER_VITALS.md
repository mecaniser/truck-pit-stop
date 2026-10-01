# DB-036: compact truck header and on-demand refresh

Date: 2026-10-01. Owner: Frontend & UX. Fast UI lane.
Branch: `codex/truck-header-vitals`; base: `7febf05b108e66a68ca69688d98c2dc5ce9fd228`.

## Acceptance and implementation
- Motive mileage beneath canonical service mileage; speed and fuel level beside PM.
- Last location and manual/provider age beside status and details.
- Engine hours and optional manual entry in Truck details > Truck vitals.
- Per-reading provenance accessible by hover, tap, keyboard; Escape and outside dismissal. No standalone repeated provenance block.
- Missing/expired readings omitted, zero preserved, unknown observation time retained. Service mileage and PM unchanged.
- Owner/admin Pull from Motive uses existing company-scoped connection and sync endpoints. Requires explicit board membership, configured connection, and elapsed cooldown. Refreshes existing caches. No browser credentials or new authorization boundary.

## Verification
- 34/34 tests: TruckTelemetry (3), PullMotiveReading (6), TruckDetailHarden (4), FleetTelemetry (21).
- Changed-source ESLint, TypeScript/production build and git diff check pass.
- CUA Playwright verified the real TruckDetail component in synthetic preview at 820x1180, 1024x768 and 390x844: no document overflow; header, detail vitals, tap provenance, Escape dismissal and fuel tooltip within phone viewport.
- Pull from Motive in preview returns connection-required notice without sync POST when unconfigured. Unit checks additionally cover correct company payload, cooldown, missing membership, role and sanitized failure.
- Runtime alignment dry-run refused retained untracked output artifacts; approved backend environment absent. Preview only, no authenticated local backend. Not full-stack or real-provider sync acceptance.
- Origin/main refreshed before handoff: no new commits beyond base. PR448 already merged; this is a separate follow-up.

## Authorized manual operations
Five additional live snapshots saved after individual full-VIN matches, confirmed in truck views and persisted board after reload. Private operational receipt is outside Git. No coordinates inferred and no canonical mileage changed. Source reading time remains unknown; dashboard age and approximate browser observation context retained. Eight of 22 Motive vehicles displayed Add Vehicle Gateway; fourteen had location data. Motive session expired before remaining truck details could be checked. Remaining imports require user reauthentication.

## Release and provider gates
This UI change is not merged/deployed. OAuth approval, server configuration and real-fleet API validation remain required for working provider pull. No recurring browser collector is running. Browser-assisted imports are manual snapshots.
