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

Motive555 is merged at c9beafe4; its owner handed back the completed driver canary at18:14:53UTC. Collector558 owns the next slot after its six protected checks and current ETS collector idle gate; session556 integrates afterward through the authorized coordinating owners. M1 remains local implementation and must not jump that release sequence. External owner handoff is coordination evidence, not M1 application acceptance.

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

## Local fixture preparation and correction checkpoint — 2026-10-16

Independent correction-only GO closes Findings4/5 after original and expanded probes: nested fleet source IDs scrubbed while authorized/stored provenance remains; same-day pre-reset observations excluded and valid later readings still admitted. Full application gates remain open.

Root created `DB134 QA Shared Maintenance` via the actual local service catalog, ID`75a424f3-d721-42d2-a70a-8404b6f11310`:30minutes, blank flat-rate override, two required tasks (Verify service condition; Verify final reading), one Performance replacement part0004 / inventory`a9d420c7-7678-43d5-a645-5d77fbd948d0` quantity1. Saved UI shows131.50 (72.50labor+59part). This named synthetic lab fixture was created after successful migration retention comparison; no production catalog, stock quantity or financial records changed. Existing inactive DB132 fixture was left intact. Screenshot `/tmp/db134-local-service-fixture.png`.

## Saved local mobile CRUD and gate returns — 2026-10-16

Actual signed-in Performance lab UI created DB134 QA Oil service (30days/1,000mi, targets2026-10-16/100,713mi), DB134 QA Engine hours (100hours, target500hours), and DB134 QA Safety (90days, target2026-10-15), all using the named shared service fixture. UI correctly reports Due, Unknown, and Overdue respectively. Oil name changed to DB134 QA Oil service edited and interval45days using Keep targets; date/mileage targets stayed unchanged. Safety archived through confirmation and remains available under Show archived with unchanged target/history. Restore is hidden because backend can_archive is false for archived records; returned to Backend before acceptance.

At390×844 mobile/touch emulation, document dimensions390×844 have no horizontal/outer vertical overflow. One slide-panel content scroller (client730, content2468) lies between header/footer; screenshot /tmp/db134-mobile-initial.png. This is emulation, not physical-device evidence. Desktop outer-page scrolling remains under investigation; no blanket layout signoff.

Reading entry starts blank. Negative mileage produces inline validation with draft retained. Native type=time DOM fill does not survive rerender in this browser; keyboard entry also left it blank. No reading POST succeeded. Frontend owns a narrow accessible manual24-hour HH:MM correction with strict validation; no assertion that this is a proven physical-device defect. Screenshot /tmp/db134-time-input.png.

Independent legacy adapter gate returned three reproduced blockers (Findings6–8): server-day rather than shop-day validation, an older recognition overwriting newer controlling M1 evidence whose source correctly remains is_pmFalse, and coercive/out-of-range legacy request input. Backend owns narrow corrections; independent20 probes were12pass/8fail, all failures mapped to these findings. Existing five owner regression cases pass independently. Prior schema/privacy/reset gates remain valid; no full application/release GO.

## Foundation UI correction recheck — 2026-10-16

Root actual UI confirms corrected archive capabilities now expose Restore. Restoring DB134 QA Safety through its confirmation returns Overdue2026-10-15/every90days unchanged. Oil edit survives reload and its history shows separate Create/Update entries. Reading form now saves manual HH:MM successfully:100,713mi/400hours observed10:00 local remains accepted-but-stale/Unknown; a14:32 local observation changes the hour-only program to Current while all saved targets remain unchanged. These are synthetic lab observations, not telemetry or actual customer service evidence.

Desktop overflow was traced to absolute sr-only labels escaping unpositioned history/search containers. Frontend added local containing blocks and retained accessible labels/descriptions. Actual1280×900 now has document900×1280, scroll0, and one584px panel content scroller. Light Shop320×740 editor focuses Name in view, retains invalid0-day draft, focuses validation, and Escape returns to Edit with no save; document740×320 and one626px content scroller. Light740×400 has document400×740, one278px content scroller, footer buttons348–392px; Add program draft and Escape return pass. Night390×844 previously passed one content scroller; complete work/finalization acceptance remains pending backend integration.

Private visual evidence: /tmp/db134-local-light-desktop.png, /tmp/db134-local-light-320-editor.png, /tmp/db134-local-light-landscape-editor.png. Frontend reports manual-time17/17 and history/accessibility50/50 focused tests, TypeScript and strict changed-file lint passing. No production M1 writes or release.

## Legacy correction-only independent GO — 2026-10-16

Independent reviewer reran the original20 probes (all pass) and four extra boundary cases plus five prior regressions (9/9 pass). Findings6–8 are closed: actual shop-future422 with rollback; older target/controller/provenance retained; equal-date409; newer actual advance; raw-RO reading rejection/manual0; strict legacy types, range and unknown-field rejection. Scoped seven-function aggregate `bc35801c451d9cd86eb39d273f81b1071c8eacbf66384cb4f916ed856760460b`, private manifest `/tmp/db134-independent-legacy-corrected-manifest.json`. This correction recheck used isolated tests only, no preview/production/browser writes, and does not approve the unfinished work/completion lifecycle or release.

## Actual draft persistence and stale-edit acceptance — 2026-10-16

After Frontend source froze, the fleet draft DB134 fleet refetch draft /60days remained unchanged from18:36:18Z to18:37:53Z. Read-only browser network observation confirmed successful periodic fleet board/truck responses during that window. Cancel discarded the unsaved draft; no fleet program was created. An earlier attempt interrupted by development hot reload was excluded from acceptance.

Two actual local customer-truck views loaded the same Oil version. One saved DB134 QA Oil service current; the older editor retained DB134 retained conflict draft and received the program-changed error on both initial save and retry. Explicit Discard draft & reload saved loaded the current saved name; Cancel left it unchanged. The extra test tab was closed. Dates/mileage targets stayed2026-10-16/100,713mi and interval45days. No forced state/DOM/API mutation was used.

Architecture accepted the existing legacy schedule-pm one-time-package seam: capture actual explicit order package in immutable cycle configuration while preserving saved defaults when save_as_default=false; use that captured package for completion/lifecycle. Ordinary new M1 exact configured-package rule remains. Canonical contract updated before Backend integration; focused one-time/default-saving/schedule-only/missing-mapping tests required.

Night Shop390px manual reading recheck rejects24:00 with a focused HH:MM error and retains all entered values. Correcting to14:39 and saving succeeds;400hours remains Current against unchanged500hour target. At320×740, expanded source details and all actions wrap within document320×740, with a single626px content scroller and reachable footer. Screenshot /tmp/db134-night-320-provenance.png. No blanket final-workflow signoff: linked work and completion remain unopened until Backend activation.

## Bounded independent frontend gate returned — 2026-10-16

The frozen142a1b99 frontend checkpoint passes92 relevant independent tests across eight files. Two separate isolated reproductions return the gate: (1) refreshed program selection can silently narrow two selected IDs to one in an aggregate plan; (2) the old recognition calendar uses a UTC max-date cap, excluding a valid shop-local day even though the corrected backend accepts it. Frontend owns explicit selection review/blocking and removal/correction of the wrong date cap. Root has not exercised unavailable work routes. Exact private logs: /tmp/db134-independent-frontend-selection.log and /tmp/db134-independent-frontend-legacy-date.log. No production writes or release approval.

Actual selection correction recheck: one local tab selected Oil+Safety and opened Oil edit; another archived Safety and saved a newer Oil version. The original save conflicted and refreshed the list; Cancel retained two selected IDs, displayed selection-changed guidance, and disabled Plan work2 rather than submitting a one-program plan. Clear selection on390px mobile removed the warning/count. Safety was restored with unchanged targets in the second tab, then the tab was closed. Oil's current saved fixture name is DB134 QA Oil service latest. Screenshot /tmp/db134-selection-changed-desktop.png. No maintenance work request was issued in this check.

## Linked-work activation and completion gate return — 2026-10-16

Independent Findings9/10 correction-only GO closes selected-ID loss and shop-local calendar defects:35 changed tests, five independent selection probes and the original Sydney date reproduction pass. Full backend/release gates remain open.

After Backend activated all work routes, actual local UI selected Oil+Hours, reviewed one shared service, then created synthetic order `702c5103-f38c-4ffb-8e0e-2f4513eec46d` / PERF-295757AF-000014 with description DB134 shared maintenance workflow QA. It contains one30minute operation, two required checklist tasks and one59.00 part, total131.50. Screenshot /tmp/db134-shared-work-preview.png. Root saved duration45minutes and manual rate150 using blur, reloaded and confirmed171.50. Safety was then attached to that existing operation through review:171.50,0.75hours and one retained part remained unchanged; no duplicate bundle. The earlier Enter-only rate input had not saved and is excluded from preservation evidence.

Root started the named synthetic work without an order-level technician, checked both required tasks, assigned Performance Mechanic1 to its operation and completed that operation. The order remains In Progress, one operation complete,171.50; manager maintenance finalization is not yet accepted. No production service, financial or inventory mutation.

Independent carrier review reproduced a blocker before finalization: five frontend GET maintenance requests omitted mandatory channel, causing actual ASGI422 before review. Frontend owns initial/reload/query/removal carrier correction and exact request tests. The direct Fleet completion preview channel correction itself is correct. Finding11 remains open until independent recheck; passing permissive frontend mocks do not establish runtime acceptance. A misleading shop-policy rate label on wholly retained work is also returned to Frontend; retained monetary values themselves are correct.

Architecture accepted semantic finalized-status fingerprint normalization while retaining exact immutable RO snapshots. Completed→invoiced→paid alone must not invalidate service evidence; actual source changes and durable lifecycle review remain bound. Canonical contract updated before Backend correction/tests.

## Actual finalization, pending resolution and fleet gate — 2026-10-16

Finding11 carrier correction independently passes54 frontend and3 actual-ASGI checks. Root opened corrected review in Night390/320/740x400 and desktop1280. The date input clipped at320; Frontend corrected maintenance DatePicker grid span, and actual Light320 shows full2026-10-16 in a296px field. Action labels remain unwrapped and dialog document dimensions match viewport; one content scroll area and visible footer. Affected-order labels are deduplicated without dropping claims.

Actual shop review on PERF-295757AF-000014 selected Safety+Oil with synthetic confirmed2026-10-16/101000mi and left Hours unchecked. Preview retained Hours500 pending; finalization succeeded with invoice171.50, one operation/part. Oil advanced to2026-11-30/102000mi and Safety to2027-01-14. Actual Light320 resolution supplied only confirmed500hours/date and advanced Hours500→600 once. History retains original Pending and Resolve pending entries. Reaffirm with an explicit local QA reason saved600→600, with a separate audit entry; source navigation opened the correct invoiced order and browser Back returned to the same truck.

Post-finalization initially showed false Review required: prior same-day manual100713/400 observations were compared against newly accepted date-only101000/500 evidence; even date-only Safety inherited unrelated meter review. Backend corrected chronology admission and enabled-meter filtering under the accepted contract, preserving raw evidence. Actual reload now shows all three Current, exact expected targets, no spurious review. No production mutations.

Fleet Light320 created DB134 QA Fleet inspection (30days,target2026-10-16) on Performance Fleet F-0001. Actual Plan work requires Bill to and offers its authorized Performance Fleet account. Saved PM order PERF-295757AF-000015 / DB134 fleet maintenance lifecycle QA contains one30minute operation, one part, two required tasks at internal61.50. Confirmed unperformed removal lists the active cycle, removes the bundle to0/0.00 and releases the program to Plan work with target unchanged. Replanning on the same order restores one bundle at61.50; no second order.

After starting fleet work and checking both required tasks, actual finalization preview showed the date advance but finalization correctly rejected the incomplete operation. Fleet editor exposes no operation completion control. Frontend owns reuse of existing capability-driven operation execution controls plus early eligibility feedback; Backend adds existing read-only readiness guard to preview without removing final checks. The failed finalization was cancelled; order remains In Progress, program In work at original target. Full saved fleet completion and final gates remain open.

Private evidence: /tmp/db134-night-desktop-targets.png, /tmp/db134-night-320-targets.png (pre-width-fix), /tmp/db134-night-landscape-targets.png, /tmp/db134-light-320-resolve-evidence.png, /tmp/db134-light-mobile-maintenance-current.png, /tmp/db134-light-mobile-remove-review.png, /tmp/db134-light-fleet-operation-gate.png. Mobile is viewport/touch emulation, not physical-device testing.

## Saved fleet completion and final independent corrections — 2026-10-16

Root actual Light Shop320×740 verifies the corrected Fleet operation controls: assignment to Performance Mechanic2 and Complete operation succeed with existing capability/version checks. Order-level Complete stays blocked until the tracked operation is complete. Actual maintenance review then finalizes PERF-295757AF-000015 at61.50 and advances DB134 QA Fleet inspection from2026-10-16 to2026-11-15 once. Source navigation shows the invoiced order, completed operation, two checked tasks and unchanged61.50. History preserves attach/remove/replan/finalize and now omits absent meter lines while retaining date/result/source. Screenshot `/tmp/db134-light-320-fleet-operation-complete.png`. Both saved shop and fleet completion journeys now pass locally; mobile evidence remains viewport/touch emulation.

Frontend seven-file final checkpoint f5efc118 has66/66 focused tests plus TypeScript, strict changed lint and diff checks passing. Independent Fleet execution review passes21/21 cases. Fleet maintenance confirmation uses Complete repair order while shop keeps Finalize & Send Invoice.

Backend frozen checkpoint1eee68e6 passed132 maintenance and10 real-PostgreSQL tests. Independent chain Findings12/14 and original13 reproduction now pass, but the full gate remains returned: an additional delete/restore same-digest variant of13 can clear the current source's durable review when older evidence is reaffirmed; Finding15 exposes a private outside-record ID in nested receptionist history readings. Backend owns narrow corrections and regressions. Additional independent actual-HTTP tenant/membership probes pass with no writes on denied attempts. No protected CI, M1 production deployment or whole-application GO yet.
