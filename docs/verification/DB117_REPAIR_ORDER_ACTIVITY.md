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
- Remaining local edge cases, protected CI, release and production checks pending.
