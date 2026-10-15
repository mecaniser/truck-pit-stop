# DB123 — Search a truck’s repair history

Owner: Frontend & UX. Lane: Fast UI; existing authenticated GET /repair-orders vehicle_id, search, status, skip, limit contract. No API, authorization, model or migration change.

## Acceptance

- Search full server-side exact-vehicle history by existing order-number/description semantics, combine with order status and page in groups of25. No claim of operation-note or outside-shop-history search.
- Reset paging on filter change; bound requests and suppress stale results while search settles. Different customer/truck scopes must not inherit filters or results.
- Preserve filters/page through reload, browser Back and contextual new-order cancellation; keep directory and queue filters independent.
- Distinguish empty history, no matches, pending and failure; explicit retry preserves current filters, and clear recovers the full history.
- Keep desktop density and one mobile workspace scroll; verify1280 desktop,320/390 portrait,740×400 touch landscape and keyboard use.
- Focused tests, changed-source lint, protected CI, deployed source and actual production workflow evidence required.

## Audit evidence

Authenticated ETS vehicle history shows search/date controls. Searching inspection retains one matching service; an unmatched term produces No results. URL preserves search/range/sort/status/page. REA6.4.0 analyzed four fresh public observed history/filter assets:17,371 bytes,4,248 AST nodes,zero parse failures; evidence ev_bb4bcd33bfc3289d94b1c9d03159b0e9a35c4ec80fa154f0bddeead83855327a. Static syntax corroborates routing/filter state, not vendor writes. No account mutation or vendor code reuse.

DBN already exposes tenant/role-scoped exact-vehicle list filtering server-side, but the shared truck workspace only exposed paging. This UI adds access to that contract, with visible clear/status and preserved navigation context. Outside history and export-date semantics remain separate.

## Local runtime receipt —2026-10-14

Implementation: ets-checkpoint-merge, codex/vehicle-history-search, base30758c96, clean at intake. Intentional established preview overlay: ets-parity-preview at846360c3; Vite PID47264 on127.0.0.1:5174 from preview/frontend; API Docker dieselbridge_api_ets-workflow-parity,8001, preview/backend bound to/app. Populated local postgres database truckpitstop_ets_workflow_parity_20261012, schema169_external_service_history. Approved sandbox/config untouched. This frontend-only item deliberately keeps API169; main’s unrelated default-off signed-history migration170 is not needed. Only the two changed frontend application files were mirrored into the established preview. API and proxy /health/ready both healthy. Rendered search/status controls and real filtered results verified in the signed-in preview; source files match implementation. Aligned and browser-verified for this frontend change. An initial /api/health/ready check was the wrong route (404); the configured /health/ready proxy succeeded.

## Owner verification

-65 focused tests pass:14 history details/search,27 customer workspace,24 contextual repair-order/customer navigation. Exact server query, page reset, URL restoration, scoped filters, wrong-truck rejection, retry and out-of-range recovery covered. Changed-source ESLint clean. App TypeScript check and Vite build pass. An initial Vitest call from repo root lacked frontend aliases; rerun from frontend passed. An unnecessary tsc -b invocation hit the repository’s missing Node config typings; generated files removed, documented tsc application check passed. No dependency change.
-Actual local1280desktop,390/320portrait,740×400touch landscape: QA107 + Completed gives2 results; complaint steering gives1 exact order; status mismatch gives no matches. Open actual order/browser Back, reload and NewOrder Cancel/Escape preserve search/status. Explicitly blocked history network request produces retry without false empty state; unblocking/retry retains filters and recovers.320 controls44px, document width320, one content scroll area. No business writes.
-Artifacts /tmp/db123-ui; browser viewport/touch emulation, not physical-device/mobile-Safari certification. Production verification remains pending.

-Shared repair-order → customer → exact truck checked separately in local740×400landscape and1280×720desktop. Search/status retained after NewRepairOrder Cancel; desktop32–34px controls, phone44px targets. Actual rendered screenshots:local-desktop.png,local-390.png,local-320.png,local-landscape.png. The local truck has12native orders; multi-page behavior is verified with server-query component fixtures, not manufactured business records.

## Pull request

[PR525](https://github.com/mecaniser/truck-pit-stop/pull/525), checked source a1c0071f4f26623fdd772a4a08a4b5920631be7b. [Quality gates](https://github.com/mecaniser/truck-pit-stop/actions/runs/38660652943) in progress. Fast UI owner verification; no independent specialist gate required by this existing-contract change. Merge/deploy and production acceptance pending.

Main advanced with documentation-only PR524 during CI. Preserved its DB121 receipt and DB122/DB123 board entries when resolving the board-header conflict; application diff unchanged. First run had5/6green, fullbackend still running; strict branch protection requires a new complete gate on the merged base.

## CI and merge

Final checked source9931c571188ac8f2230ed28a01ac8a1ac8381347. [Quality gates38661170151](https://github.com/mecaniser/truck-pit-stop/actions/runs/38661170151) all six SUCCESS: frontend1,554tests/162files; critical backend530passed/11skipped; full backend3,060passed/152skipped; frontend build/checks, migration graph and Playwright smoke pass. First superseded CI run was automatically cancelled after five successful jobs when the main-doc sync was pushed; no code/test failure.

PR525 merged b12048d7442c23256d791fa69134659c346319b2 at2026-10-15T00:58:18Z. Fetched main and verified exact tree equality with checked9931c571. Web deployment56194765-658a-46b2-ae47-626b474262ab building the exact merge. Production session renewed by user; acceptance pending deployment.

## Final acceptance correction — history-filter focus

A new regression test reproduced a real return-path edge: after Customers → truck → NewOrder → Cancel, changing the history query created a new location key and replayed the customer page’s focus-on-NewOrder effect. The test failed with NewRepairOrder focused instead of the search input. This was not covered by bulk fill followed only by result assertions. Product completion withheld.

Correction preserves the full navigation/directory/truck return state while marking its focus intent consumed for history-filter URL edits. A fresh order return still restores focus normally. Regression covers search focus, status focus, original query/truck retention and repeated cancellation. Branch codex/history-filter-return-focus from merged b12048d7. Runtime preflight repeated: same5174PID47264 preview source and8001Docker backend, proxy readiness healthy; schema/config unchanged. Browser acceptance pending renewed local sign-in. Fast UI, no API/model change.

[Corrective PR527](https://github.com/mecaniser/truck-pit-stop/pull/527) adds the focus regression fix. All66 focused tests pass and changed-source lint is clean. The first corrective CI run38664748231 had five successful jobs while the full backend suite ran. Main advanced with independently reviewed PR526 (7a873566); merged that base without conflicts, preserving its backend/board work, so strict CI must run again. Corrective application diff unchanged. PR525 Web56194765 reached SUCCESS; live HTML serves index-qSQ3ebg9.js and /health/ready reports database/Redis healthy. Both browser sessions have since expired; signed-in final acceptance is still pending, not passed.

Production read-only search/status/no-match/clear, exact-order open/Back/reload and controlled request-block/retry recovery passed on PR525. Night Shop mobile screenshots revealed the existing Export/NewOrder action buttons used an undefined --customer-text fallback (#17283f), making text unreadable on the dark workspace. Corrective PR527 also changes those controls to inherit the workspace foreground and use its border token, with unchanged dimensions. Final light/dark browser acceptance and fresh protected CI remain required.
## Corrected local acceptance — 2026-10-14

Preview process restarted after interruption. Vite PID97270 serves ets-parity-preview/frontend at5174, explicit API8001; confirmed cwd/command. Preview base846360c3 with exactly matching DB123 CustomerVehicleDetail, CustomersPage and customer-workspace.css overlay from current branch. Docker source remains preview/backend; postgres/truckpitstop_ets_workflow_parity_20261012; schema169; readiness via frontend proxy healthy. No configuration/database/flag changes. Local browser error-page authority was blocked; user navigated back to the live localhost page, after which actual signed-in QA resumed.

Local1280desktop: manually open exact truck from customer (no vehicle URL shortcut), create form, Cancel -> New repair order focus. Type Q then A107 -> input focus retained and full value present. Choose Completed -> select focus retained and2matches. Repeat create/cancel -> same truck/filters and expected NewOrder focus; type -D ->1match with input focused.390phone Escape return, character typing and320Cancel/continued typing pass.740x400landscape Escape/typing passes.44px search controls, one slide-panel-content scroll area at320; CDP content/viewport equal320x640 and740x400, no overflow. Actual screenshots under/tmp/db123-ui/local-focus-*.png. This is browser viewport/touch emulation, not physical-device certification. Light theme remains legible; production Night Shop contrast correction awaits deployment. No business writes.

Production pre-fix control: after standalone customer -> exact truck -> NewRepairOrder -> Cancel, allow return focus to settle, then sequentially type PM. Browser reports lost focus after first character; DOM has search P and active button New repair order. This reproduces the same regression as the failing integration test and corrected local pass. Shared repair-order -> customer -> truck PM search/Cancel/continued typing already passed; defect is the standalone CustomersPage return effect. Production search/status/no-match/clear, exact-order open/Back/reload, and scoped-network-failure/retry passed without business writes.

All six gates in corrective run38666206352 passed on8db19af6. PR528 merged26c21267 just before readiness and introduced a board-header conflict; both DB123 and DB125 entries preserved, unrelated backend/migration171 work retained unchanged. Application correction unchanged. New strict-base CI required. Automatic merge is disabled by repository configuration; no protection bypass attempted.

## Explicit truck selection correction

Further production read-only acceptance with two 77 CARGO trucks sharing unit77 reproduced stale cancellation return state: choose the other truck and filter correctly, then reload reopened the previous truck and its unfiltered seven-record history. A two-truck cancel/switch/filter/remount integration test failed with vehicle1 context instead of vehicle2. Explicit truck choices now use the existing vehicle URL parameter and customer-scoped detail cache/query, dropping the obsolete cancelled-order navigation state. Back removes vehicle from the URL, so customer-level reload stays at the customer. Vehicle edit/merge selection uses the same handler. Existing server permissions and API remain unchanged.

All67 focused tests pass (14history,27customer,26navigation); changed-source lint and app TypeScript check pass. Local1280manual truck selection/search/status/reload retains exact truck and filters; post-cancel sequential typing keeps focus.390 Back-to-customer/reload stays at company details with no truck search input. Production two-truck recheck remains pending final deployment. One immediate local Cancel action left the loaded intake open; a settled-form Cancel completed normally, no submit or business write. The integration tests include return and pending-save cancellation gates; final production acceptance waits for the loaded form before Cancel.

Run38668172675 passed all six checks on beee67fb, before the newly reproduced truck-selection correction. A fresh protected run is required for this final UI change.

Final application head38d3f7d5 passed all six checks in run38670425359 (1,556frontend tests;530critical backend tests). Protected merge was blocked because independently reviewed fleet-label PR529 advanced main70a63e7c and conflicted only in the board header. Preserved both entries and placed DB123 updates beside its existing intake, leaving the shared header available for other work. Application diff is unchanged; refreshed strict-base CI remains required. Latest390phone Escape, sequential steering search and reload retain exact truck/filter and one-scroll layout.

## Corrective merge and deployment

Run38671703685 passed all six protected gates on0241735653f89f262d20b6528c3850f56739400d. PR527 merged01d8146bc19124b5b398ee78fa6548f3ad0077bd at2026-10-15T02:48:56Z. Fetched main and verified exact tree equality with the checked source. Railway Web732200cf-3d1f-4402-b2d5-8b78a82e1f38 is building that merge; final production acceptance remains pending.

## Final production acceptance — 2026-10-14 local / 2026-10-15 UTC

Railway Web732200cf-3d1f-4402-b2d5-8b78a82e1f38 reached SUCCESS for merge01d8146bc19124b5b398ee78fa6548f3ad0077bd. Production HTML and authenticated browser load index-DafQAQ8U.js. Readiness reports production database and Redis healthy. Final refreshed CI full backend:3,093passed/152skipped; frontend1,556tests/162files; critical backend530passed/11skipped; all six protected checks succeeded. Source tree exactly equals checked02417356.

Actual signed-in production acceptance passed without business writes:

-1280x720desktop: manually choose VIN-identified truck among two sharing unit77; open fully loaded NewRepairOrder and Cancel; type PM character-by-character with search focus retained. Back to customer, choose the other truck by plate, search coolant + Paid, reload: correct truck, unchanged filters, one matching paid order. The pre-fix production control reopened the former truck and seven unrelated records; the corrected build retains the explicitly selected truck.
-390x700portrait: open intake from the filtered truck; Escape after load; append tank character-by-character without focus loss, same matching record.44px search control; content/viewport390x700.
-320x640portrait: Back to customer and reload leaves company details (no vehicle query or truck search input); open the other truck without inherited filters, search PM, NewOrder Cancel, append service, then switch truck/search coolant + Paid/reload. Correct exact truck and matching record remain. Content/viewport320x640; exactly one visible vertical scroll container (slide-panel-content),526px viewport/706px content. Buttons stay whole and wrap into rows when needed.
-740x400landscape: open the exact filtered repair order, browser Back preserves truck/search/status; a no-match query shows an explicit no-match state; Clear recovers all21truck records, reapplying coolant + Paid returns1. Content/viewport740x400.
-Shared repair-order entry: order -> customer -> exact truck -> coolant -> NewOrder Cancel restores selected order/customer/truck/query;2matching records. Resize390, continue typing coolant tank, reload: same scoped context and2records.
-Night Shop Export history and New repair order now inherit rgb(246,248,251), matching their parent. Actual screenshots confirm readable desktop/portrait actions; desktop action height34px, phone controls44px. Local light-theme screenshot remains legible.

Production screenshots: /tmp/db123-ui/production-final-desktop.png, production-final-390.png, production-final-320.png, production-final-landscape.png. Local final screenshot: /tmp/db123-ui/local-final-390.png. Browser viewport/touch emulation only; no physical-device or mobile-Safari certification. Prior production request-block/retry acceptance remains recorded above; the corrective change does not alter that data contract. No records, financial state, settings, or vendor data changed during final acceptance. Temporary browser overrides/tabs are removed after evidence capture.

DB123 Done. Owner Frontend & UX. Existing API/auth/tenant/model unchanged; Fast UI owner acceptance plus protected CI, not a separate specialist QA gate. Outside-shop receipt attachments and capacity-aware scheduling remain separate parity backlog items; this release does not claim exhaustive ETS parity.
