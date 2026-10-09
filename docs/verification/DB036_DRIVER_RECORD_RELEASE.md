# DB-036 driver worker release, October 9, 2026

Accountable implementation owner: Backend & Integrations. Release coordination: Release & Reliability. User explicitly authorized deployment. The original implementation is PR492, merged as `0cdc80964b2ece965b180cdf9ba149c71e7063a3`; all six checks passed.

## Verified production baseline

- Web deployment `f9771390-8d08-4a38-96d7-a428f49e05b6` is SUCCESS at the merged SHA. Read-only database check returned `163_fleet_driver_records`; `/health/ready` reports database and Redis healthy.
- Exact tenant/company lookup returns one active fleet-enabled customer for 77 CARGO LLC. Private configuration evidence is excluded from Git.
- Separate service ID `7d282295-b0cf-47c5-b83f-36c2ef2abc0e` was created and subsequently renamed to `DBN-motive-drivers-safety` outside this agent's actions. Keep that name.
- Source-only deployment `4e22b901-5d00-46bd-8dad-5629edd30ef1` built from an immutable archive of the merged backend; image digest `sha256:e6984f6ec1ad277c2cdb7247f5adcfd3c3ef8d58dc0f07d23ede23d85628415b`. Running collector SHA256 matches the merged file (`1b44b8a2997b2f29c9aba05d7651314e34e9335a20ade84a2f047ca39502b391`).
- Initial entrypoint is a bounded sleep for manual source-only SSH acceptance. No schedule, no DATABASE_URL, saving false. Only existing Motive source credentials are referenced. No production import occurred.

## Live gate findings

1. Directory extraction fails closed because Motive renders an empty utility/checkbox column ahead of DRIVER NAME / ID and VEHICLE ID. Actual DOM: 13 columns; target columns at indexes 1 and 2; 22 rows and explicit Showing 22 of 22 footer. Fixed-position extraction at 0 and 1 is invalid. Backend & Integrations corrected this with strict header-derived extraction. Independent parser/directory evidence passed. Subsequent probes identified asynchronous summary hydration, optional action text in identity matching, and a trailing event action column; the final collector now uses unique named columns, exact provider URL/breadcrumb identity, and observed content-loader completion. The final candidate has 20 passing tests and SHA256 `a38ddfc0b4916fa012f4359f62843df4024deed5393bee4c7092fe01b8492369`. Targeted live checks match score/coaching/event values and all four sections for two drivers. Two full final-candidate captures remain in progress.
2. Railway refused volume creation: `You can only have 10 volumes per project`. Live inventory contains 11 volumes across production/staging, all attached. No storage was detached or deleted. Persistent source/attempt/receipt storage is mandatory before any controlled import or daily activation. The user selected the existing database instead of increasing the Railway plan/quota. Migration164 and the durable journal passed independent QA/Security; see [the contract](DB036_DRIVER_JOURNAL_CONTRACT.md). 84 focused tests pass. Fresh isolated PostgreSQL tests cover the full migration chain, session-lock exclusion, independently durable commit intent, immutable evidence, replacement-process replay and an actual terminated journal connection. The lost-connection test rolled back the application transaction, retained intent, and recovered exactly one request without local files. Production migration remains pending. A source-only ephemeral probe may proceed with immediate private evidence export.

## Runtime boundaries

Local preflight: branch `codex/motive-driver-release` from merged 0cdc8096; Vite5173/PID76897 serves this checkout's frontend; backend8000 and approved backend/.env absent. Existing frontend preview HTTP200; no new authenticated local full-stack claim. Production browser binding repeatedly timed out; a fresh browser tab reached the normal sign-in page with an expired session. No authenticated card/popover acceptance is claimed. This release changes only collector/recovery behavior; independent QA accepts source fidelity, production schema, exact-SHA worker, authorized dry-run/apply/replay/readback and current-driver service projection as its runtime scope. The original cross-layer UI item retains its signed-in UI follow-up.

## Acceptance and rollback

Before activation: two complete live source captures with useful extracted metrics, independent source/patch review, persistent receipt storage, rollback-only importer validation, controlled import with unchanged replay/readback, and current-driver service projection. Then enable a daily schedule and retain execution evidence. Signed-in card/detail acceptance remains explicitly open on the original cross-layer item. On identity/layout/tenant/replay failures, disable saving/schedule and preserve evidence. No other worker schedule or production fleet assignment may be changed as part of acceptance.

## Release plan

Use one focused PR from `codex/motive-driver-release`. Required CI now includes the collector tests and driver service/import/process/journal regressions. Merge only after independent review and protected checks. The normal web release applies migration164. Deploy the separate worker from an immutable archive of that merged backend, configured for database journal mode and private `/tmp` working files. Start with saving false and no schedule; validate a dry run, then run one controlled import with immutable receipt/replay/readback evidence before enabling daily13:45 UTC. Preserve other workers and all existing volumes.

## Source gate follow-up

A full capture of candidate `a38ddfc0` completed 22/22 directory rows (20 captured, one unassigned, one VIN unavailable), with no summary-read fallback or hydration timeout. It exposed five explicit zero-fuel/no-event source states. Motive omits the percent sign for zero utilization; the parser must preserve that observed zero and driver-specific empty event state. Independent QA also reproduced malformed utilization substring matches (negative, malformed decimal and multiple percent values); these are returned to the collector owner for strict parsing tests. PR493 remains draft until the revised candidate passes independent review and two complete captures.

The correction is candidate SHA256 `5ccd7cba19d7c31cd434e9e6abd9344c257b56f31db05324d8784d96e5bdca96`: exact complete fuel-card parsing accepts only the observed bare zero as unitless, and a unique driver-specific empty-event message yields the existing `empty` section state. Malformed/duplicate utilization and contradictory/wrong-driver empty evidence are rejected or unavailable. All 25 collector tests pass; two revised-candidate full captures and independent re-review are in progress. No database-journal implementation changed.

## Merge and deployment handoff

PR493 merged at `854898418df3c891b2c44e75289a57b8f2a5afbf` on2026-10-09 20:49:28 UTC. All six protected checks passed; full backend suite:2,647 passed/107 skipped. Independent final collector/source GO covers two complete captures (22 directory rows,20 retained driver observations,1 unassigned,1 VIN unavailable). Both preserve20 fuel summaries,14 scores,15 coaching statuses,15 populated event samples and5 explicit empty states. One intervening incomplete identity-mismatch capture failed closed and remains an undiagnosed reliability observation; it was rejected by validation and never imported.

The separate worker is deploying from an immutable archive of that merged backend. Database journal references are configured with saving false, stable key `db036-motive-driver-safety`, and `/tmp` working files. No plan, volume, or other worker schedule was changed. Production migration/import/schedule evidence follows below.

## Build transport recovery

Production Web `c3a4507e-ded8-4c2e-b497-26b57a29b6f7` is SUCCESS at `85489841`. Read-only verification confirms migration `164_motive_driver_journal`, the journal table, and healthy database/Redis readiness. Driver builds `3b378000-85b4-4cff-a0cc-a987de301bd7` and `dcef7873-9bd3-4936-9454-413034027d87` both failed before startup when Docker Hub returned HTTP429 for base-image metadata.

The focused build fix uses Docker Official Images hosted in public ECR. Both multi-platform index byte hashes match the current Docker Hub originals; the worker Dockerfile pins those exact digests. Only image download location and reproducibility change; application source and existing worker Dockerfiles remain unchanged.

- `python:3.11-slim-bookworm`: `sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89`.
- `node:22-bookworm-slim`: `sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392`.

2026-10-09 20:59 UTC local preflight: branch `codex/motive-driver-image-source` at85489841; Vite5173/PID76897 still serves this worktree; proxy targets8000, which has no listener and no approved backend/.env. Local full-stack remains blocked; no runtime or database was replaced. Image validation is registry-level and production build evidence follows.
