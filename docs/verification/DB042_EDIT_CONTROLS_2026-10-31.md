# DB-042 — smaller edit controls and non-overlapping header

Owner Frontend & UX, Fast UI. Branch `codex/part-edit-control-density` frome4b692ad. User requests smaller edit fields and fixes Edit details overlapping part identity. Existing API, mutation, validation, pricing and permissions remain unchanged.

## Implementation and QA

- Scoped desktop fields override shared staff forms'16px text floor:30px tall inputs with minimum13px text,40px resizable description, restrained focus outline. Labels stay visible. Supplier fields use one row where room permits; contact spans full width on narrow layouts.
- Selling-price input and Price/Markup controls share one row instead of a tall segmented-control heading. Photo guidance and section spacing are tighter. All12 identity/pricing/supplier fields remain. At1920px, selected edit surface592.81px and editor500.17px in this fixture.
- Header now uses actual content/action grid columns rather than absolute positioning plus52px padding. Full desktop Edit details label has reserved space and no hover width jump. At1920px: copy right1772.86px, actions left1780.86px (8px gap); at1280px:1082.47/1090.47px (8px gap). Narrow icon-only Edit retains its accessible name; touch Cancel has its own column. At390px:279/287px, no overlap.
- Actual signed-in browser verifies Cost17 + Markup50% computes25.50, blank cost reports validation, Escape cancels and restores Edit focus. Real description Save/reopen persisted a test change; second save restored its original value. No pricing changes saved. Touch at390px retains44px inputs, no document overflow.480px pointer screenshot shows all fields and Save in the compact form.
-61/61 focused inventory/Activity tests pass, covering validation/session guards, Save/photo pending cancellation, readonly/archive restrictions, photo fallback/preview, price modes, stock/ordering/activity interactions. Changed-source ESLint, TypeScript/Vite build and git diff checks pass. Design detector review recorded below.
- Fictional QA images: [desktop](db042-edit-controls/desktop-editor.png), [narrow pointer](db042-edit-controls/narrow-pointer-editor.png), [touch](db042-edit-controls/mobile-editor.png).

## Runtime receipt —2026-10-31

Vite5198 PID96068 cwd this checkout/frontend; API8014 container `dieselbridge_api_part-edit-controls` binds this checkout/backend. Branch/base above, changed source rendered and checked. Existing fictional `truckpitstop_db042_qa`, Redis12. Bootstrap upgraded this retained fixture from192 to current196 using existing main migrations193–196; reviewed equipment-type/default, optional review URL, and historical evidence/identity audit schema/guards; no inventory contracts or evidence/grants seeded. Both direct/proxied readiness and real inventory save/reopen pass. Prior owned API source-checked and gracefully replaced; shared5173/8000/8018 sessions untouched. http://127.0.0.1:5198/dashboard/garage/inventory aligned and browser-verified. No production record writes, uploads, messages or payments.

Protected PR CI, merge/deployment and live smoke pending; item Review rather than Done.
