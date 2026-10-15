# Dedicated local GitHub Actions workers

Two disposable ARM64 Ubuntu VMs run the six existing `Quality gates` checks.
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
`db-ci-worker-1` and `db-ci-worker-2`, label `dieselbridge-local`.

```sh
launchctl print "gui/$(id -u)/com.dieselbridge.ci"
limactl list
gh api repos/mecaniser/truck-pit-stop/actions/runners
```

This is a user login service. After reboot/FileVault unlock it starts at login;
it cannot run while the Mac is powered off, disconnected or before user login.
An unavailable Mac queues trusted jobs; it does not silently move them to billed
hosted hardware. To stop, boot out the launch agent and allow cleanup. To resume,
bootstrap it. Force-killed or power-interrupted worker VMs are discarded on the
next supervisor startup. Never remove unrelated VMs/containers or worktrees.

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
