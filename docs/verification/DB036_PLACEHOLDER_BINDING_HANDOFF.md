# DB-036 truck26 reviewed placeholder binding handoff

Board ID: DB-036, separate placeholder outcome.
From / To: Backend & Integrations to independent Security/QA, then parent Release & Reliability.
User outcome: Track truck26 with its existing local `PENDING-26` reference until a genuine VIN is supplied, preserving its UUID/history and honest Motive provenance.

Scope completed: explicit reviewed binding model/service/operator CLI; immutable driver and telemetry XOR identity; narrow collector allowlist and grounded positive summary reader; current-context projection guards; driver API/frontend additive vehicle identity; focused negative and retention tests. [Contract and activation commands](../contracts/db036-placeholder-binding.md).

Scope not completed: no production binding/config mutation, worker run, PR, push, merge or deployment by this owner. Independent Security/QA, protected CI, source-only final collector proof, migration deployment, exact truck26 mapping activation, fresh driver/location import and signed-in app acceptance remain parent gates. No claim that truck26 is already syncing.

Contract/migration: `177_dashboard_bindings` follows `176_merge_contact_pricing`, adds no mapping or fabricated VIN, and retains exact genuine VIN captures. A separate unmerged maintenance branch also starts from176 with a different177 revision; second-to-land must reparent/retest or add a proper merge revision. Downgrade blocks if reviewed history exists; disable the allowlist and revoke the binding while keeping the current guarded application reader and additive schema. A pre-binding Web/API image is not a safe rollback.

Runtime: mandatory local-runtime preflight completed before implementation in `codex/driver-placeholder-binding`; shared5173 and parent fixture5177 preserved. No8000 or approved local backend config, so this checkout is not served and fullstack local browser acceptance is unavailable. Source-reader live acceptance was supplied by the parent against authenticated Motive, separately from local fixture tests. No production environment copied into tests.

Verification environment: `/tmp/db128-backend-venv`, worktree PYTHONPATH; existing frontend dependencies symlinked solely for tests. Task-owned disposable PostgreSQL15 `db036-placeholder-pg` on127.0.0.1:55448 with a task-owned anonymous data volume, synthetic DB `placeholder_final`. Full empty-database Alembic upgrade to177 passed. PostgreSQL retention/XOR/FK/unique-active/downgrade-history test passed1/1. Shared PostgreSQL instances are untouched. Disposable database may be reused read-only by reviewers; tests that downgrade need a new empty database and full migration to177.

Owner verification: 233 focused Python tests pass (driver capture/import/projection, binding/source-evidence boundaries, telemetry, durable journal and fleet/process runner suites); 61 Node collector/reader regressions pass; 44 frontend driver/detail/binding tests pass; TypeScript and changed-source ESLint pass. PostgreSQL1/1 and full migration upgrade pass as above. Logs remain local/private under `output/`; no raw source or sensitive data is committed. Initial synthetic SQLite idempotency assertion compared aware and naive representations of the same timestamp; the test now compares UTC values and passes, with no production logic workaround. The latest Ruff reports one pre-existing FURB162 on the unchanged timestamp `Z` normalization; changed Python checks pass with only that rule excluded.

Known risks / return conditions: Reject any unsupported source layout, ambiguous/mismatched identity, source outside binding interval, revoked binding replay, real VIN, inactive tenant/admin/vehicle or changed membership. A source-only initial approval capture cannot be imported after activation because it predates the new binding. No arbitrary expiry is imposed. Send any boundary/runtime failure to Backend & Integrations with exact reproduction; do not ask the user to regress it.


## Independent gate return and owner correction

Independent review at995c19d8 returned NO-GO for shared-directory fleet eligibility ordering (`output/independent-binding-gate/test_independent_scope.py`, line19). The correction moves stable request filtering before no-VIN binding resolution. It preserves all live checks for eligible requests and preserves verified real-VIN invalidation. Affected binding/driver/fleet/journal/process suites pass105 tests. The exact independent reproduction passes1/1 with the backend fixture plugin (its initial inclusion outside the backend test directory lacked `db_session`; the corrected `-p tests.conftest` invocation passes). Changed Python lint and diff checks pass. Added tests exercise three approved scopes through the actual runner and four revoked/changed eligible-binding commit/readback cases. Await independent re-review on the correction commit; no release approval is claimed.


## Rollback guidance gate return

Independent review reproduced unsafe prior-application rollback (`output/independent-binding-gate/test_independent_rollback.py:23`): prior-main0ae7534f projects retained revoked15mph telemetry as moving because it ignores binding identity. The current guarded reader suppresses it. Corrected contract and migration failure messages now require retaining the guarded application, models/schema and all immutable history while disabling the allowlist and revoking the binding. No old unguarded Web/API restoration is permitted. Forward fixes must retain projection guards; an alternative compatibility strategy requires separate review. Added moving-speed revocation coverage alongside stopped-speed coverage for the supported current reader;25 binding tests, changed Python lint and diff checks pass. No production reader logic changed: the existing guard already rejects revoked captures. The historical unsafe-reader reproduction is intentionally retained as evidence and is not “fixed” by altering stored history.

## Independent gate accepted

Independent Security and local QA GO on `c364f35516f18d3c82e1b7f5351d0c42697395dd`: both cross-fleet eligibility and unsafe-reader rollback findings are closed. The reviewer independently passed35 final checks, with prior205 Python,44 Node,4 frontend identity and fresh PostgreSQL migration/retention proof remaining applicable. Review receipt is retained privately at `output/independent-binding-gate/review-c364f355.json`. This is local gate approval only; protected CI, coordinated merge/deployment, fresh source evidence, reviewed activation, post-activation imports and authenticated UI acceptance remain required.

## Actual manual source proof

After the shared browser was handed back, the parent captured real company checks and two fresh truck26 summary snapshots on2026-10-16. The exact final `summarySnapshot` function ran read-only through the supported CUA CDP fallback; its hash is `e74410c9d13349f38f14eaa86b2b0110f931fa62e112fc0974069c647e47583d`. `summaryIdentity` and `sameIdentity` accept both snapshots as the exact provider vehicle with null VIN and `not_displayed`; timed-out earlier calls contribute no proof. Summary timestamps are19:47:46.813 and19:49:02.130UTC, bracketed by observed company checks. The retained source envelope SHA256 is `c57313e8a35d39dda9c7c691280f56ece047e871f0f9c8a646fd62ba369a63fa`.

Independent review recomputed every raw-file hash, reran both final parsers and the production evidence validator, and returned source-proof GO. The existing contract permits this genuine manual form as an alternative to untouched collector source.json before binding creation. Evidence must still be within two hours immediately before activation (current cutoff21:49:02.130UTC); recollect if needed. No binding is active yet. Fresh full driver/location collector canaries after effective_from remain mandatory. Raw source files and the review stay private under output/.


## Driver display copy follow-through

Parent signed-in acceptance found internal profile-state wording still next to the driver. Removed the redundant Truck details role row and only the “Legacy contact” prefix from saved-contact selection. Name/fallback, phone, vehicle count, Assign/Change driver and Create profile actions remain. Updated the existing assignment locator and removed its obsolete detail-label assertion while retaining managed-driver/Motive identity separation assertions. No binding code, API contract or data changed.

Mandatory runtime preflight atc4b091d9: this branch is not served;5173 PID27324 belongs to motive-driver-records,5177 PID38102 belongs to driver-identity-timeout-retry, and8000/approved local backend config remain absent. Both other listeners were preserved. Eleven affected assignment/detail tests and TypeScript pass. TruckDetail and both touched tests lint clean; FleetModals retains ten pre-existing explicit-any violations and two refresh warnings, with no new errors in baseline-aware comparison. Parent owns signed-in desktop/mobile deployed-copy acceptance; this local candidate is not claimed visible or deployed.

## Release-base integration

On October16 at20:40UTC, integrated released popover PR561/main `c0e0dcb8` into the reviewed binding candidate `74aa1dac`. Only appended project-board histories conflicted; both were retained. Every non-document binding/copy path from the reviewed candidate remains byte-identical. Migration177 SHA256 remains `a6eeeb8e58235dddcdffcec4bf2ecc8306b995267311440b2966b9bd3cd1ddf2`. Protected CI on the final combined revision remains required.

Fresh local-runtime preflight confirms this checkout is not served:5173/PID27324 belongs to motive-driver-records and5177/PID38102 to driver-identity-timeout-retry. Backend8000 and approved local backend configuration remain absent; Vite targets127.0.0.1:8000. Existing listeners and databases were preserved. This is source integration and isolated test evidence, not local full-stack browser acceptance.
