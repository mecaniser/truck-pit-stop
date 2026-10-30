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

Pending protected CI, normal merge, automatic Web deployment and signed-in production changed-journey acceptance. No Done claim before those gates.
