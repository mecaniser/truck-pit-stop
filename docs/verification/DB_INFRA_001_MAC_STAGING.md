# DB-INFRA-001: dedicated Mac staging

Owner: Release & Reliability. Status: in progress; not production-ready.

## 2026-10-21 cleanup and infrastructure

User explicitly authorized unused simulator/cache cleanup and, after inspection,
stopping EXO and removing its downloaded models. Remote host identity was verified
against the user's independently supplied ED25519 fingerprint before SSH access.

- Initial free space approximately 42 GiB. After cleanup, 114 GiB free before
  image downloads; later 113 GiB while staging build was running.
- EXO stopped via SIGTERM; process absence verified before removing only
  `~/.exo/models` (approximately 26 GiB). Configuration and logs remain (2.8 MiB).
- Apple's `simctl runtime delete --notUsedSinceDays 30 --dry-run` identified iOS
  18.6 and 26.2. Both were removed through simctl; runtime list then showed zero.
  Unavailable simulator devices were subsequently removed through simctl.
  User CoreSimulator directory decreased from approximately 20 GiB to 4 KiB.
- Removed Homebrew, pip and npm content caches (approximately 9.5 GiB combined).
  Preserved active Cursor/Figma updater caches and browser data.
- Inspected Trash. Removed deletable selected app bundles; protected GarageBand,
  Xcode, iMovie and Logitech remnants returned permission denied. Mixed documents,
  exports and other unknown Trash entries remain. Trash is approximately 12 GiB.
  No ownership changes, privilege bypass, or broad Trash wipe attempted.
- Existing Docker Desktop started successfully through its supported CLI.
  Engine 29.2.0, aarch64, approximately 8 GiB VM memory. Existing unrelated
  stopped containers and volumes preserved.
- Staging secrets generated on the remote machine; private directory 0700,
  environment file 0600. No Railway environment or production data transferred.
- Source archive: tracked backend/frontend at
  `626194996e78bd42556ce476847473e5730aa388`. Source root on remote:
  `~/dieselbridge-staging/source`; secrets outside root in `../private`.
- Separate Compose project `dieselbridge-staging`; PostgreSQL and Redis healthy.
  Network inspection confirms `Internal=true`. No database/Redis host ports.

## Runtime alignment

Implementation branch: `codex/mac-staging-server`, managed worktree
`/Users/sergio_m1_promax/.codex/worktrees/mac-staging-server/truck-pit-stop`.
Local runtime skill read; controller dry-run did not start services (dirty
documentation intake and absent local dependencies/environment). Target is the
separate Mac's container deployment, port 18080 through SSH, with a fresh staging
database. Original workstation checkout and running environments preserved.

## Independent review

QA/Security found an unrecognized build-ignore location and incomplete seed
emptiness check. Owner added `backend/Dockerfile.dockerignore` and checks for
existing Tenant, User and Customer rows. Runtime acceptance remains pending.

## Private staging acceptance

- Native ARM64 build passed TypeScript/Vite and Python dependency installation.
- Fresh Alembic migration completed at `187_labor_twilio_merge`.
- Two synthetic tenants, owners and customers created. Second seed invocation
  refused with `Database already populated; seed refused`.
- Actual Docker 29 internal-only networking suppressed published app ports.
  Architecture approved a fixed nginx ingress bridge; only gateway joins a normal
  network and publishes `127.0.0.1:18080`. App/database/Redis remain internal-only.
- `/health/ready` reports staging with healthy PostgreSQL/Redis. `/build-version`
  matches archived source SHA above.
- Both owners logged in through the real HTTP login endpoint and each sees one
  own customer. Cross-tenant customer reads return 403 in both directions;
  unauthenticated customer reads are denied.
- CUA browser login as Staging Alpha rendered the dashboard and exactly one
  `Synthetic Alpha Fleet` customer at `http://localhost:18080/dashboard/customers`.
  This URL reaches the Mac through the workstation's loopback SSH tunnel.
- App-container sockets to 1.1.1.1:443, api.stripe.com:443 and api.twilio.com:443
  fail. Checked Motive, WorkOS, Stripe, Twilio, SendGrid and QuickBooks credential
  fields are empty. Gateway has separate outbound capability and is not a forward
  proxy; do not claim all-container egress isolation.
- PostgreSQL custom-format backup restored successfully to a separate
  `staging_restore_check` database; counts match 2 tenants, 2 users, 2 customers.
- Scoped restart of all four staging services preserved those counts and a Redis
  persistence key. Post-restart readiness returned 200.
- User LaunchAgent `com.dieselbridge.staging.awake` runs `caffeinate -s` to inhibit
  system sleep on AC power. Does not bypass lid sleep or FileVault/login recovery.
- Free space after staging image installation approximately 105 GiB.

## Final independent gate

QA/Security independently approved private synthetic staging on final image
`sha256:af4441619645e92619df201d3a808b40c570b0dede97331bd405af3745f1567d`.
Readiness, source identity, migrations, networks, empty credentials, blocked
outbound sockets and restored/live counts were independently verified. Auth
script/results and authenticated browser screenshot were reviewed. Owner fixed
both seed/build findings. This approval excludes the remaining gates below.

Setup and evidence are in draft PR #619:
https://github.com/mecaniser/truck-pit-stop/pull/619 . No merge or production
deployment was performed. CI/merge approval remains separate from local staging.

## Remaining gates

Protected PR checks/merge remain pending. Unattended reboot recovery and
extended uptime not yet tested. Live worker/provider testing is a later isolated
stage, not authorized production access. Railway production remains untouched.
