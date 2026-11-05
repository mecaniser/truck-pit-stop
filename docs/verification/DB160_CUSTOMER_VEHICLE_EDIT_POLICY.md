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
