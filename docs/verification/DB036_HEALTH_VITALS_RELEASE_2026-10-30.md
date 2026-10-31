# DB-036 health vitals production release — 2026-10-30 EDT

Owner: Backend & Integrations. Product outcome: automatically collect dashboard mileage/engine hours and display them in Truck health alongside existing fault codes.

## Protected merge and web/API

[PR714](https://github.com/mecaniser/truck-pit-stop/pull/714) passed all seven exact-head checks on `3c15ab875055befd1ab1b6962e751c0c30ea191b` ([run41162412338](https://github.com/mecaniser/truck-pit-stop/actions/runs/41162412338)). Independent QA and Security/Architecture issued fresh GO after live selector correction. Repository policy requires squash; normal protected squash merged `17608d101a66733a4f75fd88ec52f0dd4b3ef6c1` at2026-10-31 03:42:08UTC. Checked head and merged tree both `c1eb36641ab0347a799c42b293aac5d81b3935b7`.

Automatic API/frontend deployment `38ebb82e-2863-4f2e-8bfd-06db18a5f124` succeeded for exact merge17608d10. `https://www.dieselbridge.com/build-version` returned that full SHA, built2026-10-31 03:46:33.501UTC. `https://api.dieselbridge.com/health/ready` returned ready with database and Redis ok after restart. The API service builds and serves frontend assets; no separate frontend service was deployed. `/build-version.json` is a SPA fallback and was not used as version proof.

Parent's authenticated production browser gate passed after refresh: truck603 Truck health shows mileage692,224.14mi and engine-hours23,520h alongsideSPN639/FMI2, dashboard capture provenance and unknown observation time. Service odometer682,225mi remains unchanged. This uses the existing current-membership truck detail telemetry contract; no new endpoint, migration, canonical mileage overwrite or fault lifecycle mutation.

## Health worker rollout

Health service `4da46413-32b0-429c-9bab-f022ec5e41b7` deployment `22509ac0-886c-40c0-94a0-6080e07bc537` succeeded; image `sha256:9021dcd7dae8a00ea14e78e52a1f33bdf6c6607522ae1913809fd1a4a7770323`. Upload contained a git archive of exact merged backend17608d10, no untracked files, credentials or local dependencies. Effective service manifest preserves Dockerfile`backend/Dockerfile.motive-health`, entrypoint`python -m scripts.motive_health.run_worker`, cron`30 * * * *`, restartNEVER, one replica and volume`/data`. The service did not apply the optional root manifest predeploy hash command; no claim is made that it ran. Instead, SSH attestation on the running deployed instance verified all four worker source fileSHA256 values against exact merged source: collect.cjs, import_health.py, runner.py, run_worker.py.

Existing optional `MOTIVE_HEALTH_FLEET_CUSTOMER_ID` was deliberately set with skip-deploys to the previously verified exact77 CARGO LLC fleet. Running instance attestation verified the fleet pin and explicit commit=true. Provider credentials, cron, state volume and other worker services were not changed. A first upload to the nonproduction environment ID returned404 and created no deployment; the successful upload used independently verified production environment`b5c9fdf5-4430-4cb3-97b9-cd739d7d5ece`.

Exactly one authorized off-schedule canary was triggered after confirming the prior execution had completed with verified receipt. Canary `455f7a6b-49d0-44e5-bf02-27377ffd629e` uses deployment22509ac0 and started2026-10-31 03:46:34.283UTC. No repeated trigger or retry of an uncertain import occurred.

Canary finalized all21 source rows and both company/directory checks. At03:52:01.461UTC application log reports `mode=commit stage=verified committed=true counts={created:36,excluded:2,unavailable:3,source_missing:2}`, followed by `worker_complete` at03:52:02.182UTC. Platform execution455f7a6b then EXITED at03:52:03.517UTC after329seconds; successful import is proven by application receipt and readback, not EXITED alone.

Read-only monitor on the deployed instance observed committed source/receipt, verified all19 vitals snapshots against exact source values, VIN, tenant/fleet, source-read capture time and unknown observation time, and confirmed canonical service mileage unchanged. It verified truck603 fleet projection692,224.14mi/23,520h. Source artifact identity: `cc92bc222bd77af0c452f1e6ec06942189816568e61389ba2c4bf1274fb0c913`; persistent receipt path `/data/motive-health/20261031T034635Z-0e76f755-6210-4b8d-824c-d8c3b774cc0c/receipt.json`. Monitor's19 vitals plus17 diagnostic creates explain the36 total. One source vehicle remains VIN-unavailable and another fails the pinned current-fleet scope; no identity override occurred. Three unavailable fault observations and two current fleet source-missing classifications are separate categories, not distinct-truck sums.

Parent performed a final authenticated production popup refresh: capture time advanced from10:55PM to10/30 11:48:49PM for both vitals; values remained692,224.14mi/23,520h with the11:48PM fault check and SPN639/FMI2 alongside. This confirms the deployed collector's fresh readings reached the production popup. No unresolved implementation or release gate remains for this health-vitals outcome.

## Rollback and preserved data

Previous API release: `f36f28756da45d924c25ec9ddc472f4d833f04ce`, deployment`c454d9eb-57a4-47b7-8b74-c18840e06f17`. If necessary use the connected API service's one-time `railway deployment redeploy --service 57db24db-bb57-4464-8263-5d2064f9221e --commit f36f28756da45d924c25ec9ddc472f4d833f04ce --yes`; no database downgrade or snapshot deletion is needed.

Previous health source: PR669 merge`46e6af84a38c12fd13495746e69f4af1d79ee700`, deployment`b5f1c9e1-f354-4cc9-897b-179f0be11365`, image`sha256:c0f43c4a4f620e5caeb07687981d90940d7c2c5f93570928f613ae16ee68b5bd`. Preserve`/data`, current fleet pin and cron. Before any old-runner restoration, reconcile any uncertain new vitals receipt using the exact new runner/source; old code must not silently discard the new eligible vitals request set. If saving must be held, explicitly disable commit for future starts rather than retriggering uncertain work. No rollback was needed.

Customer identity, canonical service mileage, fault repair state, payments and outbound messages were not altered for QA. Authorized telemetry/diagnostic captures are append-only, source-preserving records. Parent authenticated UI evidence and deployed worker readback remain separate from deployment status.
