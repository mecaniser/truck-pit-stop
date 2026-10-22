# TPH Mac backup rehearsal

This prepares and tests a synthetic backup/restore and switch in both directions. It does **not** make the Mac an approved live backup. Railway production, its database, domains, jobs, provider settings and credentials remain unchanged.

Both native application copies run on the Mac. The first is explicitly named `railway-simulation`; it is not the real Railway service. Their database is synthetic, restored using real MongoDB backup tools, and shared as one authority. No production records or credentials are copied. No native booking, message, payment, webhook or job mutation is admitted. Native PIN verification is the only admitted application mutation, to prove continuity across switches. A separate fake provider tests operation deduplication; native live providers do not yet consume this ledger.

## Operator commands

Run `deploy/tph-mac-backup/tph-backup status` from this checkout, or install that file as `~/.local/bin/tph-backup`.

```sh
tph-backup status
tph-backup switch mac
tph-backup switch railway
tph-backup tunnel
```

`mac` and `railway` select **rehearsal copies on the Mac**. They never change production. With the tunnel running, open <http://localhost:18310>. The page banner and `/__backup/status` identify the simulation and active owner. The private synthetic PIN is stored on the server in `~/mac-hosting/tph-backup-rehearsal-v3/private/credentials.json`; do not publish it.

`rehearse` is a one-shot acceptance run. It refuses a repeat rather than deleting failures, resetting state or replaying uncertain work. `activate-live` always refuses. Never edit the sealed manifest, remove an initialization marker or rebuild an accepted container to force a retry. Investigate retained evidence first.

The operator serializes changes, drains admissions, refuses any pending/unknown result, stops the exact old container, checks the exact ready target, and verifies current authority/watermark before promotion. A lost acknowledgment freezes the rehearsal until definitive fake-provider reconciliation. There is no automatic timeout takeover. Reversal preserves the same database and operation ledger. A native request with an uncertain outcome needs investigation; the synthetic cancellation command cannot cancel it.

## Zero-loss requirement for a future live backup

The user requires zero lost records. Stale, unavailable or unprovably current data must block activation. Periodic snapshots alone do not meet this requirement.

Live readiness requires a separate reviewed production release:

1. Establish a durable data authority that survives the intended Railway outage, with demonstrably current records and any required files. Include transactional write admission and recovery evidence.
2. Put both real hosts, workers and webhook consumers behind a shared fencing mechanism. Stop new primary work, settle admitted/inflight work, and prove the old owner cannot write or dispatch. An unreachable primary is not proof that it stopped.
3. Integrate stable business-operation identifiers, payload binding, durable outcomes and provider reconciliation into native payments, email, SMS and jobs. The fake ledger is not a replacement for this integration. Never retry an unknown payment or message blindly.
4. Prepare production credentials, host/domain/callback settings and a controlled public routing change. Do not expose this synthetic rehearsal or repoint the production domain to the test app.
5. Test failover and failback against that exact release and data model, including split-brain, stale data, provider uncertainty and recovery of writes made on the Mac. DNS reversal alone cannot reconcile records.

Until these prerequisites pass, keep Railway authoritative and live activation locked. This work deliberately cannot claim a tested switch of the actual live service while leaving its safeguards unchanged.

## Evidence and isolation

Private receipts live under the dedicated server root, mode 0700. No Docker socket is mounted. The four rehearsal containers use one internal-only network; the router has no working published port on Docker Desktop’s internal network. A reviewed host relay binds loopback18310 and uses fixed-container Docker exec transport. Existing fourteen application/staging container identities, configuration and accepted monitor baseline are checked before and after operator changes. Redacted verification belongs in `docs/verification/TPH_INFRA_005_MAC_BACKUP.md`.

The initial Mongo permission failure (v1), native invalid-index seed failure (v2), and Docker internal-network transport failure (v3 first harness) are retained in separate private receipts. The corrected `rehearse_v2.py` uses the same sealed v3 instances and a separately hashed transport extension. Backup index equality covers created fixture indexes before native application startup, not complete production schema/index compatibility. The unsupported native monthlySquareLocationId index is outside this change.

## Recovery after the Docker interruption

`recover_existing.py` is a separate, one-shot recovery helper. It starts the
**same accepted** Mongo container, recorded `railway-simulation` owner, and router,
in that order. The inactive `mac-backup` stays stopped. It does not initialize,
seed, switch owners, replay admissions, reconcile effects, or start the host relay.
Existing failures, journals, volumes, images and sealed files remain intact.

Before using it, complete the separately reviewed deployment-controller recovery.
This helper requires its explicit `identity_matches: true`,
`uncertain_recovery: false`, configuration/baseline matches and no uncertain
operation. Missing flags or a mismatch refuse recovery. It pins the four monitored
containers to the existing `20261022T192823Z` observation baseline and compares all
fourteen protected identities, starts, network and configuration hashes before
each start and afterward. Recovery cannot repair the failed original observation
or pass the new 24-hour observation early.

Install the reviewed helper as a **separate extension**, retaining its source hash;
do not alter the accepted manifest or replace sealed operator files. With its
source and proposed private plan independently reviewed, use on the Mac:

```sh
umask 077
python3 /path/to/reviewed/recover_existing.py inspect > /path/to/private/plan.json
# Record and independently approve this exact file's SHA256 before starting.
python3 /path/to/reviewed/recover_existing.py recover \
  --approved-plan /path/to/private/plan.json --sha256 APPROVED_FULL_SHA256
```

Inspection opens the control and fake-provider SQLite databases read-only. It
requires owner epoch5/watermark8, three accepted PIN admissions, one rejected
admission, five accepted fake effects with matching provider-ledger receipts,
no unsettled work, the same four accepted container IDs/images/configurations,
and the fixed internal-only sandbox topology. No provider credentials are read
or printed. After the active owner becomes healthy, a fixed read-only local
`GET /authority` checks the restored database identity, source, exact authority,
watermark8, PIN usage3 and container hostname binding before starting the router.
The logical SQLite contents and all protected services must remain unchanged.

The helper records exclusive `existing-recovery-started.json` and then either
`existing-recovery-completed.json` or `existing-recovery-failed.json` privately.
Any previous attempt refuses a repeat, including a partially successful one.
Investigate retained evidence and obtain a separate reviewed continuation instead
of removing markers, stopping recovered services automatically, or rerunning it.
No completed receipt or actual restart is claimed by the source preparation.

Recovery inventories canonicalize only the validated mount-list order. Every
mount destination must be unique, including across mount types; the entire
metadata record remains in its identity hash, including source, read/write mode,
driver and propagation. Reversing Docker's Mongo mount-list order therefore
preserves the plan, while changing any mount metadata refuses it. Config and
HostConfig arrays retain their exact accepted order; command arguments, duplicate
environment semantics and other potentially ordered fields are not normalized.
All four expected start timestamps and running states are checked throughout.
Each authorized start captures its new timestamp, which must remain fixed;
all three recovered services must be healthy at completion.

### Separate continuation of the recorded partial recovery

The first actual recovery stopped after starting the same Mongo and active owner
healthy, before starting the router. The original helper discarded Docker stderr;
the authority GET failure's cause is **unproven**. A later read-only GET succeeded.
The original started/failed markers remain immutable and the original helper
still refuses a repeat.

`resume_existing.py` is a separate reviewed continuation for this exact partial
state. It pins the old helper, old plan and started/failed receipt hashes, requires
the two observed new start timestamps and healthy state, and requires the router
and inactive app still stopped at their original starts. Any discrepancy,
unsettled state, protected-container change or previous resume marker refuses.
It can start only the preserved router CID; it cannot restart Mongo or the owner.

The dependency remains the already reviewed `recover_existing.py` at the server
root, SHA256 `270960841fd8af20b24a420c978cf9b88bc42f2b7c1fef7a9c52d6c7b74c58ab`.
Install the new resume helper separately without replacing that dependency.
Before its only mutation, obtain fresh independent QA/Security approval of both
source and the exact new private plan:

```sh
umask 077
python3 /path/to/reviewed/resume_existing.py inspect > /path/to/private/resume-plan.json
# Inspect ready:true and approve the exact plan SHA256 independently.
python3 /path/to/reviewed/resume_existing.py resume \
  --approved-plan /path/to/private/resume-plan.json --sha256 APPROVED_FULL_SHA256
```

Inspection returns `ready:false` with a bounded diagnostic if its fixed local
read-only authority GET fails. Diagnostics classify Docker exit, timeout, HTTP,
JSON parsing and proof mismatch; only status/booleans, stderr byte count and hash
are retained. No raw response, authority value, credential or stderr is printed.
The same GET is repeated around the router start; these are read-only checkpoint
checks, never provider retries. Exclusive `existing-resume-started/completed/failed`
receipts preserve the original failure; any resume attempt blocks another run.

### One diagnostic start with the relay unchanged

The separate resume also failed before changing the router. Its recorded authority
GET proofs succeeded; Docker start output was not retained. The loopback port is
owned by the reviewed relay, and daemon events suggest a binding interaction,
but neither failed attempt captured the actual Docker error. Do not label that
cause as established or stop the relay on inference alone.

`diagnostic_router_start.py` prepares a newly reviewed, one-shot diagnostic start
of the existing router with the relay **left running and unchanged**. Its plan
pins both consumed attempts and helpers, the exact partial container state,
shared state, protected14/new monitored4, and relay PID/start/command/cwd/source
hash and sole loopback18310 listener. The helper has no relay-stop or port-fix path.
Fresh independent source and exact-plan approval are required before `diagnose`:

```sh
umask 077
python3 /path/to/reviewed/diagnostic_router_start.py inspect > /path/to/private/diagnostic-plan.json
# Review and approve the exact ready:true plan SHA256 independently.
python3 /path/to/reviewed/diagnostic_router_start.py diagnose \
  --approved-plan /path/to/private/diagnostic-plan.json --sha256 APPROVED_FULL_SHA256
```

Only one `docker start <exact-router-CID>` is issued. Total stdout/stderr capture
is limited to64KiB in new0600 private files with exit status, byte counts and
hashes recorded. The wrapper records the immediate router state and verifies
state/protected containers and unchanged relay afterward. A nonzero exit is a
retained failure, never permission to retry. Only literal captured binding-error
text produces a known-bind classification. A35-second timeout or capture overflow
is uncertain; terminating only this invocation's Docker CLI cannot prove whether
the daemon started the router, so no second start is allowed. A zero exit must
prove the single new router start healthy, unchanged other services and a fresh
read-only authority check before completion.

Exclusive `router-diagnostic-started/command/failed/uncertain/completed` receipts
preserve all older failures. Do not publish the raw private command logs. The
port-aware continuation remains on hold until actual captured evidence supports
a separately reviewed action; this diagnostic helper never performs that action.

### Port-aware recovery after the captured bind error

The reviewed diagnostic attempt returned exit1 and retained the actual Docker
error `bind: address already in use`. Its254-byte private stderr has SHA256
`63129cf162b8927bf5e097c0e8d4fb8e54540fbea1caa1331e50729725a95c36`.
The accepted relay remains the sole loopback18310 listener; the router remains
stopped. This captured result now supports a separate, narrowly scoped port fix.

`router_port_recovery.py` requires fresh source and exact-private-plan approval.
It binds every consumed helper/attempt plus that diagnostic evidence, and verifies
the exact two healthy starts, unchanged stopped router/inactive app, control and
provider state, protected14/new monitored4, and relay process/source/listener.
Under the existing operator lock it rechecks the exact relay before one SIGTERM,
waits for that PID to exit and port18310 to become free, then issues one start for
the existing router CID with new bounded private capture paths. It never signals
a Docker backend or another process and never recreates containers or volumes.

```sh
umask 077
python3 /path/to/reviewed/router_port_recovery.py inspect > /path/to/private/port-plan.json
# Independently approve the exact ready:true plan SHA256 before recovering.
python3 /path/to/reviewed/router_port_recovery.py recover \
  --approved-plan /path/to/private/port-plan.json --sha256 APPROVED_FULL_SHA256
```

The router must retain its single new start and become healthy with unchanged
shared/protected state and a valid read-only authority proof. Only if host port
18310 is then free does the explicitly reviewed restoration step launch the same
relay source with the same Python executable, arguments and working directory.
The new relay PID must own only127.0.0.1:18310, and a fixed status GET must prove
simulation owner/epoch5/watermark8. The new relay PID/start/source is journaled.
Any unexpected listener, including Docker's backend, stops the workflow without
killing it, moving ports or starting another relay. A failed restore is retained
without automated compensation; neither first-two container nor inactive app is
restarted. Exclusive `router-port-*` journals and unique command/relay logs preserve
all previous attempts. No automatic repeat or marker reset exists.
