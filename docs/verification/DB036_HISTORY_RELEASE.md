# DB-036 history release — 2026-10-03

Accountable: Backend & Integrations. Scope: available historical trips, imported date bounds, reusable session-dependent daily collection.

- PR460: https://github.com/mecaniser/truck-pit-stop/pull/460
- CI37101257508: all six jobs passed on db90b6a5608aa371efcf8198f6cee94eb2ed2de4.
- Merge/deployed SHA: 42917864197c3aed4d8010d9a6bb4396816de130.
- Railway deployment dadbee53-fa8d-4ad0-8dab-bc77cdcf0fa7 SUCCESS; public build-version matches and database/Redis readiness healthy.
- Independent gates: DB036_HISTORY_COLLECTOR_REVIEW.md and DB036_HISTORY_COLLECTOR_MODULE_REVIEW.md; contract DB036_HISTORY_COLLECTOR_CONTRACT.md.
- Tests: bounds55 backend/20 frontend; normalizer16; collector6; batch runner7; TypeScript/lint pass.

## Import and live acceptance

| Source window | Source rows | Accepted | Created | Unchanged | Excluded |
|---|---:|---:|---:|---:|---:|
| August |764|645|645|0|119|
| September1–15 |872|784|784|0|88|
| September16–30 |1050|964|744|220|86|
| October1–3 |154|131|9|122|23|

2,182 new / 2,524 total completed trips across13 verified trucks. Earliest imported departure August15. April–July reports explicitly empty. Exclusions:309 unit26 rows without verified VIN,4 missing locations,3 ongoing trips. Unit26 vehicle admin shows no VIN. Never infer missing history as zero activity.

Dry-run then authorized atomic apply, exact unchanged replay, and unchanged vehicle/telemetry/repair fingerprints verified for every batch. Existing frozen metrics retained; new history has no invented fuel/stop metrics. Private artifacts and mapping stay outside Git; source company verified before and after capture.

Authenticated production: August645 trips/9 trucks; September1–30 shows1,748 trips/13 trucks,117,974.8mi,2134h14m, and Imported Aug15,2026–Oct3,2026 · Partial. Screenshot: output/trips-qa/september-release-history.png. Local synthetic actual-component preview passed; local authenticated backend unavailable.

## Daily operation

Heartbeat daily-motive-trip-refresh is active at6AM America/New_York. It invokes the runbook and reusable CUA collector, normalizer and production batch runner for previous two dates through today; exact replay avoids duplicates. Mac/Codex and signed-in Motive are required. Expired sessions stop and request login. No passwords/cookies stored. First future scheduled run has not yet executed; today's pipeline was run and verified.

Trip refresh only: this does not schedule fresh location/odometer/fuel telemetry. OAuth approval remains pending. No universal one-year retention claim. Superseded partial captures are identified in private history-run-manifest.json and must not be resumed.

This release ledger and runbook clarification were recorded locally after deployment; application code is the deployed PR460 commit.
