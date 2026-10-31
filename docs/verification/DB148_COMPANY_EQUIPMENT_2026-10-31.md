# DB-148 local implementation evidence

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
- PostgreSQL15 rehearsal: actual migration193 applied to isolated populated vehicles schema; unknown defaults preserve both tractor/trailer unit IDs, typed writes accepted, invalid/null rejected, downgrade/re-upgrade preserve row identities/count. Entire transaction rolled back. Rehearsal source:output/equipment/rehearse_migration.py. This tests the new migration against a minimal populated target, not the full historical migration chain.
- `git diff --check` pass.

## Signed-in browser acceptance

Final acceptance: PASS at desktop1440×1000 and mobile390×844. Chromium served the real staff app from this checkout on5187, proxying to a loopback-only fixture API on8017. The API includes the real API router and JWT identity dependencies, plus production settlement-domain error handling; database/Redis state is disposable test state. It is not a WorkOS/SSO or production-middleware verification. No external provider was used.

On both sizes: select the test company; open T1003130; see only its maintenance history; edit notes while preserving trailer type and unit; open the history RO and see Invoice TEST-INV-T1003130; create an equipment record (desktop trailer/mobile other), verify persisted type/customer and visible list item; check all four seeded equipment→RO→invoice identities using real authenticated APIs. Assertions passed with no page errors or unexpected API failures. The disabled settlement endpoint returns its expected409; payment/settlement behavior is outside this change. No payment controls were used.

Visual review found the preexisting VIN Decode control clipped at mobile size; the input now has min-w-0 and button shrink-0. Final screenshots show contained controls and no page or VIN-row horizontal overflow. Add-mode copy now says New equipment and Link/manage equipment.

Evidence: output/equipment/browser-results.json; desktop/mobile-create-equipment.png; desktop/mobile-edit-trailer.png; desktop/mobile-company-equipment.png; desktop/mobile-repair-workspace.png. Repeatable fixture/API and browser drivers: browser_api.py, browser_acceptance.cjs; test Vite config frontend/vite.db148.config.ts. Generated browser_fixture.json contains a disposable JWT and must never be committed/published. Browser drivers require installed e2e dependencies; no real configuration/secrets are copied.

Runtime receipt: base6336ef16 with the recorded HMR-served VIN/copy diff, branch codex/company-equipment-types. Test frontend PID99367 cwd frontend under this checkout; test API first PID99350, then PID2514, restarted only after its exit to register the existing domain handler. Readiness source root matched this checkout. Existing5173 belonged to machined-sidebar and8000 to Docker; neither was restarted or changed. Test runtime was aligned and browser-verified during acceptance, then shut down; the disposable database and JWT fixture were discarded.

Independent equipment_review source and browser-evidence QA/security GO, including the final history→RO→invoice expansion. This is local acceptance, not production verification.

## EDG contract coordination

Architecture cross-checked the active EDG task's docs/DB094_EQUIPMENT_CONTRACT_HANDOFF.md and services dieselbridge_financial.py/dieselbridge_equipment.py. EDG already accepts trucks/trailers via VIN or reviewed equipment allocation. DBN company equipment types need no receiver change while v2 exact keys/revisions/hashes remain unchanged. Future exported fields need a separately versioned contract; no fields were added by this PR. See docs/contracts/db148-company-equipment.md.

Changing source vehicle/VIN requires fresh attribution review against the authorized revision; booked financial effects require explicit reclassification. The user-confirmed Aufine000023→T1003130 fact is recorded without production correction, historical merging, changed billing access, or assumptions about price/date/payment/funding.

## Remaining gates

The user explicitly approved PR publication. Replayed only the two equipment commits onto GitHub main9dea1f1a, excluding unrelated local inventory work. The prior provisional DB-097 ID was already assigned on current main, so this feature is DB-148; its migration193 now follows192. Preserved current main compact customer layout and refreshed browser screenshots/assertions. Current-main focused backend31/31, frontend30/30, build/lint, linear migration graph and PostgreSQL rehearsal pass. Publication/required-check evidence is recorded on the board; merge and release are not authorized. No production migration, deployment or source-data correction occurred.

## PR publication

User approved publication after reviewing the local candidate. Existing-PR lookup returned none. Published PR713: https://github.com/mecaniser/truck-pit-stop/pull/713 on branch codex/company-equipment-types. Required CI is being monitored; merge/deploy/production-data authority is explicitly absent. Independent current-main source/QA review GO is scoped to the changed journey; inherited pale unselected desktop row text was observed and is not broad contrast approval.

CI first-run failure: critical backend594passed/1failed; test_workspace_typeaheads expected the pre-change exact keyset. Updated the exact allowed fields to include equipment_type (without relaxing minimal-payload/tenant guards), asserted legacy unknown, and added four real authenticated typeahead classification cases. Local typeahead suite7/7 passes. Frontend required check and migration job passed on that run; smoke was skipped due backend prerequisite failure. Corrected candidate will rerun all required gates.

Current-main company-panel regressions also had two stale Truck relationships headings; reproduced2failed/16passed before updating intended Equipment wording. Updated headings and typed-tractor label assertions for list/card keyboard journeys; panel+modal18/18 and changed-test ESLint pass. No product behavior changed by these CI corrections.
