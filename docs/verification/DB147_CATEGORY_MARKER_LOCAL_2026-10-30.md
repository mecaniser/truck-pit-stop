# DB-147 category-colored sliding marker — local review

Owner: Frontend & UX, Fast UI lane. User requests local preview before any delivery. Branch `codex/sidebar-category-marker`, HEAD `01c386e76a8c26ac6ac545b9656f0a0f3a34d27f`; source changes remain uncommitted.

One persistent absolute marker moves between the four primary routes, using actual computed glyph color. CSS transform transitions take220ms and retarget mid-flight; initial placement, keyboard activation and reduced motion snap. ResizeObserver aligns compact/expanded and font/density layouts without canceling an already-correct in-flight destination. Other routes hide the primary marker; message notification badges remain separate. No route, role, tenant, API, schema, dependency or provider changes.

## Runtime alignment

Frontend PID74219, port5173, cwd `/Users/sergio_m1_promax/.codex/worktrees/machined-sidebar/truck-pit-stop/frontend`, validated branch/SHA environment matches the branch above. Restarted only the exact verified previous Vite PID17535 from this same worktree. API port8000 `dieselbridge_api_dev` still mounts this worktree's backend and uses local `postgres` / `truckpitstop_db146_c3`, environment development. Both repository and database remain at `192_vehicle_issues`; no migration, reseed, credential copy, worker or provider action. API readiness and actual frontend readiness proxy returned200. The rendered in-app runtime badge confirms `codex/sidebar-category-marker@01c386e`; served-source marker behavior verified below. **Aligned and browser-verified** at `http://127.0.0.1:5173/dashboard/customers`.

## Acceptance evidence

- Existing DashboardLayout regression suite13/13; exact TSX ESLint, TypeScript/Vite production build and diff integrity pass.
- Actual local API/signed-in Chromium batch: all four category markers equal glyph RGB and center on the selected row. Twenty animation frames include multiple distinct intermediate positions; rapid Shop Work/Customers/My Shop clicks settle correctly.
- Keyboard Enter selection and reduced motion have0s transition duration. Automatic960px compact and return to1440px expanded stay aligned. Settings hides the primary marker. One marker node remains; no JavaScript page errors.
- The user's actual signed-in in-app tab was refreshed to clear an obsolete inline background retained from an intermediate hot-reload iteration. Fresh source verifies My Shop bar and icon both `rgb(223,200,160)`. Native Customers click verifies both `rgb(195,178,255)`, `data-animate=true`, transition0.22s. User preview remains open on Customers.
- Screenshots and motion samples: `/Users/sergio_m1_promax/.codex/visualizations/2026/10/30/01a18e7d-68d0-7420-a357-f190993f8409/category-marker-expanded.png`, `category-marker-collapsed.png`, `category-marker-checks.json`.

Local review only. No commit, push, PR, merge or deployment performed for this follow-up. The previous shipped version remains unchanged.


## QA motion correction

Product authorized fixing only the slide cancellation and explicitly excluded Inventory. CSSOM serializes fractional transforms at rounded precision; comparing that string to unrounded geometry caused redundant observer updates to disable animation. Coordinates now normalize to three decimal places before comparison. Actual My Shop transition completes in3/3 reproductions with transitionrun/transitionend, .22s duration. Full28-observation local browser rerun reports no motion findings and no page exceptions; existing out-of-scope resource404s remain unchanged. Focused13/13 tests, ESLint and diff integrity pass. No push or deployment.


## Painted visibility correction

User screenshots revealed a genuine stacking defect missed by prior geometry/computed-color checks. Screenshot pixel probes before correction returned navy(9,22,38) at the marker center for Shop Work, Orders and Customers, despite their correct computed category colors. My Shop's translucent row allowed its marker through. The shared marker now has z-index1, above positioned navigation rows, while remaining pointer-transparent. Pixel probes now match each category RGB in all four expanded and all four compact selections. Motion/rapid retarget/keyboard/reduced-motion checks also pass. Earlier blanket QA-pass claims are superseded by this painted-pixel acceptance. Inventory remains excluded; no deployment.
