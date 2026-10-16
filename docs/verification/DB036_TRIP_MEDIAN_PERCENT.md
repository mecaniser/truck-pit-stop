# DB-036: percentage beside trip comparison bars

Owner: Frontend & UX. Fast UI lane; existing authenticated Trips data and permissions.
Branch: `codex/trip-median-percentage`, release base `2f093ca3`.

## Acceptance before implementation

- Show `(truck distance / fleet median distance - 1) × 100` at the start of each yellow comparison bar, rounded to one decimal. Use the same reporting trucks and selected period as the existing median marker.
- Positive values have a plus sign and green text; negative values have a minus sign and red text. A rounded zero is neutral `0%`.
- Switching to Driving hours recalculates against the driving-hours median. Missing trips, a zero median, or fewer than two reporting trucks must not produce a misleading percentage, infinity, or NaN.
- Keep the white median marker, yellow track, and total readable on desktop and mobile. Accessible text identifies the comparison baseline.
- Focused component checks, changed-source lint, build, protected CI and signed-in desktop/mobile release verification.

## Runtime preflight — 2026-10-16

Primary checkout is unrelated/dirty and preserved. Intended checkout is
`/Users/sergio_m1_promax/.codex/worktrees/motive-driver-records/truck-pit-stop`.
Its previous Vite PID44354 was gracefully stopped after confirming ownership;
replacement Vite PID27324 runs this branch at `http://127.0.0.1:5173` with the current base SHA.
The configured API target is localhost8000, which has no listener. The local
runtime controller retains an obsolete primary-checkout receipt and is not
healthy. No approved backend configuration is present in this worktree; no
database, secrets, payment settings, or migrations were changed.

Local full-stack acceptance is **blocked**. The existing synthetic
`/tests/fuel-preview.html` mounts the actual TripOverview component and blocks
live API requests; it is suitable for isolated frontend layout acceptance only.
Production signed-in acceptance remains required.

## Implementation evidence

- Labels precede the yellow bar and retain the white median marker and total.
  Accessible text and hover titles name the baseline. Existing comparison
  population, selected period, data requests and permission contracts are unchanged.
- 33 FleetTrips tests pass, covering positive/negative signs, measure switching,
  rounded neutral zero, zero baseline and missing-reporting-peer exclusions.
- Changed-source ESLint, TypeScript, production build and `git diff --check` pass.
- Actual TripOverview fixture verified at1280×900 and390×844: green+20%/+6.7%,
  red−6.7%/−20%, neutral0% after switching to driving hours. Existing table scroll
  works; document remains390px wide without page overflow. Median ticks and totals
  stay legible when scrolling the compact table. Screenshots retained locally in
  `output/trip-median-percentage/`.
- Local frontend fixture is aligned and browser-verified at
  `http://127.0.0.1:5173/tests/fuel-preview.html`; this is not local full-stack or
  production acceptance. Protected CI and signed-in release check remain pending.

## Production release acceptance — 2026-10-16

- PR553 checked head `cf13a2d2797eb90628762a890cedd2f0762046fe` passed all six
  protected checks in run38913239743. Merged at14:38:41UTC as
  `7299722d4966fa4fbb88bd4c577d8e0bc8b10476`. Both commits have tree
  `ae6dfc9e089eac5d21db041022fe9eca48a3dc5b`; the redundant post-merge main
  run38917434806 was canceled, not counted as a pass.
- Web deployment `3033ecbb-deee-4064-9f37-fcb733353d78` serves that exact SHA
  through `/build-version` (built14:42:17UTC). Signed-in production refreshed
  successfully and renders the new percentage labels.
- Desktop1280x900 and1600x1000, plus mobile390x844, verified. Weekly median
  1,962.9mi:2,487.3mi renders green+26.7%;1,071.7mi renders red-45.4%. All16
  row values agree with the visible median/totals within display rounding.
  Every reporting row retains its white median marker.
- Driving hours recalculates against37.3h; Month changes the distance median
  to4,926.2mi, with eight positive/eight negative labels. Compact comparison
  scrolls horizontally; document width remains390px. No errors were logged
  during this release acceptance; older14:12 stale-asset errors belong to the
  previous rollout and were resolved by refresh.
- Private screenshots/readbacks retained under `output/trip-median-percentage/`,
  including production-desktop-wide.png and production-mobile-bars.png.
  Viewport restored. Fast UI runtime gate PASS; no API/data/security changes.
