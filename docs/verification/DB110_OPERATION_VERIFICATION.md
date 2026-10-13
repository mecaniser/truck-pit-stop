# DB-110 — Per-operation technician workflow

Status: implemented and locally browser verified; independent review and CI recorded below. Not merged or deployed. Backend & Integrations accountable.

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
| Self timer and switch | Explicit start, one clock; same-order switch no hold | Passed with Alex switching between mobile order operations |
| Completion with checklist | Required check blocks until checked; completion stops only linked timer | Passed in technician desktop and phone UI |
| Parallel technicians | Completing one operation leaves other technician timer running | Passed: Alex completed2m36s while Blair continued |
| Order gate and reopen | Remaining scope blocks review; reopen clears review-ready stage | Passed live, then desktop fixture finalized to Invoiced |
| Legacy and provenance | Not tracked remains explicit; recommendation source survives | Passed in staff desktop and phone UI |
| Phone390 and320 | Visible controls, no horizontal overflow; full mutation round trip | Passed helper and staff390/320, including corrected staff scroller |
| Error/stale state | Retry/409 refresh, no false complete/zero display | Passed blocked-network unverified state and explicit Retry recovery |

## Implementation, checks and runtime acceptance

Implemented on the focused branch; validation details follow. No merge/deployment authorized.

### Desktop acceptance checkpoint

Source93dd34d3 / previewbe1da5d8. Staff signed-in127.0.0.1:5174; synthetic mechanics signed in normally at localhost:5174 in an origin-isolated tab, without affecting owner session. Synthetic DB110-DESKTOP02c73fd3-fb52-4890-b524-a08c6b3e83e3 has distinct Lead/Alex/Blair. UI assignment persisted with no timers; Alex clock-in/start/checklist passed; Blair independently started second operation. Staff completed Alex, preserving Blair clock. Lead DONE returned409 with1unfinished operation and preserved order InProgress/timer. Required checkbox disabled after operation completion. Source recommendation link stillvisible, legacyuntracked explicit.

Initial desktop screenshot revealed metadata squeezing title to~65px. Fixed layout to two compact rows with fullwidthdescription and independently wrappingmetadata; visually rechecked at1280x800. Corrected screenshot `output/db110/desktop-parallel-timers-fixed.png`; initialfailure `output/db110/desktop-parallel-timers.png`.

### Phone acceptance checkpoint

Actual authenticated responsive Chromium interactions at CSS390 and320: assigned both mobile operations to Alex independently of Lead; helper sees only own operations; required checklist gates completion; starting steering closes brake timer with no whole-order hold; completing brakes preserves steering timer; self completion stops steering timer and retains attributed time; reopen leaves no automatic timer, then explicit start/completion succeeds. Final320 screenshot `output/db110/mobile-320-completed.png` independently inspected by QA. CSS width/scrollWidth320/320 with mobile emulation; 390 responsive interaction width390/scrollWidth377 (vertical scrollbar only). No physical-phone or Safari claim.

The IAB mechanic tab has90% user zoom. Responsive interaction metrics are compensated and allowed to settle before locator actions. Mobile emulation screenshot mode is separately measured; coordinate offset during early harness attempts hit adjacent timer controls, and is not counted as successful completion. Final successful interactions used the stable responsive mode and canonical completed state.

Additional actual-browser findings returned to owners: operation mutations emitted a misleading Work started notification; selected order's local snapshot stayed InProgress while ledger changed to PendingReview. Fixes add an observed compact workspace query and suppress stage notifications for operation-only refreshes. Independent QA also found two generic route variants of the completion cutoff/reset bug; all remain gated pending final tests.

### Final backend/runtime checkpoint

Source7941f454 / previewd448c083, same5174PID23640/cwd and Docker bind; readiness200, migration168. The live selected workspace now follows technician DONE into PendingReview and operation reopen back to InProgress, with canonical footer actions. Operation-only updates do not emit Work started. Blocked operations requests produced Status is unverified with Retry, never a false completed count; restoring requests and clicking Retry recovered2/2.

An actual repeat-review test exposed duplicate gamification credit. Fixed under the existing tenant lock, with independent same-lead and changed-lead probes. Final UI recheck held759points/3done before and after resubmitting the already-credited desktop fixture (the earlier synthetic duplicate records were preserved as historical test evidence). Desktop Finalize & Send Invoice succeeded: Invoiced,253.75, both operations completed, required checks read-only, source recommendation still linked. Synthetic customer has blank email/phone; no recipient or real payment. Read-only DB receipt confirmed zero active clocks on both DB110 orders,2completed operations each, preserved253.75 totals. Alex, Lead and Blair shifts ended through actual Clock Out UI.

Backend full suite:2850passed/125skipped/4failed. The four failures were outdated generic-denial expectations and invoice-discount fake isolation; all corrected and46focused checks passed, including40canonical operation cases. This is not reported as a clean full-suite rerun. Additional independent41accounting checks,9PostgreSQL races,3finalization regressions and71frontend tests passed. TypeScript/build and changed-source lint passed.

DraftPR509 targets codex/operation-workflow-base so checklist/conversion dependencies do not obscure the operation diff. Automatic PR CI only targets main; run Quality gates by workflow_dispatch on final feature SHA. No merge/deployment. Staff320 layout remains pending a scoped single-scroller correction; helper390/320 and staff390 controls passed.

### Final UI acceptance — dba05f84 / preview846360c3

The staff320 failure was fixed with one scroller containing header/stages/body and a separate stable footer; stages use one horizontally scrollable row. Reopen and Complete operation both worked from this narrow staff view, with stage/count updates. A positional gradient selector exposed during visual recheck was changed to explicitly target only the header. Final measured widths320/320 and390/390 have no page horizontal overflow; usable scroller heights340px and468px respectively. The footer progress button scrolls to and opens the operation. Actual final1280x800 desktop recheck retained compact rows, technician names, completion/time, legacy Not tracked and recommendation provenance after finalization.

Final screenshots in local output/db110: desktop-final.png, mobile-staff-320-fixed.png, mobile-staff-390-fixed.png, mobile-320-completed.png, mobile-390-complete.png. Staff320 reopen/completion and all backend/time mutations used normal authenticated UI. Browser emulation and failure-injection overrides were restored; synthetic mechanic shifts ended. The preview is aligned and browser-verified at http://127.0.0.1:5174 (API8001). No physical-device or Safari claim.

Final mobile patch:88focused frontend tests, TypeScript, production build, explicit touched-source ESLint and diff checks passed. Independent QA reran50backend checks including all40operation cases and4cutoff/credit probes, and independently repeated populated168→167→168 migration on the isolated test DB: legacy2h/$200 and3600s session preserved, null attribution retained. Preview database was not downgraded.

### Final CI acceptance

[Quality gates run 38454803809](https://github.com/mecaniser/truck-pit-stop/actions/runs/38454803809) passed all six jobs on c5aedbd6552d9e91136bf599474d66e64f3c6d68. Logs confirm the full backend suite passed with 2,856 passed and 125 skipped; the full frontend suite passed all 1,399 tests across 152 files. Critical suites passed 530 backend tests (11 skipped) and 203 frontend tests; all five Playwright smoke tests and migration graph checks passed. These suites overlap and are not additive coverage counts.

The earlier run 38454039584 was superseded and cancelled while its informational backend suite was running; the completed final run above is the acceptance evidence. Changes after c5aedbd6 only record this evidence, with no product or test changes. Draft PR #509 remains stacked, unmerged and undeployed; no production migration was performed.
