# DB-036 reviewed source isolation

Owner: Backend & Integrations. Board item: DB-036. High-risk worker follow-up to the protected truck-26 binding release.

## Trigger and contract

On October 16, the post-activation driver run `de0a5dc1` committed and verified the primary fleet, including truck 26's Motive safety score. During the second fleet's source collection, Motive's reviewed vehicle page disagreed with its requested identity. The collector stopped before importing that fleet. One controlled retry (`16318503`) hit the same identity error in the primary fleet; it also imported nothing. Existing verified journals and captures were retained. The location collector separately recorded truck 26 as `source_changed_during_capture` in two complete runs; an unrelated incomplete location run imported nothing.

Only an exact allowlisted provider vehicle whose **pre-summary** identity page returns `vehicle_identity_changed` may be recorded as an unavailable row. The row keeps its exact directory provider driver/vehicle/unit, has no VIN, no score or other content, and no claim of a verified vehicle. Company identity, complete directory, assignment after-read check, performance ranges and all other rows still must pass. A new VIN, changed post-summary identity, company mismatch, changed directory, invalid configuration or unrelated vehicle error still fails the whole import. The normal importer and tenant/current-membership gates are unchanged. No schema, API or frontend contract changes.

Acceptance includes a source unit test for the narrow fallback and its negative cases, importer test showing an unavailable reviewed row creates no capture or binding change, focused worker tests, protected CI, independent Security/QA review, then a fresh all-three-fleet production canary with source/capture/projection parity. A skipped truck 26 reading must show an honest unavailable state until a later verified observation; the existing placeholder remains. Keep the saved contact name and phone as driver contact details, while omitting the internal “Local contact” label everywhere.

Rollback: disable this collector image or deploy a reviewed successor while keeping the binding-aware guarded Web/schema/history. Do not roll back to a pre-binding reader. Existing schedule, allowlist, mounts and fleet scopes remain unchanged.

## Local runtime preflight

October 16, 22:02 UTC: intended checkout `codex/driver-source-isolation`, HEAD `d67d4da4`, initially clean. Frontend 127.0.0.1:5173 belongs to PID 27324 in `motive-driver-records`; backend 8000 has no listener. This checkout has no approved `backend/.env` or `frontend/.env`; frontend Vite proxy targets local backend. The other task's listener and local databases were preserved. This is backend-only implementation with offline tests; local full-stack/browser readiness is blocked by absent approved backend configuration. Production browser acceptance remains separate.

## Source-isolation review and local checks

Independent Security review: **GO**, with protected CI and production canary remaining release gates. The reviewer confirmed the exact reviewed provider’s pre-summary `vehicle_identity_changed` leaves an unavailable row without score content, then reaches directory equality, performance-range equality, final company verification and assignment after-check. Non-reviewed/other errors and conflicting or changed post-summary VIN state still fail closed. The focused database integration test commits another driver’s capture while preserving the truck-26 binding, membership and `PENDING-26`.

Local verification: Node source suites 46 passed; backend binding/worker suites 65 passed. `git diff --check` passed. Changed-file Ruff/Black tools are not installed in the available isolated backend environment; protected CI remains authoritative for those gates.
