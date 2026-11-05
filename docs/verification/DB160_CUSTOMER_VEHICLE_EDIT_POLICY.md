# DB-160 customer vehicle editing and field enforcement

Backend & Integrations is accountable; Frontend & UX owns the shared editor. User authorizes implementation, independent checks and deployment, after PR801's Add vehicle placement release. Architecture reviewed the contract independently before implementation.

## Contract and implementation

Customers may update unit number (50 characters), license plate (20), color (50), and notes. Omitted fields remain unchanged; explicit null clears nullable labels. Both customer-accessible update paths reject VIN, even unchanged/null, vehicle specifications, mileage, equipment type and unknown/privileged keys with422; mixed permitted/protected requests fail atomically. Customer updates do not invoke VIN/NHTSA correction work.

The nested customer PUT preserves direct ownership or active, nondeleted owner/operator links. Direct PATCH preserves its direct-ownership scope. A shared resource guard verifies actor/account/vehicle/relationship tenant identity, excludes deleted accounts/vehicles, denies missing customer identity and driver access, and applies the existing active-fleet restriction to fleet managers. Staff full-update VIN normalization, duplicate checking and NHTSA correction remain available. No migration or new durable edit-history claim.

One editor serves the Vehicles list and Account Vehicles. Row Edit vehicle opens the exact record; VIN is read-only and is never included in the update payload. Errors preserve the draft; pending saves disable controls and do not retry automatically. Saves invalidate Account and portal vehicle caches. Form state is bound to its original authenticated session; Account state remounts on identity/epoch changes and resolves the selected ID only from the current authorized query. Pre-dispatch and post-completion guards reject stale session work.

## Local checks

- Policy HTTP tests first reproduced41 failures/12 passes against the old implementation after fixture correction. Current54 policy HTTP tests pass, including staff correction through both full-update paths.
- Existing identity/NHTSA checks17 passed. Focused frontend67 passed across six files; changed-source lint and production build/typecheck/control checks pass. Existing bundle-size advisory remains.
- Initial independent Security review found an Account editor identity-switch leak and missing pre-dispatch epoch check. Both were corrected with explicit regression tests. Reviewer independently passed53 policy HTTP,14 identity and2 UI probes; final commit-bound gate pending.
- Independent QA has its own synthetic session and is verifying actual PostgreSQL save/reload/cache refresh/restore and desktop/mobile layouts. Final gate pending.

## Runtime and release boundaries

Local5173 proxies8020, frontend and backend serve the same `truck-portal-overview` checkout and `codex/customer-vehicle-edit-policy` branch. Frontend restarted after branch change; API `portal-overview-preview-api` restarted after policy changes, retaining the existing isolated `portal-overview-pg/portal_overview_current` synthetic clone and disabled provider settings. Readiness200 with database/Redis ready. No migration, reseed, production customer edit or provider call is part of acceptance. Raw sessions, fictional credentials and screenshots remain private outside committed evidence.

PR801 release is tracked separately. This editing implementation requires final independent Security/QA, exact-head protected CI, merge and production smoke before Done. Production acceptance will inspect the real read-only form and cancel without saving customer data; write persistence is verified only on isolated synthetic PostgreSQL fixtures. Rollback must consider that the previous version retains the discovered customer VIN enforcement gap.

## Independent gate results

Security GO on implementation commit `2cd2b5994cd85970d5426420b00ffe8a26c0d9cd`, with matching hashes for all seven reviewed security source files. Independent53 policy HTTP +14 identity +2 UI identity/dispatch probes passed. No production mutations. Root's extra nested-staff correction test brings policy coverage to54.

Independent QA functional checks passed against real local PostgreSQL: all four labels saved/reloaded; portal directory refreshed; Account editor parity and cancel; changed/unchanged/null VIN rejected atomically through both routes; failed save retained draft; foreign scope showed no editor;1380/390/320px containment. Exact synthetic baseline labels restored and VIN unchanged. QA found narrow centered text fields caused by shared-control alignment. A local rule in the shared-control layer now stretches editor inputs to their label width; final visual confirmation pending. Security implementation bytes are unchanged by that CSS-only fix.

## Final pre-release gates

Independent Security and QA both GO on `64becfeaf97673bb658f141adddfc96dad31a966`. Security matched seven reviewed source hashes; QA matched eight DB160 implementation hashes to its tested version. The current-main phone-formatting merge changes no DB160 implementation bytes. Root focused frontend checks now72/72 across six files, including that main integration; changed-source lint passed. Root policy HTTP54/54 plus existing identity/NHTSA17/17 pass. Final visual gate confirms full-width inputs align with labels at1380/390/320px. All synthetic values restored; no production mutations. Protected CI and release remain required.

The new54-case backend field-policy HTTP test and both frontend editor/identity test files are added to the existing critical-test manifest, retaining every prior entry. These regressions therefore execute in protected critical gates, alongside the full-suite complement.

## Merge and production deployment

PR806 passed all seven exact-head checks on `cadc7983b843f1598ae90afa25520ee56b37705f`, run42111727998. Critical backend3m30 and full backend6m24 actually executed; frontend critical/build and full suite plus smoke passed. Protected squash merge `215f38aa2a89296491f6b76bb7e244d2b1efe724` completed at21:28:55UTC. Checked and merged backend/frontend/critical-test-manifest trees are identical. Security/QA-reviewed application bytes remain unchanged.

Automatic production deployment `a997fa2d-7bb7-4fd7-ae3d-6415f7985696` started on the exact merge SHA, after PR801 deployment was already SUCCESS and real signed-in Add vehicle smoke had passed. No protection bypass, forced deployment, migration, provider operation or production vehicle update was used. Final deployment/read-only production acceptance pending.

## Production acceptance and closure

Railway deployment `a997fa2d-7bb7-4fd7-ae3d-6415f7985696` is SUCCESS on `215f38aa2a89296491f6b76bb7e244d2b1efe724`. Public `/build-version` reports that exact SHA, built at2026-11-05T21:31:21.671Z. `/health/ready` returns ready with database and Redis healthy.

Signed-in production customer acceptance opened Edit vehicle from its exact list row. VIN is actually readOnly; unit number, license plate, color and notes are editable; pristine Save changes is disabled. At1380/390/320px, document widths equal viewport widths and every form field spans its container. Cancel returns to the vehicle row without submitting. The Add vehicle header action remains separate from row actions. No browser console errors were captured. Private screenshots remain outside the repository; no customer vehicle values, credentials or record identifiers are published here.

Production acceptance was read-only and made no customer updates. Write persistence, negative HTTP enforcement and restoration were verified using isolated synthetic PostgreSQL fixtures, with independent Security/QA gates above. No schema migration or provider operation was introduced. Rollback signals are newly failed customer saves, broken ownership isolation, or acceptance of protected fields; prefer a corrective release or safe rejection over restoring the previous VIN enforcement gap without review. No such failure was observed. DB160 is Done; Backend & Integrations remains accountable.
