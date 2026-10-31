# DB-042 — consistent density across all selected-part tabs

Frontend & UX accountable; Fast UI. Branch `codex/part-overview-ordering-density` fromdc7fecda. Existing API/mutation/permission/tenant/pricing contracts unchanged; no dependency or schema changes.

Overview: paired label/value summary facts and tighter supplier/repair/movement sections. Supplier identity/details remain, with decorative initial block and card framing removed. At437px inspector, Overview panel560.30px versus768.34px baseline (27% shorter). Ordering: tighter recommendation/action, supplier source facts (two compact rows), source form and purchase history. Empty-source panel373.44px versus455.05px baseline (18% shorter). Every fact, action, as-of state, validation and link retained. Scoped styles preserve Stock/Activity's released density and standalone Activity.

## Full workflow QA

-61/61 inventory/Activity tests pass; coverage includes populated supplier sources, source mutations/concurrency/removal confirmation, archived/readonly controls, identity lifecycle/numeric validation, stock/reorder, purchase preparation, sorting/selection and Activity filtering. Changed-source ESLint, TypeScript/Vite build, diff checks pass. Design detector finds only7 warnings in unchanged CSS7023–7061.
- Signed-in desktop: four tabs; Overview/details load, blank cost rejects, Escape restores trigger; photo preview opens/closes; Stock adjustment Escape cancels; Ordering Add source rejects missing supplier, Cancel restores Add trigger, Add to purchase list changes to Prepared/View purchase list; Ordering→Activity ArrowRight works; Activity search/empty/reset works.
-390×844 coarse pointer: Overview and Ordering fit; source inputs44px, source form two columns for numeric controls and full-width lead time; all four tabs fit without horizontal scrolling; Stock stepper ends208.19px versus Save start218.42px and Cancel288.81px (no overlap); Activity filter controls46px; no document overflow. Runtime directory has no suppliers, so populated-source success paths use existing component fixtures; runtime covers real form layout, missing-supplier validation and focus recovery.
- Fictional screenshots: [Overview desktop](db042-four-tabs/desktop-overview.png), [Ordering desktop](db042-four-tabs/desktop-ordering.png), [Overview mobile](db042-four-tabs/mobile-overview.png), [Ordering mobile](db042-four-tabs/mobile-ordering.png).

## Runtime alignment

2026-10-30 EDT: Vite5198 PID85422 cwd this checkout/frontend, API8014 `dieselbridge_api_part-overview-ordering` /app bind this checkout/backend. Branch/base above; modified source browser-verified. Retained fictional DB `truckpitstop_db042_qa`, Redis12, schema192_vehicle_issues, no-op upgrade. Direct/proxied readiness passes. Normal local fixture account sign-in refreshed expired local session. Shared5173/8000 untouched; prior owned5198/8014 services source-checked/gracefully replaced. http://127.0.0.1:5198/dashboard/garage/inventory aligned and browser-verified. Local purchase preparation only; no production data writes. Protected CI/merge/deployment/live check pending; item Review.
