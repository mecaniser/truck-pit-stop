# DB-INFRA-002: local DieselBridge and Trucks Parking Hub copies

Owner: Release & Reliability. October 21, 2026. Private synthetic runtime accepted
by independent QA and Security. Public hosting and production migration are not
part of this acceptance. Existing PR619 remains open and unmerged.

## Scope and acceptance contract

User authorized local test copies of both applications, including databases and
workers, while keeping Railway production untouched and preventing duplicate
messages/jobs. Architecture approved separate fixed projects, fresh synthetic
state, private queues, controlled worker adapters and no production credentials.

Acceptance: build exact committed source, exercise native HTTP/browser and
permission paths, prove private worker behavior and idempotence, verify isolation
and non-delivery, restart only new stacks, restore backups into new databases,
and preserve the existing four-container staging observation unchanged.

## Source, build and runtime identity

| Application | Pinned committed source | Accepted application image |
| --- | --- | --- |
| DieselBridge | `65afe9b8fa52a946ca86f645abbf4ebe70aa3604` | `sha256:15b11ee6629e2e3938dc21803802ff42c1bd2f0d21c9c113627e873923fe3cc4` |
| TPH | `b369e9f5e28584ba99f1cbe35d8f65080a51aeda` | `sha256:b9ad065cf317c2516c35de57bb6e42229087b75b7f796951bcef5242818ce727` |

Both native ARM64 builds passed. Source came from explicit tracked `git archive`
allowlists, verified against traversal, active environment/session files, symlinks
and AppleDouble entries. No production data or operational environment was copied.
The original dirty/conflicted TPH checkout was not edited. Source application code
was not changed; infrastructure and adapters live in the owned Mac-staging branch.

The mandatory local runtime skill was read and controller dry-run executed. The
workstation worktree lacks backend/.env and Vite dependencies; it was not switched
or made to serve DieselBridge. This acceptance intentionally targets packaged
applications on the dedicated Mac through SSH tunnels, corroborated by image IDs,
served source/readiness and rendered features. No local5173/8000 visibility claim.

| Runtime | Project | Database/storage | Workers | Access |
| --- | --- | --- | --- | --- |
| DieselBridge | `db-local-test` | PostgreSQL `dieselbridge_local_test`, Redis13, owned upload volume | Native Celery app/schema gate, restricted synthetic registry and queue | `http://localhost:18200` through SSH |
| TPH | `tph-local-test` | Mongo `tph_local_test`, owned database/config volumes | Real blog job service with synthetic provider; actual provider-disabled identity worker | `http://localhost:18201` through SSH |

All ten expected containers run with applicable health checks passing and no OOM.
Named volumes/networks are disjoint from each other and original staging. Only
fixed gateways publish loopback ports. App, worker and database socket probes
cannot reach external networks; gateways alone are dual-homed, fixed upstreams.

## Functional evidence

- DieselBridge migrated its fresh database and seeded two synthetic tenants,
  owners and customers. Both owners log in and see one own customer. Foreign
  reads return403 in both directions; unauthenticated access returns401/403.
- Browser signed in as Staging Alpha, rendered Shop Cockpit and the one
  Synthetic Alpha Fleet customer. Saved screenshot shows the signed-in Inventory
  surface the user subsequently browsed, rather than mislabeling it as Customers.
- Native Celery schema gate passed. Independent inspect finds only
  `localtest.database_probe`, imports[], Beat{}, queue `db-local-test`, Redis13.
  Repeated benign probes leave exactly one receipt with execution_count1 and
  report two customers. This is a synthetic database task, not production job
  delivery acceptance.
- TPH seeded two locations, one hidden, one hashed manager PIN and one manual
  synthetic research job. Actual public location API returns the visible fixture;
  hidden direct lookup returns404. Native manager PIN/JWT flow passes, including
  independent HS256 issuer/audience validation. Wrong PIN403 and admin401 pass.
- Browser rendered the TPH homepage and LOCAL TEST banner, verified the native
  PIN/manager confirmation, and reached `/spot-changes`. This synthetic manager
  has no operational yard records; full HR/admin Auth0 was not bypassed or tested.
- Real TPH job service atomically claimed and completed the one manual job with
  attempts1 and post linkage, producing one saved draft, zero published posts and
  zero scheduled jobs. Only research generation is replaced by a local fixture.
  Subsequent polling, probes and restarts leave the same job/draft counts.
- Actual identity service returns skipped/not_configured/processed0 before any
  provider lease or external call. Inspected WorkOS cursors, delivery, messaging,
  payment, notification and provider-outbox state contain no production work.

## Safety and failures resolved

TPH's direct server entrypoint starts business schedules even with the connector
flag disabled. Test bootstrap imports its exported server, avoiding that direct
block, and sets DISABLE_SCHEDULER=true. No cron enqueue, Beat or production queues
run. Native local log maintenance remains distinct from business schedules.

Both gateways add an enforced same-origin CSP, preserving the application's
existing policy. Scripts, connections, frames, fonts and images cannot use remote
provider origins. Browser stayed on local URLs; no production request was used as
a test. This is CSP containment, not a guarantee against user-driven top-level
navigation to an external site.

Fresh database/session/API secrets were generated on the Mac, private mode0600,
and are distinct from original staging. No live provider keys exist. TPH Square
initialization needs an explicit invalid noncredential marker in sandbox mode;
Auth0 uses nonfunctional `.invalid` placeholders. External identity, maps,
payments, communications and research behavior remain intentionally unavailable.

Initial TPH readonly startup failed creating backend/logs. Verified image UID1000,
then added only a bounded non-executable private logs tmpfs. Startup subsequently
refused an absent Square constructor value; the explicit invalid marker resolved
that without credentials. Gateway HTML then exposed an oversized upstream CSP
header; bounded32KiB proxy buffers resolved502. Seeds were never repeated.
Phase journal, private failure logs/config snapshots and redacted errors remain.

The first TPH acceptance process imported a logger with background maintenance,
printed passing checks but did not exit. Owner stopped only that exact probe PID,
then changed the operator probe to independent JWT verification and explicit exit.
Corrected tools-source probe passed normally. The application image's original
unused probe file is not the corrected operator acceptance entrypoint. Runtime
application/worker adapter code is unchanged. One independent read-only WorkOS
probe overlapped the planned restart; its explicit-exit retry passed without OOM.

## Persistence, backup and recovery

Scoped restarts of only the two new stacks preserved all seeded state and worker
receipts. Post-restart probes again report database receipt1 and TPH job attempts1,
draft1, published0, scheduled0.

Private PostgreSQL custom-format and Mongo archive backups restored into new
uniquely named check databases without overwriting either primary. Independent
QA verified primary/restore PostgreSQL counts2/2/2/1 (tenants/users/customers/receipt)
and Mongo counts2/1/1/1/0 (locations/PIN/job/draft/published). Backups and restore
databases remain; this does not establish off-device disaster recovery.

Separate `com.macapps.teststacks.recover` LaunchAgent is loaded and exited0 at
bootstrap. It recovers only accepted test stacks without migrations, seed or
scheduled enqueues. FileVault still requires local unlock/login. These new app
stacks were not reboot-tested during the original observation window.

## Gates and preserved staging

Seven focused configuration checks passed, plus independent image-shape/isolation
negatives and source syntax review. Independent QA and Security both GO for final
private runtime, worker boundaries, non-delivery, backup/restore and persistence.
They made no implementation edits.

Original baseline SHA256 remains
`1e7618809a071feb45cadb84667827c97c483c63f7e3fbf645b92628b4544d1e`.
All four original staging container IDs/start times/source match prior evidence.
Final redacted snapshot:88samples, zeroissues, still observing. Original October21
7:09:59PM through October22 7:09:59PM America/New_York window and existing heartbeat
remain unchanged. No reset, duplicate automation, worker replay, DNS change,
Railway deploy, setting/secret change or production data action occurred.

[Operator guide](../../deploy/mac-test-apps/README.md).
[Initial redacted runtime receipt](mac-test-apps/2026-10-21-runtime.json).
[Final redacted runtime receipt](mac-test-apps/2026-10-21-final-runtime.json).
[DieselBridge signed-in screenshot](mac-test-apps/dieselbridge-inventory.png).
[TPH homepage screenshot](mac-test-apps/tph-home.png).

Private copies are accepted and usable through SSH. PR/merge/protected checks,
public ingress, live providers and completed24-hour observation are separate
states; no production release or public readiness is claimed.

## Source publication check

The pre-push credential scanner rejected three Mongo URL templates/concatenations.
Inspection confirmed generated-variable references, not embedded credential
values. Backup URL assembly now uses structured URL APIs and escaping. Compose
uses the standard Mongo password placeholder; controller validation requires all
six private values to contain at least32characters before any Docker operation.
Missing/short Mongo credentials fail before Docker in the new regression.
Seven focused checks pass; unchanged scanner reports no HIGH findings, with no
scanner bypass. The revised backup path passed another actual restore into new
check databases, retaining both primary databases. Only configuration/tool source
changed; no application image, queue or running service was replaced.
