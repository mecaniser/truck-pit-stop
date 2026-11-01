# DB-152 — shared application controls

Owner: Frontend & UX. Fast UI lane. Branch: `codex/shared-controls`.
Status: local acceptance passed; PR integration gate and authorized release pending.

## Delivered architecture

`ControlButton`, `ControlInput`, and `ControlGroup` own native semantics and reusable grouping. `controls.css` owns height, padding, radius, typography, focus, icon sizing and responsive targets. BaseSelect/PlatformSelect, ShopWorkSelect and headless triggers consume the same geometry. Existing surface classes retain colors and emphasis.

The source inventory covers 1,554 buttons and 470 text-like inputs across application features. Structural/content buttons explicitly preserve record, tile, navigation and disclosure layout. Public marketing, checkbox/radio/file/range/color controls retain their distinct contracts. See [inventory](DB152_CONTROL_INVENTORY.md). Build-time `lint:controls` rejects new native buttons/text fields or unmarked headless triggers outside documented primitive exceptions.

Desktop fine-pointer controls have a 34px minimum height; mobile/coarse-pointer, large density and touch-first portals use 44px. Text can grow rather than clip. Icon actions are square. Appearance font scaling remains inherited. The development-only [catalog](../../frontend/tests/control-catalog.tsx) exercises real primitives without business writes.

## Acceptance evidence

- Signed-in fictional local shop: Shop Work, repair-order panel, issue Open/Resolved filter, refresh, Add issue dialog open/close, customer list/detail, inventory.
- At 1440px: issue select, refresh and Add issue are 34px high; refresh is 34px square. At 390px: the same controls are 44px; no page overflow.
- Catalog checks cover keyboard select, disabled action, dark surface, 20px base typography/large density, date input and quantity stepper. Desktop/mobile screenshots are in `db151/`.
- Native contract tests cover implicit submit, explicit non-submit, forwarded refs, form data, disabled fieldsets, keyboard activation and controlled input events.
- Production TypeScript/Vite build and control guard passed. Initial full suite exposed two obsolete hardcoded-size class assertions; replaced them with shared-control assertions while retaining workflow/keyboard checks. Focused rerun: 143 tests passed across four files. Final full suite: 209 files / 2,228 tests passed. After integrating main4645ea6a, production build/control guard and61 affected Team/inventory tests passed. Changed-source lint: zero new violations across195 TypeScript files, using the repository signature/baseline rules through a batched ESLint API runner (same rule/message/source-line comparison; the slower per-file CLI run was stopped).
- No API, permission, tenant filtering, financial or authentication behavior changed. Normal login used an existing fictional local fixture. No business records were saved during browser checks.

## Runtime receipt — 2026-11-01

- Worktree: `/Users/sergio_m1_promax/.codex/worktrees/shared-controls`; implementation `0872112bc9ce9a0055807e65bd2c7389983e86be` includes main4645ea6a; rendered source and branch indicator browser-verified.
- Frontend: `http://127.0.0.1:5235`, Vite PID79709, cwd is this worktree's `frontend`; isolated dependencies.
- Backend: `http://127.0.0.1:8035`, container `dieselbridge_api_shared-controls`, image `truck-pit-stop-api`, bind mount this worktree's `backend` to `/app`.
- Approved local configuration: PostgreSQL `truckpitstop_db042_qa`, Redis DB12, schema head/current `196_historical_owner_self_review`. Existing sandbox/provider settings preserved; no migration or reseed.
- Direct and frontend-proxied `/health/ready` report database and Redis ready. Task origin added only to this isolated API's CORS allowlist. Existing5173/8000 services untouched.
- User's in-app preview signed in through normal login with Remember me, then reloaded successfully into Shop Work. Its session is distinct from the automation browser. Password-manager storage was not changed.

Not merged or deployed. Protected PR CI and release approval remain required.

## Review handoff

[Draft PR735](https://github.com/mecaniser/truck-pit-stop/pull/735). Latest-main conflict was confined to delivery-board history; both histories retained. Team and inventory desktop/mobile screenshots refreshed after integration. Mobile Team actions measure44px with no page overflow. DB-152 supersedes the initially allocated DB-151 identifier because a concurrently merged Team item used DB-151. Screenshot folder `db151/` retains its original evidence paths.
