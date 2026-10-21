# DB-CI-002: CI throughput

Owner: Release & Reliability. Infrastructure lane; independent QA/Security required.

## Acceptance

- Run protected quality checks once per PR candidate; remove redundant main-push suite.
- Preserve all six required contexts and strict up-to-date branch protection.
- Frontend-only changes skip backend pytest; narrowly defined docs-only changes skip application suites.
- Unknown paths, workflow/tooling/dependencies and backend changes fail closed to full coverage.
- Nightly and explicit manual runs execute full coverage on main.
- Keep migration graph, collector contracts, scope/partition guards and deployment configuration checks.
- Lightweight and explicit no-op checks do not consume disposable local worker slots.
- Improve capacity without host mounts, privileged job users, shared databases, persistent dirty VMs or interrupting running jobs.
- No production application, SMS, registration, payment or provider mutation.

## Runtime preflight

2026-10-21: isolated checkout ci-throughput, base180855ce, branch codex/ci-throughput. Root application checkout has unrelated dirty work and is preserved. Ports5173/8000 have no listeners; controller status contains a stale historical receipt, not current serving proof. This change runs CI scripts only; no application server or database is needed or started, and no local UI visibility is claimed. CI/runner verification replaces product browser QA because no user journey changes.

## Baseline

GitHub run39529600380 (#598) elapsed43m53s; backend remaining execution20m47s. Run39508728270 (#596) elapsed90m29s. Two self-hosted workers share local capacity. Current workflow triggers PR plus main push; critical and remaining partitions already avoid intra-run duplication. Branch protection requires all six names and strict base freshness.

## Rollback

Revert this focused PR through normal protected review; previous workflow and supervisor remain available. Never relax branch protection or enable SMS to recover CI. Preserve active jobs when applying host changes.

## Implementation decisions

Protected PR CI remains the single pre-merge integration gate. The automatic main push trigger is removed; a daily07:23UTC audit and explicit workflow dispatch still run all suites. Branch protection stays strict with all six existing required names. Scope is evaluated using the protected base classifier, so a PR cannot approve its own reduced scope. Initial adoption fails closed for missing outputs.

Markdown-only means root or docs/ files ending in.md; executable/configuration content does not qualify. UI source/assets retain frontend partitions, build and real browser smoke while skipping backend pytest. Dependency and tooling changes require all suites. Migration graph, collector contracts, classifier/partition guards and Railway configuration remain on every PR. Lightweight gates/no-op checks use standard hosted Linux in this public repository; no subscription or spending settings change.

Local suite repetition is unnecessary: focused reproduction while editing, then protected CI once on the final candidate. A failure must be diagnosed before another push; changes to the tested tree legitimately require new checks. No manual blanket main-run cancellation is needed after this workflow is active.

## Independent source gate

Fresh independent QA/Security GO:11 classifier/partition tests and13 supervisor/installer tests pass; actionlint and whitespace checks pass. Adversarial paths, backend deletion/rename, missing revisions and dependency/tooling exclusions verified.65 collector contract tests and Railway config validation pass. Gates remain unchanged in GitHub branch protection. App UI testing is inapplicable; runtime acceptance is real Actions routing and installed disposable-worker behavior.

Four2-vCPU/8GiB workers retain the prior eight-vCPU total allocation, with32GiB maximum guest memory on the64GiB host. Install requires no active guest jobs; original supervisor is frozen only while guests finish, then cleaned/unloaded. Backups permit restoring the previous profile. No host mount, rootless Docker, firewall, token or ephemeral-destruction policy is relaxed.
