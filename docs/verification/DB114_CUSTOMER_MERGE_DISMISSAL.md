# DB-114 Customer merge dismissal

Accountable: Frontend & UX. Fast UI: existing merge API/permission/data contract unchanged. No dependencies added.

## Acceptance and change

- Named dialog and Close merge dialog button, Escape and outside dismissal, keyboard focus contained and restored.
- Dismissal clears search/duplicate selection; reopening starts clean.
- While the existing merge request is pending, Escape, close and Back cannot discard its context; an error retains the selected duplicate and permits dismissal/retry.
- Existing candidate exclusion and winner/duplicate merge payload remain unchanged.
- Narrow-phone confirmation cards stack and complete action labels remain on one line; buttons can wrap as whole controls.

## Local evidence — 2026-10-13

- Two new regressions failed against the previous unnamed overlay.
-42 customer/order interaction tests passed; final27 customer tests passed after the mobile action adjustment. Changed-source ESLint, production build and diff whitespace check passed.
- Pending/failure scenario tested with a mocked request only. No actual merge submitted.
- Runtime revalidated after switching from17dfdf74 onto codex/customer-merge-dismissal: implementation ets-checkpoint-merge, approved selective preview mirror at5174/PID23640, backend8001 bound to preview/backend, database truckpitstop_ets_workflow_parity_20261012, Alembic168_operation_execution; direct/proxied readiness healthy.
- Signed-in local1280×700: named dialog, keyboard focus within dialog, Escape/close return to Merge.
- Touch-emulated390×700: Escape/close return to Customer actions (More), draft search resets.
-320×700: selected duplicate comparison and all controls reachable, no horizontal overflow; observed wrapped Merge Customers label corrected, rechecked at `/tmp/db114-local-320.png`.
- Physical device, native browser and software keyboard behavior not claimed.

## Release gate

Protected CI, merge/deployment identity and production desktop/mobile verification pending. ETS parity remains paused until both DB113 and DB114 pass.
