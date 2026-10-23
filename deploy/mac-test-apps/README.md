# Full private application test copies

DB-INFRA-002. Release & Reliability owns both isolated stacks on the dedicated
ARM64 Mac. These are real application builds with synthetic databases and
controlled workers. They do not connect to Railway production.

| App | Browser URL through SSH | Project | Data and workers |
| --- | --- | --- | --- |
| DieselBridge | http://localhost:18200 | db-local-test | PostgreSQL, Redis DB13, upload volume, restricted native Celery app |
| Trucks Parking Hub | http://localhost:18201 | tph-local-test | MongoDB, controlled blog queue worker, provider-disabled identity worker |

Each app has a separate internal network and owned named volumes. Only fixed
nginx gateways join ingress networks and publish loopback ports. No database or
worker port is published. The additional browser CSP allows only the local
origin; public provider scripts, fonts, frames and connections are blocked.
Every page carries a LOCAL TEST banner. Stay on the local origin during testing;
CSP does not prevent a user from following a normal external navigation link.

## Operator commands

Run from the owned Mac-staging worktree:

```sh
./deploy/mac-test-apps/test-apps status
./deploy/mac-test-apps/test-apps tunnel dieselbridge
./deploy/mac-test-apps/test-apps tunnel tph
./deploy/mac-test-apps/test-apps probe
./deploy/mac-test-apps/test-apps recover
```

Run each tunnel in its own terminal. URLs work while those SSH tunnels run.
`probe` performs synthetic database/worker and native authentication checks. It
replays the benign DieselBridge probe but creates only one receipt; it does not
enqueue another TPH blog job. Native login checks update synthetic PIN/login
usage metadata, not production data. No credentials or tokens are printed.

Remote root: `~/mac-hosting/test-stacks`. Secret environment and synthetic login
credentials are in `private/local.env` and `private/credentials.json`, mode0600
under a mode0700 root. Do not copy them into Git, screenshots or chat. Passwords,
PIN and database/API/session keys were generated independently on the Mac.
DieselBridge synthetic login names are `staging-alpha@example.com` and
`staging-beta@example.com`. TPH has one synthetic manager PIN. HR/admin Auth0 and
WorkOS are not bypassed; no production identity credentials belong here.

## Source and build contract

Pin tracked source only, never the operational checkout or its `.env`/sessions:

- DieselBridge: `65afe9b8fa52a946ca86f645abbf4ebe70aa3604`.
- TPH: `b369e9f5e28584ba99f1cbe35d8f65080a51aeda`.

The dirty/conflicted original TPH checkout is preserved. Source archives were
created with `git archive` over explicit app paths, checked for environment files,
symlinks, traversal and AppleDouble metadata, then extracted into new build roots.
DieselBridge uses its committed Dockerfile plus `Dockerfile.db` adapters. TPH uses
`Dockerfile.tph`, an explicit local API build URL, disabled analytics/payments and
nonfunctional Auth0 placeholders. Configuration uses full ARM64 image IDs from
`private/images.json`; mutable tags are not the runtime authority.

## Preventing duplicate jobs and delivery

- Fresh synthetic data only. No production database, queue, webhook replay,
  worker journal, customer contact list or provider cursor was copied.
- DieselBridge retains its native Celery application and schema startup gate,
  but removes production task imports and Beat schedules. Its only registered
  application task is `localtest.database_probe`, on queue `db-local-test` and
  private Redis database13. The synthetic receipt insert is idempotent.
- TPH's direct production server startup calls its business scheduler. The
  sandbox `tph-web.cjs` requires the exported server, skips that direct-start
  block, sets `DISABLE_SCHEDULER=true`, connects to the local database and starts
  HTTP. A separate internal readiness listener verifies MongoDB.
- The TPH blog adapter uses the real Mongo-backed job claim/save service with a
  process-local synthetic research provider. It accepts only the one allowed
  manual synthetic topic with no source URLs, creates an unpublished local draft,
  and never schedules/enqueues jobs itself. This is not real AI/research testing.
- The actual WorkOS identity worker runs with WorkOS disabled and returns
  `skipped/not_configured/processed:0` before any provider lease or call.
- No live provider credentials exist. Square's eager constructor requires an
  explicit invalid noncredential marker in sandbox mode. All app/worker/database
  outbound socket probes fail; only gateways have outbound connectivity.
- Payment, SMS, notification, provider outbox and TPH scheduled delivery features
  remain off. TPH's native local log maintenance still runs; that is distinct from
  business schedules and cannot contact a provider through these networks.

The application sources are unchanged. Test bootstraps/provider fixtures are
separate adapters with explicit acceptance limits.

## Initial setup, recovery and backups

`configure.py` generates only the two fixed projects into a recognized new root.
`stackctl.py bootstrap` is one-shot, journals each phase, starts fresh storage,
migrates/seeds only the new databases and refuses automatic retries after an
uncertain partial run. Inspect the exact failed phase before resuming a scoped
operation. Never clear the bootstrap marker or reseed populated databases.

`recover` starts accepted existing stacks and refreshes only their gateways. It
runs no migrations, seed or scheduled enqueue. The separate user LaunchAgent
`com.macapps.teststacks.recover` successfully ran at bootstrap. Docker's existing
login startup is a prerequisite. FileVault still requires local unlock/login;
these new stacks were not reboot-tested during the original observation window.

Run `backup-restore.py` on the Mac to save private PostgreSQL custom-format and
Mongo archive backups and verify them in new uniquely named restore databases.
It never overwrites a primary database. Mongo credentials use a temporary private
configuration, not process arguments. This is local backup/restore acceptance,
not off-device disaster recovery. Backups and restore databases are retained.

The old four-container DieselBridge staging stack, its port18080, source, volume
contents, baseline, minute sampler and existing heartbeat remain untouched.
Railway services, DNS and live credentials were not changed. Public hosting and
real provider authentication/delivery require separate acceptance.
