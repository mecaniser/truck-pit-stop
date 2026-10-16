# DB134 / M1 — multiple maintenance programs

Accountable: Backend & Integrations. Lane: High risk (schema, tenancy, financial/stock integration and completion state). Status: **In progress — implementation handoff**. Branch: `codex/maintenance-programs`, base `c42009e08b10003ddc2ab54e96c39a6a61be5bbd`. M1 application implementation is in progress; local preview migration177 applied and retained existing rows; no PR or release yet.

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

## Runtime acceptance plan and safe fixture

Use the existing local Performance Carrier001 / C-0001 synthetic truck in the preserved lab, customer `68cb3854-dbba-4282-815a-824d423e15fe`, vehicle `88040033-d530-47a0-99b1-9e9b7ad3b038`. Source UI currently shows100,713mi; this current reading must never be silently substituted for a historical service reading. Named M1 test programs and orders are local only; preserve or archive test history through the normal product flow after acceptance.

1. Create distinct date/miles/hours programs with explicit known targets; inspect unknown hours, due zero and known-overdue priority. Edit a name directly; change interval while preserving target; explicitly recalculate with reviewed actual evidence. Save/reload and verify history.
2. Record a current manual reading without changing targets. Submit invalid/future values, cancel, and ensure drafts/errors remain visible. Exercise stale update with two local views.
3. Select two programs sharing one service; verify one operation and parts bundle, separate claims and correct captured pricing. Attach existing operation without resetting saved hours/prices/checklists. Duplicate retry and occupied cycle must not create a second order or charge.
4. Complete required work and manager review. Supply complete evidence for one program and omit the other's required reading: normal local finalization succeeds, only the valid program advances; pending program retains all old targets. Resolve later once, preserving original work link/history. Saved financial workflows use named synthetic lab records only.
5. Cancel/delete/restore unperformed local work; remove one shared operation through the existing confirmation; inspect reopen/source-review behavior. Test rollback/conflict alternatives with API/PostgreSQL proof where destructive UI action is not necessary.
6. Repeat changed essential journeys in Light/Night1280desktop,390/320portrait and740×400landscape. Verify visible entered values, correct focus/Escape/close, one content scroll area, no page overflow, unwrapped action labels, and drafts survive fleet's60second refetch. Production checks later use existing records/unsaved drafts and clearly distinguish saved local proof.

Pre-migration exact-row capture at17:36:37UTC covers28 existing financial/configuration/vehicle/PM/checklist/source/membership tables under read-only repeatable-read with20s statement/2s lock limits. Private capture `/tmp/db134-preview-before.json`, helper `/tmp/db134-preview-retention.py`. Requires independent helper review and fresh post-migration comparison; no migration or M1 completion claim yet.

Independent helper review returned the first retention comparator for missing metadata validation. Root corrected comparison to require exact expected before/after revisions, version1, read_onlyon, fixed database/table scope, count/hash shapes and offset/time ordering. Corrected SHA256 `7ed2dbb2d41b3738bbd1d50c57c511a96a47c8a3921954daab2ae8d2066dbd17`; independent negative recheck pending. Original capture was read-only and no database mutation occurred.

Architecture accepted the narrow removal-carrier amendment: direct DELETE uses optional expected_maintenance_fingerprint only when M1 links are affected; PM replacement extends the existing P1 preview with named affected program links and keeps its sole existing pricing token. Old clients fail closed for linked removals; no extra dialog. Backend and Frontend share the frozen shape. Independent retention comparator passes16 connection-free cases; comparator-only GO, migration/application gates remain open.

## Release retention preparation

Private M1 capture/comparison helper is frozen at `Documents/Codex/ets-priority-preparation-20261015/db134-production-retention-v1.py`, SHA256 `592372ecfb5ad5694a2f371c50c389d48cc5c8ac23b95cb39ed567023d298c56`. It protects13 original cohorts across orders/labor/parts/invoices/counter sales, customer terms, vehicle PM targets/packages, payments, inventory and cores; returns only opaque references/hashes/counts. Read-only repeatable-read,20s statement/2s lock limits, fixed cutoff/baseline digest and exact schema/scope checks. Changes and new M1 adoption require review, never timestamp-based exemption.

Root ran capture only against the LOCAL176 preview, then independent reviewer passed28 initial negative cases and15 correction cases after adding payment/stock protection. Comparator-only GO recorded separately. No production execution or application/schema approval follows from these preparation checks. Final revision/source and production environment must be rechecked before actual release use.

## Foundation gate return — 2026-10-16

Independent PostgreSQL probes returned NO-GO: duplicate finalize/advanced completion records were accepted for one program/work/source when recognition_key was null. Backend is correcting durable link/source constraints and must re-freeze/rehearse migration177. Other20 probes passed, including tenant FKs, active-cycle uniqueness, immutable evidence/event requirements and zero/NaN guards. All34 disposable old+M1 table fingerprints were unchanged after rollback. Preview remains schema176, preserved backup intact; no M1 production change.

Frontend contextual editors now appear under the toolbar or selected program row, with first-field focus and Escape/trigger return coverage for20 programs. This is source/component evidence pending actual browser acceptance. Runtime recheck at HEADde8db657 retained frontendPID39898, intended bindmount and direct/proxied readiness200; preview still176.

## Corrected foundation and local migration — 2026-10-16

Independent foundation GO:36/36 real-PostgreSQL probes, including null-key/different-key duplicate rejection and valid pending→resolve. All34 disposable table hashes retained after rollback. Frozen177 SHA256 `ab8513967a6400cbe238cb83c1a67a7a4af78866202a32caf43034b319618432`, maintenance model `9e7770b2cfb4f1a83ca31a3afb1fc4300843a681ba1b8645465c03f9f465738a`, repair-order identity index `a1d8d8609fbc353ffc96bdc2f3adfd66177f17ddfb7a3872ac2a4dc50c8ed3cd`.

Root rechecked all three hashes and captured fresh read-only preview baseline at2026-10-16T18:06:13.148008+00:00, applied normal Alembic176→177 to the preserved local database, then captured post-state at2026-10-16T18:06:25.311646+00:00. Comparator returned **all28 original tables/rows unchanged**, zero changed tables. Private captures `/tmp/db134-preview-before-migrate.json` and `/tmp/db134-preview-after-migrate.json`. Both direct8001/proxied5174 readiness200, DB/Redis okay; solehead177. This is local schema/foundation proof, not full application acceptance or production release. Backend may expose coherent foundation routes after its legacy/merge writer guards; complete work/evidence/lifecycle gates remain open.

## Bounded service gate return — 2026-10-16

Independent Findings4/5 reproduce private outside-service UUIDs exposed via nested Fleet reading provenance despite outer masking, and pre-reset same-day readings selected after rebaseline. Backend owns corrections and regression evidence; reviewer uses ephemeral isolated tests, no preview/production writes. Architecture is clarifying old recognize-pm compatibility and native-RO reading provenance because historical completion can copy Vehicle.mileage into mileage_out. Application acceptance remains open.

## Legacy recognition clarification — 2026-10-16

Architecture and Product/Delivery accepted a narrow backward-compatible old recognize-pm adapter: explicit staff-reported legacy attestation, one atomic scalar/program advance, no independent/occupied/review bypass. New M1 evidence never edits source. Raw native RO output/arrival mileage is not admissible actual service evidence because existing routes can carry/fallback it; require explicit confirmed actual inputs instead, with no provenance backfill. Frontend removes misleading source-reading choices and silent legacy input defaults. Focused owner regressions and independent recheck required.
