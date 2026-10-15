# DB-131 / R1 independent QA and Security review

Reviewer: independent QA/Security agent `r1_independent_gate`. The reviewer did
not implement or direct the implementation and owns this review receipt only.
Review basis: approved `docs/contracts/db131-repair-order-scheduling.md`, tracker
acceptance and current working diff on `codex/ets-repair-order-scheduling`.

## Current gate

**Source/security checks pass; final QA pending runtime evidence.** Both review
findings below have corrections and passing independent focused regressions.
Final candidate identity, complete runtime evidence, protected CI and deployment
acceptance have not been reviewed here. This is not a release approval.

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

## Interim visual inspection

`local-phone-dialog.png` is readable at 390px with fitting date/Clear controls
and a compact footer. `local-conflict.png` shows the kept draft and explicit
saved-schedule/keep-draft choices. The preliminary `local-phone-workspace.png`
capture instead shows an approximately 106px-wide application in the corner of
a 390px white canvas; it is **not accepted as mobile layout evidence**. Parent
notified to recapture settled viewport-matched workspace/theme images and
confirm whether the malformed image is capture state or actual layout. These
interim images do not substitute for the remaining complete theme/device matrix.

## Remaining gates

- Review stable corrected candidate and independently rerun relevant focused
  backend/frontend checks, including dashboard scope and deadline freshness.
- Inspect actual local Light/Night desktop, phone and landscape journey evidence
  for save/reload/clear/cancel/Escape, stale-write recovery, overdue navigation,
  customer return, density, touch targets and scrolling.
- Record final QA/Security decision separately from protected CI, merge,
  schema/deployment readiness and actual production acceptance.
