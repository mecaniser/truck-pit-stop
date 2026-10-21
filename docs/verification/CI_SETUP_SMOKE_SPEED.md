# DB-CI-007: dependency preparation and smoke latency

Owner: Release & Reliability. Infrastructure lane, independent QA/Security gate.

## Acceptance and runtime boundary

Preserve every test and six strict required checks, current-run artifact verification, lockfile integrity, npm lifecycle scripts and audit, isolated database/browser smoke, fixed four disposable two-CPU workers, and trusted scope classification. No duplicate local suite or same-head CI retry. One final candidate supplies actual timing; no promised speedup from source changes alone.

2026-10-21 preflight: managed worktree `ci-throughput/truck-pit-stop`, branch `codex/ci-setup-smoke-speed`, base `636e7e91`; initially clean. Ports5173/8000 have no listeners. This changes only CI orchestration; application serving/database/browser QA is inapplicable. Real smoke executes in protected CI; unrelated primary checkout preserved.

## Evidence and change

Baseline39671946719: whole pipeline8m20s. Preparation172s: checkout13s, setup-node16s (npm cache hit110MB), npm ci84s, package12s, upload42s. Smoke139s: containers31s, Python15s, Node7s, backend install14s, artifact14s, Playwright install24s, migrations3s, actual browser tests18s. Smoke waited until frontend critical/build ended despite starting its own source servers via `e2e/playwright.config.ts` and consuming no built bundle or test output.

- Preparation uses default shallow checkout. Its npm installation and artifact identity need package files/current SHA, not Git history. Lint's separate full checkout remains unchanged.
- `npm ci --prefer-offline` prefers the existing content-addressed tarball cache, fetching missing entries normally. Clean installation, lockfile checks, integrity, lifecycle scripts and audit remain enabled. This does not reuse installed node_modules across runs or omit optional packages.
- Smoke depends on scope and dependency preparation, starting alongside both frontend partitions. It still restores the exact-run installation and runs the same service readiness, migration and browser checks. Critical backend, frontend tests and production build remain separate mandatory merge gates. Preparation failure still explicitly fails required Frontend checks.

Peak after preparation is remaining backend plus frontend critical, frontend remaining and smoke: four worker slots. If backend critical remains active, normal queueing keeps the same limit. No capacity, VM permissions, test retries, timeout or test source changes. Tradeoff: smoke may execute even when a separate critical check fails; merge still fails, and no test is duplicated.

## Validation and rollback

Actionlint and whitespace validation pass. Independent reviewer must verify dependency graph, missing-cache behavior and preserved failure/scope/strict-check semantics. Final run supplies all check results, unchanged counts and observed whole-run timing. Revert this focused workflow change for routing/failure regressions; do not relax gates. No production app/provider/SMS/payment/registration changes.

Independent source QA/Security GO: fresh-server smoke consumes no critical/build output; all six live strict contexts preserved; prerequisite failure guard, shallow-checkout history boundary and npm semantics intact. Up to five eligible jobs if backend critical remains active are safely queued within four slots. No full suites dispatched locally.
