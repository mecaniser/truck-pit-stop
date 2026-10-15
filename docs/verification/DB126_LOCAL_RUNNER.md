# DB-126 — dedicated local CI runners

Owner: Release & Reliability. High-risk infrastructure lane.
Branch: `codex/dedicated-ci-runner`; PR [#530](https://github.com/mecaniser/truck-pit-stop/pull/530).

## Acceptance and scope

Preserve all six required checks and their existing failure semantics, execute
trusted CI/release-verification on owned hardware, verify clean-worker isolation
and persistent service recovery. Do not change subscription, spending limits,
branch protection, application databases, production migrations or Railway
provider configuration. No API/data contract change.

Infrastructure runtime is isolated in Lima; existing local application servers
and databases are not reconfigured. The local-runtime skill preflight found a
stale existing application runtime receipt (reported main/older SHA; no backend
on its expected port), so no claim is made that this checkout is served by the
development UI. Changed journeys are GitHub job execution and service recovery,
verified against the actual CI workers instead.

## Implementation

- Two 4-vCPU/8-GiB/40-GiB ARM64 Ubuntu workers, each accepting one ephemeral job.
- Pristine credential-free base remains stopped and is never used for jobs.
- Separate runner UID 1100 without sudo or privileged groups; rootless Docker.
- No filesystem mounts, host sockets or agent forwarding. Root-owned firewall
  denies host/private/link-local and IPv6 access, including container egress.
- Per-login launch agent supervises worker replacement; restart discards old VMs.
  Recovery before macOS login/FileVault unlock is not claimed.
- Outside contributors require GitHub server-side workflow approval. Fork PRs
  keep all checks on standard hosted runners; VM isolation remains the boundary
  against malicious workflow edits that request the local label.
- Production Railway Docker build, migration and hosting are unchanged.

## Verification in progress

- `actionlint .github/workflows/quality.yml`: pass.
- `shellcheck scripts/ci_runner/provision.sh`: pass.
- `python3 scripts/ci_runner/test_supervisor.py`: 5/5 pass (unowned deletion,
  firewall/identity preflight failures, cleanup failure, token/clone transport).
- Independent QA confirms all six check names, commands, dependencies, full-suite
  failure semantics, migration and smoke diagnostic steps are preserved.
- Independent Security inspected the live base: UID/groups/sudo, mounts,
  rootless/rootful Docker separation, firewall/service ownership and deny rules.
- Shell and rootless-container probes: public GitHub succeeds; host gateway,
  private networks and metadata endpoints are unreachable.
- [Quality run](https://github.com/mecaniser/truck-pit-stop/actions/runs/38670616253):
  migration/readiness passed on `db-ci-worker-2`; remaining suites pending.
- [Deliberate failure acceptance](https://github.com/mecaniser/truck-pit-stop/actions/runs/38670750634):
  `exit 42` is reported Failed by GitHub; worker subsequently discarded.

Final six-check outcome, clean-disk recovery, supervisor restart, independent
operational GO and merge/main-run evidence remain required. Not Done.
