# Engineering Delivery Workflow

This repository is developed by a product-owner/release-manager working with
multiple focused coding agents. Treat each active worktree as an independent
developer: it owns a narrow change, has its own branch, and reaches `main`
only through a reviewed, green pull request.

## Working model

Use short-lived branches from current `main`:

```text
codex/<area>-<purpose>
```

Examples: `codex/fleet-detail-read-model` and
`codex/repair-workspace-quote-cache`.

One PR should address one user workflow or one technical concern. Do not mix
UI polish, migrations, performance changes, and unrelated cleanup merely
because the files are nearby. Before starting a new task, check active PRs and
worktrees for overlap. If two changes need the same file or API contract, work
sequentially or agree on the shared contract first.

`main` is the integration branch. No one pushes directly to it. The release
manager merges a PR only after the required GitHub checks are green, the PR
template is complete, and any dependent migration PR has landed first.

## Required pull-request contract

Every PR must provide:

1. A concise user and system impact summary.
2. Focused tests for the changed behavior.
3. A migration declaration: `none`, `new migration`, or `merge revision`.
4. A rollout signal and a rollback trigger for production-impacting work.
5. The commands actually run, including the production build for frontend
   changes.

The repository quality workflow provides the baseline gates:

- `Migration graph`: exactly one Alembic head.
- `Backend tests`: Python compilation and the stable critical regression suite.
- `Frontend checks`: lint non-regression checks for changed frontend files, the
  stable critical regression suite, and the production build.

The full backend suite also runs on every PR as an informational job until the
existing baseline failures are repaired. It must not be made a required check
while it is red: that would either block all delivery or train everyone to
ignore failed checks. The remediation goal is to make it green and then promote
it to the required `Backend tests` gate.

The repository also has pre-existing full-frontend lint violations. The
required changed-file lint gate compares each edited file with its base revision
and blocks only violations introduced by the PR. Clear the lint backlog by
feature area, then switch the workflow back to the full `npm run lint` command.

The full frontend suite runs as informational coverage until its existing stale
expectations are repaired. Once it is green, promote it from informational to
the required `Frontend checks` job.

## Database migration policy

Alembic changes require special handling because two independently valid
branches can create multiple heads when merged.

1. Keep migration PRs focused. Avoid adding unrelated application work to them.
2. Before merging a migration PR, rebase it on current `main` and verify the
   `Migration graph` check again.
3. Merge only one migration-bearing PR at a time.
4. If two migration histories must both land, create a dedicated Alembic merge
   revision from the current heads. Do not change production startup to run
   `alembic upgrade heads`; production must remain on one intentional head.
5. Deploy and confirm `alembic upgrade head` plus schema preflight before
   merging application code that depends on the new schema.

## Release path

Until a separate staging environment exists, a merge to `main` is a production
release. Make that explicit rather than pretending it is a harmless
integration step:

1. Merge one production-impacting PR at a time.
2. Watch Railway deployment logs through migration and schema preflight.
3. Run a small production-safe read-only k6 canary for performance-sensitive
   changes.
4. Check Grafana and Platform Analytics for at least 10-15 minutes: API P95,
   database query P95, Redis latency, 5xx rate, and alert state.
5. Record the merge SHA, deploy time, observed result, and any follow-up in the
   PR or release log.

The target setup is separate environments:

```text
local -> performance (synthetic load) -> staging (release candidate) -> production
```

The existing `performance` Railway environment is only for synthetic data and
k6 capacity tests. It must never be pointed at customer data or repurposed as
staging. A future staging environment should mirror production service
configuration with isolated data and deploy candidate commits before production
promotion.

## Rollback policy

For a user-facing regression, stop merging related work, identify the deployed
SHA, and revert the smallest responsible PR. Confirm the rollback deployment
and the affected metrics. For migrations, prefer an additive, backwards
compatible migration so the application can be reverted safely; do not delete
or rewrite an already deployed revision.

## One-time GitHub configuration

Configure a branch protection rule for `main` after the quality workflow has
merged once:

1. Require a pull request before merging; disable direct pushes.
2. Require branches to be up to date before merging.
3. Require these status checks: `Migration graph`, `Backend tests`, and
   `Frontend checks`.
4. Require resolved conversations and block force pushes/deletion.
5. Keep the release manager able to merge after reviewing the PR. Do not
   require a second GitHub approval until there is a real second reviewer;
   coding agents do not have independent GitHub identities.

## Agent handoff format

At the end of each task, record only:

- branch and PR URL;
- what changed and what did not;
- verification run;
- migration/deployment requirement;
- measurable production expectation.

That keeps concurrent work understandable without creating a separate project
management system inside the codebase.
