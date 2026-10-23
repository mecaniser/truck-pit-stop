# DB-036 driver startup fix

Owner: Backend & Integrations. High-risk lane; independent QA/Security required.

## Evidence and acceptance

Production natural execution d699694f-ad66-47fa-86b8-cfdf0651f1af on diagnostic deployment d23b25cc-e08e-4b01-b736-7977a69c9033 failed before driver_source_start. The top-level handler hides the underlying exception as invalid_fleet_configuration.

Read-only configuration validation on October 23: three valid fleet targets, database journaling, DATABASE_POOL_SIZE=2 and DATABASE_MAX_OVERFLOW=1; timeout unset, source default 10 seconds. No secret values retained. Current run_fleets acquires a distinct journal connection per target then opens a separate authorization session: third fleet consumes the last available connection before authorization needs a fourth. Reproduction and regression evidence pending.

Acceptance: reproduce original resource exhaustion; batch journals must retain sorted per-fleet locks, immutable identities, independent receipts and atomic source preparation while preserving room for application sessions; failures release all locks; denied tenants never launch collection. No guard bypass, source/journal deletion, retry, credentials/config changes or production execution.

## Local runtime preflight

October 23: /private/tmp/db036-driver-startup, codex/driver-startup-fix, base 8a31cea173ce58170a5e40a7be0701b49a4fc082. Clean worktree at intake. No host listeners on 5173/8000. Existing unrelated Docker services preserved. Backend-only offline worker tests; no local browser journey or provider-backed process started, no environment files copied. Full web runtime alignment is blocked by absent local configuration and is unnecessary for offline worker tests; no rendered/local UI claim.

## Proposed fix contract

Hold all batch journal locks on one checked-out PostgreSQL session, in stable key order. Return separate Journal objects in fleet input order; each retains its own worker key, identity, binding check and advisory-lock ownership validation. Authorization/import sessions remain separate short transactions. Keep single-fleet database_journal compatible. All held locks must release on startup/authorization/recovery/projection failure; invalidate a connection whose lock cleanup fails. No schema, schedule, credential or import-contract changes.

A shared session reduces held journal connections from N to one without increasing the configured pool. The historical exception was suppressed; this investigation identifies and reproduces the deterministic resource defect in the actual configured topology, not a recovered production traceback.

## Security remediation boundary

A separate private rotation plan has been refreshed with Railway's October23 preliminary report, populated consumer inventory, provider/database/session/encryption batches, coordinated deployment requirements, old-key revocation and read-only validation. No secret values included. Executing it requires explicit authority for named credential batches, consumer deployment windows, downtime/sign-out and encryption migration; the current no-credential-change/no-deploy instruction remains binding. Security exposure is not established as the cause of this resource defect.

## Reproduction and verification

A new isolated local PostgreSQL15 container (db036-driver-pool-fix, loopback55459, synthetic database driver_journal_pool_fix) reproduced the original retention order with pool_size=2/max_overflow=1: the third retained journal causes SQLAlchemy QueuePool TimeoutError when authorization requests its connection. Test timeout shortened to 0.1 seconds; production default remains 10 seconds. The same real server verifies shared-session batches of three and nine fleets, competing lock exclusion, immutable per-fleet source/receipt identities, atomic source preparation, non-primary lock-loss rejection and cleanup after identity mismatch or partial lock acquisition failure.

Focused owner suite: 127 passed, including two real-PostgreSQL cases plus pool, fleet orchestration, journal, worker and driver-record guards. Source lint and diff checks passed. Independent QA/Security GO for PR preparation: nine pool regressions independently passed with PostgreSQL; extra probes confirmed atomic rollback, cancellation cleanup and lock reacquisition. Supplemental four acquisition/unlock OSError/CancelledError cases independently passed after fail-closed acquisition hardening. No production collector or provider login was invoked; production exception text remains unavailable because the previous handler suppressed it.
