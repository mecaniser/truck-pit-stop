# DB-043 — My Shop navigation stability

Owner: Frontend & UX. Fast UI; CSS-only existing-contract correction.

The outer shell's 12px gutter previously depended on the Inventory workbench being mounted. Purchasing and loading/error content fell back to different shell padding. The shared My Shop workspace now owns the gutter, content inset and desktop bottom padding across its sections. The existing 2px keyboard focus outline uses -2px offset so parent clipping cannot cut it off. Active colors, targets, routes and permissions remain unchanged.

## Verification

- MyGaragePage and DashboardLayout component suites: 16/16 pass.
- TypeScript and Vite production build pass. Changed-source lint reports no changed TypeScript; CSS is compiled by the production build. `git diff --check` passes.
- Signed-in fictional shop, 1600×1000: Inventory → Purchasing → Inventory gives identical x/y/width/height for breadcrumb and all six navigation links. Breadcrumb x236/y12; tab y56/height44. No document horizontal overflow.
- 390×844: same bidirectional geometry equality, breadcrumb x12/y73; first row y126, second y178, secondary row y247; every link height44. No document horizontal overflow.
- Real Shift+Tab and Enter: Inventory receives visible 2px focus outline, offset -2px, and activates correctly on desktop/mobile. Active route remains correct. Screenshot visually reviewed on desktop. Mobile geometry and focus verified; temporary viewport override reset.
- [Desktop](db043-nav/desktop.png), [mobile](db043-nav/mobile.png).

## Runtime receipt — 2026-11-01 10:56 EST

Branch `codex/my-shop-nav-stability`, base f61fd271447312c588d714e5d6f04c1a98d7490c, task CSS/docs edits only. Frontend http://127.0.0.1:5173 PID3456 serves this worktree/frontend, proxy8019. API container `dieselbridge_api_my-shop-nav` port8019 binds this worktree/backend. Database `truckpitstop_my_shop_nav` is an isolated clone of existing fictional QA data; Redis15; schema196 matches repository head, no migration run. Approved backend environment linked, no secret copies or provider-setting changes; no worker started. Direct and proxied readiness pass. Normal staff login succeeded against the cloned fixture; local fixture password setup affected only the clone. No production/customer/provider mutations.

Aligned and browser-verified. Shared API8000 and other task services preserved. Review candidate only; protected CI, merge and deployment remain outstanding and no production release is claimed.

## Navigation hierarchy refinement — 2026-11-01

User requested the main rail's icon/selection family at secondary priority, with Team/Analytics tertiary. Operational links now use26px softly raised glyph tiles (main rail34×36px), neutral selected fill and a short22×2px copper marker. Team/Analytics keep the divider, plain22px glyph containers, transparent selected background and a muted marker. Labels remain readable; every target stays44px. Existing route names and keyboard order unchanged; decorative wrappers are aria-hidden and links retain explicit accessible names. Legacy presentation retains its original styling.

All six destination changes retain exactly equal breadcrumb/tab rectangles at1280px. At390px, switching from Book Time to Purchasing also retains geometry, no page overflow, keyboard Shift+Tab focuses Inventory with2px/-2px outline. Light/dark/high-contrast visual checks pass; dark check used temporary DOM theme and transition overrides, all restored/removed. Mobile viewport reset. Runtime unchanged: frontend5173 PID3456/API8019 same worktree, isolated fictional database and Redis15; proxied readiness passed. Served glyph wrapper and computed CSS confirmed. Aligned and browser-verified.

16/16 focused component tests pass again, changed TSX ESLint passes, TypeScript/Vite build passes, diff check clean; Impeccable component detector reports no findings. [Light desktop](db043-nav/hierarchy-desktop.png), [mobile](db043-nav/hierarchy-mobile.png), [dark](db043-nav/hierarchy-dark.png), [high contrast](db043-nav/hierarchy-high_contrast.png). No records or preferences saved during browser checks. Draft PR728; review/CI/merge/release remain separate gates.

## Approved direction correction — 2026-11-01

Supersedes raised-tile hierarchy above: user rejected all item/icon backgrounds and requested a direction-aware bottom marker. All modern tab states are transparent; plain16px icons inherit readable label color. One aria-hidden marker travels between selected bounds (tab width minus20px), with transform/width240ms ease-out. Natural geometry gives leftward/rightward motion and interruption continuity. Team/Analytics retain muted marker and separate cluster. Initial entry and ResizeObserver layout updates snap; prefers-reduced-motion disables transitions. Existing main-menu styling is untouched.

Runtime browser measured leftward frames x542→488→435→391→…→247 and rightward x246→305→356→399→…→540, ending exactly at selected target542.094. Selected/glyph computed backgrounds both transparent. Reduced-motion reports0s and exact new target immediately.390px resize snaps to correct target, no page overflow, all targets44px, Tab focus offset-2px. Emulation/viewport restored and temporary verification tab closed. [Current desktop](db043-nav/sliding-marker.png). Same aligned5173/8019 runtime and isolated fixtures as above; no restart, data or preference mutation.

17/17 focused tests pass, including a shared-marker identity test across forward/backward/tertiary routing. Initial test failure was jsdom missing ResizeObserver; test stub added, no application fallback or weakened browser behavior. Changed-source/test ESLint, TypeScript/Vite build and diff check pass. PR728 remains draft; no merge or deployment.

## Colored mechanical icon refinement — 2026-11-01

User explicitly requested the main rail's mechanical icon treatment and distinct colors after accepting transparent tabs and the moving marker. Only the glyph housing returns:28px operational /24px tertiary vs34×36px main rail. Shared dark shell material, diagonal highlight and small offset shadow match the rail. Inventory sand, Purchasing blue, Services mint, Book Time amber, Team violet, Analytics cyan. Tab selection/hover backgrounds remain transparent; the shared moving underline is unchanged. High-contrast/system-color glyph fallbacks retained.

Signed-in browser confirms all six distinct computed colors and28/24px dimensions, all six tab backgrounds transparent.390px has44px targets and no horizontal overflow; visual desktop/mobile inspection passes. Same aligned5173/8019 runtime; proxied readiness healthy, no data/preference changes. [Current desktop](db043-nav/mechanical-icons.png), [mobile](db043-nav/mechanical-icons-mobile.png).17 component tests, changed TSX lint, TypeScript/Vite production build and diff check pass. PR728 stays draft, not deployed.
