# DB-103 repair-order workspace refinement

Frontend & UX owns this Fast UI item. Existing authenticated UI and contracts only; no API, migration, auth, tenant, payment processing or provider changes. PR is stacked on DB-099 / PR498 to retain its already-tested mobile sheet and recommendation behavior.

## Acceptance and outcome

- Queue reserves about 327 CSS pixels at the verified 1248px desktop viewport, leaving the majority of space for the job. Compact rows keep company, unit first, status, order reference, amount and update time; selected order has a visible outline and aria-current. Search, status filters, detail disclosures, selection, pagination and keyboard handlers remain intact.
- Truck/unit leads the job header; order number and status support it. Customer navigation, fleet qualifier, full order-number disclosure, vehicle detail toggle, previous/next and order actions remain available. Darker copper improves white-text contrast; internal fleet retains navy.
- Six collapsed service rows fit above the parts table in the tested active job. Rows measure about 55 CSS pixels and expand to the existing description, labor duration/rate and linked-parts controls. Financial totals and all mutation/lock guards are unchanged. Disclosure state is exposed to assistive technology.
- Workflow details wrap instead of horizontal scrolling. Technician name remains visible. Existing assignment/start/review/estimate handlers are unchanged. Invoice payment is primary; resend and void/revise are secondary, fully labeled and one-tap on mobile, with the existing pending/paid/Zelle guards and underlying dialogs intact.
- Empty prior recommendations occupy less space without changing fetching/error/carry-forward behavior. White-sheet text remains readable in Modern dark chrome.
- During responsive verification, the phone sheet retained a scroll offset after returning to desktop, hiding the header. Desktop overflow:clip eliminates that offset while mobile retains whole-sheet scrolling and desktop body scroll remains usable.

## Automated evidence

2026-10-12: 129 tests pass across RepairOrdersLedger, PriceBuilderPanel.pending-feedback, WorkflowInfoStep, RepairOrdersPage.authorization, RepairOrdersPage.void-revision and RecommendedWorkPanel. Includes new phone one-tap dispatch, pending-disabled and paid-action guard coverage. A 32-test ledger rerun passes after the final CSS correction. Changed-source ESLint passes with no findings. TypeScript and Vite production build pass. Impeccable layout detector returns an empty findings list. Existing Browserslist age advisory does not fail the build.

## Browser acceptance

Authenticated local synthetic tenant, Modern staff presentation. Desktop 1248x1185 and phone 355x767 CSS viewport (390x844 requested viewport at existing browser zoom). This is browser responsive verification, not a native mobile-device claim.

Verified queue filtering returns one exact order, selection and detail disclosure, visible truck/unit header, six-service scan, expanded labor editing, keyboard Enter/Escape workflow popover and returned focus, phone whole-sheet scrolling, and one-tap Record payment opening the existing modal. Closed the modal without submitting. Paid, pending and Zelle action guards are covered by component tests. No messages, invoice resend, payment, or invoice-state mutations were performed in browser acceptance. Existing DB-102 checklist remains present and read-only on the finalized fixture.

Screenshots in local `output/db103/`: desktop-active-final.jpg, mobile-active-final.jpg, mobile-service-edit-final.jpg, mobile-invoice-actions-final.jpg. Earlier pass captures remain for comparison.

## Runtime receipt

2026-10-12, approved frontend 5174 / API 8001. Source implementation `codex/repair-order-workspace` at bafd9752. Deliberately integrated for acceptance into `codex/ets-parity-preview` at 38f88c80b5b04b43230fae02b97402649d2a9f79 so earlier DB098–102 features remain available.

Both frontend process and backend bind mount serve `/Users/sergio_m1_promax/.codex/worktrees/ets-parity-preview/truck-pit-stop`. Vite PID 66282 explicitly proxies to http://127.0.0.1:8001. API container dieselbridge_api_ets-workflow-parity, identity da0d8e5e2be1, localhost 8001:8000. Dedicated PostgreSQL database `truckpitstop_ets_workflow_parity_20261012` at postgres; existing schema 165, no migration or data changes for DB-103. Resend/Twilio disabled. `/health/ready` 200 with database and Redis OK through frontend proxy. Branch/build indicator plus served DOM, process cwd and source mount corroborate alignment. The original dirty checkout, populated original database and other task's 5173 service are preserved.

Local implementation and responsive browser acceptance complete. PR CI, merge and production deployment remain separate pending gates. This item is Review, not Done.

Draft [PR #502](https://github.com/mecaniser/truck-pit-stop/pull/502) targets `codex/recommended-work-carry-forward` / PR498. The Quality gates workflow automatically runs only for main-targeted PRs; dispatch it manually for this stacked head. No merge or deployment is authorized by this UI request.
