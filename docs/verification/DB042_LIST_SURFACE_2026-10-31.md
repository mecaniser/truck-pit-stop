# DB-042 — white Parts page, gray inspector, bordered rows

Owner Frontend & UX; Fast UI; branch codex/inventory-continuous-surface from e749b452. Final user direction supersedes earlier surface experiments: white surrounding page AND full ledger/header/gaps/gutters/footer; only the selected-part inspector retains its gray canvas and beige selected header. Every list item has a thin rounded border.

Implementation uses existing surface-overlay on the Parts main canvas and ledger backings, preserving the inspector surface-canvas. A 1px inset workspace-border outline follows each existing 10px row radius without geometry shift. Selected beige and hover/focus styles remain. No API, tenant, data, dependency, migration or payment changes. Other routes untouched.

Signed-in final desktop/390px QA: page/list/header/footer rgb(255,255,255); inspector rgb(232,237,244); row outline 1px, radius10px; no page horizontal overflow. Existing selection, photo-preview/Escape, sticky-header overlap journeys passed during this CSS-only refinement. Temporary device overrides cleared. Fictional-data screenshots: [desktop](db042-list-surface/desktop.png), [mobile](db042-list-surface/mobile.png).

61/61 focused inventory/Activity tests passed. Changed-source lint and production build passed before the last color/outline-only refinement; final build and updated-head protected CI pending. Mechanical detector reports only pre-existing findings. PR #726 remains held until final gates pass.

Runtime: Vite5198 PID26431 cwd this checkout/frontend; API8014 dieselbridge_api_inventory-surface binds this checkout/backend. Existing fictional truckpitstop_db042_qa, Redis12, schema196_historical_owner_self_review verified before startup; migration upgrade no-op. Direct/proxied readiness passes. Prior owned runtime gracefully replaced, shared5173/8000/8018 untouched. Source and rendered CSS verified. No production record writes.
