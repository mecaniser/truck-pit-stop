# DB-042 Selected-part workspace density rebuild

Owner: Frontend & UX. Fast UI. Branch `codex/selected-part-workspace-density` from7ac5f434. User requests the whole selected-part workspace become fast to navigate and edit, specifically pictured Stock and Activity.

## Changes and acceptance

- Compact identity header on every tab, retaining name, SKU, bin, unit, stock state, photo preview, Edit details and mobile Back. Header87.05px versus171.70px baseline at437px inspector (49% reduction).
- Sticky navigation; all four tabs fit at390px without horizontal scrolling. Arrow-key navigation remains functional.
- Stock facts, adjustment form and receiving use a tight grid. Stock panel468.83px versus623.94px baseline (25% reduction). Cancel has its own grid cell beside Save; compact QA caught/corrected a6px stepper collision. Final390px bounds: quantity ends208.19px, Save begins218.42px/ends282.42px, Cancel begins288.81px. No overlap.
- Adjustment reason is two lines and resizable. Save/Cancel are native controls. Signed-in fictional stock adjusted0→1 and restored1→0 through the real UI; Escape discards a reason draft and returns focus. Fractional receive1.5 rejects with explicit whole-quantity error. Existing mutations, validation and archived/readonly restrictions are unchanged.
- Activity lifecycle cards become dense labeled facts, preserving aggregates and as-of time. Inspector Activity removes repeated explanatory prose and the already-known part identity from each visible event, while preserving source links, dates, actors, before/after values, and more-details disclosure. Search/category/actions share two compact rows; export remains accessible. Standalone Activity retains its existing heading/description/layout.
- Real signed-in search yields empty state; Reset restores records. Ordering→Activity via ArrowRight works. Edit details loads and Escape restores Edit trigger focus.390px no document overflow; coarse-pointer filters/buttons46px and tabs44px. Photo preview/hover behavior from#708 retained.

## Verification

61/61 focused inventory + Activity tests pass, including compact query/filter/reset coverage. Changed-source ESLint, TypeScript/Vite build, git diff checks pass. Mechanical detector warnings only in existing CSS, outside new styles. Browser screenshots use fictional fixture data: [Stock](db042-workspace-density/desktop-stock.png), [Activity](db042-workspace-density/desktop-activity.png), [mobile Activity](db042-workspace-density/mobile-activity.png).

Runtime2026-10-30 EDT: intended worktree `selected-part-workspace-density/truck-pit-stop`, branch/base above, changed source rendered. Vite5198 PID78481 cwd this checkout/frontend; API8014 container `dieselbridge_api_selected-part-density` binds this checkout/backend. Existing fictional `truckpitstop_db042_qa`, Redis12, schema192_vehicle_issues; migration upgrade no-op. Direct and proxied readiness pass. Prior owned5198/8014 servers were source-checked and gracefully replaced; shared5173/8000 untouched. http://127.0.0.1:5198/dashboard/garage/inventory is aligned and browser-verified. No production record writes. Protected PR CI/release pending; item remains Review rather than Done until required release evidence exists.
