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

## Assisted reboot acceptance — October 21, 2026

User restarted the dedicated Mac and unlocked/logged into sergio. Boot epoch
changed from `1788363354` to `1792623263` (22:54:23 UTC / 6:54:23 PM EDT).
Login startup log recorded recovery at 23:02:26 UTC. Docker started automatically;
all four staging containers returned, readiness passed, web source remained
`626194996e78bd42556ce476847473e5730aa388`. PostgreSQL retained 2 tenants,
2 users and 2 customers; Redis persistence key retained `verified`. Unrelated
containers remain stopped. This proves assisted FileVault unlock/login recovery,
not unattended recovery after power loss.

Worker image `sha256:f02783a1ac3e46d713004643ccf20624701f3c328b65cc6c51b7e03c9d325567`
contains pinned PR611 source `576ce5a8a2c0bad7b8d33a236e6514bc448e8677` plus
reviewed synthetic browser harness. Packaging initially included macOS AppleDouble
files; validation now excludes/rejects metadata and NUL-bearing Python files.
The corrected archive contains 1,037 entries and zero AppleDouble files.

Before reboot, location and health each completed, committed and passed source/
capture/read-model parity for six vehicles. Trips completed and committed 18 rows;
after reboot its persisted receipt and exact 18-row parity passed. All three
containers exited zero and were not retriggered. Location source hash
`e17883bca56fe6891ce6ab5d17f2cd9b77c7a184d6240c5ed258be29895a1b2c`.
Health hash `dd6839e6eddbeeef7cd8533a42e8a6a11d2be72b6567dd12152d6173418209a3`;
trips hash `87d2635c1bc91d053c5990550d7614927b0522ccd19d2936978cb0b68c3f16f5`.

Five real location importer negative cases passed after a valid authorized dry-run:
incomplete source, wrong company, conflicting VIN, foreign actor and foreign tenant.
Each requested commit but hit its exact expected rejection; complete capture and
Vehicle row contents remained unchanged (state hash
`342db51a14224fa67503b5fa7a8ff7a59ff03373938cb7a207fe246c87931a5a`).
These are location-import negatives, not all five worker-specific negative suites.

Fuel/drivers runtime, journal recovery and independent final QA remain pending.
The accepted 24-hour clock has not started; reboot-period failed samples are
retained and are not treated as healthy time. Railway production untouched.

### Five-worker results and crash probe

Fuel completed and committed 18 reports, with exact source/capture/read-model
parity (`cb7eb769ba6c2e013f8204aa595bf71b371fb460f677053615390519553054b2`).
Drivers completed six records across three independently verified journals sharing
one collection (`1ae98ae00aaaa902f38571b50e9f6017d94b615c2bc5ce8f228f31c3d5797785`);
read-model parity passed. Thus all five actual collector/import pipelines passed
against synthetic provider DOM, not live Motive.

The first driver crash probe did not interrupt PID 1: it exited zero and finished
all three fleets. Its marker alone was not accepted as crash evidence. A new
scoped probe preserved those records, used fresh private state and Docker `--init`,
and exited 137 without OOM after the first fleet committed. Exact source hash
`4b1817f009e2a96acddae56a923dd302892dcc2bdb56984a5ec39b2dc06ac4e1` has one
verified journal and two source_saved journals. Reconciliation/recovery pending.

Soak reporter received independent static GO after 41 boundary checks, including
optimized Python. It requires approved container start identities and rejects
future/naive timestamps, incomplete gates and unhealthy/gapped samples.

### Actual committed-journal crash recovery

The scoped `--init` probe exited 137 with `OOMKilled=false`. Before resume, a
read-only exact-generation audit saved all primary capture/directory columns,
three journal IDs and one browser launch. It observed two records and one
directory, primary verified, two other journals source_saved. One reconciled
resume exited zero with `fleet_recovery_complete` and `fresh_collection:false`.
After audit found the same three journals verified, six records and three
directories, byte-equivalent normalized primary row contents, and browser launch
count still one. Final source/capture/read-model parity passed for all six records.
No blind retry or second collection occurred during recovery.

Tracked launcher now refuses a PID1 fault probe and exits70 if SIGKILL returns.
That safeguard passed independent static/PID1 checks but is not in image f02783;
the successful runtime probe used that image with Docker `--init`. Runtime image
and tracked harness revision are deliberately recorded separately.

Final independent runtime review is pending before starting the accepted window.
The 24-hour observation will cover infrastructure health and persistence after
these worker tests. It will not prove recurring worker schedules or live-provider
authentication/DOM compatibility.

### Independent runtime GO and accepted observation window

Independent QA/Security verified reboot, source/health/private network/blank
credentials/blocked egress, all five committed pipelines and exact driver recovery.
GO applies to private synthetic staging infrastructure observation only.

Created private baseline exclusively (no overwrite) from a fresh healthy sample:
**2026-10-21 23:09:59.450841 UTC through 2026-10-22 23:09:59.450841 UTC**,
or **October 21, 7:09:59 PM through October 22, 7:09:59 PM America/New_York**.
Baseline records all four approved container start timestamps, web source, reboot
identity, worker acceptance and independent GO. Reporter initially returned
`observing`, one sample, zero issues; 24-hour acceptance remains pending.
Minute LaunchAgent samples and 15-minute heartbeat are active. Heartbeat preserves
failed samples and baseline, alerts only for meaningful changes, and pauses after
verified completion. It may not count offline intervals or silently reset time.

PR619 remains open (currently not draft), unmerged. Railway production untouched.

### Monitoring ownership handoff — October 21, 2026

Board ID: DB-INFRA-001. From Railway recovery chat to dedicated Mac staging
chat `01a160dc-3a05-7742-902c-fb6b9ca45fef`; Release & Reliability remains
accountable. Railway recovery and PR611 stay with the original chat.

Read-only `soak-report.py` returned `observing`, `complete:false`, 38 samples,
latest `2026-10-21T23:46:08.204424+00:00`, and no issues. Recent minute samples
show readiness, approved web source, all four unchanged container start identities,
no OOM, and approximately 143 GB free. Existing active 15-minute heartbeat
`verify-mac-staging-recovery-and-24-hour-stability` targets this chat. PR619 is
attached; branch at handoff is `codex/mac-staging-server`, head `0a3ac1b0`.

No baseline reset, duplicate automation, worker trigger, service restart, live
credential use, or production action occurred. No API or migration impact.
The accepted October 21–22, 7:09:59 PM America/New_York window remains pending.
Next action: inspect ongoing samples/report; preserve and report any failure.
Return condition: 24 elapsed hours with required continuity/identity/health gates,
redacted final evidence, then pause the existing heartbeat. Existing synthetic-only,
assisted-unlock, recurring-schedule and undeployed PID1 safeguard limits remain.

### App hosting continued during observation

Separate `~/mac-hosting` private stateless deployment and rollback acceptance
completed without changing this baseline or its four container identities.
Independent QA/Security GO; original observation continues. Public domain/HTTPS
activation remains blocked on account/network access. See
[app hosting receipt](DB_INFRA_001_APP_HOSTING.md) for exact evidence and limits.

### Full application test copies

DB-INFRA-002 added separate DieselBridge and TPH database/worker stacks during
observation. Independent QA/Security accepted their private synthetic runtime;
original staging identities and baseline remain unchanged. See
[local app copies](DB_INFRA_002_LOCAL_APP_COPIES.md) for source, worker, persistence
and provider-exclusion evidence. The original observation is still pending.

### Original observation failure — October 22, 2026

The last healthy sample was17:38:35.644264UTC. Failed URLError samples began17:39:35.831217UTC (October22 1:39:35PM America/New_York). At17:49 the reporter returned failed with invalid_container_sample and unhealthy_or_source_changed. Read-only diagnosis found the host boot unchanged, Docker Desktop/backend processes absent and its Unix socket missing. Docker Electron logs recorded before-quit/will-quit at17:39:19, followed by backend shutdown at17:39:27. The quit initiator is not established. Container OOM/final states could not be inspected with the daemon stopped; no clean-container-shutdown or no-OOM claim is made.

The original baseline hash1e7618809a071feb45cadb84667827c97c483c63f7e3fbf645b92628b4544d1e and all failure samples remain intact. This window cannot be accepted as uninterrupted24hours, even after availability is restored. Saved [redacted failure receipt](DB_INFRA_001_SOAK_FAILURE_20261022.json) before one supported Docker Desktop start. No baseline reset, worker trigger or Railway action. Recovery results follow separately; a future accepted window requires explicit reconciliation and a separate baseline without erasing this one.

One supported Docker Desktop start returned exit 0. Existing restart policies automatically resumed 18 original containers at approximately 17:52:54 UTC (1:52:54 PM Eastern), with unchanged container IDs/images and changed start timestamps. All four staging services are running, configured health checks are healthy and `/health/ready` returns 200. A read-only PostgreSQL query confirms tenants/users/customers remain 2/2/2. Three synthetic backup-rehearsal containers remain exited/unhealthy; they were not manually restarted. No worker was explicitly triggered, no image build or pull command was issued, and no baseline or sample was deleted. The reporter correctly remains failed, now also reporting changed container starts. Availability recovery does not repair the original observation or prove live-provider/recurring-worker behavior. The existing monitor remains active and should alert again only for a meaningful state change.


### Renewed observation and merge-readiness gates — October 22, 2026

The user confirmed the original Docker closure was accidental. The original failed observation and baseline remain immutable; recovery did not repair that window. The user separately authorized a new observation and isolated safety work toward merge readiness, without merge, production deployment or live activation.

Fresh independent runtime QA verified four current staging containers, expected source626194996e78bd42556ce476847473e5730aa388 and image, readiness, no current OOM, PostgreSQL2/2/2, Redis persistence, internal network/gateway-only ingress, disabled provider flags and retained driver journals. No completed worker was replayed. QA approved starting, not accepting, a new infrastructure-only observation. Fresh independent Security gave scoped source GO but overall merge NO-GO pending stability, recovery acceptance and final integration checks.

New exclusive remote observation root: `~/dieselbridge-staging/private/observations/20261022T192823Z`. Its baseline SHA256 is `0002ccdd4d0b797e4a79543c1be310cd7a292d8f23b8ecba786031dec16ed328`. Window: **October22 3:28:23PM through October23 3:28:23PM America/New_York**, precisely UTC2026-10-22T19:28:23.277321 through2026-10-23T19:28:23.277321. Existing minute logs are linked into this root; no second sampler exists. The unchanged reporter's `report(new_root)` evaluates this window; its default CLI intentionally continues to report the original failed window. First new sample19:28:56UTC: observing, one sample, zero issues.

The existing fifteen-minute heartbeat was updated in place and remains ACTIVE. It monitors this new root, preserves both baselines and failures, and carries all three PRs through remaining gates. Acceptance requires the full elapsed24hours plus a qualifying sample at/after the end, unchanged source/start identities, readiness/health/noOOM/disk checks and no unexplained gap over90seconds. Offline time is not healthy time. No new baseline may silently replace this one.

Remaining merge gates: PR619 accepted new observation and final independent acceptance; PR622 reviewed recovery of accepted container starts/network fingerprints while preserving old snapshots/rollback and rejecting unexpected drift; PR623 scoped recovery and current verification of stopped synthetic rehearsal services/ledger without reinitialization or effect replay. All three require final current-main conflict resolution and one serial protected CI run per final head after concrete fixes/reviews. Main advanced after the previous greens; those results do not establish current merge readiness.

Live activation remains separately blocked: current durable production data outside the failure domain, primary/web/worker/webhook fencing, native payment/message/job operation IDs and unknown-outcome reconciliation, exact-release failover/failback and explicit production release approval. Synthetic fake-provider evidence cannot satisfy these gates. PR466 native source work is separate evidence and has not been integrated into this dormant rehearsal.


### Journaled recovery progress — October 22, 2026

The reviewed PR622 controller transition was applied once after independent QA and Security approved exact proposal9cd1bd57, SHA9e4bb727. It archived old state, changed only the accepted snapshot, preserved all non-snapshot release/database/rollback fields and restarted no container. Fresh independent postchecks confirmed identity/configuration/baseline matches and no uncertain operation/recovery. Staging and both app copies remain healthy.

PR623 recovery started the same synthetic Mongo and recorded active application once, at20:03:53.486818263UTC and20:04:00.591453794UTC. The inactive backup remains stopped with original05:12:05.03396976UTC start. The router did not start; original recovery and separate router-only resume failure records remain intact. Both attempts reached router Docker start, as subsequent backend logs establish; the early checkpoint-failure label was superseded rather than treated as a proven cause. Native read-only authority checks currently confirm the restored database, source, PIN usage3, watermark8 and exact active instance; control remains epoch5 with settled fake effects5.

An independently reviewed diagnostic then executed one exact captured router start, leaving the relay unchanged. Exit1 and retained stderr directly demonstrate127.0.0.1:18310 bind address already in use, owned by the accepted rehearsal relayPID67282. All prior records remain; no attempt is rerun or deleted. The minimal fix requires a new reviewed plan to release only that exact relay, start the original router once and restore the same reviewed loopback access path without port movement or other-container changes. It has not yet been applied.

The existing heartbeat was updated in place with these precise checkpoints, consumed-attempt prohibitions and new recovery gates. Redacted detailed receipts reside on the owned PR622/623 branches. No safety source was pushed or CI duplicated during this work. The accepted new observation and both baselines remain unchanged; the first56 samples were healthy with zero issues. Full24hour acceptance and final independent/current-main integration gates remain pending.
