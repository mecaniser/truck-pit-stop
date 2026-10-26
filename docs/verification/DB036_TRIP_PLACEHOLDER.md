# DB-036 PENDING-26 trip identity

## Authorization and ownership
User explicitly authorized PENDING-26 collection because a VIN is not yet available. Backend & Integrations owns implementation after Architecture contract. Independent diagnostic_gate owns QA/Security. No invented VIN, generic unit-only lookup or membership backdating is authorized.

## Known evidence
Existing reviewed binding: Motive company KT8934277 / 77 CARGO LLC, provider vehicle 5981300, local vehicle f946f5da-f9f4-4960-8670-5ca87467d879, reference PENDING-26. Current contract supports telemetry and drivers; trips still require VIN. Earlier fully loaded summary and vehicle-admin observations established no displayed VIN. Current priority trip backfill excluded unit26, with missing-directory and unverified-provider representations of the same unresolved truck.

Independent read-only production evidence confirms binding `b098e859-54f0-4999-8255-9142073a2ec3`, reviewed/effective from `2026-10-16T21:42:51.108657Z`, with no end, revocation or deletion. Membership begins `2026-10-07T22:09:21.510523Z`. The binding boundary governs the earliest eligible trip interval; no earlier history is admitted by this authorization. Redacted evidence: `/tmp/db036-unit26-binding-proof.jsonl`.

## Acceptance
Use exact reviewed tenant/company/provider/local-vehicle binding with positive no-VIN source evidence. Preserve tenant authorization, active membership and actual historical bounds, immutable trip identity, unique departure deduplication, exact-attempt recovery, readback and unchanged replay. Reject wrong tenant/company/provider/local vehicle, ambiguous or revoked binding, real-VIN conflicts, stale/partial source and unauthorized historical dates. Ensure trip read projection supports the explicit identity kind. Independent tests and exact release/runtime evidence required.

## Runtime preflight
New worktree motive-trip-placeholder, branch codex/motive-trip-placeholder, base a6a6af962a851b077ddb8d46a6a20faedc97e561. No 5173/8000 listeners. Runtime switch dry-run blocked: backend/.env and frontend Vite missing. No local services, production credentials or customer data copied. Isolated fixture verification planned.

## Architecture contract accepted
Add nullable reviewed-binding trip provenance with a genuine-VIN versus binding XOR constraint and tenant/vehicle/membership composite foreign key. Preserve existing VIN digests and unique tenant/provider/departure keys. Public/manual TripImport and correction contracts remain genuine-VIN-only; only the explicit private worker path accepts the exact reviewed binding. Positive loaded-summary no-VIN evidence is required before/after each report; unknown/timeout/real-VIN conflict fails closed. Every write, replay, recovery and readback revalidates authorization, exact company/provider/vehicle/binding and current membership. Full trip intervals must fit both original membership and binding effective intervals; no historical backdating.

The guarded read query must enforce binding validity in SQL before pagination, totals and imported bounds, with explicit identity provenance. Revocation, expiry, placeholder changes, real VIN, deletion or wrong identity suppress affected bound rows. New null/default fields must not alter existing genuine-VIN immutable payloads.

## Required release order and rollback
Migration and Web/read-model guards precede bound collector activation. Then release the exact trips image, capture/import within allowed intervals, independently verify persisted source/receipt/readback/replay and signed-in Fleet projection. After any bound rows exist, retain migration and guarded readers on rollback; disable bound collection rather than delete or rewrite historical records. Downgrade must reject existing bound rows.

## Owner verification
Source implementation passed 141 focused Python tests and 33 Node fixtures; diff whitespace checks passed. Thirteen new cases cover bound import/readback/replay, strict public input, revocation and foreign-tenant visibility, source-proof bracketing, identity/interval changes, stable coverage hashes across new observation timestamps, migration DDL and downgrade rejection. Full source proofs remain receipt-hashed; only volatile observation timestamps are omitted from mapping-scope identity.

Actual PostgreSQL delta migration189 applied successfully in fresh isolated synthetic database `trip_placeholder_owner_20261026` on `db036-placeholder-pg`. Both constraints validate. Synthetic bound insertion succeeds; mixed VIN/binding, nonexistent binding, null absence proof and wrong provider are rejected. Downgrade refuses existing bound history. This verifies the delta against predecessor trip-table shape, not the entire migration177–188 chain. Existing databases preserved; no production data or credentials copied.

## Independent QA/Security
GO for the reviewed source. Independent gate passed 104 Python tests and 11 Node identity cases. PostgreSQL constraint validation confirmed; migration189 follows188, and migrations177–188 do not alter the trip/binding target shape. Private/public contract separation, complete interval checks, replay/readback, source proof, tenant isolation and SQL aggregate filtering were reviewed. Observation timestamps do not invalidate stable mapping scope; binding identity and intervals do.

## Status
Independent source QA/Security GO. Protected CI, migration/Web release, bound collector release and production acceptance remain pending.
