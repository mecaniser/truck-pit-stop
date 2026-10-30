# DB-146 / C3 implementation receipt

Status: **Done — merged, deployed and production accepted, 2026-10-30.** Backend & Integrations accountable; Architecture contract owner. Earlier sections retain the implementation and gate history. Branch `codex/c3-truck-issues-implementation`, base8b611ea2. [Contract](../contracts/db146-truck-issues.md), [merge compatibility](../contracts/db146-vehicle-merge-compatibility.md).

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

Final released-main integration5662530f production build passes. Independent integration QA confirms all incoming released files retained, reviewed C3 application/test/migration blobs unchanged. Final source candidate includes documentation-only receipt updates. Runtime integrated08011ccb frontend95285/backend95302 exact cwd, same isolated192 database, direct/proxy readiness and actual Night desktop issue rendering verified; later communications integration is source-disjoint and final-build checked.

## Initial CI correction

PR698 candidate97aed6f1, workflow41119909254: the existing workflow was manually dispatched after no automatic PR run appeared. Migration/backend/full backend/frontend critical-build/Playwright pass; full frontend reports15 failures across force-void and void-revision tests because their ThemeContext mock omits appearanceTokenRecord. The C3 dialog legitimately consumes the exported theme function. Correct the test mocks while retaining their existing mocked useTheme behavior; no production source correction or relaxed assertion. New exact-head CI is required before release.

Correction verified: both mocks now preserve real ThemeContext exports and provide DEFAULT_APPEARANCE. All45 focused checks pass (13force-void,3void-revision,29C3), scoped lint passes. No production source or test assertion changed.

## Protected merge and deployment

Corrected candidate93c55d2d62941c667540c04630f158e234d49414 passed all seven jobs in41121811152, including the full frontend suite. PR698 normally squash-merged18255c03dac148a3326ca95d334cda03365139a6. Both trees equal891138ef3538ad19fb328cd90267fdd539134e04. Automatic Web7cb8095e-97fb-4401-9fac-485aa9e36960 started on that exact merge. Production acceptance remains pending. Owned local frontend95285/backend95302 stopped gracefully after exact cwd verification; no live local preview claim.

## Final release acceptance — 2026-10-30

PR [698](https://github.com/mecaniser/truck-pit-stop/pull/698) passed all seven protected checks in [41121811152](https://github.com/mecaniser/truck-pit-stop/actions/runs/41121811152) on `93c55d2d62941c667540c04630f158e234d49414`. Full frontend: 1,934 passed across 185 files. Full backend: 4,156 passed, 415 skipped. The initial failing run above is not counted as release success; the test-only mock correction passed fresh independent QA before the final run.

Normal squash merge: `18255c03dac148a3326ca95d334cda03365139a6`. Checked and merged trees both equal `891138ef3538ad19fb328cd90267fdd539134e04`.

| Release gate | Observed result |
| --- | --- |
| Automatic Web | `7cb8095e-97fb-4401-9fac-485aa9e36960`, SUCCESS at exact merge SHA |
| Automatic Worker | `d22a85d7-81f1-4bb8-bdd6-8b7d8e868101`, SUCCESS at exact merge SHA |
| Served frontend | `/build-version` matches exact merge; built at 2026-10-30T20:26:45.841Z |
| Runtime | `/health/ready` database and Redis OK; sole migration `192_vehicle_issues` |
| Fixed source retention | 31 cohorts / 26,315 existing rows unchanged; zero new rows in those cohorts |
| Production C3 metadata | Issues, links, events and request receipts all remain zero after browser QA |

Production acceptance used an actual signed-in NC owner and existing customer/truck and paid native visit. Day and Night at desktop 1280 and mobile 390 passed: compact Truck issues placement, separate existing RO recommendations, readable open priority/staff menus, blank date shown as Not scheduled, full inline mobile calendar and footer without horizontal overflow, required description validation, unsaved draft Keep editing and Discard. Existing RO placement also passed on desktop/mobile. No issue Save, state change or visit-link mutation was submitted in production. Mutation lifecycles, exact issue reuse, link/end/relink and return navigation were exercised with fictional local fixtures as recorded above. Day appearance and default viewport were restored.

Deployed read-only handlers using existing actual identities returned admin 200, customer/fleet manager/mechanic/super admin 403 and foreign vehicle 404 under REPEATABLE READ READ ONLY with rollback. This is deployed-handler proof, not authenticated nonowner browser evidence. No existing driver/receptionist identity was available; the selected owner identity had no truck, while the actual signed-in NC owner browser supplied the positive owner acceptance. Automated role and tenant cases remain the full negative coverage.

Private fixed-cohort baseline SHA-256: `302d8d8d244c6f27507055763bd35fe1da8c327f390fa51a337f864c13e46209`. Post-browser receipt SHA-256: `ff6d3f76d1dbf5d694d2954b54905f389d17cde91c3222b6e7228256a37b45eb`. The receipt digest changes with schema/receipt metadata; all fixed source row hashes match. Private identity-bearing receipts and screenshots remain outside Git.

No financial, invoice, payment, settlement, credit, selling-price, stock, time, attendance, order-status, provider, outreach or collector changes were made for acceptance. The ETS importer remains held; Shop Work redesign remains separate. No unresolved C3 release gate remains. Tracker advances to 8/30 completed, with R3 next under its own contract.
