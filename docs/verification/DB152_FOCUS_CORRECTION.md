# DB-152 focus and alignment correction

Owner: Frontend & UX. Fast UI lane. Existing contracts; no API, migration, authentication, tenant, or business-data changes. User authorized merge/deployment on 2026-11-01.

## Reproduction and acceptance

The prior release missed a second `--db-repair-orders-control-height: 44px` declaration in `repairOrderControls.css`. Signed-in desktop reproduction measured a 34px trigger inside a 44px wrapper, placing Overdue 5px below the trigger. Search and select wrappers also retained 10px corners and independent focus shadows, while the controls used 7px corners and another focus indicator.

Acceptance: one visible outline on the actual boundary, matched wrapper/child heights and aligned adjacent controls, no duplicate shadows or clipped outlines; preserve 34px desktop/44px touch minima, keyboard menu selection, disabled behavior, and text enlargement. Content rows/navigation retain their own sizing and focus treatment.

## Correction and audit

- Shared controls own an inset 2px focus outline. Existing page/Tailwind rings cannot stack with it. Forced colors use Highlight.
- Shared `data-db-control-shell` contract handles bordered compound fields and wrappers around complete controls. Content determines height and the shell owns the sole focus outline.
- Nested clear actions keep their own focus boundary and full hit area; border compensation prevents a height jump. Signed-in Labor search Tab/Enter clears text at34px desktop/44px mobile with no outer duplicate outline.
- Migrated staff search, SearchAddBar, repair-order status, inventory workbench/operations, labor search, global search, fleet board/driver/service/proximity search.
- Removed fixed-height search/status wrappers; inventory toolbar aliases now use the shared height. Repair-order create is an explicit square icon control.
- Audited application CSS focus-within rules, control-height aliases, and fixed/important sizing. Remaining focus-within rules for tooltips, textareas, content actions and quantity-stepper selection are intentional; content controls are outside the compact action contract.
- `lint:controls` now rejects hardcoded toolbar control-height aliases across application CSS. The browser regression loads both repair-order stylesheets, which the earlier component-only checks missed.

## Local evidence

2026-11-01: branch `codex/control-focus-alignment`, base `aa549f2e`, uncommitted correction served from `/Users/sergio_m1_promax/.codex/worktrees/shared-controls`. Vite PID30148 at `http://db-controls.localhost:5235`, same worktree frontend; API container `dieselbridge_api_shared-controls`, port8035, same worktree backend bind. Approved local database `postgres/truckpitstop_db042_qa`; migration196 current/head. API readiness passed database/Redis. Existing provider/sandbox configuration preserved. Signed-in fictional garage UI showed the branch indicator and corrected source geometry. Preview aligned and browser-verified.

- Production build/TypeScript passed.
- 76 focused tests passed: control native semantics, repair-order ledger, inventory operations.
- `frontend/tests/control-focus-regression.cjs`: 276 browser focus/geometry checks (23 controls × 2 viewport widths × 3 appearance modes × 2 text sizes), plus forced-colors and disabled assertions. Checks include oversized wrappers, inner clipping, duplicate outlines/shadows, and actual focus boundary. Appearance modes/text sizes are fixture DOM settings; no user preferences saved.
- Signed-in repair-order selected pane: search/trigger/shell34px, matching Overdue; Tab/Enter opens status listbox, Escape closes. Screenshots in local `output/playwright/db152-*-focus.png`.
- Signed-in actual search journeys cover inventory, labor, customers, repair orders on desktop/mobile; global search opens/closes without saving records.
- Initial six-route desktop/mobile survey found no page overflow; bordered mobile inventory input42px sits inside its44px clickable field, as intended.
- Raw ESLint exposed existing `no-explicit-any` errors in FleetModals and existing refresh warnings; baseline-aware changed-source lint is the gate. No unrelated lint cleanup included.

## Release — complete

- PR: https://github.com/mecaniser/truck-pit-stop/pull/745
- Baseline-aware lint:13 changed TypeScript files, no new violations. Production build passed.
- Final integrated head: `770dcce8d511ecb3da32e91c9eb3b85d3655ec38`. Both concurrent main updates were backend/docs-only; frontend implementation remained unchanged.
- All7 CI checks passed: https://github.com/mecaniser/truck-pit-stop/actions/runs/41351346898 (including both full suites and Playwright smoke).
- Squash merge: `b28bac1ab124c9682e9264f1c48dc57fe8aa882f`.
- Railway deployment: `4ba1f382-3c7d-4e8c-a40b-c223501ecc2e`, SUCCESS, exact merge SHA.
- Production web and API `/build-version`: exact merge SHA, built2026-11-01T21:29:15.579Z. API readiness: database and Redis healthy.

### Production browser acceptance

Fresh authenticated production tab, real repair-order selected pane, then full ledger and inventory. Read-only navigation/filter controls only; no business records saved.

| Check | Before correction | Released result |
| --- | --- | --- |
| Desktop status wrapper / trigger |44px /34px |34px /34px |
| Desktop status / Overdue top |150px /155px |140px /140px |
| Desktop search wrapper / input | legacy independent focus styles |34px /34px, one2px inset outline |
| Mobile status wrapper / trigger / Overdue | not measured before |44px each, top221px each |
| Inventory search | not measured before |34px outer boundary, one outline, inner outline disabled |

Status dropdown opened with all expected options and closed normally. Focused search/status shells use2px solid inset outlines and no box shadows; inner controls do not duplicate the ring. No page overflow at1440px or390px. No Runtime exceptions or error log entries during captured interactions (initial page load is outside that event window). Local keyboard tests additionally cover Enter/Escape status selection and Tab/Enter Clear behavior; production focus checks used ordinary DOM focus/click through browser tooling.

Visual evidence is local, cropped to controls to exclude customer information:
- `/Users/sergio_m1_promax/.codex/visualizations/2026/11/01/01a1987c-744f-7bf2-a2e7-bb9ab22a7190/controls-focus-production.png`
- `/Users/sergio_m1_promax/.codex/visualizations/2026/11/01/01a1987c-744f-7bf2-a2e7-bb9ab22a7190/controls-focus-production-mobile.png`

Temporary browser viewport override reset after acceptance. No unresolved blocker for this correction.
