# DB-INFRA-001: repeatable Mac app hosting

Owner: Release & Reliability. October 21, 2026. Private stateless hosting accepted;
public activation and the existing 24-hour observation remain pending.

## Contract and runtime alignment

User authorized continued Mac hosting work while keeping Railway production
untouched and the original monitor running. Architecture approved a separate
`~/mac-hosting` subsystem, `macapps-<slug>` projects, loopback18100–18199,
immutable reviewed ARM64 images and bounded scoped deployment/rollback.

Owned worktree: `/Users/sergio_m1_promax/.codex/worktrees/mac-staging-server/truck-pit-stop`,
branch `codex/mac-staging-server`, existing PR619. Developer runtime skill read
and controller status/dry-run executed. Local frontend5173/backend8000 absent;
controller refuses switch without backend/.env and Vite dependencies. No local
application services or configuration were replaced. This acceptance intentionally
uses separately packaged synthetic app images on the dedicated Mac, not a claim
that this worktree's DieselBridge source is rendered by a local dev server.

## Delivered

- `deploy/mac-hosting/hostctl.py`: generated restricted Compose, deploy/status/
  rollback/access/config-backup/recover commands, app ownership, global lock,
  immutable images, reviewed nginx policy, no image-declared volumes, no custom
  Compose/env/mounts, loopback ports, resource caps, capacity/free-space guards.
- `deploy/mac-hosting/mac-host`: dedicated SSH operator entry point, including
  app tunnel. Existing accepted images and release events remain inspectable.
- Two independent stateless apps: hosting-demo v1 at 18100 and second-demo v2 at 18101.
  Up to four apps under this initial contract; stateful apps require another contract.
- Independent user LaunchAgent `com.macapps.hosting.recover` installed and
  successfully recovered accepted hosted apps at bootstrap. Docker's existing
  login startup is a prerequisite. FileVault still needs local unlock/login.
- Mode 0600 local registry backup contains both states and safe relative paths;
  independent reviewer verified 19 archive members. No off-device backup claim.

## Acceptance and failures retained

Nine focused unit checks pass. Independent QA added passing reserved-port,
immutable-port, capacity, OS/architecture, first-failure and retry checks.

Actual owner lifecycle: v1 accepted, v2 accepted, explicit rollback to v1,
unhealthy release rejected, previousv1 automatically restored and healthy.
A second app independently accepted v2. Browser CUA at `http://localhost:18100`
via dedicated SSH tunnel rendered “App hosting is ready.” and “Release v1”.
No credentials or financial actions are present in these synthetic apps.

Initial first release found nginx's default fastcgi/uwsgi/scgi temp paths on a
read-only filesystem. It was stopped without an accepted state. Owner inspected
exact stopped owned image/container identities, preserved events and recorded
cause, corrected all temp paths to `/tmp`, and safely retried. A managed marker
supports later scoped retries; unknown existing projects remain refused.
Security review found image-declared anonymous volumes; owner added rejection
and an actual empty app-mount gate before acceptance. No failure was erased.

Independent QA and Security both GO for the final private runtime: UID 65532 apps,
UID 101 ingress, read-only roots, empty app mounts, capability drop, no privilege
escalation, separate internal app networks, blocked app outbound socket probes,
loopback gateways, accepted immutable images and bounded resources. Final
controller SHA256 `4d6c491b22c4a99cf60f8c42d1f24a8466f8b21b2d2eb456b06cd8adf613763d`.

## HTTPS preparation

Caddy v2.11.7 official macOS ARM64 release installed into the hosting bin directory.
Official GitHub asset SHA256 verified before extracting only its executable:
`cda3030e5d5b13eb9f0b6fb541037f633bddd958c070c5f561d7a5cccb581665`.
Binary SHA256 `0d746e47f39d9706883b3633bf419feb25973e6caaa8eabbf5b44421d59e3973`.
Homebrew had no compatible macOS 27 bottle; its failed install log is retained.
No Homebrew Caddy service was installed or started.

Bounded native Caddy test served alpha.macapps.test/v1 and beta.macapps.test/v2
only at 127.0.0.1:18443. Verified TLS 1.3 chain/hostname, both app routes, unknown
Host 404 and wrong TLS name denial using a process-specific CA. Admin disabled;
`skip_install_trust` prevents machine trust installation. Exact child terminated;
independent QA/Security verified no Caddy process or edge/admin listener remains.
Initial cleanup assertion confused TCP TIME_WAIT with a live listener; corrected
to no-listener connection check and reran successfully. Public template was
adapted only, never provisioned or run. Independent QA/Security GO applies only
to this localTLS acceptance, not public trust or reachability.

## Existing staging and production preserved

Before/after baseline SHA256 matches:
`1e7618809a071feb45cadb84667827c97c483c63f7e3fbf645b92628b4544d1e`.
All four monitored container IDs and23:02 start identities match pre-hosting values.
Approved web source remains 626194996e78bd42556ce476847473e5730aa388.
The existing minute sampler and 15-minute heartbeat retain the original October 21
7:09:59 PM through October 22 7:09:59 PM America/New_York window. Latest redacted
receipt records current sample count; independent final review observed 52 samples,
zero issues, status observing. No baseline reset, duplicate automation or worker
retrigger occurred. Railway production, provider credentials and original checkout
were not changed. Original 24-hour acceptance is still pending.

## Public activation blocker and next action

User selected public websites/HTTPS and supplied www.elisprotech.com. Read-only
DNS shows existing www CNAME to l5clouc3.up.railway.app; preserve it. Registry RDAP
lists Squarespace Domains LLC, with Google ns-cloud-c1..c4 authoritative servers.
No observed apps A/AAAA/CNAME exists. `apps.elisprotech.com` public Caddy template
is prepared and disabled. No DNS, nameserver, router, public firewall or Railway
configuration changed.

Public activation needs authorized DNS-account access, reserved Mac LAN address,
router/WAN feasibility (including CGNAT/ISP), new apps-only DNS and exact inbound
TCP 80/443 forwarding to dedicated 8088/8443, then independently reviewed public
TLS/recovery/retention acceptance. No implied nameserver migration, paid tunnel
plan, production-domain replacement or claim that custom-domain hosting is live.

Source and operator guide: `deploy/mac-hosting/README.md` and `edge/README.md`.
[Redacted runtime evidence](mac-hosting/2026-10-21-runtime.json).
PR619 remains open/unmerged; protected final-head checks and any merge are
separate from this user-authorized Mac acceptance. Item remains In Progress.

[Browser evidence](mac-hosting/private-demo.png).
