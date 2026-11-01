# DB-152 focus and alignment correction

Owner: Frontend & UX. Fast UI lane. Existing contracts; no API, migration, authentication, tenant, or business-data changes. User authorized merge/deployment on 2026-11-01.

## Reproduction and acceptance

The prior release missed a second `--db-repair-orders-control-height: 44px` declaration in `repairOrderControls.css`. Signed-in desktop reproduction measured a 34px trigger inside a 44px wrapper, placing Overdue 5px below the trigger. Search and select wrappers also retained 10px corners and independent focus shadows, while the controls used 7px corners and another focus indicator.

Acceptance: one visible outline on the actual boundary, matched wrapper/child heights and aligned adjacent controls, no duplicate shadows or clipped outlines; preserve 34px desktop/44px touch minima, keyboard menu selection, disabled behavior, and text enlargement. Content rows/navigation retain their own sizing and focus treatment.

## Correction and audit

- Shared controls own an inset 2px focus outline. Existing page/Tailwind rings cannot stack with it. Forced colors use Highlight.
- Shared `data-db-control-shell` contract handles bordered compound fields and wrappers around complete controls. Content determines height and the shell owns the sole focus outline.
- Migrated staff search, SearchAddBar, repair-order status, inventory workbench/operations, labor search, global search, fleet board/driver/service/proximity search.
- Removed fixed-height search/status wrappers; inventory toolbar aliases now use the shared height. Repair-order create is an explicit square icon control.
- Audited application CSS focus-within rules, control-height aliases, and fixed/important sizing. Remaining focus-within rules for tooltips, textareas, content actions and quantity-stepper selection are intentional; content controls are outside the compact action contract.
- `lint:controls` now rejects hardcoded toolbar control-height aliases across application CSS. The browser regression loads both repair-order stylesheets, which the earlier component-only checks missed.

## Local evidence

2026-11-01: branch `codex/control-focus-alignment`, base `aa549f2e`, uncommitted correction served from `/Users/sergio_m1_promax/.codex/worktrees/shared-controls`. Vite PID30148 at `http://db-controls.localhost:5235`, same worktree frontend; API container `dieselbridge_api_shared-controls`, port8035, same worktree backend bind. Approved local database `postgres/truckpitstop_db042_qa`; migration196 current/head. API readiness passed database/Redis. Existing provider/sandbox configuration preserved. Signed-in fictional garage UI showed the branch indicator and corrected source geometry. Preview aligned and browser-verified.

- Production build/TypeScript passed.
- 76 focused tests passed: control native semantics, repair-order ledger, inventory operations.
- `frontend/tests/control-focus-regression.cjs`: 264 browser focus/geometry checks (22 controls × 2 viewport widths × 3 appearance modes × 2 text sizes), plus forced-colors and disabled assertions. Checks include oversized wrappers, inner clipping, duplicate outlines/shadows, and actual focus boundary. Appearance modes/text sizes are fixture DOM settings; no user preferences saved.
- Signed-in repair-order selected pane: search/trigger/shell34px, matching Overdue; Tab/Enter opens status listbox, Escape closes. Screenshots in local `output/playwright/db152-*-focus.png`.
- Signed-in actual search journeys cover inventory, labor, customers, repair orders on desktop/mobile; global search opens/closes without saving records.
- Initial six-route desktop/mobile survey found no page overflow; bordered mobile inventory input42px sits inside its44px clickable field, as intended.
- Raw ESLint exposed existing `no-explicit-any` errors in FleetModals and existing refresh warnings; baseline-aware changed-source lint is the gate. No unrelated lint cleanup included.

## Release

PR: https://github.com/mecaniser/truck-pit-stop/pull/745. Baseline-aware lint passed all13 changed TypeScript files with no new violations. Final production build passed; pointer-focus shadow regression also passed. Pending protected CI, merge, deployed commit and production browser acceptance. Do not mark Done until those exist.
