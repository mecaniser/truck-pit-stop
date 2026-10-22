# TPH-INFRA-005 preserved rehearsal recovery preparation

Accountable implementation owner: Security & Identity implementation subtask,
coordinated by Product & Delivery Lead. Independent QA/Security reviewers must
not be the implementing agent. Existing PR623 remains the release boundary.

The Docker interruption stopped the accepted Mongo, router and active
`railway-simulation` at approximately 17:39UTC on October22. The inactive
`mac-backup` was already stopped after the accepted return switch. Read-only
inventory confirmed the same four accepted IDs and immutable images, owner
`railway-simulation`, epoch5, watermark8, three accepted and one rejected
admission, and five accepted fake effects. This preparation does not change the
failed original soak or imply live backup readiness.

The proposed helper `deploy/tph-mac-backup/recover_existing.py` uses the existing
operator lock and sealed configuration validation. A reviewed private inventory
plan binds its source hash, manifest, accepted containers, SQLite logical state,
protected14 snapshot and the existing new observation baseline SHA256
`0002ccdd4d0b797e4a79543c1be310cd7a292d8f23b8ecba786031dec16ed328`.
Only exact Mongo, recorded active owner and router CIDs may be started, in order;
there is no Compose recreation, new volume, owner promotion, worker, provider
call, message, payment, booking mutation, PIN verification, seed or effect replay.
The inactive app remains stopped. A fixed local read-only authority GET verifies
restored watermark/PIN usage and instance binding before router availability.

The separate PR622 controller recovery must first expose and pass exact accepted
identity/config/baseline checks with no uncertain recovery or operation. The
helper refuses if those flags are absent. Current source preparation is therefore
**not permission to start containers**. An exact proposed plan and helper must
receive fresh independent QA/Security approval before remote recovery.

Focused tests cover read-only settled SQLite inspection, unknown effects and
receipt mismatch refusal, reviewed-plan drift, prior-attempt refusal, exact
three-CID order, protected/state drift, partial-start failure retention, explicit
controller identity gate and fixed native-authority GET binding. Test results
are source evidence, not actual recovery acceptance. Failure/started/completed
receipts are exclusive and no automatic retry or cleanup exists.

Runtime acceptance remains pending. After approved recovery, record the exact
three starts, unchanged inactive identity/start, control/ledger hashes/counts,
restored authority/PIN checkpoint, protected14 and monitored4 preservation, and
new observation status. Retain the interruption evidence and all previous
rehearsal failures. Production Railway, provider settings and native live flows
remain outside this action.

## Local source checks

October22 local candidate: 11 new focused recovery tests passed; the complete
rehearsal suite passed42 tests. `py_compile` and `git diff --check` passed.
The full suite emits pre-existing SQLite connection ResourceWarnings from the
older control tests; the new focused suite completes without those warnings.
No remote recovery helper was installed or executed and no container was started.

Runtime alignment preflight: intended worktree
`codex/tph-mac-backup`, HEAD `dce49b3d906eaa5d4317e331e10e724e7cf0f5b4`,
was clean before this scoped implementation. No local DieselBridge5173/8000
listener was present. This infrastructure helper does not serve a local product
UI; no local server or browser visibility is claimed. Existing staging and
Railway services were not changed by this preflight.

## Independent gate findings retained

The first source candidate had a real identity-check gap: later comparisons did
not bind container start timestamps, and completion checked only the running set.
It was corrected to preserve the inactive start, capture each authorized start,
require all expected starts/running states throughout subsequent checks, and
require all three recovered services healthy at completion. That revision
(`76fe492d…`) passed14 focused /45 cumulative tests and source review; it did not
start containers.

Actual-plan QA then refused plan `6d708…` before any start: repeated Docker
inspection returned the same two full Mongo mount records in reversed list order,
changing the raw-array hash. That unapproved plan and installed source are
preserved. No recovery attempt markers were created and no containers started.

The corrected candidate validates mount type/destination and refuses duplicate
destinations even across different types. It sorts those validated complete
records by destination/type before hashing; no fields are discarded. Tests use
the accepted Mongo's full two-mount metadata and prove permutation equivalence
through inventory, expected-runtime comparison and the complete simulated recovery
path. Changed Source, RW and Propagation still refuse identity comparison; extra
persistent mounts and both same-type/cross-type duplicate destinations refuse.
Config and HostConfig arrays remain exact. Dictionaries were already hashed with
sorted keys. No evidence justified normalizing commands, environment entries,
mount specification arrays or security options, so those remain unchanged.

Current focused recovery tests:17 passed. Complete rehearsal suite:48 passed.
`py_compile` and `git diff --check` passed. These supersede the earlier source
check counts above. Fresh QA/Security and a newly generated exact plan remain
required; the prior plan cannot authorize this changed helper. No remote helper
installation, start or runtime acceptance was performed by this correction.

## Actual partial recovery and separate resume preparation

The independently approved original one-shot recovery actually started Mongo at
`2026-10-22T20:03:53.486818263Z` and the recorded owner at
`2026-10-22T20:04:00.591453794Z`. Both became healthy. It then failed on the fixed
local authority GET before starting the router. The old helper discarded Docker
stderr and retained only the exception type; no precise failure cause can be
reconstructed. A later read-only GET returned200 with the exact restored database,
source, watermark8, PIN usage3, owner prefix and authority hash. This does not
establish that the first failure was a transient503 or any other specific cause.

The inactive app and router remain stopped at their original starts. The old
started and failed markers are retained, no old marker was cleared, and the old
helper still refuses a retry. The proposed separate `resume_existing.py` freezes:

- original helper SHA256 `270960841fd8af20b24a420c978cf9b88bc42f2b7c1fef7a9c52d6c7b74c58ab`;
- old reviewed plan raw SHA256 `8868ac83858a1370d256cac26dc5766b637f33b9a9448580dc8b814a048975f7`;
- canonical original-plan binding in the unchanged started receipt;
- exact original started/failed receipt hashes;
- two actual authorized start timestamps, original stopped router/inactive starts,
  all accepted identity/configuration/mount/network hashes, shared SQLite state,
  protected14 and monitored4 snapshots.

A new exact private plan must pass fresh independent QA/Security approval. Only
one `docker start` for the existing router CID is admitted. All first-two and
inactive starts/running states remain fixed throughout. Fixed bounded local GETs
before and after that start reprove the restored authority/checkpoint and retain
sanitized Docker/timeout/HTTP/parse/proof diagnostics if a future failure occurs.
No native PIN, checkpoint write, provider, effect retry, owner switch or database
reset is involved. Exclusive new resume journals preserve every old marker.

Resume source checks:9 focused tests passed; all57 cumulative rehearsal tests
passed; `py_compile` and `git diff --check` passed. Negatives cover changed or
stopped first-two containers, inactive start drift, router already running,
uncertain state, protected drift, duplicate resume markers, altered old evidence,
and captured failed GET diagnostics without raw payloads. Positive tests prove a
single router-only start and preservation of the original failure. These are
source checks only: no resume helper was installed or executed by this preparation.

## Router diagnostic preparation after the consumed resume

The actual router-only resume also failed before changing its original start.
Its retained authority GET diagnostics were accepted/HTTP200. Docker start output
was discarded in that path, so neither attempt establishes the exact Docker
failure cause. Read-only inspection found the accepted relay PID67282 listening
only at127.0.0.1:18310 with its reviewed command/source and original start. Daemon
exposer events are suggestive of port interaction but are not captured
EADDRINUSE evidence. No relay-stop/port-fix helper was implemented or applied.

The new `diagnostic_router_start.py` instead allows one independently approved
exact-router start **with that relay unchanged**. Both consumed attempts are
bound by immutable helper/plan/receipt hashes. The current two healthy starts,
original stopped router/inactive starts, state5/8, PIN admissions/fake effects,
protected14, new monitored4 and full relay identity/listener must match the new
private plan. No old marker is cleared and no data/provider action is invoked.

The invocation retains at most64KiB total stdout/stderr in exclusive0600 private
files, exit/timeout/output-limit status, hashes and immediate router observation.
Only captured literal error text can classify a binding failure. Timeout/overflow
remains uncertain and blocks any repeat. The wrapper may terminate only its own
Docker CLI child on timeout/overflow; it has no container-stop or relay-stop
command. Nonzero exits retain failure; a zero exit needs same-start health,
read-only authority proof and unchanged protected/relay state for completion.

Diagnostic source tests:8 focused passed, all65 cumulative tests passed;
`py_compile` and `git diff --check` passed. Real local child processes prove
bounded private capture and literal binding-error classification without Docker
or provider calls. Negative tests cover prior diagnostic markers, plan/relay
identity drift, uncertain output and no repeat; positive simulation proves a
single healthy accepted start. This is source preparation only. No diagnostic
helper was installed or executed remotely, and fresh independent source/plan
review remains required. A possible port-aware recovery stays on hold until the
actual result is understood.

## Captured cause and port-aware source preparation

The actual independently approved diagnostic start returned exit1. Its254-byte
stderr SHA256 is
`63129cf162b8927bf5e097c0e8d4fb8e54540fbea1caa1331e50729725a95c36`;
the captured Docker error explicitly reports `bind: address already in use` for
TCP127.0.0.1:18310. The original router start is unchanged, the two authorized
containers remain healthy, and relay PID67282 remains the sole listener. Unlike
the earlier attempts, this result establishes the actual binding failure. All
consumed diagnostic journals and raw private command logs are preserved.

The proposed `router_port_recovery.py` binds that captured evidence and every
prior helper/failed attempt. After fresh independent source/private-plan approval,
it can TERM only the exact reviewed relay process, wait for exit/free port, and
attempt the exact existing router once. Its output is bounded to64KiB in new0600
`router-port-stdout/stderr.log` files. The single router start must become healthy
and preserve all other container starts, shared state and protected14/new4.

Only if port18310 is free afterward does the reviewed restoration launch the same
relay source/executable/argv/cwd. The new PID is journaled before readiness and
must bind only127.0.0.1:18310. A fixed read-only status GET and authority proof
confirm owner/epoch5/watermark8/PIN usage3 without another PIN or native mutation.
Unexpected port ownership, including Docker backend ownership, refuses restoration;
no other process is killed and no port is moved. Nonzero/uncertain starts or failed
relay restoration retain new exclusive failure/uncertainty receipts and cannot
repeat. Failure-side boundary observations are retained without concealing the
initiating error or authorizing cleanup/retry.

Source checks:12 focused port-recovery tests and all77 cumulative tests passed;
`py_compile` and `git diff --check` passed. Tests cover exact single TERM and PID
reuse refusal, changed partial state, foreign/Docker port owner refusal, captured
bind-evidence integrity, one router-only start, exact relay argv/cwd/new listener,
failed/uncertain start and failed restore without retries, unique bounded private
capture and preservation of old logs/markers. No remote helper installation or
port recovery was performed by this preparation. Fresh independent source/plan
acceptance is still required before applying it.


## Independent runtime acceptance — October 22, 2026

Recovery is complete for the preserved synthetic rehearsal's availability. The exact same Mongo and active simulation containers are healthy at their single authorized recovery starts20:03:53.486818263UTC and20:04:00.591453794UTC. The same router is healthy at20:30:40.663990507UTC. Inactive Mac backup remains stopped with its original05:12:05.03396976UTC start.

All failed attempts remain. Backend logs corrected the early checkpoint-failure assessment: both failures reached router Docker start. A separately approved captured diagnostic proved exit1 because the accepted host relay already owned127.0.0.1:18310. A fresh independently reviewed planb01bfa79/helperf0f7bd07 authorized one exact relay stop, one router start and restoration of the same reviewed relay on the same loopback port. It succeeded; old relay67282 was replaced by reviewed-source relay25245. No unknown process, Docker process, port mapping, container identity, volume or application source was changed.

Independent QA and Security runtime postchecks passed. Native authority proof confirms restored database/source, watermark8, PIN usage3, authority hash and exact active instance. SQLite logical hash, epoch5, admissions3accepted/1rejected and five accepted fake effects remain unchanged. Existing consumed recovery/resume/diagnostic records are retained; there is no new uncertainty or replay. No fresh switch/failback or provider effect was performed.

PR622's protected14/current accepted snapshot still matches after rehearsal recovery; no additional identity acceptance was needed. Both originalfailed and newactive observation baselines are intact; the new observation had66 healthy samples and zero issues at the final receipt. Actual provider/SMS/scheduler flags remain disabled; `activate-live` exits1 with the enforced refusal.

Final local source verification: PR62236 tests; PR62377 tests, including17 recovery,9 resume,8 diagnostic and12 port-sequencing tests. Each new helper and exact runtime plan received fresh independent QA/Security review. No source was pushed or CI rerun during safety work. Detailed redacted evidence: [partial failure](TPH_INFRA_005_PARTIAL_RECOVERY_20261022.json), [captured Docker cause](TPH_INFRA_005_ROUTER_START_DIAGNOSTIC_20261022.json), [successful recovery](TPH_INFRA_005_RECOVERY_RUNTIME_20261022.json).

Merge readiness still requires completion of the separate24h infrastructure window, final independent acceptance and one current-main/final-head CI run per PR in sequence. Existing greens are historical because main advanced. Live zero-loss backup activation remains separately blocked on production data authority, primary/worker/webhook fencing, native provider idempotency/reconciliation and exact-release failover/failback approval. This recovery does not supply or waive those proofs.
