# DB-145 Shop Work dropdowns, accent digits and Activity count

Owner: Frontend & UX. Lane: Fast UI. Branch: `codex/shop-work-dropdowns`.

## Acceptance and boundaries

- Timing, Sort, mobile category, Activity staff/type triggers and open menus match Day/Night.
- Existing Headless UI Listbox owns keyboard selection, focus return, Escape/outside dismissal and viewport anchoring. Filters stays open while selecting a nested menu.
- Compact desktop/mobile controls; user-approved accent digits replace solid count fills.
- Activity first-page count appears on arrival, before selecting Activity. `+` reflects server `has_more`; it is not a total or unread count. Filters/pagination do not change the tab summary. Loading/failure never claims zero.
- Existing GET `/activity` contract and permitted roles retained. Shared query is keyed by tenant/principal/role/session/filter; no financial/API/permission/migration/importer changes.
- Payment-only closeout and missing timing Unknown remain separate/unchanged. C3 resumes after this correction; redesign remains separate.

## Source and local evidence, 2026-10-30

- Root cause: `activityCount` initialized to zero and updated only by the feed mounted after selecting Activity; previous value was loaded items, not a total.
- Shared first-page query now mounts with DashboardHome and is reused by the unfiltered feed. Manual refresh invalidates it. No extra polling or full history enumeration.
- Focused checks: 46 pass (14 WIP,17 ledger,5 activity query,10 DashboardHome presentation). Query tests cover initial read/cache reuse, filter independence, disallowed/inactive principals, tenant/session cache separation and unknown/error versus zero.
- Changed-source ESLint passes. TypeScript and full production build pass.
- Local runtime aligned: checkout a2-closeout-count, branch above, base `0f369f980fdee3c2f37981082f238630ae0b64c5`; frontend PID60351 at5173, backend60317 at8000, exact source cwd confirmed. Explicit localhost isolated `truckpitstop_db145_a2`, sole191,0invoices; no migration/reseed. Direct/proxy readiness database/Redis OK.
- Real component synthetic browser pass at1280×900 and390×844: Day/Night open menus, selection, keyboard Arrow/End/Enter, nested Escape/focus return, outside dismissal and viewport bounds. Synthetic activity count visible before feed mount and stable on filtering; no mutation controls invoked. Harness removed before commit. Private screenshots under `/tmp/db145-controls-release/`.
- Browser-discovered nested focus dismissal and portaled theme inheritance corrected; shared theme token declarations reused for menus. Local preview is component-verified, not authenticated production acceptance.

## CI correction

Initial run41108481638 passed protected checks and browser smoke, but the informational full frontend suite exposed eight DashboardHome fixture failures: its catch-all query mock returned dashboard data for the new activity query. Corrected the query/auth/theme fixtures and added a page-level assertion that Activity20+ is visible before feed mount and refresh invalidates activity. All46 affected tests and changed-test lint pass. No application-source change after local browser/build acceptance.

## Release

PR692 all seven checks41111029819 passed on40d8911c. Normal squash merge19900b7e; checked/merged tree d30382af8b5b947a253d0f4005c79866184ef4e4. Automatic Web825850fd-6919-43b9-a234-08255c3035ba SUCCESS; public build exact and DB/Redis ready. Authenticated production confirms Activity20+ on arrival before click, stable count while filters yield no matches, retained Closeout1, Day desktop timing/sort keyboard/Escape/focus/outside behavior and390px category menu bounds (320px maximum height, no horizontal overflow).

Production acceptance found a narrow Activity staff trigger forced its open menu to approximately90px, splitting names across lines. This is a visual gate failure, not a data defect. Focused follow-up `codex/shop-work-menu-width` gives only the open menu a viewport-bounded200px minimum. Trigger footprint remains unchanged. No new application logic, data, API, dependency or migration change.

Follow-up runtime aligned on2026-10-30: frontend5173 PID71845/backend8000 PID71717 exact a2-closeout-count source; localhost truckpitstop_db145_a2, sole191 and0invoices unchanged; direct/proxy DB/Redis ready. Real ShopWorkSelect component with fictional staff names verified Day/Night1280/390: menu200px, names legible, within viewport, keyboard Escape retained. Temporary harness removed. All14 WIP component tests and TypeScript/production build pass; CSS-only change has no changed TypeScript lint surface. Owned local servers stopped after exact-PID/cwd checks. Production timing/category menus and accent digits also pass Night1280/390; Day restored. Follow-up CI/deployment and actual full Day/Night production acceptance remain pending; no Done claim.


## Final production acceptance — 2026-10-30

Status: **Done**, Frontend & UX accountable. PR694 closes the mobile-width finding from PR692.

- PR694 all seven checks41113337592 SUCCESS on `a7f1efc47f40f58c82fe34b2911eee62b30a73f7`; normal squash merge `ce473b88d221ef153cbe3dc5a2f721917cbb1f13`. Checked/merged trees both `35005fa951968cd0eaed450caef7dbc211ff264f`.
- Automatic Web deployment `f14a49a1-32a2-469a-8f94-e41019a2d7df` SUCCESS. Public build matches ce473b88; production database/Redis readiness OK.
- Authenticated production at1280×900 and390×844 in Day/Night: Activity20+ visible on fresh arrival before selecting Activity; Closeout1 remains separate. Activity filters can return no matches without changing the tab summary. The number is a capped recent page count, not an exact all-time or unread total.
- Timing/sort selection, keyboard End/Enter, Escape and focus return, nested Filters persistence and outside dismissal pass. Mobile category menu scrolls within320px and stays inside viewport. Activity staff/type menus now200px minimum: names remain readable, right edges228/328 at390px, document width390. No horizontal overflow.
- Open menus: Day white with rgb20,36,58 text; Night rgb17,31,51 with rgb246,248,251 text. Accent count digits retain transparent backgrounds. Header touch controls and compact trigger footprint remain unchanged.
- Original Day appearance, default viewport and unfiltered Active work restored. Private screenshots under `/tmp/db145-controls-release/`; no customer identifiers or screenshots published to GitHub. No financial records, invoices, order statuses, provider actions or importer/collector settings changed.
- C3 contract work resumes separately. No Shop Work redesign is included.
