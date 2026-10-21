# DB-CI-005: dependency and build throughput

Owner: Release & Reliability. Independent QA/Security required.

## Acceptance

Keep npm lifecycle scripts and audit, all tests, production TypeScript/Vite checks, browser smoke, strict protection and six required contexts. Installed dependencies may be reused only within the current workflow run/attempt/commit with exact package/lockfile and runtime identity. Reject missing or mismatched artifacts; never fall back to silently skipping validation. Preserve disposable workers and resource allocation. No duplicate full suite or CI retry. Final candidate must show passing gates and measured improvement.

## Runtime preflight

2026-10-21: managed worktree on `codex/ci-install-speed`, basef560b418, clean before intake. No listeners5173/8000. Test/build infrastructure only; application servers and authenticated browser acceptance do not apply. Source/dependencies belong to this worktree; unrelated checkout and services preserved. No production/provider configuration used or changed.

## Baseline

Run39648802098: frontend critical npm ci77s, remaining npm ci82s, smoke frontend npm ci78s. Production build68s, including Vite14.56s; TypeScript dominates the remaining build time. Backend installs55s/27s and smoke backend15s are smaller. All three frontend installs already restore npm's download cache; that cache does not avoid repeated extraction/lifecycle installation.

## Design

Frontend checks remain the sole producer and execute npm ci unchanged. After tests and production build pass, archive only node_modules as gzip with preserved executable permissions/symlinks. Upload a one-day immutable artifact named by current run and attempt. Remaining frontend and smoke jobs already depend on this producer. They download that exact artifact and reject a mismatch in run, attempt, commit, exact Node version, ABI, OS, architecture, libc, package manifest, lockfile or archive checksum. Consumers refuse an existing node_modules directory. No installed dependency cache crosses workflow runs or PRs; no host mount or persistent VM state is introduced. Artifact retention adds temporary storage usage; no subscriptions or spending settings change.

TypeScript and Vite are independent readers of source. The CI build launcher runs both within the existing two-CPU VM and awaits both exit codes. Either failure fails the job, including signal termination. Production npm run build remains unchanged. Build output is not substituted with cached output.

## Focused checks

17 integrity/build-failure tests pass: exact restore, refusal to mix installs, identity/checksum mismatches and absent identity, plus both build programs executing and either failure propagating. actionlint and whitespace checks pass. One final protected run validates real artifact transfer and both consumer jobs; no full local test suite is duplicated.

## Rollback

Revert workflow/script changes through normal protection: restore independent npm ci and serial npm run build. Never weaken gate failures, skip installation lifecycle checks or increase test deadlines to recover performance.

## Independent source gate

Independent QA/Security GO for one candidate; reviewer verified all17 focused checks. Local build41.89s serial versus38.22s parallel, both passing. Final Linux timing must include packaging/upload/download/restore overhead. Failed-jobs-only retries cannot reuse an artifact from an earlier attempt; a genuine retry requires a complete new attempt, never a relaxed identity check. No retry has been started.

## First candidate findings

Run39653397692: all1826 application tests passed; both consumers restored successfully; frontend restore14s versus previous install82s. Packaging13s plus upload41s is54s producer overhead. Build66s versus68s. Vitest incorrectly discovered the new Node-only `.test.mjs` files and failed those two files. Corrected filenames use explicit verify entrypoints, matching existing Node checks, with all17 still required before application tests. No same-head retry; final corrected commit needs a new protected candidate.

Correction acceptance:17 Node checks pass; actual Vitest collection returns17 critical plus176 remaining equals193 application files, no overlap. Independent correction GO confirms byte-identical renamed tests and required explicit invocation.

## Release evidence

PR609 merged normally as `826e6d514d650fa6642313b0b480d4c9107f9732` after final run39655183965 passed all six checks on exact head `a3c779756fb02108aeabef62e1116b8b0b310e40`. Checked and merged trees match. Independent live QA/Security GO queried GitHub directly and confirmed both real Linux consumers and browser smoke.

| Measurement | Baseline39648802098 | Final39655183965 |
|---|---:|---:|
| Remaining frontend dependency setup |82s install|8s download +5s restore|
| Smoke frontend dependency setup |78s install|8s download +5s restore|
| Producer packaging/upload |none|11s +40s|
| TypeScript + Vite build |68s|58s|
| Whole pipeline |9m37s|8m36s|

The observed pipeline improvement includes runtime variance; it is not a guaranteed61-second reduction attributable exclusively to this change. Dependency setup savings exceed the51-second one-time transfer cost. Producer still runs clean npm ci with lifecycle/audit; consumers do not skip dependency integrity checks. Remaining frontend176files1826tests pass in199.12s with no test-count loss. All17 Node integrity/failure checks execute in the required frontend gate. Strict base freshness and all six required contexts remain enabled.

There were two different candidate commits: the first exposed a real Node/Vitest discovery bug, then the corrected source passed. No same-head rerun or duplicate full local suite. Docs-only completion uses scoped checks without application suites. No production app deployment, provider setting, SMS automation, registration or payment action is involved.
