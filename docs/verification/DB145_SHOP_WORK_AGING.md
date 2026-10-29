# DB-145 / A2 — Shop Work aging verification

Status: PR676 merged and deployed, 2026-10-29. Signed-in production acceptance found a Night empty-state contrast defect; focused follow-up in progress. Not Done.
Owner: Frontend & UX. Contract: `docs/contracts/db145-shop-work-aging.md`.

## Local runtime alignment

- Branch `codex/a2-shop-work-aging`, base81fac6dc, intake commit2f118625; contract/source changes uncommitted during development.
- Startup skill read and controller dry-run performed. Controller initially rejected dirty docs, then identified absent worktree env/dependencies. Intake docs committed; approved canonical backend/frontend env files symlinked, dependencies installed with npm ci. Existing configuration values were not copied or changed.
- Explicit isolated localhost PostgreSQL database `truckpitstop_db145_a2` created empty and normally migrated through existing source migrations to191_fuel_reviewed_binding. No new migration. Initial invoices0/users0. Other databases/volumes untouched.
- API8000 initially PID56063, restarted as own PID58770 after source changes; source cwd this worktree/backend, frontend5173 PID56097 cwd this worktree/frontend, explicit proxy8000. Both listeners were unbound before start. Direct and proxied /health/ready200 database/Redis OK.
- Private launcher overrides only its DATABASE_URL database name to the isolated database using approved local credentials. No workers/collectors/providers started. Existing env and collector configuration unchanged.
- Browser opened exact localhost5173 login successfully. Fictional local fixture shop/users/repair orders prepared only in this new database; no invoices or payments created. Signed-in changed-journey evidence recorded below.

## Automated and independent gates

- Architecture frozen v1 GO. New read endpoint/service/schema only; no migration or source writers.
- Independent QA:34 backend tests and32 frontend tests passed. Backend includes scope, status/ownership, missing/invalid clocks, API422/403, literal search, complete53-row counts/filter/pagination and mechanic/tenant negatives.
- Backend owner additionally passed13 existing daily-workset/Zelle regressions and3 actual PostgreSQL projection checks in a separate disposable database.
- Changed-source ESLint and TypeScript passed. Final npm production build passed after final CSS/cache/navigation fixes; existing chunk-size warning only. git diff --check clean.
- Independent Security GO for tenant/role/job scope, provenance veto, SELECT-only/no-autoflush path and minimized response. Final frontend cache/session and work_view review retains Security GO. Backend service fingerprint c551f1d6a6a2, schema2653d502084f, endpointb52d3c2ab23b.
- Independent QA caught Closeout/Payment review return-context loss; explicit work_view origin and regression resolved it. Root caught Night select contrast and mobile search flex-basis310px gap; CSS fixes reverified, final CSS fingerprint c21a7412b400.

## Actual local browser acceptance

Permitted CUA on signed-in fictional owner, exact localhost5173/frontend to8000/API in this checkout. This is local synthetic acceptance, not production or physical-device acceptance.

- Day and Night,1280x900 desktop and390x844 mobile viewport: active counts/categories, clocks, filters and rows readable; document width equals viewport, no horizontal overflow.
- Ten fictional repair orders:7 active jobs,1 separate native unpaid closeout,2 ETS orders excluded. Active counts include Parts1, Approval1, Technician1, Review2, In progress1, Preparation1; overdue1 and Unknown2.
- Wait timing Unknown returns only2 missing-clock records. Parts/overdue each isolate the expected existing job. Empty search displays0 and explicit empty state.
- Existing-workspace drill-down via keyboard and mobile; closing the workspace preserves Parts filter. No hold, status, invoice, payment or source action invoked.
- Unpaid completed/invoiced own-truck analogue updated today remains Closeout / Payment Due; its update does not fabricate an active wait. Payment-review roundtrip covered by focused component regression rather than a real payment fixture.
- Native Night dropdowns now use light text on dark background; mobile search field44px, view labels single-line. Screenshots retained privately under /tmp/db145-browser-proof (fictional records only).
- Independent QA reviewed screenshot evidence and adopted parent interaction receipt: local journey QA GO.

## Retention and release boundary

Private read-only repeatable-read pre/post hashes across13 source tables (10 existing fixture rows) match exactly. Invoices, payments, settlements, ledger, refunds, overpayments, time sessions/audit, parts and inventory remain empty/unchanged; existing repair orders unchanged. No production data touched, no invoices created, no importer/provider/collector invocation or configuration changes.

Protected PR CI, normal merge, deployment and actual production acceptance remain open. This receipt does not claim A2 Done; ETS parity remains6/30 complete. Held B4 importer and later C3/R3/A3/S1 remain unchanged.

## Compact layout refinement, 2026-10-29

The user requested screen-space priority before merge. Impeccable context/distill/polish and Emil Kowalski interaction guidance informed an existing-contract UI refinement: compact header, search and Filters on one row, single desktop category strip/mobile selector, actionable Unknown count, and timing explanations in a popover. Payment closeout and all projection semantics remain unchanged.

- 34 focused frontend tests, changed-source ESLint, TypeScript and production build passed. Final category-strip CSS correction passed all 13 panel tests. Impeccable manual detector returned no findings.
- Actual signed-in fictional owner CUA: Day/Night desktop1280x900 and mobile390x844. First job begins at280.58px desktop (previous378px) and338px mobile (previousapproximately760px). Desktop exposes six complete rows; mobile exposes two complete rows and the next job. No horizontal document overflow. Final category strip does not clip or vertically scroll.
- Filters opens with click/Enter; Escape dismisses and restores trigger focus. Timing help dismisses outside. Unknown filters exactly two missing-clock jobs. Mobile category selection retains correct Parts count and row; controls remain accessible with 44px mobile targets. Screenshots: private /tmp/db145-browser-proof/compact-*.jpg, fictional data only.
- Read-only local fixed source cohort remains unchanged across13 tables/10 rows. Production baseline captured read-only across13 tables/20,549 rows at schema191_fuel_reviewed_binding; private baseline SHA256 7d9ab5234e2937c860c2da4f3ce784b57280b81dcb038cc96af77bd56b4c1654.
- Prior candidate ccd5e291 passed CI40943971060. Refined candidate requires fresh protected CI before merge. No deployment or production A2 acceptance claimed here.

## Released main integration before final CI

Main advanced to44575250 (PR675 payment refresh) during the compact pass. The only conflict was the board prepend; both histories were retained. All main payment-refresh source and tests are retained verbatim, and all A2 application/test paths are unchanged from the reviewed compact candidate. No new migration or financial write is introduced by this integration. Independent compact UI QA GO includes13 rerun panel tests and reviewed screenshots. Final exact-head protected CI remains the merge gate.

## Merge and deployment handoff

A second clean integration retained released inbox main e74efc5f without changing A2 paths. Final candidate9e31f861664b570bd167c9723b42145b37070857 passed all six protected checks plus dependency preparation in run40950275579. PR676 normally squash-merged at2026-10-29T20:42:40Z as3c231850ba34acc8a0939446fc9928a2f996e4cd. Checked and merged trees equal5d6341ec16dda6543a2be1e6d8b13977aedbbd57. Automatic Web9c8c0a7b-2b67-4025-922f-25deef230077 and Worker397be24d-c771-4f74-a621-6891feff5ac4 building exact merge; production acceptance pending.

## Exact production deployment and read-only retention

- Web9c8c0a7b-2b67-4025-922f-25deef230077 and Worker397be24d-c771-4f74-a621-6891feff5ac4 both SUCCESS on3c231850ba34acc8a0939446fc9928a2f996e4cd. Public /build-version matches; /health alive and /health/ready reports database/Redis OK. No separate main-push workflow is configured; protected PR run40950275579 is the integration gate.
- Schema remains191_fuel_reviewed_binding. Private fixed-identity postrelease hash receipt covers13 tables and20,550 current rows against20,549 baseline rows. Post receipt SHA25647ad16320f3ecc48b095609867dc6ff1155980cdef206cc5161657c3cce6b72a.
- Retention is not reported as wholly unchanged: one settlement changed and one linked ledger event was added. Read-only investigation identifies payment_failed at2026-10-29T20:30:23.739663Z, changing pending to unpaid with zero confirmed-principal delta. It predates A2 merge20:42:40Z and its deployment; the settlement update timestamp matches the event. Other baseline source rows match, with no new invoice/payment/time/inventory rows. Private evidence retained under the release audit directory; no corrective write attempted.
- Actual production IAB session expired and redirected to login. Standard organization sign-in requires user authentication; a concise sign-in request is pending. No postrelease production browser acceptance claimed. Local compact Day/Night desktop/mobile proof remains valid but is not a substitute. ETS importer held, no invoice creation or financial/status/provider/collector actions from A2 work.

## Signed-in production acceptance and Night correction

Actual NC owner Chrome acceptance on the released A2 surface, using a separate QA tab and existing records only:

- Day desktop1280x900 and mobile390x844: zero active jobs, two payment-only closeout jobs, four Closed Today. These are observed current counts, not fixture or financial reconciliation claims. Existing payment-only work stays out of active aging.
- Unknown0 remains actionable; timing help explicitly explains missing reliable wait starts. Filters opens, Escape dismisses and returns focus, timing help dismisses outside. Mobile filters fit within the viewport; compact labels and layout do not overflow visually.
- Production currently has no active rows. Populated clock/Unknown/category/drill-down coverage remains the separately recorded local synthetic evidence; no production records were fabricated.
- Night mobile revealed the inherited legacy empty-state CSS used hard-coded Day foregrounds. This failed final acceptance. Original Day appearance was restored through the normal UI; user payment workspace and draft were not touched.
- Fast UI correction on `codex/a2-night-empty-state`, based on releasedmaincf11290e, adds only two scoped CSS rules using existing workspace foreground tokens. Empty/loading/error copy inherits the correct theme; no API, financial/source, spacing or importer change.
- Mandatory local runtime re-aligned on the new branch: frontend5173 PID87012 and backend8000 PID87015 both this worktree, explicit localhost truckpitstop_db145_a2, approved env symlinks preserved. Direct/proxy readiness passes; rendered source verified. No migration/reseed. Local13-table/10-row source cohort still matches.
- All13 existing panel tests, TypeScript and production build pass. No JavaScript changed; CSS syntax is validated by the build. Actual signed-in fictional-owner Day token readback and Night desktop1280/mobile390 screenshots verify readable empty text: Night title rgb(246,248,251), secondary rgb(184,197,213); no horizontal overflow. Local preview is aligned and browser-verified. Protected follow-up CI/deployment and final live Night verification remain required.
