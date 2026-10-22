# Motive worker reliability audit — 2026-10-21

Evidence snapshot: approximately 18:31–18:36 UTC (2:31–2:36 PM America/New_York).
Accountable owner: Release & Reliability for investigation and execution gaps; Backend & Integrations for collector remediation. Tracking: DB-036 worker reliability follow-up, Discovery. This is an investigation, not a released fix.

## Acceptance and scope

Identify actual recent failed runs separately from deployment status; inspect available failure logs and source; assess workload and responsibility boundaries; record confirmed causes separately from hypotheses and recommend the smallest justified remediation. Read-only production inspection. No job triggers, retries, configuration changes, imports, deployment, or customer-data writes. Documentation only; local services and browser QA do not apply.

## Current production evidence

`railway cron list --service NAME --limit 100 --json` returns execution history. EXITED below is a platform status, not proof of committed data. Samples have different date windows and include manual/redeployment executions; do not compare them as controlled failure-rate measurements.

| Service | Sample | Crashed | Other | Latest execution |
|---|---:|---:|---|---|
| Location sync | 100 since Oct 21 00:20 UTC | 6 | 94 EXITED | Oct 21 10:50:54 UTC; crashed after 18s |
| Health | 100 since Oct 17 02:35 UTC | 11 | 89 EXITED | Oct 21 06:30:09 UTC; crashed after 217s |
| Trips | 15 since Oct 8 | 4 | 11 EXITED | Oct 20 21:52:22 UTC; crashed after 18s |
| Fuel | 13 since Oct 9 | 1 | 12 EXITED | Oct 21 13:31:39 UTC; crashed after 150s |
| Drivers/safety | 22 since Oct 9 | 9 | 12 EXITED, 1 REMOVED | Oct 21 13:49:34 UTC; crashed after 150s |

Latest failed run identifiers:

- Sync `4bc070c5-9700-4ca8-9ce3-0135b431cd1d`, deployment `f714812c-4fc8-480a-9494-92219e7a12c4`.
- Health `88ab88e4-1221-4814-9963-faccb02808a7`, deployment `74fe592a-a1c3-4675-8fa4-afad0669e193`.
- Trips `8a7f721c-acf0-489f-ad1b-b0ac6d68b4ca`, deployment `cb0a5cae-aadd-4f8c-804a-e41c4a141f5c`.
- Fuel `c74f8765-c9f0-4fc3-ae3f-9fdf8c377c2c`, deployment `c7afd6cb-8807-41f3-aeca-c4b62f05e18d`.
- Drivers `a5a8417d-3dae-4423-abeb-e27821e19cac`, deployment `2a92c5d8-6d28-4e8b-93d3-ab09722f1dd5`.

Latest deployment logs show sync completed 23 full collections/import worker completions before one failure. Its two immediately preceding runs explicitly logged committed imports. Health completed three collections and verified commits before its failure. Trips previously committed 138 rows on Oct 18 and 34 on Oct 19, then failed Oct 20 at 09:16 and again at 21:52. Fuel logs show six completed collections/verified commits Oct 15–20. Driver logs show three complete three-fleet runs Oct 18–20, including individual safely unavailable identity observations.

Important evidence mismatch: service/deployment status reports fuel and drivers Completed/SUCCESS, while cron execution history shows today's failures. `railway logs --latest`, explicit deployment logs, time-bounded logs, and an environment-log GraphQL query for fuel returned no application logs for today's fuel failure. Driver deployment/time-bounded logs also returned no application logs for today's driver failure. Neither absence proves the process never started. The matching 150-second durations suggest a separate startup/runtime/platform failure, but the cause is unproven.

Execution gaps: as of the snapshot, health has no later execution after 06:30 UTC despite `30 * * * *`; sync has none after 10:50 UTC despite `*/5 * * * *`; trips has no Oct 21 execution despite `15 9 * * *`. No active run appears in these history samples. A configured next-run countdown is not evidence of execution. Investigate scheduler/instance lifecycle independently of browser timeouts. A prior fuel execution has a reported duration of 86,505 seconds despite application completion logs; this needs lifecycle reconciliation and must not be treated as 24 hours of useful collection work.

## Confirmed application failure mechanism

Health explicitly logs `health_collection_failed`, `reason=ui_timeout`, `import_permitted=false`, after progress 18/19. A prior deployment failed similarly after 12/19. Trips explicitly logs `trip_collection_failed`, `reason=ui_timeout`, `import_permitted=false`, before collection completion. Sync logs only “Motive collection failed; no import permitted” with no reason, after roughly 20 seconds and before row progress. These failures occur in collection, before normal import. Logs do not identify the exact timed-out selector, login stage, or underlying provider response.

Source inspection used `origin/main` f560b4189ee80b5c30958657b0be82c1295f7578, because the current checkout is an older unrelated dirty branch. Deployed manifests identify the entrypoints, but source inspection is not byte-for-byte attestation of every deployed collector image.

- `backend/scripts/motive_sync/collect.cjs`: fresh Chromium login per run; company/timezone/directory preflight; two per-vehicle attempts; final company verification. Top-level catch discards the exception entirely. Setup/finalization has no equivalent bounded retry. Per-row unavailable handling exists, but identity/session violations correctly abort.
- `backend/scripts/motive_sync/collect_trips.cjs`: reads every vehicle VIN using fresh pages before collecting the report; unhandled VIN-page readiness timeout aborts the whole collection. Error is reduced to `ui_timeout` without stage details.
- `backend/scripts/motive_health/collect.cjs`: imports the trip collector's `readVehicleVin`; invokes it outside the per-vehicle fault-code retry. Consequently a transient VIN page timeout can terminate the whole health batch. Final inventory/company checks also can abort. The observed final failed selector remains unproven.
- `backend/scripts/motive_sync/run_worker.py`, `run_trip_worker.py`, `run_fuel_worker.py`, and `backend/scripts/motive_health/run_worker.py`: collection then validation/import subprocesses, file locks, source artifacts, bounded subprocess deadlines. Existing source checkpoints do not themselves provide automatic safe resume of browser work.
- `backend/scripts/motive_drivers/run_fleets.py`: serially starts a separate collection for each local fleet. Latest successful logs traverse the same 22-driver source directory three times. It aborts remaining fleets if a child fails. There is real repeated provider work here.

No retrieved error establishes OOM, CPU exhaustion, database exhaustion, or Redis failure. Memory/CPU metrics and private failed source artifacts were not retrieved; do not claim those causes ruled out. SSH into the stopped sync service did not establish a session and was canceled without executing a remediation.

## Workload assessment

These are already five separately scheduled services. Each typically runs a Python coordinator, one Node collector, Chromium subprocesses, and then an importer. Multiple Chromium processes are expected and are not by themselves evidence of too many responsibilities.

Observed successful sync durations are around three minutes; the last 100 platform executions have median 188s, against a five-minute schedule. Health median is 204s against hourly. Trips median is 137s against daily. Fuel usually processes 22 vehicles × three dates = 66 reports in roughly 11–13 minutes. Drivers takes about 12–14 minutes across three serial fleet collections. The 18-second trip/sync failures happen too early to blame a large accumulated batch. These measurements do not replace resource metrics.

Railway skips a scheduled execution when its predecessor remains running; it does not automatically terminate it. See https://docs.railway.com/cron-jobs and https://docs.railway.com/guides/cron-workers-queues. Current manifests use restartPolicyType NEVER; do not blindly switch to Always or unbounded retries, because that can repeat writes and browser logins without resolving uncertain commits.

## Recommended work split

1. **P1 — Release & Reliability:** reconcile missing scheduled executions and both 150-second crashes. Obtain platform exit/start reason, resource metrics, and instance-level evidence; compare last run with last verified commit. Alert on overdue verified success, missing execution, and failed startup separately. Do not label an EXITED run a successful import.
2. **P1 — Backend & Integrations:** add shared sanitized stage diagnostics to collectors: browser launch, login redirect/form, company, timezone, directory, vehicle readiness, report, final verification, validation, commit. Include run ID, attempt, elapsed time, safe reason, and counts. Preserve private artifacts; never log credentials, cookies, raw authenticated HTML, or location details.
3. **P1 — Backend & Integrations, Architecture contract:** bounded retries for specifically transient readiness failures, with backoff/jitter and an account-wide concurrency limit. Preserve fatal company/VIN/provider/assignment/tenant mismatches. Retry collection separately from uncertain commit recovery.
4. **P2 — Architecture + Backend:** durable small jobs per vehicle/date/report window, with explicit failed/unavailable coverage and idempotent receipts. Final company/directory checks and deletion/absence semantics must remain safe; never import an incomplete report as evidence that missing rows disappeared. Resume only under renewed source identity and freshness checks.
5. **P2 — Architecture + Backend:** collect one immutable driver source observation per provider account, then independently validate/project it into authorized local fleets. Keep tenant membership, per-fleet journals, idempotency, and access gates separate. This reduces the demonstrated three full source scans without removing isolation.

Retain existing location/health/trips/fuel/driver service boundaries initially. Smaller recoverable units and clearer stages are justified; a large increase in services or unrestricted parallel browser sessions is not justified by current evidence. Any implementation is high-risk worker work and requires acceptance/negative tenant cases, focused tests, independent QA/Security, protected PR checks, and explicit release evidence. No remediation is implemented or deployed by this audit.
