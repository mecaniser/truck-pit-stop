# DB-150 — list/detail separation and rounded backing

Frontend & UX accountable; Fast UI; branch codex/workspace-pane-spacing from f61fd271. User reports selected Shop Work card touches the right workspace without a scrollbar, and square backing appears behind rounded top/bottom detail corners.

Root cause: shared desktop override in index.css forces column-gap0 on repair-order/customer split layouts and border-radius0 on detail wrappers. Shop Work uses the same repair-order workspace. Change only those two declarations:12px gap and16px wrapper radius. Existing overflow:hidden clips child surfaces to the rounded boundary. No new outer page gutters, API/auth/data/financial/dependency or interaction changes.

## Acceptance and QA

Before signed-in local5198: gap0px, wrapper radius0px; top-left/bottom-left interior corner hit tests return the square wrapper. After focused5199: actual measured list/detail gap12px, wrapper radius16px and overflow:hidden; same corner hit tests return outside the panel. Both no-scrollbar720px height and scrolling360px height preserve12px (list scrollHeight220/clientHeight164 in compact-height check). Customer detail also measures actual12px gap and16px radius.

Shared navigation selected URL changes with Next/Previous; original order restored. Existing menu and footer controls retained.390px mobile pane still spans0..390px with no page horizontal overflow; desktop-only override leaves mobile behavior intact. Temporary device overrides cleared. No production/fictional order/customer writes.

85/85 focused tests pass: ShopCockpitActionLedger, CustomersPage.workstation, RepairOrdersPage.customer. TypeScript/Vite production build passes; diff check clean. CSS-only, no changed TypeScript for lint; no implementation-mirroring CSS test added. Protected PR CI remains integration gate.

Screenshots: [Shop Work desktop](db150-pane-spacing/shop-desktop.png), [mobile](db150-pane-spacing/shop-mobile.png), [Customer desktop](db150-pane-spacing/customer-desktop.png). Fictional local data only.

## Runtime receipt

2026-11-01: Vite5199 PID16583 cwd this checkout/frontend, branch above/basef61fd271. API8016 dieselbridge_api_workspace-pane-spacing binds this checkout/backend. Proxy target8016 verified; direct and proxied readiness DB/Redis healthy. Existing fictional truckpitstop_db042_qa schema196_historical_owner_self_review matches source alembic head; no migrate/reseed. Redis12, no worker start or payment testing. Normal local sign-in with existing fictional QA account. Approved backend env symlink retained, no credentials copied or printed.

http://127.0.0.1:5199/dashboard?selected=3858e180-0a2b-40d4-a2f0-b3c37ac3da7f&queue=needs_action&work_view=active aligned and browser-verified. Inventory branch/PR727 and5198/API8015 preserved. Focused shared-layout PR only; not merged/deployed. Status Review.

Draft PR #729: https://github.com/mecaniser/truck-pit-stop/pull/729. Protected CI pending; local source and runtime QA passed.
