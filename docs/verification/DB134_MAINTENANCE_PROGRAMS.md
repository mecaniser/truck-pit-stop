# DB134 / M1 — multiple maintenance programs

Accountable: Backend & Integrations. Lane: High risk (schema, tenancy, financial/stock integration and completion state). Status: **In progress — implementation handoff**. Branch: `codex/maintenance-programs`, base `c42009e08b10003ddc2ab54e96c39a6a61be5bbd`. No M1 code, applied migration, PR or release yet.

## Outcome and acceptance

One truck can have separate date, mileage and actual engine-hour programs. Due status remains independent of work status. Staff can explicitly share one operation between selected programs, add work to an eligible order or create one atomically, and retain saved prices/stock/checklist identities. Managers confirm actual service evidence; missing readings preserve targets and stay pending.

The [v1 contract](../contracts/db134-maintenance-programs.md) defines all API shapes and acceptance cases. Required evidence includes independent triggers, trustworthy readings, versioned edits, shared operations without duplicate billing, captured P1/C1 terms, both completion paths, pending resolution, source/lifecycle corrections, tenant/role isolation, concurrent claims, additive migration/legacy retention, and actual Light/Night desktop1280 plus mobile390/320/740×400 browser-emulated workflows. No new notifications, scheduler, provider integration, financial backfill or automatic order generation.

Existing legacy PM behavior and scalar values must remain unchanged until explicit conversion. Defaults alone do not enroll trucks. All existing financial rows must survive migration unchanged. A populated downgrade must refuse evidence loss. No independent QA/release approval is implied by the contract.

## Runtime alignment — 2026-10-16

Root read and ran dieselbridge-local-runtime after branch switch. Intended checkout `/Users/sergio_m1_promax/.codex/worktrees/ets-checkpoint-merge/truck-pit-stop`; branch `codex/maintenance-programs`, HEAD `c42009e0`. Dirty files at intake are known C1 release receipts/tracker/board, preserved for commit.

- Frontend `http://127.0.0.1:5174`, PID39898, Vite cwd intended checkout/frontend, effective `DIESELBRIDGE_API_ORIGIN=http://127.0.0.1:8001`.
- Backend container `dieselbridge_api_ets-workflow-parity`, running image `bde2e27ba1f9353127cca22d4643b6fa0dd47336223c739c3bc5e83c9f480ea4`; intended checkout/backend mounted rw at/app; localhost8001→8000.
- Database host `postgres`, database `truckpitstop_ets_workflow_parity_20261012`, Alembic solehead `176_merge_contact_pricing`. No restart, reseed, provider/tenant-flag change or migration at intake.
- Direct8001 and proxied5174 `/health/ready` both200 with DB/Redis okay. Signed-in Performancecustomer Businesssettings Pricing shows Labor145/hrShop, matching current C1 source. Aligned and browser-verified for the inherited baseline; no M1 rendering claim yet.
- Root controls preview backup/migration. Backend uses isolated disposable tests first.

## Ownership and gates

Architecture owns frozen contract. Backend owns all backend/schema/lifecycle integration and backend tests; Frontend owns shared maintenance UI/types/adapters and frontend tests. Root owns docs, actual browser verification, preview migration and release. Independent QA/Security must not implement or direct application changes.

## Release ordering

Motive555 has the next protected merge/deploy/canary slot, then collector558 after555 handback and active collector idle. M1 local implementation can continue; no main merge/deployment jumps that sequence.

## Preserved preview backup

Before M1 schema work, custom-format backup captured at `/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/db134-preview-schema176-before-m1-20261016T1735Z.dump`: mode0600,4,035,153bytes,1,775 archive entries, SHA256 `ecdd6d5a250b64e0c2dbf96a357b0a6a31c59fc3cd42d66e9ad7a3b3858a72ab`. `pg_restore --list` succeeds. This local backup is not committed or uploaded. No preview migration has occurred.

## Architecture handoff — 2026-10-16

Architecture verifies c420 application tree equals prepared0a193, sole schema176 and dynamic Worker expected-head discovery. Accepted v1 explicitly returns resolved source readings for confirmation, limits historical RO recognition to completed/invoiced/paid, and preserves entire multi-service legacy packages with one cycle claim across all mapped operations. These are source-backed completeness corrections, not new scope. Product & Delivery accepts canonical v1 before parallel Backend/Frontend implementation.
