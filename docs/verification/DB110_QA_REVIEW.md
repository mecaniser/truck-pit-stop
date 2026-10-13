# DB-110 independent QA review

2026-10-13. Independent `operation_qa` reviewer; no implementation or contract
direction. Backend & Integrations remains accountable for corrective changes.
Review base: `2e67b78a0657bdfa057a465d9fc55d9329825ac7`; initial checkpoints
`e7a91d94` / `a515363f` with owner corrections in progress. This review is local
only, not merge, deployment or production acceptance.

## Gate

**LOCAL QA GO at `dba05f84` / preview `846360c3`.** All three findings below
are resolved. Final source, independent focused tests, migration preservation,
and parent-operated authenticated desktop and responsive mobile journeys provide
the local acceptance evidence. The final backend test adaptations at `1e23d29d`
were independently inspected and tested. CI, PR, merge and deployment gates are
separate; this is not a production acceptance claim.
The parent owns authenticated browser journeys and preview fixtures. This
reviewer does not operate those tabs or mutate preview data concurrently.

## Findings

- **Q1, P1 — pending-review time becomes repair hold time on approval.**
  `operation_execution.finish_order` recalculates wall/idle minutes with fresh
  `datetime.now()` on every call. `approve_completion` calls it again after the
  order already has `work_completed_at`. A one-hour job, fully timed with no hold,
  followed by one hour awaiting review changes from `actual=60, hold=0` to
  `actual=60, hold=60`. The work-end boundary must remain stable across review and
  approval; explicit reopen already clears it. Reproduction is the isolated
  in-memory test `/tmp/db110_qa_timer_probe.py`,
  `test_review_wait_does_not_become_hold_time`: **failed as expected**, reporting
  `Review wait became 60 hold minutes`. Routed to Backend via Product & Delivery.
  No product files were edited by QA.
  At `ea8938ce`, the original review-wait reproduction and all **35 canonical
  operation tests passed** (36 checks including the independent probe). However,
  the generic `PUT /repair-orders/{id}` transition into pending review still does
  not set `work_completed_at`, so its later approval has no effective work-end
  cutoff. Independent `test_generic_review_transition_records_effective_work_end`
  fails with `work_completed_at=None`. The generic return to in-progress also
  needs to clear completion snapshots. This variant was returned to Backend;
  the accounting gate remained open at that checkpoint for other completion paths.
  **Resolved at `724def67`:** shared finalization stamps its effective work end
  once; generic and explicit reopen paths clear completion snapshots. All three
  independent probes now pass, along with all38 canonical operation tests
  (**41 passed** in this final correction run).
- **Q2, P1 — repeated review submission awarded completion credit again.**
  Parent's actual lead UI increased from253points/1job to506points/2jobs for the
  same order after operation reopen and resubmission. Owner added a tenant/order
  EARNED-credit existence guard under the serialized completion transaction.
  Independent `/tmp/db110_qa_credit_probe.py` passes the current uncommitted owner
  correction: complete → helper operation reopen/recomplete → complete leaves
  exactly one EARNED transaction and unchanged available/total-earned balance.
  **Resolved at `7941f454`:** the independent probe passes on committed product
  source. Parent's normal lead UI retained759points/3jobs before and after
  another review submission; earlier synthetic duplicate credits were retained
  as history, not rewritten. Parent then finalized the synthetic blank-contact
  order to invoiced, retaining253.75 total, readonly checks and source link.
- **Q3, P1 — staff320px workspace has no usable operation content area.** Parent
  supplied `output/db110/mobile-staff-320.png` at320×740. Independent inspection
  confirms the truck/header, multilevel stage controls and footer consume the
  entire workspace; the operator cannot see an operation row or its body. Helper
  phone screenshots alone did not establish staff phone acceptance.
  **Resolved at `dba05f84`:** the narrow workspace uses one content scroller and
  a persistent footer. Independent inspection of
  `output/db110/mobile-staff-320-fixed.png` confirms a readable white operation
  body, source link and intact Reopen control. Parent measured a 340px content
  scroller and `innerWidth=scrollWidth=320`, and completed the reopen → complete
  round trip at `260f37dc`; the final correction only targets the header gradient
  and canonical footer labels. The footer completion count also scrolls to and
  opens the first operation. The header can move out of view in the same scroller
  without losing the bottom controls.

## Independent checks

- Operation execution, mechanic time service, mechanic job scope, service
  checklists and repair-order finalization: **104 passed, 1 existing skip**.
- PostgreSQL operation races in isolated local `db110_test_operation_execution`:
  **9 passed**, including start/assignment in both orders, complete/start,
  hold/finalize/remove versus start, duplicate start replay, required checklist
  reopen versus completion, and stale manager edit versus operation stop.
- Frontend operation controls: **10 passed**; mechanic portal and checklist
  components: **15 passed**. These include the in-flight legacy-scope fallback.
- Affected recommendation conversion, price-build service, internal fleet
  repairs, fleet workflows, PM mileage and fleet-manager price access:
  **178 passed**. Independent backend total is **282 passed, 1 existing skip**
  plus the **9 PostgreSQL races** above.
- Python dependency warnings and the existing Browserslist database warning are
  diagnostic noise, not evidence of a failed acceptance criterion.
- Final changed frontend suite at `724def67`: **71 passed** across operation
  controls, mechanic portal, checklists, WebSocket invalidation/notification and
  RepairOrdersPage selection synchronization. These supersede the earlier25
  overlapping frontend checks, rather than adding a second count for them.
- At `724def67`, a repeated finalization/contention check passed all **9 PostgreSQL
  races plus3 existing finalization regressions**. This is a final-source rerun of
  overlapping checks, not additional unique test coverage.
- Final source `dba05f84`: **79 frontend checks passed**, comprising69
  PriceBuilderPanel feedback cases (including finalized footer labels) and10
  operation-control cases. Existing Headless UI act warnings were emitted; both
  suites passed. These overlap earlier frontend runs and are not a unique total.
- At product `7941f454`, **50 checks passed**:40 canonical operation tests,
  six tests from the four-failure regression files, and four independent
  accounting/credit probes. The real-DB operation matrix now explicitly rejects
  manual invoice creation when pending operations remain.

Backend execution used the existing project virtual environment and isolated
SQLite or the expressly scoped PostgreSQL test database. The PostgreSQL URL was
read from a restricted temporary file and never printed or committed. No browser
authentication shortcuts, preview migrations, operational data changes or
provider changes were performed by this reviewer.

Migration proof was then independently rerun with an explicit URL guard allowing
only localhost `db110_test_operation_execution`. Populated168 →167 →168 passed:
the legacy line retained2hours/$200 and null execution status/version0; the
historical timer retained3600seconds and null operation attribution. This used
`/tmp/db110-qa/migration_proof.py` and changed only the isolated test database.
The user's populated preview database and its backup were not touched by QA.

## Acceptance disposition

No unresolved DB-110 QA blocker remains. Final review includes migration
preservation, authenticated staff and distinct helper desktop journeys, 390px and
320px completion/reopen and timer controls, required checklist blocking, parallel
technician isolation, legacy/provenance display, stale/error recovery and the
staff320px layout correction. Runtime interactions belong to the parent; this
review independently inspected saved screenshots and exercised the backend
invariants. All mobile evidence is responsive Chromium, not physical-device or
native Safari acceptance. CI/PR and release gates remain separate.

Backend owner's full run completed with **4 failed,2850 passed,125 skipped**.
All four were reviewed against source: foreign-order lookup now returns generic
404 rather than403 and retains the no-mutation assertion; same-tenant nonlead
denial remains403 with the assigned-workspace message; two discount-math unit
fakes isolate the added completion guard. The latter has separate real-DB manual
invoice rejection coverage. The independent targeted50-check rerun passes.
These adaptations do not weaken tenant/role assertions. A clean whole-suite rerun
is not claimed; protected CI remains a separate integration gate.

## Desktop runtime evidence reviewed

Parent receipt identifies preview `be1da5d8` and source layout correction
`93dd34d3`. Independent visual inspection of
`output/db110/desktop-parallel-timers-fixed.png` (1280×800) confirms readable
compact operation rows, order lead retained in the job header, completed Alex
brake operation with 2m36s real tracked time, Blair steering operation with a
running timer, explicit legacy `Not tracked`, recommendation source link,
remaining-operation count and visible bottom controls. The superseded screenshot
without `-fixed` is not acceptance evidence.

Parent interaction receipt: assignment did not start a timer; Alex and Blair used
normal authenticated UI sessions and discovered only their assigned scope; a
required check preceded Alex completion; owner completion stopped Alex while
Blair remained running; order lead's whole-job completion returned409 with one
operation remaining and preserved in-progress state plus Blair's timer. These
interactions were performed by the parent; this reviewer inspected their saved
visual result and independently exercised the associated backend invariants.

## Narrow-phone visual evidence reviewed

Independent inspection of `output/db110/mobile-320-completed.png` confirms two
complete operation cards fit at320px, with readable description, technician,
real tracked duration, completion actor/time, intact `Reopen operation` buttons,
the helper's2/2 completion count and the checked required checklist1/1. No
horizontal clipping or overlap is visible. Parent measured
`innerWidth=scrollWidth=320`, height740, and reports successful normal locator
interaction after accounting for the IAB user's90% zoom. This is responsive
Chromium acceptance, not a physical phone or Safari test. Parent's actual journey
covers same-order timer switch without hold, completion of brakes preserving
the steering timer, then steering completion stopping the remaining timer.

The replaced `output/db110/mobile-390-complete.png` was independently inspected:
both complete operation cards, own-scope2/2 count, intact reopen controls,
completion actor/time and required checklist1/1 are readable. The sticky
`Open operations` action and bottom navigation do not overlap content. Parent
reports the390px reopen → start → complete round trip, with steering tracked time
increasing to2m9s and the timer stopped after completion. Earlier intermediate
contents of this filename are superseded.

Parent's final724def67 runtime receipt confirms lead completion updates staff
header and ledger to pending review plus the finalization action without reload;
owner operation reopen returns both to in-progress without starting a timer.
Blocking only operation GET requests produces explicit unverified progress and
Retry, including an unverified footer rather than false completion. Restoring
the route and clicking Retry recovers canonical2/2 progress and legacy scope.
Lead whole-order completion also succeeded through the320px UI. Credit replay
and finalization subsequently passed at product7941f454 as recorded above.


## Final staff narrow-screen correction

The final `output/db110/mobile-staff-320-fixed.png` was independently inspected at
source `dba05f84` / preview `846360c3`. It shows the completed steering operation,
assigned technician, 2m9s tracked duration, source recommendation and reachable
Reopen action in the white content area. Footer totals, operation progress and
technician controls remain visible. Parent's measured320×740 viewport has no
horizontal overflow, and the340px scroller replaces the previously zero-height
operation body. Independent inspection of
`output/db110/mobile-staff-390-fixed.png` also confirms readable operation
controls and content with the persistent footer. Parent measured a468px content
scroller with `innerWidth=scrollWidth=390`, and reports final desktop invoice
status, technicians, time and source remain intact after the CSS correction.
