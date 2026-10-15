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
