# DB-036 driver daily audit and contact wording

Frontend & UX accountable for the Fast UI cleanup; production worker inspection is read-only. Checked October 14, 2026 Eastern (October 15 02:12 UTC).

## Daily collection evidence

PostgreSQL repeatable-read, read-only transaction queried the exact three approved fleet scopes. Each successful daily batch has three terminal `verified` commit journals, committed readback/replay and 18/1/1 available records, with zero unverified assignments.

| Scheduled date | 77 Cargo completion UTC | Elis completion UTC | DONTRANS completion UTC | Result |
| --- | --- | --- | --- | --- |
| Oct 10 | 13:51:35 | 13:55:54 | 14:00:04 | Verified |
| Oct 11 | 13:53:28 | 13:57:45 | 14:01:43 | Verified |
| Oct 12 | — | — | — | Failed before import |
| Oct 13 | 13:57:58 | 14:02:27 | 14:07:45 | Verified |
| Oct 14 | 13:53:03 | 13:57:10 | 14:01:11 | Verified |

Oct 12 Railway logs report `driver_collection_failed`, reason `vehicle_identity_changed`, at 13:53:59 UTC, then `worker_failed` and `fleet_worker_failed`. The collector compares the vehicle VIN before and after reading the driver summary; a mismatch aborts the complete collection before a journal/import. This proves an identity-check failure, not whether Motive changed the VIN or a page read was incomplete. No incomplete source was imported. The current successful Oct13 deployment is `b058af1a-84f1-499e-a9b7-936d7ec7284b`, immutable image `sha256:4eda1a6233747fb5d8ded8e27f56f4dde6e036e573d42d088195a677a5acad80`, command `python -m scripts.motive_drivers.run_fleets`, cron `45 13 * * *` (09:45 EDT). Oct14 logs end with three worker completions and `fleets_complete`. No worker settings, retry policy, volume, plan or fleet membership changed in this audit. An uninterrupted daily success claim is false; historical Oct12 data cannot be reconstructed by pretending a current recapture happened that day.

Current application projection: 22 trucks; 20 available records, all non-stale, 14 numeric scores, six records with no Motive score and two no-capture trucks (70/26). W900 is88, 02 is82 and609 is81; the Motive score period is Sep28–Oct11. Assignment checks are from today's09:53–10:01 EDT collection. Current signed-in Trips DOM independently shows these three values, including609 under Elis. Fresh collection does not require the provider's score or score period to change daily.

## Location versus speed

The actual W900 projection at02:12UTC selects location observed Oct15 02:02UTC (minute precision), captured02:03:56UTC. Its10mph value was captured Oct2 19:25:34UTC with no trusted observation timestamp. The selectors rank each field independently; the location collector does not supply a new speed. Motion is `unknown`, not moving. The address age therefore describes the latest location observation, while the speed age describes a historical saved reading. No timestamp was rewritten and no old speed was promoted to current.

## UI acceptance and verification

Remove visible “Local contact” and “Call local contact” wording; retain saved aliases/phone numbers and separate Motive identity. Phone-only states have no leading separator. Shared `LocalDriverContact` covers FleetBoard, CurrentDriver, FleetMap, TruckDetail, FleetApp people panel and TripOverview; the driver detail popover and call accessible-name fallback are also cleaned up. Strict exact alias and current assignment guards are unchanged. No API, data, schema, worker or dependency changes.

62 focused DriverRecord, TruckDetailHarden and FleetTelemetry tests pass. Changed-source ESLint, TypeScript and Vite production build pass. Repository search finds no remaining operator-facing local-contact label. Existing whitespace-alias, reassignment, managed-profile, unavailable score, phone-only, overlay interaction and telemetry provenance regressions pass.

Local preflight: intended checkout `/Users/sergio_m1_promax/.codex/worktrees/motive-driver-records/truck-pit-stop`, branch `codex/driver-contact-labels`, base26c21267. Vite5173 PID21165/source cwd verified and preview HTTP200; proxy target127.0.0.1:8000, but no backend listener or approved environment. Local full-stack verification is blocked. Browser automatic URL policy rejected the local preview tab; no alternate local browser route was attempted. Production Chrome read-only Trips verification succeeded. Local serving is aligned but browser-unverified. Protected PR CI, merge/deploy and production desktop/mobile changed-label acceptance remain pending.
