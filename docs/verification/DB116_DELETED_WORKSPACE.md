# DB116 — deleted repair-order workspace

Owner: Frontend & UX. Fast UI lane: existing API, restore permissions and soft-delete semantics; no backend/data/migration change. User authorized implementation, release and production desktop/mobile verification before resuming ETS parity.

## Acceptance

- Delete an agent-owned QA order, reopen it from Deleted without reloading, and immediately see Deleted and Restore. Previously viewed History must not override that state.
- Do not request active-only detail/checklist/operations/recommendations/notes/quotes/photos for a deleted order or show their error panels. Hide edit, assignment, completion and pricing actions until restored.
- Restore retains its existing API and owner/admin permissions, handles pending/failure without false success, and restores the active workspace without reload. Dismissing the view or its action sheet must not restore implicitly.
- Verify active-order regressions, desktop, 390/320 portrait and compact landscape using synthetic local/production data. Preserve real customers, timers and financial records. No physical-device claim from emulation.

## Runtime preflight — 2026-10-13 local

Implementation checkout `ets-checkpoint-merge/truck-pit-stop`, branch `codex/deleted-order-workspace`, baseline `5d455d42` (main2461084e plus prior release documentation). Root checkout's unrelated dirty work preserved. Intentional integration preview remains `ets-parity-preview/truck-pit-stop`, branch `codex/ets-parity-preview`, HEAD846360c3 with prior task-owned HMR overlays; all application files match implementation baseline (only seven test-file differences).

Vite PID23640/cwd preview/frontend serves127.0.0.1:5174. API Docker `dieselbridge_api_ets-workflow-parity` binds preview/backend→/app and127.0.0.1:8001→8000. Effective proxy corroborated by direct8001 and proxied5174 `/health/ready` (development, database/Redis ok). Isolated local DB `postgres/truckpitstop_ets_workflow_parity_20261012`, Alembic168_operation_execution head; existing provider settings/volumes untouched. Signed-in local Performance Owner UI works. Old boot indicator3ea3c7d is not current source proof; matching app files plus served-source checks after edits provide that proof. Baseline aligned and browser-verified; DB116 edits require a fresh changed-feature check.

## Diagnosis

The server's deletion notification uses status `deleted` as an event marker while the canonical repair order retains its lifecycle status and sets deleted_at. The WebSocket hook cast that marker into cached repair-order status and a later event timestamp, causing stale History data to override the canonical workspace on reopen. Active-only subpanels also remained mounted/enabled for deleted orders. Fix stays within the current contracts.


## Local verification

- Five focused Vitest files: **125 passed** (deleted workspace, WebSocket cache, hold workflow, request cancellation and pending feedback). Covers cold deleted link, warm History/delete/reopen, failed and pending restore, no repeat submit, restored editing, owner/admin permission gating and preservation of unrelated cached orders.
- TypeScript/Vite production build passed. Changed-source ESLint: zero errors, two unchanged hook-dependency warnings in RepairOrdersPage. `git diff --check` passed.
- Signed-in real API browser at1280×700: created only synthetic zero-cost order `PERF-295757AF-000005` / `c0fc8807-252f-4e6f-bf1a-ce0216ffbd3d`, existing QA customer/truck. Warm History → cancel Delete → Delete → Deleted → reopen without reload shows Deleted and footer Restore immediately. Only order workspace request200; no active-only subpanel requests or error placeholders.
- Closing the order action sheet left deletion intact. Blocking only this fixture's restore request left Deleted/Restore intact; clearing the block and explicitly retrying returned editable active workspace with preserved description and $0 total. Pending/no-repeat behavior covered by deferred automated response.
- Repeated warm History/delete/reopen in390×700 touch emulation, checked320×568 and740×400 landscape: direct44px Restore remains visible, intact label, no horizontal overflow or unavailable panels. Reloaded deleted landscape and restored through UI; active controls return. Final cleanup soft-deleted only the QA order. No services, invoice, timer, customer or vehicle changes.
- Screenshots: `/tmp/db116-local-desktop.png`, `/tmp/db116-local-mobile.png`, `/tmp/db116-local-320.png`, `/tmp/db116-local-landscape.png`. Temporary viewport/touch/request-block overrides cleared and QA tab closed. Browser emulation, not physical device testing.

## Release gate

Protected PR CI, merge, deployment and authenticated production workflow verification remain outstanding. ETS parity remains paused.
