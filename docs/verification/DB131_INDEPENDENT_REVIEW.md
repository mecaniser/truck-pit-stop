# DB-131 / R1 independent QA and Security review

Reviewer: independent QA/Security agent `r1_independent_gate`. The reviewer did
not implement or direct the implementation and owns this review receipt only.
Review basis: approved `docs/contracts/db131-repair-order-scheduling.md`, tracker
acceptance and current working diff on `codex/ets-repair-order-scheduling`.

## Current gate

**Independent local QA GO / Security GO**, 2026-10-15, for implementation commit
`e12994da5978e90a1bff329034b8cf01ad3d822a` (PR #538). No unresolved application
blocker remains in the reviewed scope. Both findings below are corrected, their
focused regressions pass and the final local runtime evidence is accepted.

This permits the candidate to proceed through protected CI and release checks;
it does **not** assert merge, deployment or production acceptance. Do not mark
R1/DB-131 Done until those separate gates have completed. A subsequent app-source
change requires review of the affected delta.

## Findings returned to owners

1. **Schedule privacy across dashboard rows — blocker.** Initial dashboard
   serialization used only the actor's role to expose the new schedule fields.
   Existing tenant-wide queue membership therefore exposed schedules for
   non-fleet work to fleet managers and for unassigned work to mechanics, while
   the exact schedule endpoint correctly rejected those orders. Affected paths:
   `backend/app/api/v1/endpoints/dashboard.py` action queue, daily workset and
   stats serialization. Reproduction: create a scheduled, non-fleet order with
   no assignment to mechanic M; load these dashboard paths as M (and action
   queue as a fleet manager). The new schedule fields must be hidden for orders
   outside that actor's schedule scope without widening existing row access.
   **Corrected and independently checked:** `_mask_dashboard_schedules` applies
   a single bounded, tenant-qualified query for returned IDs and masks dates,
   timezone and overdue outside lead/operation assignment or internal/fleet
   work scope. Applied to action queue, daily workset, stats and recent rows.
   Negative dashboard fixture passes for mechanics, fleet managers and drivers.
2. **Open workspace deadline freshness — correction requested.** Initial frontend
   interval refreshed list/dashboard rows but not the observed selected workspace
   query. Leave a selected order open across its deadline: its summary can remain
   “Due” while the refreshed queue says “Overdue”. Affected query:
   `frontend/src/features/repair-orders/RepairOrdersPage.tsx` `workspaceOrder`.
   **Corrected and independently checked:** the selected workspace now refetches
   every 60 seconds when it has a promise, and on focus, without hidden polling.
   Page-level regression advances the clock with the workspace still open and
   confirms its visible summary changes to Overdue. Filter preservation during
   open/close/Back also passes.

## Independent evidence so far

- Ran `/tmp/db128-backend-venv/bin/python -m pytest
  tests/test_repair_order_schedule.py -q` in the candidate backend directory:
  **61 passed**, 39 existing deprecation warnings, 17.07 seconds. Receipt:
  `/tmp/db131-independent-backend-tests.log`. This was an interim source state,
  before the dashboard-scope correction, and does not cover that later change.
- Reviewed tenant-qualified schedule row loading, role-first rejection, locking,
  exact timestamp version comparison, whole-pair validation before mutation,
  no-op behavior, staff-only event masking and post-commit staff broadcast.
- Reviewed shared overdue predicates, exact deadline boundary, hold/review and
  terminal/deleted/released behavior, deterministic ordering, list/count/value
  source/projection fallback and shop-time/DST conversion.
- Inspected owner-supplied PostgreSQL evidence and guarded disposable-database
  runner: seven PostgreSQL cases passed and an empty schema 173→172→173 cycle
  passed. Migration-cycle evidence remains an owner receipt.
- Independently reran all seven PostgreSQL cases against the guarded, disposable
  localhost `db131_test_scheduling` database: **7 passed**, 8.88 seconds. Covers
  competing editors, concurrent completion/release/deletion, database ordering
  constraints and actual trigger-backed source/projection search/count/value
  across two pages. `/tmp/db131-independent-postgres-tests.log`. No preview
  migration, preview data or production mutation performed by this reviewer.
- Independently ran schedule editor/page, ledger and customer-return frontend
  suites after the final queue-deadline layout correction: **86 passed across
  four files**, 24.30 seconds. `/tmp/db131-independent-frontend-final.log`.
- Independently reran the editor/page suites against committed `e12994da`, after
  the final 320px field-layout correction: **16 passed across two files**,
  6.27 seconds. `/tmp/db131-independent-e129-schedule-ui.log`.
- Independently reran the stable schedule suite including dashboard masks and
  the final date-overflow validation: **62 passed**, 33.29 seconds.
  `/tmp/db131-independent-schedule-final.log`.
- Independently ran schedule, counts, workspace projection, value summary and
  dashboard regression suites: the interim run had **109 passed / 4 failed**.
  The four failures used pre-existing projection-only orphan fixtures or a fake
  result missing the now-required coverage tuple. Reviewed owner corrections:
  they add real parent tenant/customer/vehicle/order records, preserve assertions
  and implement the fake tuple; no application behavior was relaxed. A fresh
  run of both affected test files passes **7/7**. Evidence:
  `/tmp/db131-independent-backend-final.log` and
  `/tmp/db131-independent-counts-recheck.log`.

## Final local runtime and independent visual review

Parent executed the signed-in browser journeys on the aligned local preview;
reviewer independently inspected the supplied screenshots and assessed the
journey notes against code and automated tests. Mobile proof is supported browser
viewport emulation, **not physical device testing**. Browser timezone was
America/Los_Angeles while the shop uses America/New_York.

Accepted exact-viewport captures under `/tmp/db131-qa/`:
- `local-light-desktop-workspace.png`, `local-light-desktop-dialog.png`, and
  `local-light-desktop-live-overdue.png` (desktop 1280px).
- `local-night-desktop-workspace.png`, `local-night-desktop-dialog.png`.
- `local-light-390-workspace.png`, `local-phone-dialog.png`,
  `local-night-390-workspace.png`, `local-night-390-dialog.png`.
- `local-light-320-dialog.png`, `local-night-320-dialog.png`.
- `local-light-landscape-dialog.png`, `local-night-landscape-dialog.png`
  (740×400).

These show readable dates, complete AM/PM content, fitting Clear/Save/Cancel and
named close controls, compact queue deadlines, aligned totals and a compact
workspace footer. The 320px layout gives date inputs full width and places Clear
alongside their labels. Desktop density remains intact. Parent's DOM checks
confirm viewport/scroll width agreement and touch sizes; the screenshot review
does not itself claim a measured hit-target size. Existing repair work sheets
are intentionally light in Night Shop; the new controls remain readable.

Accepted parent runtime evidence:
- Set/save/reload/edit and clear one/both dates on the synthetic local order.
  Overdue list/count/value changes from one order/$290 to zero/$0 after clearing.
- New York DST gap rejected, repeated clock time requires explicit occurrence,
  chosen second occurrence persisted at 06:30Z; browser zone does not alter it.
- Reversed dates rejected without losing the draft. Escape restores trigger
  focus; Cancel/named close discard unsaved changes. Customer return and search
  are preserved.
- Two real browser editors demonstrate stale-write rejection, preserved draft,
  saved-value comparison and explicit Keep my draft before a successful retry.
- Actual live deadline: at 18:39:58Z the 14:40 EDT promise is Due and the overdue
  queue shows zero/$0; by 18:41Z the open workspace and queue show Overdue and
  one/$290 without a page reload or navigation away from the selected order.
- Invoiced `DB110-DESKTOP` shows disabled date/Clear inputs and no Save; closing
  retains `search=DB110-DESKTOP`. Dashboard On Floor → selected order → All overdue
  work routes to the full ledger with `overdue=true` and removes the bounded
  `queue=on_floor` context.
- Parent restored the fixture's null dates, unchanged In Progress status/$290/
  two operations, original Night preference and removed browser overrides.

**Explicit evidence split approved by Product & Delivery Lead:** the browser
exercised one/zero overdue row transitions; more than 25 rows, search, count,
value and deterministic pagination are proven by the independent real
PostgreSQL suite plus page integration tests. No >25-row browser fixture run is
claimed. This targeted split avoids duplicating the database fixture in the
shared preview while retaining the cross-layer evidence.

Preliminary `tab.screenshot` captures after emulation produced host-canvas scaling
artifacts (`local-phone-workspace.png` and the white-margin conflict capture).
They were rejected as layout evidence and replaced with supported exact-viewport
`Page.captureScreenshot` captures. No acceptance relies on those malformed
images; conflict behavior is established by the actual two-editor journey and
independent component tests.

## Remaining release gates

- Protected CI on the reviewed candidate and confirmation of the merged tree.
- Schema-before-code deployment/readiness with application rollback retaining
  nullable schedule columns and saved dates.
- Actual production desktop/mobile Light/Night changed-journey acceptance and
  release receipt. No production action was performed by this reviewer.
