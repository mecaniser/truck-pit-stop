# DB-097 local implementation evidence

Accountable owner: Backend & Integrations. Architecture reviewed the contract; independent reviewer `equipment_review` issued source-level QA/security GO, not runtime/release GO.

## Current behavior and change

DBN previously stored generic Vehicle records without equipment classification. Customer create/edit forms called them trucks/vehicles. RepairOrder.vehicle_id already points to the individual physical asset; invoices reference repair orders. No new invoice linkage or company authorization is needed.

The candidate adds tractor/trailer/other/unknown classification, staff company creation/editing, type labels on table/cards and searchable type labels. Legacy records/omitted legacy creates default unknown. Explicit null/invalid values fail validation; omitted updates preserve classification. Merges require equal classification and snapshots record it. Existing routes, IDs, company roles, bill-to scope, repair/invoice relationships, and EDG v2 export shape remain intact.

User evidence: Aufine invoice 000023 belongs to trailer T1003130, not tractor609. This implementation makes no production assignment or historical invoice correction.

## Verification

- New equipment contract/CRUD/tenant/merge/repair-invoice tests:5/5.
- Existing DB094 invoice-export scope/revocation/pagination/regressions:8/8.
- Existing vehicle identity/merge regressions:11/11.
- Existing company workstation:15/15; new equipment modal create/edit:2/2.
- Production frontend build, TypeScript noEmit and changed-source ESLint pass.
- PostgreSQL15 rehearsal: actual migration157 applied to isolated populated vehicles schema; unknown defaults preserve both tractor/trailer unit IDs, typed writes accepted, invalid/null rejected, downgrade/re-upgrade preserve row identities/count. Entire transaction rolled back. Rehearsal source:output/equipment/rehearse_migration.py. This tests the new migration against a minimal populated target, not the full historical migration chain.
- `git diff --check` pass.

## Remaining gates

Signed-in desktop/mobile equipment and repair-to-invoice browser acceptance is pending. Component fixtures and database join tests do not replace that gate. Browser CLI startup was cancelled after it yielded no output; shared app services were not changed. Protected PR/CI, merge and release are pending. No production migration/deployment/data change occurred.

EDG's existing v2 consumer rejects extra fields, so the producer shape is unchanged. Equipment-type export requires a coordinated version change; trailers must not be automatically posted through a truck-only consumer. A VIN/vehicle correction must require fresh attribution review. Keep this item release pending until those rollout constraints are addressed; existing billing access is never inferred from a source reassignment.
