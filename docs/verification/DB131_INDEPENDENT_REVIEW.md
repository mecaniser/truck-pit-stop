# DB-131 / R1 independent QA and Security review

Reviewer: independent QA/Security agent `r1_independent_gate`. The reviewer did
not implement or direct the implementation and owns this review receipt only.
Review basis: approved `docs/contracts/db131-repair-order-scheduling.md`, tracker
acceptance and current working diff on `codex/ets-repair-order-scheduling`.

## Current gate

**Independent QA GO / Security GO / Production closure GO**, 2026-10-15,
for PR #538 deployed as `7b3dc4b30a52e6880580f1511716afc38dbd1ba2`.
Application candidate `e12994da5978e90a1bff329034b8cf01ad3d822a` passed the local
gate; final CI candidate `21546789` adds documentation/screenshots only and its
Git tree equals the merge. All six required CI checks, exact Web/Worker release,
schema 173, production changed-journey acceptance and independent synthetic
fixture restoration checks have passed. Both findings below are corrected. No
unresolved R1 blocker remains; the delivery owner may mark R1/DB-131 Done and
advance to the user-approved next item P1/DB-132. A subsequent application-source
change requires review of its affected delta.

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

## Release gates required after the local review — now satisfied

- Protected CI on the reviewed candidate and confirmation of the merged tree.
- Schema-before-code deployment/readiness with application rollback retaining
  nullable schedule columns and saved dates.
- Actual production desktop/mobile Light/Night changed-journey acceptance and
  release receipt. No production action was performed by this reviewer.

## Independent release identity and readiness — 2026-10-15

The reviewer subsequently performed read-only GitHub, Railway, public health and
production-schema checks; no browser or production mutation was performed.

- All six contexts required by strict main protection succeeded in CI
  `38788259786` for head `21546789d591e214ed2a579d6e43c5e8f80d17d2`. This head
  differs from approved app commit `e12994da` only by docs/screenshots.
  Compact independent receipt: `/tmp/db131-independent-ci.json`.
- GitHub confirms PR #538 merged at `2026-10-15T19:41:35Z` as
  `7b3dc4b30a52e6880580f1511716afc38dbd1ba2`. Tested and merged Git trees both
  equal `d222f84b0aaa0299bfa8dcb491e55170cca0c8ca`.
- Web deployment `1638efbd-d4ec-4047-ace8-717452930791` and Worker deployment
  `ca80a3a3-86dc-4738-bb36-87446d656a50` both independently report SUCCESS at
  exact merge SHA `7b3dc4b3`. Web log records schema172→173 at19:49:13Z and
  application startup complete at19:49:35Z. Filtered Worker logs contain no
  scheduled-column/UndefinedColumn/ProgrammingError entries at this check.
- Read-only production SQL confirms head `173_repair_order_schedule`, both
  nullable `timestamp with time zone` columns, `ck_repair_orders_schedule_order`
  and `ix_repair_orders_tenant_promised_finish`. Evidence:
  `/tmp/db131-independent-schema-overlap.log` and
  `/tmp/db131-independent-web-migration.jsonl`.
- At19:50:44Z, `/build-version` returns the exact merged SHA (built19:46:47Z),
  `/health`200 alive and `/health/ready`200 ready with database/Redis OK.
  `/tmp/db131-independent-production-health.json`.

**Deployment readiness GO at the initial release check.** The
authorized existing fixture is explicitly **DB115 Production QA — not customer
work**: customer `3425eb75-fb47-4581-bc2d-ba78f69b8b2d`, vehicle
`64aec3ce-cb8a-4149-b804-0fccf53fa488`, order
`bce9b62b-a7e3-4ba9-a740-6ced6857e9b3` / `TPS-828ACD84-000056` in tenant
`828acd84-38bf-4a66-8fa1-cdf076f4e241`. Independent pre-journey read confirms
soft-deleted, null schedule, underlying In Progress, $0, one operation, zero
invoices, no assigned technician and work-start2026-10-14T01:05:50.048351Z.
Delivery owner may restore that fixture through its normal recovery action for
the authorized checks, restore null dates, and soft-delete it again afterward.
New deletion timestamp/audit events are expected; other baseline invariants must
remain. See `/tmp/db131-release-checklist.md`. The final independent closure and
cleanup comparison are recorded below.

### Independent production visual review

Reviewer independently inspected all eight exact-viewport production captures
supplied by the delivery owner under `/tmp/db131-qa/`: `production-light-` and
`production-night-` variants of `desktop.png`, `390.png`, `320.png` and
`landscape.png`. The schedule dialog, shop timezone, complete date/AM-PM text,
Clear, close, Cancel and Save remain legible and within each viewport. At 320px,
Clear sits beside the label and the input uses full width; at 740×400 both fields
and actions fit inside the visible dialog. Desktop workspace density and amount
alignment are retained. No new visual blocker was found. These screenshots
establish appearance; save/reload/conflict/cleanup acceptance additionally uses
the delivery owner's runtime notes and the independent cleanup comparison below.
Mobile evidence is browser viewport emulation, not physical-device or mobile
keyboard testing. Night Shop's existing light repair working sheet is preserved.
The same eight captures are preserved under `docs/verification/db131/` and linked
from the production release receipt.


### Final independent production closure

**GO**, 2026-10-15. Accepted the production journey evidence in
[DB131_REPAIR_ORDER_SCHEDULING.md](DB131_REPAIR_ORDER_SCHEDULING.md), independently
inspected all eight production screenshots, and independently checked the source,
CI, deployed SHA, schema, health and fixture state. The delivery owner performed
the browser interactions; this reviewer made no production writes.

Accepted actual authenticated production journeys include desktop Light save,
reload and invalid-pair rejection; Escape and named close without a write;
explicit stale-editor conflict recovery; clear-one preserving the other date;
390px phone save/reload; 320px full inputs and reachable actions; 740×400 landscape
clear/save/reload; and the corresponding representative Night Shop journeys.
Customer return, browser Back and full-ledger overdue navigation retain their
intended context. The past-promise filter changes from one order/$0 to zero/$0
when cleared. An existing completed order is read-only with disabled inputs/Clear
and no Save. The owner restored Day Shop and cleared viewport, touch and page-
scale overrides. Final browser console errors were empty. Expected 422 validation
and 409 conflict responses were surfaced as deliberate UI errors, not treated as
server failures. Input automation attempts without a React draft change were
excluded from successful-write claims; reported values survived actual reload.

At 19:57Z the independent read-only cleanup query confirmed both schedule dates
null and the synthetic order soft-deleted again at
`2026-10-15T19:56:49.214269Z`. Automated comparison against the pre-release baseline
found **zero differences in all 17 invariant fields**: order, tenant, customer,
vehicle, status, vehicle release, hold, assigned mechanic, parts amount, labor
amount, total, work start, work completion, tracked minutes, operation count and
invoice count. Status remains In Progress; all money is $0; one existing
operation and zero invoices remain. Only expected deletion/version timestamps
advanced; audit history was retained. Receipt:
`/tmp/db131-independent-production-cleanup.log`.

At `2026-10-15T19:57:50Z`, public `/build-version` still returned exact merge SHA
`7b3dc4b30a52e6880580f1511716afc38dbd1ba2`; `/health` and `/health/ready` returned
200 with database and Redis OK and 495 seconds uptime. Exact Web deployment HTTP
logs returned **zero 5xx records** for application startup at 19:49:35Z through
19:58:00Z, covering the changed-journey observation interval. Receipts:
`/tmp/db131-independent-production-final-health.json` and
`/tmp/db131-independent-production-5xx.jsonl`. Schema 173, both nullable columns,
constraint and index were reconfirmed in the cleanup query.

The browser evidence covers representative desktop/mobile Light/Night workflows,
not physical devices, soft keyboards, all mobile browsers or mass production
fixtures. Tenant/role privacy, DST, competing transaction races and >25-row
count/value/search/pagination retain their independently accepted automated and
local evidence above. These explicit evidence boundaries leave no hidden R1
follow-up or release blocker. Application rollback must retain the additive
schema, saved schedules and audit history.
