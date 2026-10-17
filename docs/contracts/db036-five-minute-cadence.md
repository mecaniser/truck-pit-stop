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

`railway.motive-location.json` is the versioned location-service configuration
and required template for the next CLI deployment bundle. The previous temporary
upload has an hourly root `railway.json`; never reuse it unchanged. Copy the
reviewed location configuration to the bundle's root `railway.json` and verify
its five-minute schedule before any future upload, because file configuration
can override dashboard settings.

Railway rejected the reviewed custom `railwayConfigFile` selector on 2026-10-16
with `BAD_USER_INPUT` (Config-as-Code deprecated). Fresh readback confirmed the
combined mutation changed neither setting. The narrower approved adaptation
changes only this existing service/environment's `cronSchedule`; the selector
remains `null`, and the immutable deployment/image remains unchanged. This does
not claim a selected repository config file or rebuild the old uploaded bundle.
Migration to Railway Infrastructure as Code is a separate project task.
[Configuration precedence](https://docs.railway.com/config-as-code).

Independent QA/Security approved the schedule-only adaptation after inspecting
the exact variables, assertion script and rejected-mutation readback. Freshly read back the schedule, unchanged null selector, next
scheduled run, image/deployment ID, command, replica/restart settings and mounts.
Confirm this service has only the selected production instance.

Rollback is the inverse service mutation: restore `0 * * * *`, preserving the
null selector, same image and all data. Update the versioned template to hourly
before another release if rollback remains required.
Return to the owner on provider throttling/authentication, identity or receipt
failure, overlapping executions, or sustained skipped starts; do not increase
replicas or rewrite source time to mask it.

## Gates and acceptance

1. Validate JSON against the Railway schema; compare unchanged runtime settings
   with the previous deployment bundle and inspect the scoped diff.
2. Independent QA/Security reviews the schedule, exact target, image preservation,
   state/config precedence and inverse rollback before production mutation.
3. Protected CI passes for the focused PR's exact head; merge only then.
4. Apply the small schedule-only mutation. Verify two actual scheduled
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

Independent QA/Security GO for `adc8d7c43cc2211e684c06763ceb789b4365af54`:
reviewer independently validated the Railway schema, exact target/mutation,
prior-bundle equivalence, unchanged-runtime invariants, overlap controls, usage
arithmetic and rollback. No implementation edits or production mutation by the
reviewer. All six protected checks passed on that exact head (run 38910090710).
PR552 merged as `2f093ca38d767eeefe6735a1f12c471c642438a6` at 14:06:50 UTC.
Supplemental independent GO approved the schedule-only adaptation. Applied at
2026-10-16 14:10:51 UTC; fresh readback confirmed `*/5 * * * *`, next scheduled
14:15 UTC, null selector and all runtime invariants unchanged. The scheduler also
started the newly eligible 14:10 slot at 14:10:59.775 UTC; no manual runs were
triggered for this acceptance.

Two scheduled collections completed, with company identity verified before/after
and all 22 source vehicles traversed in each:

| Scheduled run | Source start UTC | Worker completed UTC | Locations | Writes verified | Numeric speed sources |
| --- | --- | --- | --- | --- | --- |
| `487f7f0f-f75d-48e6-9fe1-38f672084ebb` | 14:11:00.739 | 14:15:07.630 | 17 | 11/11 | 8 |
| `97803778-cc15-425c-847e-dc8b7b1c2f4f` | 14:15:11.602 | 14:18:44.549 | 18 | 13/13 | 10 |

Both have `collection_complete`, `committed=true`, `worker_complete`, durable
receipts, tenant/actor-scoped saved snapshot identity checks and post-commit board
projection verification. Independent readbacks at 14:16:40 and 14:21:17 confirmed
all written snapshots remained selected at their respective checks, including
five speed readings still within the existing five-minute freshness window each.
The first worker completed before the second source collection began; no observed
overlap. A third actual scheduled run started at 14:20:23.488 UTC.

Railway's second run row incorrectly reported EXITED after one second while its
collection was still progressing. This duration is not used as success or runtime
proof: source timestamps, structured completion logs and the durable committed
receipt establish completion. Both cron rows are terminal, but this provider
metadata discrepancy remains explicitly documented. Observed worker durations
from source collection start to worker completion were about 247 and 213 seconds, approximately 17–20 worker-hours/day at the maximum
288 starts; this is a usage illustration, not a dollar estimate.

The Product & Delivery Lead independently observed the production Fleet Board
refresh without reloading: source/capture timestamps advanced from 14:14/14:15:06
to 14:17/14:18:43 through its existing 60-second poll. The display expired old speed
to unavailable, then showed a fresh explicit zero from the next collection.
Five-minute scheduling does not guarantee uninterrupted fresh speed.

Final live configuration readback at 14:21 UTC retained the same deployment,
image, null selector and runtime settings; the next schedule was 14:25 UTC.
Missing source/VIN/unknown-time rows remained held rather than fabricated.
Private operational evidence is in `output/cadence/acceptance-report.json`, its
referenced receipt readbacks and `postchange-run-logs.json`; no raw PII or secrets
are committed. Independent final QA/Security acceptance is GO after reviewing both durable
receipts, verification code, completion logs, no-overlap intervals and live
configuration again at 14:22:34 UTC. No reviewer edits or production mutations.
