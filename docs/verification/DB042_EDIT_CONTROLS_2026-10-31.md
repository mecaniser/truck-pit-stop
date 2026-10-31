# DB-042 — smaller edit controls and non-overlapping header

Owner Frontend & UX, Fast UI. Branch `codex/part-edit-control-density` frome4b692ad. User requests smaller edit fields and fixes Edit details overlapping part identity. Existing API, mutation, validation, pricing and permissions remain unchanged.

## Implementation and QA

- Scoped desktop fields override shared staff forms'16px text floor:30px tall inputs with minimum13px text,40px resizable description, restrained focus outline. Labels stay visible. Supplier fields use one row where room permits; contact spans full width on narrow layouts.
- Selling-price input and Price/Markup controls share one row instead of a tall segmented-control heading. Photo guidance and section spacing are tighter. All12 identity/pricing/supplier fields remain. At1920px, selected edit surface592.81px and editor500.17px in this fixture.
- Header uses actual content/action grid columns instead of absolute positioning plus52px padding. User's final preference is pencil-only at every width: fixed44px control, aria-label Edit details, no visible or expanding label. Actual browser confirms44px before hover/on hover/on keyboard focus, no horizontal shift;1280px copy right1142.61px and button left1150.61px (8px gap). Enter opens details; Escape restores pencil focus. Earlier grid checks at1920/390px also retained8px copy/action separation.
- Actual signed-in browser verifies Cost17 + Markup50% computes25.50, blank cost reports validation, Escape cancels and restores Edit focus. Real description Save/reopen persisted a test change; second save restored its original value. No pricing changes saved. Touch at390px retains44px inputs, no document overflow.480px pointer screenshot shows all fields and Save in the compact form.
-61/61 focused inventory/Activity tests pass, covering validation/session guards, Save/photo pending cancellation, readonly/archive restrictions, photo fallback/preview, price modes, stock/ordering/activity interactions. Changed-source ESLint, TypeScript/Vite build and git diff checks pass. Mechanical detector findings are7 warnings in unchanged CSS7031–7069; no changed-line findings.
- Fictional QA images: [desktop](db042-edit-controls/desktop-editor.png), [narrow pointer](db042-edit-controls/narrow-pointer-editor.png), [touch](db042-edit-controls/mobile-editor.png).

## Runtime receipt —2026-10-31

Vite5198 PID96068 cwd this checkout/frontend; API8014 container `dieselbridge_api_part-edit-controls` binds this checkout/backend. Branch/base above, changed source rendered and checked. Existing fictional `truckpitstop_db042_qa`, Redis12. Bootstrap upgraded this retained fixture from192 to current196 using existing main migrations193–196; reviewed equipment-type/default, optional review URL, and historical evidence/identity audit schema/guards; no inventory contracts or evidence/grants seeded. Both direct/proxied readiness and real inventory save/reopen pass. Prior owned API source-checked and gracefully replaced; shared5173/8000/8018 sessions untouched. http://127.0.0.1:5198/dashboard/garage/inventory aligned and browser-verified. No production record writes, uploads, messages or payments.

Protected PR CI, merge/deployment and live smoke pending; item Review rather than Done.

Final pencil-only regression assertions preserve the accessible Edit details name, an empty visible-text node, and the icon-only action. User chose no expanding label after initial layout review; fixed44px geometry is verified for hover and keyboard focus.


## Sticky ledger header regression found during review

User reported a row thumbnail floating over column labels while scrolling. Reproduced in a separate real signed-in local tab at1920×520 with two fixture rows: ledger clientHeight161px, scrollTop65px, photo top356.34px, sticky header359.34–407.34px. Before fix the header-center hit test returned the photo rather than the header. Photo and header both usedz-index2, so the later photo painted above.

Final fix makes the sticky header layer5, above inline photo2 and row action4 while preserving floating menu9. No new row stacking contexts or menu positioning changes. At identical scroll position, hit test now returns the header and never the photo. Real-image capture: [fixed scrolling](db042-edit-controls/sticky-header-fixed.png). Hover remains scale1.08, media preview opens/closes and restores focus, and row selection remains functional. Temporary per-tab device metrics were cleared. Existing optional row-action/menu/Escape component regression is included in the focused61 tests. Updated protected head required before release.
