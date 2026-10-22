# DB-CI-008: separate PR capacity from local regression

Owner: Release & Reliability. Infrastructure lane; independent QA/Security required.

## Acceptance and preflight

All six strict required contexts, every selected test, scope classifier, exact-run artifact integrity, clean npm install/audit/lifecycle, browser isolation/deadlines, and one automatic PR candidate run remain. PR jobs must not request the four shared local slots. Scheduled/manual regression keeps the permanent isolated workers. No subscriptions, spending limits, larger runners, application/provider/SMS settings or host permissions change.

2026-10-22: managed `ci-throughput/truck-pit-stop`, branch `codex/ci-overflow-scheduling`, base169c88bf, initially clean; no listeners5173/8000. CI-only routing; no app servers, database changes or browser QA required. Primary dirty checkout preserved. Live CI supplies runtime evidence. Active release owners notified to hold main during this candidate; source work can continue without duplicate dispatches.

## Diagnosis and design

Prior39676560701 took15m39 with concurrent611/615 runs: preparation queued3m04, smoke3m53; remaining tests also slowed under shared host load. Four fixed workers cannot supply several full PR pipelines simultaneously. Current read-only inventory confirms four online idle workers and no active Quality gates; optimize the policy before the next burst.

Route every pull_request application job to standard pinned `ubuntu-24.04` capacity, including same-repository and fork PRs. Keep scheduled/manual full regressions on the existing ARM64 disposable local workers. Docs-only no-op jobs stay hosted. This eliminates the local cross-PR bottleneck without a racy queue-length poll, custom lock, global cancellation group, duplicated overflow job, or extra worker allocation. It also avoids serializing unrelated PRs behind a workflow-wide lock. GitHub-hosted account concurrency/platform queues still apply; no universal eight-minute SLA is claimed.

Every frontend artifact producer/consumer in a run uses the same runner image/architecture. Exact Node/ABI/libc/lockfile/run/attempt/SHA validation is unchanged. Hosted smoke retains `--with-deps --only-shell` and isolated PostgreSQL/Redis services. All job dependency edges, test commands, check names and strict branch protection remain unchanged. Existing per-PR supersession cancellation and no automatic main-push duplicate remain unchanged.

Repository API confirms public visibility. Standard hosted public-repository runners are free: https://docs.github.com/en/actions/reference/runners/github-hosted-runners . Local infrastructure remains installed and unchanged, available for scheduled/manual regression. Reassess routing if repository visibility changes; do not alter spending settings automatically.

## Validation and rollback

Actionlint and whitespace checks pass. Evaluated the six actual routing expressions across pull_request/schedule/workflow_dispatch and false/true/missing scope:54 cases pass. Missing scope still executes suites, never silently skips. Same-repository/fork identity no longer changes PR routing. Independent review and one full hosted candidate must confirm all gates, runner identities, native dependency compatibility, browser smoke and timings. No full local suite or duplicate benchmark run.

Rollback is a focused workflow revert through normal protected PR gates if hosted compatibility or availability regresses. Do not bypass checks or weaken VM isolation. Existing open PRs need one integration with current main before their final candidate; owners retain product release authority.

Independent source QA/Security GO: six live strict contexts verified; all routing and missing-scope paths preserved; artifact consumers stay on the same platform per run; native dependency compatibility remains the live gate. Host isolation and all test commands/dependencies unchanged. No suites dispatched by reviewer.

## Hosted compatibility correction

Initial53e8f13e/run39823392101 passed both backend suites, frontend213 critical and1826 remaining tests, build and artifact restoration. Browser installation failed explicitly because ubuntu-latest resolvedUbuntu26.04, unsupported by pinned Playwright chromium-headless-shell. Pin every hosted job to Ubuntu24.04, matching the supported local base and keeping artifact producer/consumer OS stable. No browser/dependency/test upgrade or dropped case; corrected head gets its own required run.

Independent correction GO: failure reproduced from hosted image log; all seven hosted labels now consistently24.04, local labels untouched.54 corrected routing cases and actionlint pass. Browser version, test coverage, failure guards and artifact identity unchanged.
