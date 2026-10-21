# DB-CI-007: dependency preparation and smoke latency

Owner: Release & Reliability. Infrastructure lane, independent QA/Security gate.

## Acceptance and runtime boundary

Preserve every test and six strict required checks, current-run artifact verification, lockfile integrity, npm lifecycle scripts and audit, isolated database/browser smoke, fixed four disposable two-CPU workers, and trusted scope classification. No duplicate local suite or same-head CI retry. One final candidate supplies actual timing; no promised speedup from source changes alone.

2026-10-21 preflight: managed worktree `ci-throughput/truck-pit-stop`, branch `codex/ci-setup-smoke-speed`, base `636e7e91`; initially clean. Ports5173/8000 have no listeners. This changes only CI orchestration; application serving/database/browser QA is inapplicable. Real smoke executes in protected CI; unrelated primary checkout preserved.

## Initial proposal (scheduling superseded below)

Baseline39671946719: whole pipeline8m20s. Preparation172s: checkout13s, setup-node16s (npm cache hit110MB), npm ci84s, package12s, upload42s. Smoke139s: containers31s, Python15s, Node7s, backend install14s, artifact14s, Playwright install24s, migrations3s, actual browser tests18s. Smoke waited until frontend critical/build ended despite starting its own source servers via `e2e/playwright.config.ts` and consuming no built bundle or test output.

- Preparation uses default shallow checkout. Its npm installation and artifact identity need package files/current SHA, not Git history. Lint's separate full checkout remains unchanged.
- `npm ci --prefer-offline` prefers the existing content-addressed tarball cache, fetching missing entries normally. Clean installation, lockfile checks, integrity, lifecycle scripts and audit remain enabled. This does not reuse installed node_modules across runs or omit optional packages.
- Smoke depends on scope and dependency preparation, starting alongside both frontend partitions. It still restores the exact-run installation and runs the same service readiness, migration and browser checks. Critical backend, frontend tests and production build remain separate mandatory merge gates. Preparation failure still explicitly fails required Frontend checks.

Peak after preparation is remaining backend plus frontend critical, frontend remaining and smoke: four worker slots. If backend critical remains active, normal queueing keeps the same limit. No capacity, VM permissions, test retries, timeout or test source changes. Tradeoff: smoke may execute even when a separate critical check fails; merge still fails, and no test is duplicated.

## Validation and rollback

Actionlint and whitespace validation pass. Independent reviewer must verify dependency graph, missing-cache behavior and preserved failure/scope/strict-check semantics. Final run supplies all check results, unchanged counts and observed whole-run timing. Revert this focused workflow change for routing/failure regressions; do not relax gates. No production app/provider/SMS/payment/registration changes.

Independent source QA/Security GO: fresh-server smoke consumes no critical/build output; all six live strict contexts preserved; prerequisite failure guard, shallow-checkout history boundary and npm semantics intact. Up to five eligible jobs if backend critical remains active are safely queued within four slots. No full suites dispatched locally.

## Timing gate correction

Initial candidate `bb052f07`, run39675036824, all seven jobs pass: npm ci84s to16s, same679 installed/680 audited. Whole run8m30s regressed versus8m20s; frontend remaining queued until21:03:01 and ran252.08s versus203.45s previously. All176 files/1826 tests and five browser cases passed. Earlier smoke increased concurrent contention; restore original smoke dependencies rather than claim success from one faster step.

Final correction retains shallow preparation and npm prefer-offline, restores original smoke job dependencies, and adds `--only-shell` to both local and hosted Chromium installation. Existing smoke configuration uses default headless Chromium without a channel or executable override; it already uses this same shell. Only the unused headed browser download is removed, not a tested browser. Hosted OS dependencies, FFmpeg, actual shell, tests, retries and deadlines remain. See https://playwright.dev/docs/browsers. No full suite rerun on the same source; corrected source requires its own protected candidate.

Independent corrected-source QA/Security GO: original smoke dependency graph restored; same default headless Chromium runtime with unused headed download omitted; hosted system dependencies retained. Final aggregate workflow diff is only shallow preparation, prefer-offline npm install and shell-only browser installation.

## Release evidence

PR [614](https://github.com/mecaniser/truck-pit-stop/pull/614), checked head `d3ed2adf60a75c4c4d3620e86ed70042927188f3`, normal merge `8ddcf70e0c0477ba24a550a056f8e829f6d5769d`. Checked/merged trees identical. Independent source and runtime QA/Security GO; six strict required checks unchanged.

Final run [39676560701](https://github.com/mecaniser/truck-pit-stop/actions/runs/39676560701), attempt1: all seven jobs successful. npm installation25s versus84s baseline; first candidate16s. Playwright installation11s versus24s baseline; logs confirm Headless Shell1208 and FFmpeg1011, same five smoke cases pass. Final backend3517pass/387existing skips; frontend remaining176files1826tests, critical17files213tests. No test source, selection, deadline or retry policy changed.

Total15m39s (21:10:11Z–21:25:50Z) is not an end-to-end improvement: other runs39675352654 (#611) and39677263661 (#615) shared the four slots. Preparation queued3m04s after scope; smoke prerequisites completed21:19:22Z but smoke started21:23:15Z, about3m53s queued. Remaining frontend293.90s also reflects a busier execution sample. Keep the measured step gains separate from whole-pipeline latency; do not claim a clean final baseline or trigger a duplicate run to obtain one.

Initial timing-regressing source and corrected source each ran once, with no same-head retries or duplicate full local suites. Owners coordinated to hold further changes during landing; release holds removed after documentation closes. No app deployment is required for workflow configuration; future eligible runs use merged changes. SMS/provider/payment/registration state untouched.
