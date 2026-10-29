# DB-145 / A2 — Shop Work aging verification

Status: implementation and local acceptance GO, 2026-10-29. Protected CI and release pending; not Done.
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
