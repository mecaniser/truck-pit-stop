# DB-146 / C3 implementation receipt

Status: In progress. Backend & Integrations accountable; Architecture contract owner. Branch `codex/c3-truck-issues-implementation`, base8b611ea2. [Contract](../contracts/db146-truck-issues.md), [merge compatibility](../contracts/db146-vehicle-merge-compatibility.md).

## Runtime preflight, 2026-10-30

Approved canonical environment symlinks; fresh isolated localhost database `truckpitstop_db146_c3` created and normally migrated to existing sole191, no existing data reused or changed. Frontend5173 PID83612 and backend8000 PID82927 exact checkout cwd; frontend runtime branch/SHA stamped; direct/proxy database/Redis readiness passes. Local browser reaches signed-out login; no signed-in C3 acceptance claimed. No other services stopped or changed. Root owns runtime, frontend and docs; Backend owns additive metadata source/tests. Financial records, invoices, selling prices, stock/time/status source, providers and ETS importer remain untouched.

## Gates

Architecture source compatibility confirmed; implementation, focused tests, PostgreSQL migration/races/retention, independent QA/Security, actual Day/Night desktop/mobile and protected release gates remain pending.

## Fictional local fixtures

Two synthetic tenants, five staff identities, two customers, three trucks and two zero-value draft reference visits; zero invoices, labor or parts. Reserved example.com login identities satisfy the existing EmailStr validator. Normal owner sign-in succeeds. Private `/tmp/db146-local-pre192-final.json` freezes all186 existing tables/19 rows before the additive C3 migration; predecessor receipt retained. Backend destructive tests use a separate disposable database. No production fixtures or financial source changes.

## Source and runtime evidence

118 focused backend/compatibility checks and9 real PostgreSQL tests pass in separate processes. Existing combined SQLite/PG pytest UUID wrapper omits coltype; shared harness unchanged, split suites verified.207 prior migrations byte-identical;208graph nodes, sole192 with no missing parents. Independent Security source GO manifest2e48616013e0e4d313f2f3b30f0fc6a3865acc9220cfbb1ae1fabaa1cfb796bc; release acceptance separate.

Runtime normally upgraded191→192, four metadata tables added. All original source tables retained; exceptions are alembic_version and one ordinary user appearance preference created by fictional UIlogin, not migration/source correction. Backend8000 PID88444 exact C3cwd, frontend5173 PID83612 unchanged; approved env symlinks, isolated localhost truckpitstop_db146_c3, direct/proxy readiness pass. Actual Truck issues section rendered before repair history; create withoutRO, dirty keep/discard, reason validation and resolve/reopen succeeded on fictional metadata. Night portal color and mobile calendar clipping found during browser QA and returned to Frontend; corrected-source acceptance continues.

## Final local acceptance, 2026-10-30

126 focused backend/compatibility checks (118 plus8 independent-QA gap cases),9 real PostgreSQL checks and111 frontend assertions (29C3,36recommendations,14customerworkflow,4merge,28workstation) pass. Final TypeScript, scoped lint and production build pass. Existing workstation jsdom requires command-scoped empty VITE_MAPBOX_TOKEN; no configuration change.

Actual CUA fictional Day/Night1280desktop and390mobile accepted: no-RO create; eligible staff/priority menus; literal HTML text; unscheduled/date/today; dirty keep/discard; state reason validation, resolve/reopen; same issue across visits; end/relink preserves history and leaves issue open. Night portal contrast and mobile calendar clipping were found and fixed, then visually rechecked. Linked-visit close initially lost origin; narrow auth-scoped C3 navigation now restores exact starting RO or customer/truck URL and issue-row focus, verified on390. Existing DB107 navigation remains unchanged. Screenshots private under /tmp/db146-browser.

Read-only local post-browser retention:184 of186 prior tables byte-hash identical. Only migration version and ordinary user appearance preferences differ; four additive tables contain2fictional issues,2links(one ended),8events and8request receipts. Zero invoices; financial/RO/labor/parts/stock/time/provider source unchanged. Targeted independent Security GO also covers final navigation.

Fresh production baseline captured with REPEATABLE READ READ ONLY at sole191:31source cohorts,26,315rows, digest302d8d8d244c6f27507055763bd35fe1da8c327f390fa51a337f864c13e46209. Private per-identity evidence under db146-release-20261030. No production C3 writes performed. Protected CI, release and actual production acceptance remain pending.

## Reviewed integration

Independent QA GO covers source, real PostgreSQL checks, actual local Day/Night desktop/mobile journeys and retention. Released main fd0a8a14 (exports/badge) integrated as08011ccb;82 focused C3/export integration checks and production build pass. Released communications main48058a8f then integrated as5662530f; C3 application/test/migration bytes unchanged and both board histories preserved. No migration join required: sole192 remains additive from191, all207 old migration files unchanged. Final integrated build/CI follows.
