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
- 42 customer/order interaction tests passed; final27 customer tests passed after the mobile action adjustment. Changed-source ESLint, production build and diff whitespace check passed.
- Pending/failure scenario tested with a mocked request only. No actual merge submitted.
- Runtime revalidated after switching from17dfdf74 onto codex/customer-merge-dismissal: implementation ets-checkpoint-merge, approved selective preview mirror at5174/PID23640, backend8001 bound to preview/backend, database truckpitstop_ets_workflow_parity_20261012, Alembic168_operation_execution; direct/proxied readiness healthy.
- Signed-in local1280×700: named dialog, keyboard focus within dialog, Escape/close return to Merge.
- Touch-emulated390×700: Escape/close return to Customer actions (More), draft search resets.
- 320×700: selected duplicate comparison and all controls reachable, no horizontal overflow; observed wrapped Merge Customers label corrected, rechecked at `/tmp/db114-local-320.png`.
- Physical device, native browser and software keyboard behavior not claimed.

## Release gate

Protected CI, merge/deployment identity and production desktop/mobile verification pending. ETS parity remains paused until both DB113 and DB114 pass.


## Production release and acceptance

- PR515 source `7a1ec64ad6f411b559c2fdb5829cbcba4d66a67f` passed all six protected checks in [run38485801899](https://github.com/mecaniser/truck-pit-stop/actions/runs/38485801899), including 2,856 backend tests (125 skipped) and all 154 frontend test files.
- Merged **1c76d805079c6225e0d4af74a43cb24be471d591** at 2026-10-14 00:00 UTC (Oct13 local).
- Railway Web deployment **53448622-82bd-4f19-a4ce-b53de71cefec** SUCCESS at that exact SHA. Production `/health/ready` reports healthy database/Redis. Fresh authenticated browser loaded `index-TQ0GnU-d.js`.
- **1280×700 desktop:** named dialog and named Close merge dialog; focus contained, Escape and close return to Merge. Search cancellation rechecked on final release.
- **390×700 touch portrait:** Escape and close restore Customer actions (More); reopening clears the draft search. Readable bounded dialog.
- **320×700 touch portrait:** duplicate comparison readable, all controls reachable, Merge Customers stays on one line with a 44px-high target, no horizontal overflow. Escape from confirmation dismisses without submitting.
- **Repair-order embedded customer, 320px:** same named dialog/Escape behavior and focus return; selected order/customer context retained.
- **740×400 touch landscape:** close target 44×44px inside viewport, no horizontal overflow; close → Back to order → Close order returns to the order directory.
- Captured production console errors empty. No production merge, create, edit or financial action submitted. Pending/failure mutation guards were verified with mocked local tests, not by mutating production.
- Local screenshots: `/tmp/db114-production-desktop.png`, `/tmp/db114-production-mobile.png`, `/tmp/db114-production-320.png`. Live business screenshots are not published to GitHub.
- **Done.** Both DB113/DB114 gates pass and ETS parity may resume. These are actual signed-in production browser interactions under viewport/touch emulation; physical iOS/Android devices, native Safari and software keyboards were not tested.
