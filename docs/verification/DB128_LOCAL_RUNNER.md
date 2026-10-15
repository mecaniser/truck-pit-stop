# DB-128 — dedicated local CI runners

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

## Verification

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
- [Quality run](https://github.com/mecaniser/truck-pit-stop/actions/runs/38671553825)
  at `6a23db18`: frontend full 1,554 passed, critical frontend 205 passed and
  production build passed; migration/readiness and Playwright smoke passed;
  critical backend 530 passed / 11 skipped. A remote merge-main update canceled
  the full backend suite; it is not counted as passing. Final revision requires
  an uncanceled six-check run.
- [Deliberate failure acceptance](https://github.com/mecaniser/truck-pit-stop/actions/runs/38670750634):
  `exit 42` is reported Failed by GitHub; worker subsequently discarded.
  Dependent fresh-worker acceptance succeeds. Independent QA also verified
  the sentinel is absent in the replacement of the same worker slot.
- Fresh independent Security GO for `6a23db18`: installed supervisor matches
  source; both active VMs satisfy the reviewed isolation boundary. Nonblocking
  hardening notes: Lima expanded the base image list with default fallback URLs
  (the intended ARM64 digest matches); preflight tests table existence rather
  than exact firewall contents. Live rules match the reviewed source. Full
  configuration identity and drift-proof preflight are not claimed.

- Controlled service restart on October 14, 22:59–23:04 America/New_York:
  bootout discarded both worker VMs; the base remained stopped. Bootstrap
  restored both online registrations (old IDs 35/36, new IDs 37/38). A canceled
  job briefly retained GitHub's busy state; the supervisor failed closed and
  recovered automatically after GitHub released it. Both replacements have no
  discard sentinel. Installed supervisor SHA256 matches reviewed source:
  `9af8f3c43b9bc92af33a43078171ce36226fd47f25d563d49c0d4710e81dd02b`.
  This proves service recovery, not an unattended pre-login reboot.

Final uncanceled six-check outcome, independent operational GO and protected
merge/main routing evidence remain required. Not Done.

## Complete runner acceptance

[Run38674355692](https://github.com/mecaniser/truck-pit-stop/actions/runs/38674355692)
completed successfully on70d52de6: all six jobs and their test steps passed.
Frontend full suite:1,556 passed; backend full suite:3,093 passed/152 skipped
in19m08s. Restart and fresh independent Security evidence above still apply.
Main subsequently advanced to9fe12aba; protected CI must validate the combined
revision before merge. Board identifier changed toDB-128 because an independently
landed repair-intake item also usedDB-126; that item's evidence is preserved.
