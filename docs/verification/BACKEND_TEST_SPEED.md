# DB-CI-003: backend test setup throughput

Owner: Release & Reliability. Independent QA/Security required for shared test infrastructure.

## Acceptance

- Reduce measured backend execution time without removing existing tests or assertions.
- Preserve fresh in-memory databases, committed-data isolation, DDL isolation, schema constraints, UUID behavior, and independent async connections per test.
- Keep critical/remaining partition coverage, strict branch protection, all six required contexts, and existing UI-only routing.
- No extra full local run, manual CI retry, production/provider changes, or increased worker CPU allocation.
- Focused measurements, independent review, one final candidate run, normal merge and live timing evidence required.

## Runtime preflight

2026-10-21: reused clean managed CI worktree on branch `codex/backend-test-speed`, base `02f1329a`. No listeners on5173/8000. Root checkout and other task runtimes preserved. This changes test infrastructure only; application servers, production databases and browser acceptance are inapplicable. Focused tests use synthetic in-memory SQLite and the existing Python dependency environment, with source imported from this worktree.

## Baseline and diagnosis

Existing run39627790863 backend remaining job119321257580 took20m01s including setup. Pytest itself took1101.89s (18m22s), with3514 passed and387 skipped. Existing skips are not introduced or expanded by this change. Timestamped logs show cost spread across database-heavy files, rather than one slow test. Focused18-test fractional-parts sample took8.58s; the ten slowest phases were schema setup at0.35–0.50s each.

The shared `_db_engine` fixture rebuilt all model tables and indexes for every database test. The change compiles an empty SQLite schema once per pytest process, opens that temporary template read-only, and copies it through SQLite's backup API into a new in-memory database per test. No app session uses the template. No connection is shared between test event loops. Every engine is disposed in a finally block. UUID compatibility patches remain test-only and are restored after the template lifetime.

## Focused evidence

Same18 fractional-parts tests:8.58s before,3.02s after (65% reduction on this host; not a promised CI result). Existing payment step-up and websocket security tests plus3 new schema/isolation tests:102 passed in18.75s. The new checks compare all SQLite table/index DDL against direct `Base.metadata.create_all`, prove committed data and schema cannot cross parametrized tests, prove every template table remains empty, and reject template writes. No application test assertion was removed.

CI now reports the20 slowest pytest phases for both partitions so subsequent bottlenecks are visible without a diagnostic rerun. Workflow scheduling, test selection, runner isolation, dependencies, production code and provider settings are unchanged.

## Rollback

Revert this test-infrastructure PR through the normal protected path. Restore per-test schema creation if any isolation/schema mismatch appears. Never drop a failing test or relax a required check to recover performance.

## Independent gate

Fresh independent QA/Security GO: schema/constraint equality, committed data and DDL isolation, read-only empty template, native PostgreSQL UUID delegation and per-test async-engine lifetime reviewed. All models register before template creation; no existing test mutates shared Base metadata.102 focused safety tests passed;11 classifier/partition unit tests passed. Collection proves33 critical plus274 remaining files cover307 files without overlap (one new safety file). No duplicate full local suite was run. Final protected CI and measured release timing remain pending.
