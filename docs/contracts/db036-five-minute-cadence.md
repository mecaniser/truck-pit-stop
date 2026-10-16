# DB-036: five-minute location and speed collection

Date: 2026-10-16. Release & Reliability accountable. High-risk infrastructure
follow-up; independent QA/Security must review the concrete diff before rollout.

## Authorized outcome and invariants

The existing production Motive location/speed collector should start every five
minutes instead of hourly. This changes scheduling only. No API, database,
collector algorithm, source timestamp, frontend freshness threshold, tenant,
provider account, storage, subscription or environment-variable changes.

- Project: `78a30cb6-c422-458a-ad8f-daa02073b579`.
- Production environment: `b5c9fdf5-4430-4cb3-97b9-cd739d7d5ece`.
- Existing location service: `b01d9417-d5d5-456b-ba76-ceb95386b35b` (`DBN-motive-sync`).
- Deployed application source: PR548 merge `e3ff99e0c1ef866fe3fd711c2f248841fe7c1152`.
- Existing deployment: `0d3efd78-6fe8-4c15-93ba-05d8fd32be17`.
- Image: `sha256:1c5739e696cbe6f4bb0fe476f52feb8ce95f1ae276fd75f383d01c847637f6a7`.
- Command: `python -m scripts.motive_sync.run_worker`; one replica; NEVER restart.
- Existing `/data` mount and saving policy remain unchanged.

## Scheduling and cost implications

Target schedule is `*/5 * * * *` UTC, the minimum Railway supports. Railway
skips a new execution while a previous one remains active and may start a run a
few minutes late. This is a scheduled refresh interval, not a guarantee every
truck continuously has speed less than five minutes old. Missing/stationary UI
speed and unknown timestamps remain unavailable; no zero or freshness invented.

Recent executions took 215–242 seconds, leaving about one minute of headroom.
The maximum scheduled executions increase from 24 to 288 per day (12 times).
At similar runtimes that is roughly 17–19 worker-hours per day instead of
1.4–1.6, before skipped starts. Actual CPU/memory usage billing may increase;
this is not a quote, subscription upgrade or added volume. Existing process and
PostgreSQL locks remain the defense against overlap; no concurrent catch-up runs.

[Railway cron behavior](https://docs.railway.com/cron-jobs) confirms the minimum,
UTC clock, delayed-start and skip behavior.

## Configuration and rollback

`railway.motive-location.json` is the versioned location-service configuration.
The previous temporary CLI deployment bundle has an hourly root `railway.json`.
Do not reuse it unchanged: file configuration overrides dashboard settings on
future deployment. Select `/railway.motive-location.json` for this existing
service, so future deployment bundles must include this reviewed file. Existing
config-as-code services remain supported until 2026-12-01; migration to Railway
Infrastructure as Code is a separate project task, not part of this cadence
change. [Configuration precedence](https://docs.railway.com/config-as-code).

After the independent gate, update only this exact service/environment's
`cronSchedule` and `railwayConfigFile` through Railway's public API. Do not
redeploy/rebuild or alter the immutable application image. Freshly read back
both values, next scheduled run, image/deployment ID, command, replica/restart
settings and mounts. Confirm this service has only the selected production
instance before using the service-instance mutation.

Rollback is the inverse service mutation: restore `0 * * * *` and the previous
config-file selector (`null`), preserving the same image and all data. Update the
versioned file to hourly before another release if rollback remains required.
Return to the owner on provider throttling/authentication, identity or receipt
failure, overlapping executions, or sustained skipped starts; do not increase
replicas or rewrite source time to mask it.

## Gates and acceptance

1. Validate JSON against the Railway schema; compare unchanged runtime settings
   with the previous deployment bundle and inspect the scoped diff.
2. Independent QA/Security reviews the schedule, exact target, image preservation,
   state/config precedence and inverse rollback before production mutation.
3. Protected CI passes for the focused PR's exact head; merge only then.
4. Apply the small schedule/config-selector mutation. Verify two actual scheduled
   executions finish successfully, with distinct run IDs and no overlap. Manual
   triggers do not count as scheduled-run evidence.
5. Check collection completeness and committed receipts, field readback/replay
   outcomes and speed/location observation timestamps. Record exact image,
   execution times/durations and remaining source gaps without exposing PII.

Local runtime: isolated managed checkout on `codex/motive-five-minute-cadence`
from `d5cb662839f82789184be846bc0db876c860594e`; configuration/documentation only,
so no local application servers are started or replaced and browser rendering
is not an acceptance gate for this unchanged application runtime.

## Release evidence

Pending independent gate, CI/merge and production acceptance.
