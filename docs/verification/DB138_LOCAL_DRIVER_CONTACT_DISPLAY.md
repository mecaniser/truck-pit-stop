# DB-138 local driver contact display

Accountable: Frontend & UX. Fast UI lane. State: merged and deployed; signed-in desktop and 390×844 compact-viewport acceptance passed. No physical mobile device or touch-input coverage is claimed.

## Scope and acceptance

Remove locally stored contact names/phone sublines and phone call actions from read-only fleet cards, Trips rows, map focus, and truck details. Keep the displayed current driver name and safety score. Preserve contact records, API contracts, driver assignment/edit forms, and provider data.

## Implementation and automated evidence

- Shared current-driver display no longer renders a local alias/phone contact subline.
- Trips overview no longer adds the separate local contact row.
- Map focus and truck details no longer expose `tel:` contact actions.
- Fleet cards and Drivers view use the shared display; edit and assignment forms continue to accept phone values.
- Focused Vitest: 4 files, 62 tests passed (`DriverRecord`, `FleetProximity`, `TruckDetailHarden`, `TripOverview.driver-contact`). Tests assert names/scores remain and phone/alias sublines and `tel:` actions are absent.
- Explicit ESLint on all changed TS/TSX files passed.
- `npm run build` passed, including TypeScript and Vite production build.
- `git diff --check` passed.

## Runtime and release evidence

The production Trips page showed local contact sublines at 2026-10-17 03:35 UTC before this change. The local runtime was not used for browser acceptance because 5173/5177 are owned by other worktrees and port 8000 has no listener; those services were preserved.

PR #569 (`codex/remove-local-driver-contact-lines`, head `6e6992f765fdfe74265262c4b1637ab9182182d4`) passed all six protected checks and merged normally at 04:16:28 UTC as `2c79dc78ade69342f43aab5bcc3da946a3fc4248`. Web deployment `19ab897d-f3d4-4e46-bb2c-5a288bd66be3` reports SUCCESS on that exact merge, and the public readiness endpoint reports ready.

Signed-in production desktop verification at approximately 04:38 UTC covered Fleet cards, Trips, Map and truck detail. Driver names and available Motive safety scores remained visible, while local contact sublines and phone actions were absent. On Map, the truck-26 driver-record popover displayed the current Motive assignment, score and available record sections; activating its close control removed the popover and kept the map and selected truck in place. Fleet cards displayed `Speed unavailable` where no current speed was available, rather than presenting an old speed as movement.

Signed-in compact-viewport verification at 390×844 was completed at approximately 05:04 UTC using the browser's explicit viewport control. Fleet Board showed driver names and scores (including honest unavailable states), no local contact/phone labels, and no horizontal document overflow. Trips showed driver names and score buttons without local contact/phone labels and no horizontal overflow. The truck-26 score popover opened and its close button left Fleet Board, Map, and truck details selected in place; the compact Trips popover also closed while preserving the Trips view. On Map, the selected truck remained selected; in truck details, truck 26 and its score trigger remained visible. Where the current telemetry had no speed, the UI continued to display `Speed unavailable`. The compact check used browser viewport emulation, not a physical phone or touch input. No physical-touch claim is made. DB-138's requested responsive and dismissal acceptance is met.

Automated evidence remains four focused files/62 tests, changed-source ESLint, TypeScript/Vite build, diff check, and all six exact-head protected PR contexts. Deployment, desktop, and compact-viewport behavior are confirmed. Physical device/touch testing was not performed and is not included in this acceptance claim.

Branch: `codex/remove-local-driver-contact-lines`. Pull request: [#569](https://github.com/mecaniser/truck-pit-stop/pull/569). Merge SHA: `2c79dc78ade69342f43aab5bcc3da946a3fc4248`. Web deployment: `19ab897d-f3d4-4e46-bb2c-5a288bd66be3`.
