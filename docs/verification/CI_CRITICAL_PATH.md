# DB-CI-006: overlap independent required checks

Owner: Release & Reliability. Independent infrastructure QA/Security required.

## Acceptance and preflight

Preserve every test and all six required contexts, strict up-to-date protection, exact-run dependency identity, disposable isolation and four two-CPU worker allocation. Reduce observed critical-path time without a duplicate full local suite or same-head retry. Failure of the new preparation job must fail a required context explicitly, never leave only skipped required checks.

2026-10-21: managed checkout `codex/ci-critical-path`, basec04ab4e9; no listeners5173/8000. CI-only configuration; application servers/database/browser changes are inapplicable. Existing application checkout and runtimes preserved.

## Baseline and design

Run39655183965 lasted8m36s. Frontend remaining waited until18:47:32 for critical/build/install job to complete, then ran until18:51:24. Backend remaining waited for backend critical until18:45:24, then ran until18:50:18. These partitions are disjoint; neither needs output produced by the other partition.

Separate unchanged frontend npm ci/package/upload into a preparation job. Critical tests/build and remaining tests each restore the same exact-run artifact and run independently. Backend partitions start independently after scope validation. Browser smoke still waits for frontend critical/build and backend critical success. Six existing names remain required; the new preparation job is covered transitively by a required frontend context that runs after prerequisite termination and explicitly rejects any non-success prerequisite result.

Tradeoff: a failing critical test no longer prevents its independent remaining partition from doing work. No duplicate test is run; both partitions must pass before merging. This exchanges some early-failure efficiency for shorter passing release latency. Capacity stays bounded by the existing four disposable workers; no worker or per-file concurrency changes.

Docs-only preparation/required jobs use hosted no-op paths; UI-only backend jobs remain no-op. Unknown/shared/manual/scheduled changes still run full coverage. Artifact verifier, npm lifecycle/audit, TypeScript, build, test commands, timeout values, all test sources and smoke remain unchanged.

## Validation and rollback

Actionlint and whitespace validation pass. Independent source review must cover success/failure/skipped/cancelled prerequisite states, all scope paths, unchanged test selection and fixed slot capacity. Final protected run provides timing, artifact consumer and unchanged count evidence. Revert the focused workflow PR if routing/failure propagation or timing regresses; never loosen a required check.

Independent source QA/Security GO: all six strict contexts verified live unchanged; negative prerequisite states fail required context; scope routes and fixed four-worker capacity preserved. Direct shell matrix checked all16 status combinations: only success/success returns zero. No full local suite run.
