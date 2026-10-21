# DB-036 worker recovery implementation

Date: 2026-10-21. Accountable owner: Backend & Integrations. Architecture owns the recovery contract; Release & Reliability owns production lifecycle acceptance.

Status: implementation reviewed offline; not merged, deployed, or production accepted. Railway incident QH8L8B3E remains active. The provider's 18:45 UTC update says builds/deployments remain paused. No worker was triggered, restarted, redeployed, reconfigured, or imported during this work. The precise cause of the two 150-second exits remains unproven.

## Implemented behavior

- Read-only execution audit checks actual expected UTC slots, with five minutes of start grace. A missed execution, failed execution, and 150-second exit requiring startup evidence are distinct alerts. It never equates EXITED with verified import. [Observed execution snapshot](MOTIVE_WORKER_EXECUTIONS_2026-10-21.json).
- Worker entry emits flushed startup evidence. Shared collection logs identify browser/login/company/timezone/read-task phases and safe failure categories. Exact allowlisted Playwright timeout/transport reads receive bounded retries; identity/session/company/filter failures remain fatal.
- Private atomic task checkpoints preserve completed work and original source timestamps. Integrity, scope, run identity, tenant/actor/account/binding configuration, current identities, directory/date/window and absolute expiry gates prevent unsafe reuse. Location expires at ten minutes; health, fuel, trips and drivers at thirty. Files are 0600 in existing private worker run directories. Unavailable observations are not frozen as completed tasks.
- Location and driver checkpoint reuse rechecks current VIN/provider identity; health rereads current VIN before retrieving cached codes. Fuel binds checkpoints to a freshly rebuilt VIN directory. Trips uses three daily report tasks, covering the same original three-day interval; only fully finalized reports become reusable.
- Node/browser subprocesses run in separate process groups, with bounded cleanup on completion, timeout, and cancellation. Browser close has a three-second bound. Tests check that descendants no longer run after the parent returns.
- Database driver collection runs once for the configured company, then atomically prepares one immutable source_saved row per authorized fleet under deterministic per-fleet journal locks. Each fleet uses its own existing runner, current membership/assignment/VIN/actor checks, journal and receipts. Every fresh projection rechecks thirty-minute source age.
- Pending uncertain commits reconcile before fresh reads. Unattempted source_saved/validated evidence older than thirty minutes is retained unchanged and skipped; it cannot become a fresh import. No new journal stage or database migration is introduced. A recovery-only invocation reports recovery rather than claiming a newly completed all-fleet generation.

Read checkpoints require the existing worker state storage. Driver /tmp checkpoints can disappear across container replacement; completed driver source and independent projection receipts remain durable in PostgreSQL. No new replicas, parallel browser pools, schedules, credential changes or widened identity allowlists were introduced.

## Verification

Owner checks:

- 158 focused Python tests pass: worker processes, task recovery, scheduling, fleet fan-out, source age, immutable receipts, failure cases, tenant/member import guards and fuel/trip batch runners.
- 118 Node tests pass, including existing trip report collection tests and new checkpoint/transport/cleanup cases.
- One real PostgreSQL test passes using migration 164's actual constraints and append-only trigger in an owned isolated schema. It proves all-fleet preparation, duplicate-key rollback of the whole batch, retained per-fleet identities, and tenant/company rejection.
- Changed Python lint and git diff whitespace checks pass.
- Independent QA/Security reviewed the working tree and gave offline GO. Earlier findings about stale source-only recovery, checkpoint integrity, process-tree cleanup and per-fleet freshness were corrected and independently rechecked.

Local runtime preflight: branch codex/motive-worker-recovery from f560b418. No listeners on 5173/8000. Runtime controller dry-run reports missing approved backend/.env and Vite; no existing service was replaced, database migrated/reseeded, or production environment copied. No authenticated local UI or live Motive collection acceptance is claimed. The owned PostgreSQL container db036-worker-recovery-pg is test-only and separate from all existing databases.

## Release hold and next evidence

The production incident is external: https://status.railway.com/incident/QH8L8B3E . Latest read-only snapshot still shows missing location/health/trip starts and both 150-second failures. New diagnostics distinguish a future failure before Python entry from a browser/read failure, but cannot reconstruct absent historical process logs.

Before release: protected PR checks on the final SHA, exact source/image identity, and a scoped release slot. After Railway permits deployment: deploy the reviewed worker images; observe actual new starts and verified receipts; inspect source/capture/read-model parity and shared driver source hashes with independent fleet receipts. Verify a later natural location/health schedule executes, not merely that a countdown advances. A successful recovery command alone does not prove scheduling fixed.

Rollback: restore the prior worker images without deleting state volumes, source artifacts, per-fleet journals or receipts. Stop the changed worker on identity/tenant mismatch, incomplete import attempt, duplicate committed projection, lost lock, unexpected source-age acceptance or missing cleanup. Existing import contracts and migration 164 remain compatible.

## Follow-up: 2026-10-21 21:20 UTC

PR611 candidate663686d2aeb48113f638b61080f4159a0a9f830d remains MERGEABLE. Run39675352654 passed migration, both backend partitions, dependency preparation, frontend critical/build and Playwright smoke. Frontend remaining:1823 passed,3 failed across176 files. Failures are initial asynchronous readiness lookups in ShopSearch.test.tsx:131, IncidentOutcome.test.tsx:104/118, GarageAnalyticsCostEvidence.test.tsx:36. Independent QA source/log diagnosis underway. No frontend code changed in the worker PR; no cause attributed solely to contention and no unchanged retry dispatched. Shared release owner holds further pushes/merges for PR614.

Official Railway update21:01UTC still reports major outage and no additional build-availability information; authenticated project dashboard retains outage banner. Read-only cron history confirms latest location run remains4bc070c5-9700-4ca8-9ce3-0135b431cd1d at10:50:54UTC, CRASHED. No recovery, new import, scheduled success, merge or deployment claimed.
