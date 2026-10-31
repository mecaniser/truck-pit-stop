# DB-150 — Expanded working area and consistent rounded lists

Owner: Frontend & UX. Fast UI lane. User approved the final design and subsequently authorized merge and deployment on2026-10-31.

## Final behavior

- Remove the modern staff shell's outer rounded frame and outside margin; preserve a thin navigation divider.
- Parts, Customers, Repair Orders and Shop Work use one12px horizontal workspace gutter, without nested page padding.
- Lists have12px corners and records10px corners with4px vertical spacing. Workspaces themselves stay frameless. Existing selection, inspected, hover and focus states remain.
- Customer and repair detail panes retain their separating divider. Mobile bottom-navigation clearance remains.
- Settings breadcrumb and content align; the initial broad header-margin override was removed.
- API, tenant, authorization, data model and financial behavior are unchanged.

## Review and verification — 2026-10-31 EDT

Final diff reviewed against main16f72a35. Six focused suites pass169/169: DashboardLayout, PartsInventoryWorkspace, CustomersPage workstation, RepairOrdersLedger, ShopCockpitActionLedger and WipAgingPanel. Direct changed CustomersPage ESLint and git diff check pass. TypeScript/Vite production build passes. Existing Router/Browserslist warnings only.

Signed-in browser checks cover all four lists at1600/1024/390px. Measured12px gutters; list/row radii12/10px; no document horizontal overflow. All desktop final captures were visually reviewed. Parts pointer selection, compact52px rows and keyboard Enter selection pass. Customer/repair inline Details expand; keyboard opening of customer/repair workspaces passes. Settings breadcrumb/content both measure x240 at1600px. No customer, financial or provider records mutated during final review.

Layout unit tests are regression coverage for behavior, not CSS geometry evidence; geometry and visual claims above come from the actual browser.

## Local runtime receipt

- Checkout: `codex/expanded-workspace`, based on16f72a35; final frontend sources served locally.
- Frontend: http://127.0.0.1:5210, PID78168; cwd is this checkout's frontend. Proxy targets8018.
- API: http://127.0.0.1:8018, container `dieselbridge_api_expanded-workspace`, bind mount is this checkout's backend.
- Isolated local database `truckpitstop_expanded_workspace`, cloned from fictional QA data, schema195; Redis14. Existing approved environment linked without copying secrets. No worker started. Direct/proxied readiness pass.
- **Aligned and browser-verified.** Shared default services unchanged. Local serving is not release evidence.

## Reproducible visual comparison

Open http://127.0.0.1:5210/tests/db150-comparison.html. Four area buttons, full-before/full-after controls and slider are verified. All image pairs use1600×1000, identical fictional data, dark theme and expanded sidebar. Before uses the original-main stylesheet; after uses the final implementation. Test-page assets are outside the production entry point.

| Area | Before | After |
| --- | --- | --- |
| Parts | [Before](../../frontend/tests/db150/parts-before.png) | [After](../../frontend/tests/db150/parts-after.png) |
| Customers | [Before](../../frontend/tests/db150/customers-before.png) | [After](../../frontend/tests/db150/customers-after.png) |
| Repair Orders | [Before](../../frontend/tests/db150/repairs-before.png) | [After](../../frontend/tests/db150/repairs-after.png) |
| Shop Work | [Before](../../frontend/tests/db150/shop-work-before.png) | [After](../../frontend/tests/db150/shop-work-after.png) |

Protected PR CI is the integration gate. All seven checks passed on7a201c38; concurrent main a7c0ed74 integrated with board-only conflict resolution. Fresh exact-head CI, merge, deployment and production smoke pending.
