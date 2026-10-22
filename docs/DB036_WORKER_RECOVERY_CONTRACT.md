# DB-036 worker recovery contract

Status: Final implementation contract, 2026-10-21. Accountable delivery
owner: Backend & Integrations. Contract owner: Architecture & API Contracts.
Branch: `codex/motive-worker-recovery`. High-risk worker/data lane; independent
QA and Security offline GO reported by delivery; their evidence belongs in the
verification receipt. Railway outage blocks release and production acceptance.
This document is not a release approval.

## Outcome and evidence boundary

A transient provider read failure should preserve already validated collection
work. One approved Motive driver source should serve the configured local fleets
without rescanning the provider directory for each fleet. Import continues only
when complete source evidence and each fleet's existing guards pass.

The missing schedules and exact 150-second fuel/driver crashes are separate
symptoms. Neither missing application logs nor an early exit establishes OOM,
application timeout, provider throttling, or successful collection. Railway
incident `QH8L8B3E`, reported active since 07:24 UTC on this date with builds
paused, is a relevant external condition, not proof of every historical cause.

## Safest implementation boundary

Keep current service separation, cron schedules, replicas, mounts, allowlists,
credentials, import schema and fleet assignments. Add bounded read recovery and
private checkpointing inside existing one-shot collectors. Do not introduce more
parallel browser processes as a reliability fix. No public API or migration is
required for collector checkpoints. Reuse existing per-fleet database journals
for durable driver source and uncertain-commit recovery where possible.

Source documents retain their existing import contract. A checkpoint is a
private intermediate artifact, never an importable partial source. `complete`
becomes true only after all original terminal/company/directory/assignment/time
checks have passed. Existing permitted unavailable observations remain permitted;
retry exhaustion must not invent an unavailable row or new fail-open behavior.

## Lifecycle and diagnostic contract

Worker startup/preflight and collector phase events distinguish early startup,
browser launch, login, company/timezone checks, directory work and task failure.
The shared task helper emits JSON for phase, task start, completion, failure and
resume, with bounded reason/attempt/elapsed fields. Fleet orchestration reports
source start, recovered pending work and independent projection completion.
These additions do not promise a heartbeat or event for every lock, importer,
cleanup or process-exit transition.

New shared events omit raw provider contents, VIN, names, coordinates, secrets,
URLs, environment dumps, subprocess arguments, SQL parameters and raw exception
messages. Existing driver identity diagnostics retain their bounded provider
identity/unit fields; they are not raw browser errors or source dumps. Failure
markers contain only a bounded retryable flag, safe reason and phase. Startup,
phase and process-exit evidence do not establish a verified import.

Read subprocesses own a process group. The supervisor terminates the group on
completion, failure, timeout or handled cancellation; browser close is bounded
at three seconds. Existing commit journals remain intact. Cleanup limits the
risk of a stuck execution blocking its next schedule; offline tests do not prove
that the provider's missing schedules or exact 150-second crashes are fixed.
Do not retry a whole import blindly after an uncertain commit.

## Read retry contract

Tasks are vehicle reads for location/health, driver details, vehicle/date fuel
reports and existing daily trip report windows. New shared retry classifies only
Playwright TimeoutError and an explicit allowlist of transient transport errors.
It allows up to three attempts with bounded jittered waits. Fuel/trip report
actions recreate their report page and repeat filter checks. Location and driver
tasks use one outer attempt, preserving their existing internal read/identity
retry budgets rather than multiplying them. Existing collector-specific handling
of permitted unavailable observations remains unchanged.

Company/session/origin/identity/filter/layout/validation failures do not acquire
new retry permission. Unknown errors fail in the shared helper. Retry cannot
clear guards, alter dates, broaden identities, extend source age or replay an
uncertain commit. The overall supervisor deadline still bounds Node/browser
work. A new shared retry does not wrap every provider action or importer stage.

## Collection checkpoint contract

Task snapshots store a version, integrity digest, original creation time,
completed task map and binding digest. The binding includes collector-specific
scope, resolved output path, provider account identity, tenant, actor and
reviewed allowlist. Collector scope includes company, timezone and canonical
collected directory; drivers add performance ranges and exact configured fleet
set, fuel adds dates, and trips add windows. Task keys include the read identity
and relevant date/window. Authority-changing scope cannot silently inherit an
old checkpoint. Absolute expiry derives from immutable creation time and the
collector's fixed maximum age; no sliding expiry field is required.

Write only complete validated task results. Private directories are mode 0700,
files 0600; use exclusive private temporary writes and atomic rename. The Python
resume selector rejects symlink/nonprivate/oversized artifacts and unsafe
run-directory candidates; the task helper validates regular private checkpoint
files, version, shape, binding and integrity before reuse. A checkpoint digest
detects accidental alteration; a digest alone
is not authentication, so storage ownership and path confinement remain guards.
Never store login/session secrets. Never log checkpoint/source contents.

When matching state storage survives, restart reauthenticates, reverifies
company/timezone, reconstructs the directory and compares the full bound scope.
Location and drivers recheck current identity before accepting cached rows;
health/fuel/trips reconstruct current vehicle identity before task reuse. Driver
final directory/assignment and collector-specific terminal checks remain. Reusing
a result does not waive its current identity check. Any mismatch invalidates reuse and fails closed;
never stitch observations across different companies/directories/windows.
Reused records retain their original observation time, never the resume time.

Expiry is absolute, finite and cannot slide forward on load or retry. The
implementation must expose a fixed tested bound for each collector and also
respect every stricter existing importer freshness/window rule. Fixed
limits: location 10 minutes; health, drivers, trips and fuel 30 minutes.
Reject future/invalid starts and expired checkpoints before reading task data.
Restarting a legitimate fresh collection uses a new run identity and cannot
silently refresh old observations. A failed collection leaves the source
incomplete. Final complete source requires the original complete directory and
post-collection validation. No incomplete import is allowed.

Task recovery requires the same private state storage. Driver read checkpoints
under `/tmp` can disappear when a container is replaced. Completed driver source
prepared into PostgreSQL journals survives that loss; this is distinct from
partial browser-task durability. Receipt-bearing source directories are excluded
from read resumption so a collector cannot overwrite uncertain import evidence.

## Shared driver source and fleet projection

1. Validate the entire fleet configuration before collection. Acquire existing
   stable per-fleet journal locks in deterministic order, avoiding new lock
   cycles. Check every fleet's tenant, actor, customer and company authority.
2. Inspect and reconcile each fleet's actionable pending source or uncertain
   commit before fresh collection. Reuse its immutable saved source and verify
   the existing receipt/read model. Recovery failure stops the run. Expired
   unattempted sources follow the retention rule below.
3. Collect one complete company-scoped driver source. Before the first fleet
   write, retain enough durable source and exact target-set information for a
   later process to finish remaining fleets without another directory scan.
   Prepare one source_saved row per fleet in one database transaction, before
   any projection. All target rows receive the same immutable source; partial
   target distribution cannot commit. Verify all held journal locks/bindings and
   require matching company, tenant and actor plus distinct customer/worker keys.
   `/tmp` alone does not provide durable reuse across container restarts.
4. Project the same immutable source hash through each independently authorized
   fleet's normal runner and its own durable journal/receipt identity. Recheck
   current membership, assignment, VIN/reviewed binding and actor authority at
   import. Source availability grants no fleet permission. Do not share a
   receipt or mark other fleets verified because one fleet committed.
5. If a later fleet fails, retain verified earlier receipts. Resume unfinished
   fleets from the same still-valid source after recovery. An invocation that
   actually reconciles pending rows returns after verifying recovery,
   without a new scan. It reports recovered rows only; it claims all-fleet shared
   generation completion only when every target journal proves the same source.
   Do not reapply verified fleet writes. Never use an old verified fleet journal
   as permission to skip a new source's projection. A run is complete only when every target
   fleet independently verifies that same source generation.
6. Check the complete source's 30-minute freshness before atomic preparation
   and before each fresh fleet projection. During pending recovery, validate
   artifacts first. Retain expired `source_saved`/`validated` rows unchanged and
   skip them with `driver_source_expired`, `committed:false`; these stages have
   not crossed the uncertain-commit boundary. They never become actionable old
   writes. Do not add an `expired` stage or alter migration 164 constraints or
   immutable history. Always reconcile `commit_pending`/`committed` rows, even
   when their source is older than 30 minutes. Expiry cannot erase uncertainty.
   Recovery returns the count actually reconciled. Stale-only unattempted rows
   do not cause an early return and do not block a new source generation. A
   recovery invocation claims recovered work only, never mixed-generation
   all-fleet completion. Preparation and recovery use the existing five-stage
   database schema; there is no migration.

File-journal single-fleet operation remains compatible. Additional fleets still
require database journals. No broader customer search, identity auto-match,
manual binding replacement or duplicate fleet ID is accepted.

## Schedule investigation and release

Read-only audit compares configured schedule, timezone, deployment/image, restart
policy, active prior execution, lock/heartbeat evidence and actual execution
start/end timestamps. Identify missed execution versus failed execution versus
missing logs separately. A provider-reported exited status does not prove
receipt verification. Do not alter schedules or trigger jobs to diagnose a
provider incident without the release owner's scoped authority.

Release preserves one deployment slot and requires exact SHA/runtime identities,
protected CI, fresh independent QA/Security gates and a narrow approved canary.
Acceptance needs collection/source/receipt/read-model evidence, not exit status.
Rollback retains journals and guarded import/read logic; stop the changed
collector image if guards fail, identities change, imports duplicate or cleanup
leaves executions running. Never restore an older unguarded reader or discard
uncertain commit history.

## Acceptance fixtures and negative cases

- A shared transient report read fails once, then succeeds within three
  attempts. Existing identity retry budgets are not multiplied by an outer
  task retry. Unknown/identity/company/filter/tenant failures gain no retry.
- Task N fails after N-1 successes. Restart reuses only still-valid matching
  task results and preserves their timestamps; terminal checks remain required.
- Changed company, directory, scope, fleet set, VIN, assignment, binding,
  timezone/window, expired/future start, invalid digest/schema and unsafe file
  all reject reuse. A partial artifact never passes import validation.
- A process dies at checkpoint write; previous atomic artifact stays valid or
  reuse fails safely. Cleanup exits and releases locks without logging secrets.
- Three fleets use one source collection and three distinct journal identities.
  Failure after fleet 1 verification resumes fleets 2/3 without rewriting fleet
  1; failure after commit before verification reconciles before collection.
- Wrong/deleted customer, wrong tenant/actor/company, revoked membership and
  changed source identity cannot import through source sharing. An additional
  fleet cannot inherit an old generation's authorization.
- Expired unattempted rows remain immutable, are skipped and permit fresh
  collection; expired uncertain commits still reconcile. Recovery count excludes
  skipped rows. Fresh source age is checked before preparation and each fleet.
- Single-fleet file/database mode and old pending journal recovery remain valid.
- Logs prove entry/stage/failure categories while seeded secrets/raw error contents
  never appear. Missing-execution audit distinguishes infrastructure uncertainty from
  demonstrated application defects.

Local focused tests and captured/synthetic provider flows can verify contracts
without customer writes. Live source/commit canary is separate release evidence;
no production recovery, schedule change or data mutation is approved by this
contract alone.
