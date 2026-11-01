# DB-042 — Inventory selected-part pane parity

Owner Frontend & UX; Fast UI; branch codex/inventory-panel-spacing from9d72b777. User requests the Inventory selected-part panel match released Shop Work separation and rounded corners. Existing API/data/permission contracts unchanged.

## Implementation

Wide side-by-side workbench gets12px column gap independent of scrollbar presence; redundant ledger edge dividers removed in that mode. Inspector outer radius16px in every mode, matching Shop Work. Selected header inherits the top radii so beige paint cannot cover the rounded boundary. Overlay/split inspector retains auto scrolling; narrow full-page detail retains visible overflow/page scrolling and Back behavior. Existing laptop overlay breakpoint remains unchanged; gap applies where panes are adjacent. Gray inspector/white list and all controls retained.

## QA

75/75 inventory/Activity/shared-dropdown tests pass. TypeScript/Vite production build passes; emitted CSS confirmed to include rounding/scroll overrides. Diff check clean; CSS-only, no changed TypeScript lint or implementation-mirroring CSS tests required.

Signed-in fictional desktop1680×900: actual list/inspector gap12px without ledger overflow, all four radii16px. Top-left/bottom-left corner hit tests clear rounded backing; visual screenshot confirms header follows curve.1680×520: gap12px with list and inspector overflow. Keyboard PageDown scrolls inspector to144px; pointer wheel in native laptop overlay moves144→242px.1280px overlay retains absolute position and16px radius without horizontal page overflow. All four detail tabs, editor opening/Cancel and photo preview/Escape pass.

390px coarse-pointer detail: width355px within existing workbench,16px outer/header corners, overflow visible for page scroll, no page horizontal overflow. All four tabs, editor Cancel, Back to list and row-fact tap reopening pass. No catalog/stock writes. Temporary device/touch overrides cleared; preview left at header.

Screenshots: [desktop](db042-panel-spacing/desktop.png), [mobile](db042-panel-spacing/mobile.png). Fictional local data only.

## Runtime receipt

2026-11-01: Vite5200 PID26374 cwd this checkout/frontend; API8017 dieselbridge_api_inventory-panel-spacing mounts this checkout/backend. Proxy targets8017; direct/proxied readiness DB/Redis healthy. Existing fictional truckpitstop_db042_qa schema196_historical_owner_self_review matches source head, no migration/reseed; Redis12 and no workers started. Approved backend env symlink and existing fictional QA sign-in used without copying or printing credentials. Prior5198/5199 runtimes preserved. Startup metadata is base9d72b777; changed source verified through actual12px gap/16px radii and user journeys.

http://127.0.0.1:5200/dashboard/garage/inventory aligned and browser-verified. Status Review; focused PR/CI pending, not merged/deployed.
