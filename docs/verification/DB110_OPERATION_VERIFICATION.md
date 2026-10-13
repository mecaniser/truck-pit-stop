# DB-110 — Per-operation technician workflow

Status: implementation in progress against accepted operation contract. Backend & Integrations accountable.

## Acceptance

- Assign an active tenant technician to an operation independently of the order lead.
- Assignment never starts timers or creates tracked time; one active timer per technician.
- Complete/reopen operations with checklist, order-stage and concurrency safeguards.
- All repair-order completion paths honor unfinished tracked operations and stop applicable timers.
- Helpers discover their assigned work without lead-only or cross-tenant privileges.
- Legacy orders remain compatible without fabricating historical completion evidence.
- Actual authenticated desktop and 390/320 responsive UI journeys; independent QA/security gates.

## Runtime preflight — 2026-10-13

Source: `codex/operation-technician-workflow`, base `2e67b78a0657bdfa057a465d9fc55d9329825ac7`; board intake only at preflight. Intentional implementation/preview split preserves the combined checklist/conversion dependencies.

Preview: `/Users/sergio_m1_promax/.codex/worktrees/ets-parity-preview/truck-pit-stop`, branch `codex/ets-parity-preview`, HEAD `2e67b78a`. Frontend `http://127.0.0.1:5174`, PID 23640, cwd preview/frontend. Backend container `dieselbridge_api_ets-workflow-parity`, preview/backend mounted `/app`, loopback8001. Isolated DB host postgres / database `truckpitstop_ets_workflow_parity_20261012`; Redis database9. Alembic `167_merge_checklist_conversion` head. `/health/ready` through frontend returned200 with database and Redis healthy. No configuration, migration, database or provider changes during preflight.

CUA IAB browser5 temporary tab5 rendered signed-in Performance Owner, Diesel Bridge Performance Lab, selected PERF-0000001, six operations and three standalone parts. Baseline aligned and browser-verified. Runtime badge is an older boot-time SHA; actual process source/cwd and rendered baseline corroborated. DB-110 changes are not yet visible.

## Local migration preparation

A full custom-format backup of the isolated preview database is stored outside Git at `/tmp/db110-qa/preview-before-operation-execution.dump` (3,917,507 bytes, mode0600). Pre-migration evidence:3,826 labor rows,7,651.30 planned hours,$460,402.22 labor totals;80 ended timer sessions totaling3,138,014.823655 seconds;2,804 orders totaling$938,070.30. This is preservation evidence, not operation execution evidence. Migration168 was applied to preview at14:33 local. Before fixture creation, exact pre/post counts, hours, totals and80 historical durations matched; all3,826 existing Labor rows remained null/untracked. API readiness passed at168.

A separate empty `db110_test_operation_execution` database on localhost5432 is allocated for migration and two-session concurrency testing. Connection material stays in a restricted temporary file and is not committed.

## Runtime journey matrix

Dedicated local fixtures will use a synthetic customer without delivery contacts, a distinct order lead plus Alex and Blair as operation assignees, and desktop/mobile orders. No existing user credentials or operational orders are changed by fixture setup.

| Journey | Required observation | Result |
| --- | --- | --- |
| Staff desktop assignment | Selected operation changes technician; lead and timers stay unchanged | Passed in actual UI |
| Helper job discovery | Job appears through own operation; lead controls absent | Passed for Alex and Blair, each seeing own operation only |
| Self timer and switch | Explicit start, one clock; same-order switch no hold | Pending |
| Completion with checklist | Required check blocks until checked; completion stops only linked timer | Pending |
| Parallel technicians | Completing one operation leaves other technician timer running | Passed: Alex completed2m36s while Blair continued |
| Order gate and reopen | Remaining scope blocks review; reopen clears review-ready stage | Pending |
| Legacy and provenance | Not tracked remains explicit; recommendation source survives | Pending |
| Phone390 and320 | Visible controls, no horizontal overflow; full mutation round trip | Pending |
| Error/stale state | Retry/409 refresh, no false complete/zero display | Pending |

## Implementation, checks and runtime acceptance

Pending. No merge/deployment authorized.

### Desktop acceptance checkpoint

Source93dd34d3 / previewbe1da5d8. Staff signed-in127.0.0.1:5174; synthetic mechanics signed in normally at localhost:5174 in an origin-isolated tab, without affecting owner session. Synthetic DB110-DESKTOP02c73fd3-fb52-4890-b524-a08c6b3e83e3 has distinct Lead/Alex/Blair. UI assignment persisted with no timers; Alex clock-in/start/checklist passed; Blair independently started second operation. Staff completed Alex, preserving Blair clock. Lead DONE returned409 with1unfinished operation and preserved order InProgress/timer. Required checkbox disabled after operation completion. Source recommendation link stillvisible, legacyuntracked explicit.

Initial desktop screenshot revealed metadata squeezing title to~65px. Fixed layout to two compact rows with fullwidthdescription and independently wrappingmetadata; visually rechecked at1280x800. Corrected screenshot `output/db110/desktop-parallel-timers-fixed.png`; initialfailure `output/db110/desktop-parallel-timers.png`.
