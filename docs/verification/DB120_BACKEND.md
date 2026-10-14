# DB120 backend implementation handoff

Board: DB-120. From Architecture & API Contracts / Backend & Integrations to Product, independent QA and Security. Implementer: external_history_contract. Branch `codex/vehicle-history-export`, base `a340cfd978bef4580fb989298d008f8f4e405fc9`. Contract: [db120-vehicle-history-export](../contracts/db120-vehicle-history-export.md).

## Delivered

Staff-only exact active vehicle CSV endpoint, mounted at `GET /api/v1/vehicles/{vehicle_id}/service-history.csv`. Optional inclusive History from/to filters; complete qualifying history independent of UI pagination. Completed/invoiced/paid nondeleted orders and active outside-shop entries, with truthful native/imported/reported date and historical odometer labels. Each row has vehicle/record provenance. Only work descriptions and active same-tenant labor descriptions are exported. No cost, invoice, payment, contact, internal/customer/vehicle/operation note, audit-snapshot or current odometer/PM fields.

Dedicated column projections and tenant predicates on every data family; owner/admin/receptionist allowlist before data access. Active-target recheck rejects a known completed archive/merge before emitting CSV. Transferred and merged history stays with the physical vehicle; outside original-vehicle identity is retained. No migration, model change, mutation, database locking or provider call.

Success uses UTF-8 BOM CSV, safe UUID filename, row-count and exact vehicle identity headers, no-store/nosniff. Download metadata headers are explicitly exposed for existing configured CORS clients; no allowed-origin or permission expansion. Expected and unexpected errors are JSON without attachment metadata; unexpected failure response does not disclose exception details. Formula triggers are neutralized in every untrusted text cell after control cleanup, while CSV commas/quotes/newlines round-trip.

Independent Security returned an initial resource-bound finding. The final service first selects only capped record/operation IDs; rejects operation-count overflow before text-length inspection; aggregates raw character lengths in SQL; then fetches capped text projections with streamed cumulative checks. This bounds legacy unrestricted text before materialization and covers text growth committed between preflight and fetch. Exact final UTF-8 output bytes are capped. No successful partial/truncated export. Maximum1,000records,10,000operations,2MiB raw text characters /2MiB output. This raw-input cap can conservatively reject a record full of removable control characters; the explicit413 is preferable to an unbounded read.

## Evidence

Runtime preflight before edits: intended branch/base matched; Vite PID47264 serves approved preview5174; Docker API8001 binds preview/backend. Implementation295backend files and177migrations byte-identical to preview before changes. HTTP preview and readiness200. Parent owns database identity/schema169 proof, source mirroring and actual authenticated browser acceptance; this agent did not alter preview, restart services, apply migrations or claim runtime visibility.

Commands run with `/Users/sergio_m1_promax/GitHub/truck-pit-stop/backend/venv/bin/python` from implementation/backend:

- `-m pytest tests/test_vehicle_history_export.py -q --tb=short`: **31passed**,12.18s, `/tmp/db120-export-final.log`. Final application source, including operation-ID cap-before-text correction.
- `-m pytest tests/test_vehicle_history_export.py tests/test_external_service.py tests/test_vehicle_identity_relationships.py tests/test_vehicle_merge.py -q --tb=short`: **92passed**,24.15s, `/tmp/db120-backend-tests.log`. Adjacent regression run before the final operation-ID-query tightening; final31-case run above covers that correction.
- `-m pytest tests/test_vehicle_history_export_postgres.py -q --tb=short`: **3passed**,2.90s, `/tmp/db120-postgres-tests.log`. Final application source. Existing guarded isolated local db110_test database only, separate pytest process to avoid SQLite UUID fixture contamination. Synthetic tenant cleanup; no preview/production DB writes and no migration.
- `compileall` for both new application modules and `git diff --check`: pass.

The31cases cover allowed/denied roles, missing tenant, active/archived/foreign vehicles, deliberately inconsistent foreign source/labor fixtures, deleted/voided/open-state exclusion, history beyond25records, source/dates/unknown/zero/carried mileage, DST/date-range boundaries, no private/financial data or writes, transferred/deleted customer and merged-truck semantics, CSV escaping/formulas, request validation, private JSON failures, record/operation/UTF-8 caps, preflight rejection before text fetching, and simulated text growth. The3real PostgreSQL cases exercise native DST/imported midnight dates and actual streamed dialect queries; separately committed oversized text after preflight; and separately committed archive before final response. They are not claims of immutable snapshot isolation: concurrent edits can appear in a later export.

## Files and next gate

Application: `backend/app/services/vehicle_history_export.py`, `backend/app/api/v1/endpoints/vehicle_history_exports.py`, `backend/app/api/v1/router.py`.
Tests: `backend/tests/test_vehicle_history_export.py`, `backend/tests/test_vehicle_history_export_postgres.py`.
Architecture: `docs/contracts/db120-vehicle-history-export.md`.

Parent notified final source stability and required service-only remirror after the last query tightening. Independent reviewers own Security/QA GO. Product owns frontend integration, actual downloaded CSV acceptance on desktop/mobile, protected CI, PR/merge/deploy, board and release record. No commits, release, production verification or self-approved gates by this implementer. Rollback is an additive endpoint/UI revert; no data repair needed.
