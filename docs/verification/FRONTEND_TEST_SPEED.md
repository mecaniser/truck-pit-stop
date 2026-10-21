# DB-CI-004: frontend remaining-suite throughput

Owner: Release & Reliability. Test infrastructure; independent QA/Security required.

## Acceptance and runtime preflight

Preserve all193 frontend files, every assertion, critical/build/smoke gates, per-file isolation and existing deadlines. No duplicate full local suite or CI rerun. Benchmark focused files, then one protected candidate. Existing four disposable two-vCPU/8GiB VMs and eight-vCPU host allocation remain unchanged.

2026-10-21: reused clean managed CI worktree on `codex/frontend-test-speed`, base2f3cd3c5. No listeners5173/8000. No product-server/browser journey changes; application startup and browser acceptance are inapplicable. Local npm dependencies installed in this worktree without lockfile changes. Root checkout and unrelated runtimes preserved.

## Baseline and change

Run39633172662 frontend remaining job119338772666 took7m10s. Vitest ran176 files/1826 tests serially in316.87s: tests189.11s, collection50.73s, jsdom44.52s, transform10.82s, setup6.27s, preparation11.06s. Two largest files: RepairOrdersPage.customer18.899s and PartsInventoryWorkspace14.305s.

Use exactly two isolated workers for the remaining partition, matching its VM's two CPUs. Keep critical suite serial. No disabled isolation, concurrent tests within files, increased timeout, changed environment, assertion removal, dependency upgrade or workflow change. Existing execFileSync propagates failures. The earlier unrestricted-concurrency contention risk is addressed by a hard two-worker bound and actual final CI acceptance, not longer deadlines.

## Focused evidence and independent gate

The two largest files pass all74 tests with one worker in26.40s and two workers in14.90s on this host. This is a local sample, not a guarantee for CI; loading/cache effects also differ. Collection proves17 critical plus176 remaining files equals193 files without overlap. No full local suite was run.

Independent source QA/Security GO for one candidate: worker allocation fits VM bounds; per-file isolation explicit; critical serial setting, partition selection and all safety gates remain intact. Final runtime GO requires one passing protected run and unchanged test counts.

## Rollback

Restore the remaining runner's single-worker default through a focused protected PR if actual CI reveals contention or isolation failures. Keep existing deadlines and all tests; do not hide failures with retries or relaxed checks.
