# DB118 independent QA gate

Reviewer: independent QA Gatekeeper; no application or test implementation participation. Scope is the operation-note journey on `codex/operation-shop-notes`, using the approved [contract](../contracts/db118-operation-notes.md).

## Current decision

**GO for the local workflow gate, 2026-10-14.** Reviewed implementation, independent focused reruns, owner-run backend/race results, local browser journey evidence and actual desktop/phone screenshots support the changed workflow. No remaining blocking functional finding. The separate [Security gate](DB118_SECURITY.md) is GO. Protected CI, deployment and production acceptance remain required; this is not a production sign-off.

## Independently checked

- Reviewed the new note schema/service/routes, positive role policy and history filtering, shared frontend component, both staff/mechanic integration points, and focused frontend/backend acceptance tests.
- Independently ran `npm exec vitest run src/features/operation-execution/__tests__/OperationNotes.test.tsx src/features/operation-execution/__tests__/OperationExecution.test.tsx`: **23 passed** (13 notes, 10 execution), 2026-10-14. Existing Browserslist age notice only.
- After the privacy-cache remediation and QA feedback, independently reran notes, operation-note privacy and deleted-order tests: **22 passed** (14 notes, 4 privacy, 4 deleted-order). Existing React Router future notices, React act warnings and Browserslist age notice were emitted; no failed cases. The deleted-order assertion now checks every scoped history cache under the order prefix rather than an obsolete exact key.
- `git diff --check` passed at review time.
- Identity includes authenticated tenant, actor, role, session epoch, order and labor. A late old-operation save cannot clear a newly mounted operation draft. Collapsed operations retain the mounted note component and draft. A pending-save ref plus disabled controls prevents duplicate submit; the same normalized body retains its UUID for explicit ambiguous-result retry.
- Notes are literal text with explicit shop-only wording. Failed reads have a named retry and do not masquerade as an empty collection. The frontend uses server-provided write capability; finalized state and assignment changes alter the read query key. The deleted-order parent excludes the work/note region entirely.
- Desktop note actions use a 32-pixel minimum height; compact or coarse-pointer layouts increase this to 44 pixels and textarea text to 16 pixels. No inner scroll container is introduced. Actual geometry remains a browser acceptance gate.
- Backend tests cover ordered package/manual/sublet identity, normalized boundaries and extra-field denial, exact-key replay versus changed body/target/actor, tenant/order membership, mechanic reassignment scope, frozen-order reads, held/completed-operation notes, and unchanged prices/timers/execution/order fields. Inspected PostgreSQL tests exercise contention, lifecycle/removal ordering, and cross-tenant UUID collision without loss of the outer transaction.
- Reviewed execution logs supplied by the backend owner: `/tmp/db118-backend-focused.log` **140 passed**; `/tmp/db118-postgres-tests.log` **8 passed**; `/tmp/db118-http-contract.log` **1 passed**; `/tmp/db118-history-scope.log` **1 passed**. The latter focused reruns are not additional distinct-case totals. SQLAlchemy/Pydantic deprecation and known test-cleanup cycle warnings were recorded; no failures in these final logs.
- Reviewed scoped detail-cache changes in both staff and fleet clients. Existing order-prefix invalidation remains effective. The operation composer label now wraps unbroken text after QA raised a bounded mobile-overflow concern; actual rendered geometry remains part of the owner's browser evidence.

## Local runtime evidence reviewed

The implementation owner performed the signed-in browser actions and measurements documented in [the main receipt](DB118_OPERATION_NOTES.md). This reviewer independently opened the resulting image files and assessed the receipts; no concurrent browser operations or business-data mutations were performed by this reviewer.

- Desktop measured 1280×720: manual completed operation on an active order accepts a note; draft survives collapse/reopen; author/time and save state appear. Independently inspected the replacement `/tmp/db118-ui/local-desktop-720.png`: clean capture without the compositor artifact, dense queue and job header intact, two readable operation notes with author/time and explicit shop-only text, reachable Add action, and the persistent $290 footer. The original 1280×800 capture remains excluded from visual acceptance.
- Reviewed `/tmp/db118-ui/local-mobile.png` (390×700): two manual-operation notes show readable body, author and time; actions are intact; compact header/footer preserve the workspace. Owner verified reload, blocked-read retry, blocked-save retained draft and explicit retry. Exactly two intended notes remain, with order `in_progress`, total $290, operation completion/assignment and tracked time unchanged.
- Reviewed `/tmp/db118-ui/local-320-composer.png`: composer and complete Cancel/Save labels fit 320×640; this image predates the textarea type-scale correction. Final CSS and owner measurements establish 16-pixel textarea text and 44-pixel controls. Reviewed `/tmp/db118-ui/local-landscape.png` after that correction: 740×400 touch composer retains the single workspace scroller and compact footer. Owner verified controls remain reachable and measured document scroll widths equal each viewport width.
- Service-package note on DB110-MOBILE saved and survived reload independently of other operations, preserving the $253.75 total and completion. Finalized DB110-DESKTOP read succeeds with a clear read-only explanation and no Add action, as visible in `/tmp/db118-ui/local-finalized.png`.
- Network failure injection was limited to the owner QA tab and cleared afterward. This proves visible failure recovery, not a lost response after commit. Actual ambiguous replay and contention are supported separately by backend PostgreSQL and stable-client-ID tests.
- Runtime acceptance is browser emulation, not physical mobile hardware or native-keyboard testing. Synthetic local notes are retained as evidence.

## Release evidence still required

Protected CI on the final source; exact merge/deployment and signed-in production desktop/mobile workflow acceptance, with a usable desktop capture. Material changes to reviewed behavior require a new focused reassessment. Production runtime evidence supplied by the implementation owner will be reviewed as evidence, not represented as independently performed browser actions.

## CI correction reassessment — GO for the focused fix

PR519's first full frontend run did not complete. The owner isolated a render loop in the existing customer-workspace test, whose authentication mock returns a new user object for every render. The new workspace/history synchronization effect depended on that object reference and replaced selected state repeatedly. This is a real unstable-dependency defect exposed by the mock; the failed/hung gate is not counted as passing.

The owner corrected `RepairOrdersPage` to memoize the selected detail query key from order ID, tenant ID, user ID, role and session epoch, and reused that key in the effect and query. Independent review confirms the cache identity values, authorization partitioning and invalidation prefix are unchanged. Updating an unrelated user-object reference no longer reruns workspace synchronization; genuine identity changes still select a distinct cache key.

Independent rerun on 2026-10-14: customer, operation notes, operation-note privacy, request-cancellation and deleted-order suites **53 passed across 5 files in 7.80 seconds**. The previously hanging customer suite completed all **15 cases**, including embedded customer return and preservation of search/page through cancelled order creation. Log: `/tmp/db118-qa-ci-correction.log`. Existing framework/React act warnings remain; no failed assertions or hung suites. `git diff --check` passed. QA edited only this receipt.

The focused correction is accepted. A complete frontend rerun and all protected checks on the corrected head remain release conditions, followed by the already-required production workflow acceptance.
