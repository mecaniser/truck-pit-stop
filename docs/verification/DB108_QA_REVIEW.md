# DB-108 independent QA review

2026-10-13. Reviewer: independent QA Gatekeeper (`conversion_qa`); no product or
test implementation participation. Accountable implementation owner: Frontend &
UX. Scope: contextual customer/truck repair-order entry and queue-value alignment.

## Gate status

**GO for the scoped local workflow at `d36f89a7`.** Source branch
`codex/customer-order-entry`, base `76aaa3a9`; combined preview `7029d4c5` on
5174/API8001. No unresolved DB-108 QA blocker. This is not merge, CI, deployment,
physical-device, or release-Done approval. QA edited only this report and did not
change services, migrations, tenant state, product/tests, or browser state.

## Independent checks

- Read acceptance in `DB108_CUSTOMER_ORDER_ENTRY.md`, the scoped diff, delivery
  rules, runtime skill, relevant existing GET/POST handlers and caller behavior.
- Independently ran five focused frontend files: **74 passed**. Receipt:
  `/tmp/db108-qa-focused.log`.
- Independently ran existing `RepairOrdersPage.abort.test.tsx`: **15 passed**.
  Receipt: `/tmp/db108-qa-regression.log`.
- Corrected-head expanded rerun: **91 passed, 1 failed**; all 77 focused checks
  passed. Existing mobile-modal test still expects viewport classes on the
  `role=dialog` element, whereas Headless Dialog now owns that role and the
  constrained Panel remains inside it. Returned to owner to update the assertion
  to verify the actual panel and scroll behavior. Receipt:
  `/tmp/db108-qa-final-focused.log`.
- The owner corrected the old selector without relaxing viewport/scroll
  requirements and added modal-ARIA coverage. Independent rerun at `875a678a`:
  **92 passed, 6 files**; `/tmp/db108-qa-875a-focused.log`.
- Independently rechecked the affected three suites after the final narrow-screen
  layout/touch-target changes at `a24cfb53`: **32 passed**;
  `/tmp/db108-qa-final-a24cfb53.log`. After the final save-error positioning and
  `role=alert` change at `d36f89a7`, reran its changed journey suite: **8 passed**;
  `/tmp/db108-qa-final-d36f89a7.log`.
- Reviewed owner build/lint receipts: source production build passed, ESLint
  zero errors with two existing hook-dependency warnings. Owner also reports
  27 combined-preview customer/context integration checks passing, preserving
  preexisting global-search behavior; QA did not claim to rerun that preview suite.
- Exact customer response ID checking, generic recoverable 403/404/500 handling,
  unrelated-truck rejection, bill-to preservation with a different truck owner,
  embedded Cancel context and pending-click guard are covered by the focused
  tests. No claim that mocked responses prove backend tenant isolation.
- Existing backend customer GET checks same tenant; nested exact-truck GET
  validates active customer linkage and tenant; order POST checks customer and
  truck tenant, undeleted truck, roles, and fleet restrictions. No DB108 changes
  to these contracts were found.

## Findings returned to owner and rechecked

1. **P2: Customers Cancel discards originating URL state.**
   `CustomersPage.startCustomerOrder` reconstructs `?selected=...` rather than
   retaining the current query. Existing workspace behavior deliberately
   preserves unrelated query state. Add route-level customer/truck entry and
   Cancel regression coverage.
2. **P2: Restored truck can disappear after a late customer refresh.**
   Customer-record selection effect clears `selectedVehicleInPanel` when the
   customer object changes, but `restoredVehicleForLocation` suppresses restoring
   the truck a second time for that location. Cover fresh customer response after
   cached customer/truck restoration and retain the selected truck appropriately.
3. **P2: Truck validation searches a capped collection.**
   `loadRepairOrderEntry` reads the first default 100 customer trucks. A valid
   exact truck outside that page is reported as unlinked. Existing
   `GET /customers/{customer}/vehicles/{vehicle}` already provides the needed
   exact lookup and linkage checks; assert returned ID and preserve bill-to.

All three product findings above are corrected in `2a5528a4`. Independent source
review and the passing focused tests confirm exact GET/ID validation, preserved
query state, and truck selection retained across a same-customer refresh.
Additional passing regressions cover Customers route round-trip, company-only
entry requiring deliberate truck selection, and deferred failed save with draft
retention, disabled Cancel/close, duplicate-click prevention, and successful retry.
Headless Dialog now manages modal focus. Owner's actual browser pass found
Customers cancellation focused an old navigation link; `875a678a` explicitly
restores the initiating action and its new route regression passes independently.
Owner's mobile pass also found footer/mileage overflow and service targets
shrinking under fine-pointer CSS. Whole-control wrapping, one-column truck cards
and scoped 44px button targets fix these; final screenshots were independently
inspected. Save errors are now announced and placed beside the retry action.

## Actual UI evidence reviewed independently

Parent operated authenticated CUA in-app Chromium as the local Performance Owner;
QA independently inspected the saved images, source and interaction receipt in
`DB108_CUSTOMER_ORDER_ENTRY.md`, without concurrent browser control.

| Acceptance | Evidence and result |
| --- | --- |
| Queue amount alignment | `desktop-queue-final.png`, plus owner measurement of 0.0853 CSSpx between summary and row right edges. Pass. |
| Customer/truck entry in both hosts | Settled `desktop-customer-entry-final.png`, draft image and owner route receipt. Exact record/customer retained; company-only entry requires deliberate truck selection. Pass. |
| Cancel and keyboard context | Owner exercised Escape/focus trap and initiating-action focus in both hosts; route/query/refetch/focus regression independently passes. Pass. |
| Lookup and save recovery | Owner blocked/unblocked exact GET and order POST in the QA tab; retries succeeded. `mobile-save-error.png` shows an announced, visible failure near footer. Draft-retention/deferred-submit regression independently passes. Pass. |
| Successful creation | `desktop-created.png` and `mobile-320-created.png` show the new zero-dollar drafts for C-0001/Performance Carrier 001. Owner receipt names exactly two synthetic orders, ending 000003 and 000004. Pass. |
| 390px experience | `mobile-390-draft-final.png`; full truck name, service controls and complete action labels visible. Owner measured form clientWidth=scrollWidth=376 at viewport390 and approximately44px controls. Pass. |
| 320px experience | `mobile-320-final.png` and `mobile-320-pending.png`; whole controls wrap and spinner stays inside disabled action. Owner measured form clientWidth=scrollWidth=306 at viewport320 and confirmed scroll access to order work/actions. Pass. |

An initial customer screenshot was blank during loading; QA rejected it as final
evidence. Parent reloaded and recaptured the settled customer panel and action,
which QA independently viewed. No persistent blank-panel defect was established.

## Final runtime corroboration and boundaries

Read-only QA receipt, 2026-10-13 approximately 01:12 EDT: source `d36f89a7`, preview
`7029d4c5`; Vite PID68993 listens on127.0.0.1:5174 with cwd at the combined-preview
frontend. Its effective API target is127.0.0.1:8001. Container
`dieselbridge_api_ets-workflow-parity` mounts combined-preview/backend at `/app`,
exposes loopback8001→8000, and uses database
`postgres/truckpitstop_ets_workflow_parity_20261012`. The frontend and proxied
`/health/ready` return200; database/Redis checks pass. Served source includes the
final intake panel and touch-target rules. Preview intentionally includes other
prior work and uses integrated/cherry-picked commits; no source ancestry claim.

Local status: **aligned and browser-verified for DB-108** through the owner CUA
journey and this independent evidence review. Only documentation/output are dirty.
No restart, migration, reseed, production call, payment, invoice, or notification
was required for this QA review. Browser viewport checks do not establish physical
iOS/Android or mobile virtual-keyboard behavior. Final protected CI, PR, merge
and deployment remain separate release gates with the parent.
