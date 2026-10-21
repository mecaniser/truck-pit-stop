# Dedicated local GitHub Actions workers

Bounded disposable ARM64 Ubuntu VMs run the six existing `Quality gates` checks.
A macOS launch agent supervises them; each ephemeral registration accepts one
job, then the VM is destroyed and cloned again from a stopped pristine base.
Fork PRs retain the same checks on standard hosted runners. GitHub's server-side
external-contributor approval policy must be `all_external_contributors`.
Routing labels and YAML conditions are not security boundaries.

## Boundaries

- No host directories, SSH agents, Keychain, or Docker sockets enter the VM.
- Jobs use `runner` UID 1100 with no sudo or privileged groups. Guest Docker is
  rootless; host Docker and development databases are untouched.
- Root-owned nftables blocks private, link-local, host gateway, multicast and
  IPv6 egress. Only guest loopback, established replies and Lima DNS are exempt.
- Base has no runner registration or repository credentials. The host retrieves
  short-lived registration tokens with its existing `gh` authentication, passes
  them through SSH stdin, and never puts the host token into a guest.
- VM CPU/memory/disk are bounded. A two-hour lifetime bounds hung workers.
- All check names, suites, failure semantics, branch protection, migrations and
  production Railway configuration remain intact. Playwright OS dependencies
  are provisioned using the same pinned Playwright installer before jobs run.

## Provision

Install Lima from Homebrew, then from this directory:

```sh
limactl start -y --name=db-ci-base base.yaml
limactl shell db-ci-base sudo bash < provision.sh
limactl shell db-ci-base sudo tee /etc/nftables.conf < network.nft >/dev/null
limactl shell db-ci-base sudo systemctl enable --now nftables
```

Verify isolation and rootless Docker before stopping the pristine base. Do not
run repository jobs in the base or copy worker state into it. Pin changes require
rebuilding and independently verifying a new base before replacing the old one.

```sh
limactl stop db-ci-base
python3 supervisor.py --state-dir "$HOME/Library/Application Support/DieselBridge CI/state"
```

The installed launch agent runs a reviewed copy outside the checkout so a PR
cannot change its own host supervisor. `KeepAlive` restarts the supervisor;
startup discards previous worker VMs rather than trusting their disks. `caffeinate`
keeps the Mac awake while the supervisor runs on AC power. No billing or power
management preferences are changed.

## Operations

Installed files live in `~/Library/Application Support/DieselBridge CI`.
Launch agent: `~/Library/LaunchAgents/com.dieselbridge.ci.plist`.
Logs: `supervisor.log` in the installation directory. Runner registrations are
`db-ci-worker-1` through the configured slot count (maximum four), label
`dieselbridge-local`.

```sh
launchctl print "gui/$(id -u)/com.dieselbridge.ci"
limactl list
gh api repos/mecaniser/truck-pit-stop/actions/runners
```

This is a user login service. After reboot/FileVault unlock it starts at login;
it cannot run while the Mac is powered off, disconnected or before user login.
An unavailable Mac queues application jobs; lightweight scope/safety and explicit
no-op checks use standard hosted Linux for this public repository. To stop, boot out the launch agent and allow cleanup. To resume,
bootstrap it. Force-killed or power-interrupted worker VMs are discarded on the
next supervisor startup. Never remove unrelated VMs/containers or worktrees.

## Verification once per candidate

Use focused local tests for the files and behavior being changed. The protected
GitHub workflow is the complete integration gate; do not repeat its full suites
manually before pushing. Run a local reproduction only for a concrete failure.

The six check names remain stable. Critical frontend/backend jobs execute the
existing lists in `.github/critical-tests.json`; jobs with the legacy “full suite
(informational)” names execute the remaining files. Collection checks prove that
critical plus remaining equals the complete discovered suite, with no overlap.
Both jobs must pass: test failures are not wrapped in `continue-on-error`. The
normal `npm test -- --run` and `python -m pytest` commands still run full suites.

Critical failures prevent their remaining-suite jobs and the smoke setup from
starting. Frontend source/public assets and index.html, optionally with Markdown
documentation, get explicit backend no-op checks. Dependencies, frontend tooling,
unknown/shared/backend changes run all suites. Root/docs Markdown-only changes
skip application suites while migration/contracts/configuration checks still run.
The classifier comes from the protected base commit; absent outputs fail closed.

The workflow runs automatically on PRs, not again on main push. Strict up-to-date
branch protection and all six checks remain mandatory. A daily07:23UTC audit and
manual dispatch execute full regression on main. Lightweight classification and
no-op checks use hosted Linux; heavy jobs use the disposable local workers.

Playwright has a25-minute total job budget for isolated dependency/database
setup, and a separate5-minute smoke-step limit. Individual Playwright/test
deadlines are unchanged. Inspect the actual test step when diagnosing old runs
created before failure propagation was corrected.

## Release scope

Release quality gates and production bundle compilation run on these workers.
Railway still performs its configured production Docker build, migration and
hosting. This setup does not claim to move Railway hosting/build billing onto
local hardware. Moving production image delivery requires a separate reviewed
image-publishing/provider-source cutover; no Railway settings or secrets change.

## Rollback

Boot out the launch agent, restore `runs-on: ubuntu-latest` and the original
`playwright install --with-deps chromium` in a focused PR. Keep every required
check. Never relax branch protection or delete failing checks to land a release.


## Capacity profile and safe upgrade

The original profile is two workers, each with four vCPUs and 8 GiB RAM. The
reviewed throughput profile is four workers, each with two vCPUs and 8 GiB RAM:
**eight aggregate vCPUs remain unchanged**, while RAM increases from 16 to 32 GiB.
On the measured 10-core/64-GiB host this retains memory for development and the
separate two-vCPU SEO worker. Vitest already runs one worker; pytest is serial.
Two observed busy guests used approximately 1 GiB each and 120%/47% CPU during
frontend/backend tests. More slots target queue latency, not faster individual
suites. Do not increase the aggregate CPU limit or reduce guest memory merely to
advertise more slots. No host mounts, registration persistence, privileged guest
permissions, firewall exceptions or production configuration change.

After independent review, use the explicit profile:

```sh
python3 scripts/ci_runner/install.py --slots 4 --cpus 2 --memory 8
```

The installer refuses a loaded old launch agent, busy managed registration,
unknown runner API result, or running managed VM **before changing installed
files**. It never stops workers itself. Never run it over active jobs.

For supervisors that support it, create `state/drain` in the installation
folder. Completed workers are destroyed and no replacements register while
that file exists. Already listening ephemeral workers can accept their one job;
the drain file never kills an active job. Wait for running jobs to finish before
unloading the launch agent. Remove the drain file only when ready to resume.

The original two-slot supervisor predates drain support. For that one-time
upgrade, the release operator must verify both guests are in their stable runner
phase, then suspend **only the exact installed host supervisor Python PID** with
SIGSTOP. This prevents recycling while guest jobs continue. Wait for both guest
`db-ci-runner` services to finish and GitHub to report no busy owned runners.
Do not stop VMs or listeners while jobs run. Once both are finished, terminate
and resume that supervisor for cleanup, unload its launch agent, and install the
reviewed profile. If any identity/state is uncertain, resume the original
supervisor with SIGCONT and investigate instead. Do not suspend `caffeinate`,
Lima, guest workers, unrelated Python processes, or use broad process matching.

Verify four online registrations, four fresh guests with two vCPUs/8 GiB each,
root-owned firewall, unprivileged runner identity, and successful real workflow
jobs before claiming installed capacity. Watch host pressure and job timing;
rollback uses the same drain then `--slots 2 --cpus 4 --memory 8`. Infrastructure
verification uses VM/runtime evidence; no application server or browser preview
is required for this capacity-only change.
