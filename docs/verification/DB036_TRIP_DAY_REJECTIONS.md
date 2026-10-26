# DB-036 deterministic day rejection isolation

Backend & Integrations accountable; high-risk worker lane. Architecture and independent diagnostic_gate contract GO before implementation. Base98e51f40, branch codex/motive-trip-day-rejections. No migration or source/import guard relaxation.

## Acceptance before implementation

A typed PriorCoverageMismatch originates only in verify_prior_coverage inside prepare, before dry-run/import/normalized receipt creation. Explicitly roll back that session. Only a fresh CLI non-recovery invocation with an explicit nonce may persist an immutable rejection.json beside the exact daily source. Bind evidence to version, reason, run directory/day, raw source file SHA256, authorized tenant/actor/company plan scope, nonce, timestamp and bounded prior/covered/missing counts. committed=false and import_attempted=false. Existing normalized, receipt, attempt or unknown artifacts forbid continuation.

Node must require dedicated exit code AND fresh exact private rejection evidence; never parse arbitrary error text. Valid rejection skips only that import for this invocation and continues other bounded dates with existing company/identity/freshness gates. No same-invocation retry. Any timeout, auth/identity failure, unknown exit, absent/forged/stale/cross-day evidence, recovery, or possible prior attempt aborts. Every other day still requires its exact validated/verified receipt.

Worker terminal status is explicit PARTIAL with rejected dates and counts, not complete/recovered. Scheduler execution may finish normally after all planned dates have terminal outcomes; rejected dates stay unaccepted and visible, never enter verified_days or advance strict/reconciled cursors. Original immutable trips remain unchanged. Next invocation retries unresolved days normally. Rollback to previous worker is safe but restores starvation; no database rollback is necessary.

Tests: real preimport mismatch rollback/no DB writes; subprocess code+artifact validation; mixed rejection/success; malformed/stale/cross-day/source/scope/nonce evidence; existing attempted artifacts; timeout/systemic error abort; recovery rejection forbidden; coverage cursors remain unchanged; output privacy. Independent source/security/QA gate before commit/PR, protected CI and release-owner canary before Done.

## Runtime preflight

2026-10-26 Eastern: clean new managed worktree at stated base. No5173/8000 listeners. Controller switch dry-run blocked missing backend/.env and Vite. No secrets copied or services changed. Use isolated fixtures; no local browser/runtime acceptance claimed.

## Owner verification

- 113 focused Python tests pass across day_rejections, worker, worker_process, catchup, terminal_coverage, empty_proof and placeholder suites using `/tmp/db036-terminal-coverage-owner-20261026/bin/python`.
- 35 Node tests pass across collect_motive_trips.test.mjs, collect_motive_trips.dom.test.mjs and trip_diagnostics.test.cjs. Existing frontend jsdom dependency supplied through NODE_PATH.
- Real Node/Python process tests exercise the actual importDay wrapper and shared artifact validator: valid preimport rejection continues to the next day; missing evidence, wrong nonce, attempted-import artifacts and timeout abort. Separate actual runner DB test proves explicit rollback before import_batches and no normalized/receipt creation. Mixed worker test proves PARTIAL with rejected date and unchanged strict cursor. Recovery never converts a mismatch to a continuable rejection.
- Rejection evidence uses a raw-file hash and also checks that the current file still matches the canonical document validated before rollback. Source edits between prepare and proof persistence fail closed. New helper is included by existing Docker COPY backend/; no image layout changes.
- No production execution or merge/deployment. Independent diagnostic_gate GO:46 relevant Python and35 Node tests independently pass; no blocking findings. Parent-owned release evidence and aggregate matrix copied only from the three explicitly authorized paths; future API transport proposal remains separate and unimplemented.

## Handoff to Release & Reliability

Independent source/security/QA GO on the final source diff. Merge/deploy/canary remain release-owner actions. Canary must show a rejected historical day remains unaccepted while later recent dates produce exact verified receipts, original retained trip fingerprints remain unchanged, and a systemic failure still stops. PARTIAL is not sustained recovery or full historical acceptance.
