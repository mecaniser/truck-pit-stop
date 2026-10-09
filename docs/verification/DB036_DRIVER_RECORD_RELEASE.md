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
