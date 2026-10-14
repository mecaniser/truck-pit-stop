# DB117 — Readable, searchable repair-order activity

Owner: Frontend & UX. Fast UI lane. Source: `codex/readable-order-history`.

## Acceptance and contract

- Open History in one click on editable orders; finalized orders retain an explicit disclosure.
- Present recorded action, operation description, actor and timestamp. Strip the known legacy operation snapshot suffix from presentation only. Do not infer historical technician names from the current roster; retain stored audit data unchanged.
- Search all loaded events by action, work and actor, including older events outside the current page. Clear/no-match recovery, ten-event pagination, order-change reset, loading and partial-failure/retry states.
- Keep existing authorization/deleted-order query gates, permissions, timers, completion and financial data unchanged. No API, schema, dependency or worker change.
- Preserve dense desktop and single-scroll mobile layout, keyboard/touch controls and full button labels. Verify local and deployed production UI before Done.

## REA audit — 2026-10-13

Used the approved `rea-agents@6.4.0` web subset at `/tmp/dieselbridge-rea-evaluation-20261012`, installed without lifecycle scripts. Read-only ETS service1764 showed Recent Activity with named actors, completed/created operations, parts additions and timestamps. No ETS edits, timers or financial actions.

Four observed ETS static assets were captured through the signed-in browser, without credentials or customer payload exports: `index.CIRbAkCE.js`, `layout.BbfQi207.js`, `Heading.DOmBfukR.js`, `ServiceItem.BMDIHCGN.js`. Local manifests and inert analysis remain in `/tmp/dieselbridge-rea-activity-20261013`. REA `analyze-javascript-application --artifact-format directory --full-output --format json` returned `ok:true`, parsed four files with no parse failures; evidence `ev_5740f40f94251103080c746b3e55dd15afe00f1d6baddb2a28fe5f202d3ae68d`. Static graph corroborates the service/item surface; activity semantics are grounded in visible UI, not inferred from static imports. This is a bounded audit, not full ETS parity.

Selected the readable activity gap already identified during DB115. Search across the full loaded history and explicit failure recovery improve the review process. External service records and scheduling remain separate gaps needing new contracts.

## Local runtime receipt

2026-10-13: implementation starts from main `ed93d871` plus DB116 release receipt `a3348e1a`. Approved shared integration preview remains `ets-parity-preview`, frontend5174 PID23640, backend8001 container `dieselbridge_api_ets-workflow-parity` with preview backend bind mount. Effective `DIESELBRIDGE_API_ORIGIN=http://127.0.0.1:8001`. Direct and proxied readiness report DB/Redis healthy. Database identity `postgres / truckpitstop_ets_workflow_parity_20261012`; migration168_operation_execution is head. No restarts, migrations, reseeds, flags or provider changes. All frontend application/backend sources matched before editing; only four owned frontend source files are mirrored for HMR. The startup badge SHA is historical and not used as source proof.

## Checks

- 97 focused tests passed across history, price builder, authorization and deleted-workspace regressions.
- Production build passed. Changed-source lint: zero errors, two existing hook-dependency warnings in RepairOrdersPage.
- Signed-in local DB115-HOLD-QA shows one-click history and readable Brake inspection completion without raw technician/version fields; search, no-match and clearing passed.
- Mobile measurement explicitly uses DOM CSS viewport dimensions: the host browser has110% zoom, so raw emulation dimensions alone are not acceptance evidence. Measured390×844 screenshot `/tmp/db117-local-mobile.png` has no horizontal overflow.
- Final local acceptance: measured1280×800 desktop,390×844/320×640 touch portrait and740×400 landscape. One-click editable history, finalized-order disclosure, search across older results by work/action/person, no-match/clear, keyboard clearing, ten-event pagination/show-less, collapse/reopen, order-change reset, customer detour/return and reload passed. DB110-DESKTOP showed readable reassignment/completion/reopening; DB115-HOLD-QA preserved readable hold events. One mobile `.db-workspace-scroll` area, no page horizontal overflow. No business data writes.
- Failure injection blocked only the observed local `/api/v1/repair-orders/46d5bd79-254e-4a0e-b282-c169cdfd04f5/detail` request. UI displayed loading then incomplete-history warning, retained search and restored matching events on explicit Retry after removing the block. All request blocking was removed; expected injected failure is not a backend outage.
- Screenshots: `/tmp/db117-local-desktop.png`, `/tmp/db117-local-mobile.png`. Browser emulation only; no physical-device or native-keyboard claim.
- [PR518](https://github.com/mecaniser/truck-pit-stop/pull/518), exact source45794573. All six checks in CI38501647498 passed: frontend1446, backend2928 passed/132 skipped, critical frontend204 and backend530 passed/11 skipped, migration graph and Playwright smoke. Merged ase3af2b3de66aa6b8589edb8158068cae942c7de6 at2026-10-14 02:46:57UTC; merge tree exactly matches checked45794573. Railway Weba96ec906 building; production acceptance pending.

## Additional REA activity evidence

The observed global `app.Ca3LeB7z.js` asset contains the actual ActivityList flow: permission-gated service activity, initial loading, a resource-specific activity route, `has_next_page`, and a separate full-history modal. Its current error value is stored but not rendered in the inspected Recent Activity template. This static finding supports making DBN's incomplete-load/retry state explicit; no live ETS failure was induced.

Inert REA analysis of that one observed1,140,674-byte asset returned `ok:true`, one parsed file,309,258 visited AST nodes and no parse failures. Evidence `ev_37c63aad839491da18a10a55ab46de4928b7f157a2aabff9091a6ce46233e113`; sourceSHA256 `b22a6211a3d7e692b7994be16760c205b5dec00ef20255e2c39ebb6089fea099`. Local artifact `/tmp/dieselbridge-rea-activity-20261013/activity-analysis.json`. No vendor source is included in DBN code. Backend source review confirms DBN detail returns all permitted non-deleted events for the exact tenant/order; search adds no endpoint or cross-order collection.

## Release and production acceptance — 2026-10-13 local

- Protected merge: `e3af2b3de66aa6b8589edb8158068cae942c7de6`, PR518, merged2026-10-14 02:46:57UTC. All six checks passed; no bypass. Merge tree equals checked45794573.
- Railway Web deployment `a96ec906-d648-451d-88e3-5e35e3a1b6b8`: SUCCESS, exact mergeSHA. Production `/health/ready` reports ready with database/Redis healthy. Browser loaded new `index-DtHaQV3K.js` and the changed history UI.
- Existing native orderTPS-828ACD84-000054 and imported orderETS-0963-82487 were inspected read-only. Native history returned7 events; imported history20. No records, assignments, timers, invoices, payments or customer data were changed.
- Measured1280×800 desktop: open/review, actor+work multi-term search, action search, order switch/reset and pagination20/20 passed. Search found an event beyond the initial ten after Show less.
- Measured390×844 and320×640 touch portrait,740×400 landscape: search, no-match/clear, wrapping and accessible controls passed. One `.db-workspace-scroll`, no page horizontal overflow. Customer detour returned to the same selected order; reload still returned the recorded history and search result.
- Production failure/retry: temporarily blocked only the selected native order's observed detail GET in the dedicated QA tab. Loading and incomplete-history warning appeared; explicit Retry after removing the block restored the matching work event while retaining the search. This was a browser-injected failure, not a production outage.
- Final fresh reload had no console errors. Request blocking and device overrides were removed; dedicated QA tabs closed, user tabs preserved.
- Screenshots: `/tmp/db117-production-desktop.png`, `/tmp/db117-production-mobile.png`. Screenshots inspected, not just DOM assertions. Browser emulation only; no physical phone or native keyboard verification claimed.
- Operation reassignment/completion/reopening description formatting is covered by automated tests and actual local DB110/DB115 histories. Production acceptance used existing native/imported history; no new execution events were manufactured.

DB117 is Done. Remaining ETS capabilities such as external service records and resource-capacity scheduling retain separate contract requirements. This release closes the history-review gap and does not claim complete ETS parity.
