# DB-VOID-002 local review

Owner: Frontend & UX. Lane: Fast UI. Status: Local review; not released.
Timestamp: 2026-10-20T14:42:23-04:00.
Branch: `codex/void-order-dialog`, base `064db78cccf57be3f26d559972bdecfe3df4e233`; task changes uncommitted.

## Outcome and contract

The native invoice card exposes **Void entire order** for the existing owner/admin override. A compact Headless UI dialog names the order and invoice, labels the reason/password, and states that the order is cancelled while the invoice is voided and history retained. The existing invoice correction action is labeled **Revise invoice**; its existing mutation still voids the unpaid invoice and reopens the order for revision. No API, authorization, tenant, payment, data-model, migration, dependency, or provider behavior changes.

Protected orders no longer expose the ineffective Delete/danger-sheet entry. Draft Delete and deleted-order Restore remain reachable. Imported history gains no native void action. The dialog validates a trimmed 3–1000 character reason and password, prevents duplicate submission and dismissal during a pending request, traps keyboard focus, returns focus on dismissal, clears fields when abandoned, retains the reason after rejection, and clears the password after an attempt. Server-authoritative errors remain visible; no automatic retry was added. Success retains the existing cache refresh, workspace closure, and dismissible order-number confirmation.

## Verification

- Four focused suites: 108/108 passed (`RepairOrdersPage.force-void`, `RepairOrdersPage.void-revision`, `RepairOrdersPage.abort`, `PriceBuilderPanel.pending-feedback`). Final focused void rerun: 12/12 passed after the dialog root visibility correction.
- Production build including TypeScript: passed. Changed-source ESLint: zero errors, two existing page hook dependency warnings (lines 1147 and 1434).
- New dialog Impeccable detector: `[]`. Diff whitespace check: passed.
- Playwright CLI with actual page/components and browser-only synthetic owner/receptionist/paid fixtures: desktop 1440x1000 and compact 390x844 passed; reduced viewport height 390x500 retains reachable cancellation. Verified labels, initial focus, forward/reverse focus containment, Escape without closing the order, focus return, validation, password rejection, reason retention/password clearing, cancellation reset, success confirmation/closure, role visibility, and the paid-invoice revision guard.
- Browser check reports zero page errors and zero real API requests. Existing React Router future warnings remain. Preview intercepts all HTTP API calls with a local Axios adapter and replaces its WebSocket; fixture submission changes only browser memory.
- Captures: `output/playwright/void-order-dialog/desktop-invoice.png`, `desktop-dialog.png`, `mobile-dialog.png`. Browser check and logs are in the same output area and `output/void-order-dialog/`.

## Local runtime receipt

Frontend **aligned and browser-verified with fixtures**: `http://127.0.0.1:5173/local-void-preview.html`, listener PID `20817`, source/cwd `<worktree>/frontend`. Served changed module contains `Void entire order?`; process source and branch agree. Preview HTML/TSX are local review scaffolding outside `src`, excluded from the production build and intended delivery diff.

Full frontend/backend runtime is **blocked**. Controller dry-run found repository migration `185_callrail_inquiry_main_merge` versus configured local database `the configured local e2e database` revision `148_elis_outcome_source`. No service switch, database migration, reseed, payment, provider call, or financial state mutation was performed. Existing canonical backend configuration and Python runtime are referenced through local ignored symlinks rather than copied. Port 8000 has no task-owned backend. Existing other local APIs were preserved.

Local serving and fixture acceptance do not establish authenticated full-stack or production behavior. No PR, merge, or deployment in this local-review stage.

## Compact invoice header follow-up — 2026-10-20T14:46:02-04:00

Removed the separate void-action row and divider. The invoice disclosure and void confirmation now use sibling buttons on one header row. Desktop shows the action label; compact screens show the labeled circle-slash icon with a 44px target. The decorative invoice icon is hidden on compact screens to preserve space for the invoice number and payment status. Invoice status truncates instead of wrapping when space is constrained.

Browser geometry compares eligible and readonly fixtures: the collapsed card is 70px high in both at 1440, 390, and 320 widths, without horizontal overflow. A long invoice number `TPS-828ACD84-000003` also remains 70px at all three sizes. Verified disclosure expansion/collapse never opens confirmation; void confirmation never toggles disclosure; Escape returns to the existing order. Captures: `output/playwright/void-order-dialog/inline-invoice-1440.png`, `inline-invoice-390.png`, `inline-invoice-320.png`, and `inline-desktop.png`. Focused void tests 12/12, changed-source ESLint, TypeScript, and diff checks pass. Frontend remains PID20817 on this worktree; fixture-only browser verification and full-stack schema blocker still apply.

## Release candidate

Product approved shipment after reviewing the compact header. PR #599 contains only the frontend implementation/tests and delivery evidence. Fresh final-source tests: 108/108 pass; TypeScript/production build pass; exact-source lint has zero errors and the same two existing page hook warnings. Review found no release blockers. The branch integrated `0195e36f` from main cleanly; its unrelated Twilio pilot files are inherited base content and are outside this PR diff. Protected CI and deployment/production smoke are pending.

## Merged; deployment blocked — 2026-10-20T19:40:20+00:00

PR #599 passed all six protected checks at exact head `8a81f9522cdc71cf0c0254fdba3aed50bd943798`, Quality run `39478723765`, and squash-merged as `fb80ad2cd83623f1e1d264295f7cfa08898f1b7a` at 2026-10-20T19:37:11Z. Checked-head and merge trees are identical. No backend app, migration, or Railway configuration differences exist between the previously deployed Web source and this merge. Main Quality run `39485001790` is separately pending.

Production Web exact-commit deployment was requested through Railway's supported `redeploy --commit` with the existing project/environment/Web service IDs. Railway rejected both attempts with `Deploys have been paused temporarily`; no new deployment ID was created. The official status page confirms a platform-wide pause of new builds, including a 19:10 UTC update on October 20, and states that attempts must be triggered again after builds resume: https://status.railway.com/. No alternative upload, provider setting change, Worker deployment, or gate bypass was attempted.

The last successful Web deployment remains `eb92d1da-5ae8-4c0f-bec5-dbe00b157287`, source and served `/build-version` SHA `b772fb56399ce45f16096cb7c94d36c6215170f2`. `/health` returns HTTP 200/alive; `/health/ready` returns HTTP 200/ready with database and Redis checks OK. The new UI is therefore merged but not live. The signed-in production session and matching invoiced order were located read-only; acceptance of the new UI remains pending deployment. No financial state changed.

Status: Blocked by external provider outage; not Done. Next safe action: once Railway resumes builds, re-check main/source identity, retry the reviewed merge SHA on Web only, verify successful deployment and served source, then open/cancel the new confirmation in the authenticated order without submitting a financial mutation.

## Production verified — 2026-10-20

PR #599 is released. Railway Web deployment `067a6d59-605b-4c78-85ca-61ef7f719e42` reached SUCCESS. Provider source and served `/build-version` both equal the approved merge `fb80ad2cd83623f1e1d264295f7cfa08898f1b7a`. `/health` is alive; `/health/ready` is ready with database and Redis OK. The release receipt separately confirms all six protected PR checks passed on the identical checked tree.

Authenticated production acceptance passed in Chrome through `https://www.dieselbridge.com/dashboard/repair-orders`, using the existing Truck Pit Stop (NC) session and the previously identified invoiced order. A fresh page shows the inline **Void entire order** action and footer **Revise invoice**, with no old Order actions entry on this protected order. Invoice disclosure expands and collapses independently. The confirmation names the matching order/invoice, labels reason and password, focuses reason initially, and disables empty submission. Escape closes only the confirmation, keeps the order open and returns focus to **Void entire order**. No password was entered and no void/payment/invoice-send action was submitted. Earlier cached tabs retained the old frontend; a fresh page on the working www hostname loaded the released UI. The bare hostname timed out from the terminal during this check; no DNS/provider change was made.

Status: Done for this focused UI release. Frontend & UX accountable; no contract or migration impact. Local desktop/compact geometry and interaction evidence above plus this production smoke satisfy the Fast UI acceptance. The recovery heartbeat can stop. Postmerge board/evidence edits remain local; the PR release comment is the durable release receipt.
