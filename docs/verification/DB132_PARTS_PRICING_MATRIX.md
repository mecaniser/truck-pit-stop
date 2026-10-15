# DB132 / P1 parts pricing matrix

Accountable: Backend & Integrations. State: **In progress — implementation and local acceptance; independent corrections returned to owners**. Selected second in the [parity tracker](../ETS_PARITY_TRACKER.md), after R1 production closure.

## Scope and acceptance
[Architecture contract](../contracts/db132-parts-pricing-matrix.md) defines acceptance, writer coverage, privacy, tenant/concurrency boundaries and production verification limits. Reuse existing inventory settings and price controls; preserve compact desktop and complete mobile journeys. No existing prices, inventory valuation, financial records or shop defaults change merely from deployment.

## Source and preparation
Branch `codex/ets-parts-pricing-matrix` begins at R1 merge7b3dc4b3. Preparation reviewed21546789; full application tree is identical. Backend/frontend integration handoffs and later C1/M1/B1/A1 drafts are preserved in `/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/`; those are preparation, not completion receipts. Canonical tracker retains all29 discoveries and selected order.

## Remaining gates
All-writer integration and focused automated checks; final independent QA/Security; actual Light/Night desktop/mobile workflows; focused PR and protected CI; exact release; authorized production acceptance with no invented real-shop pricing activation. P1 source, migration and synthetic inactive configuration are local only; no PR or production release yet.

## DB137 prerequisite closure and implementation handoff — 2026-10-15
Compact controls DB137 are Done after PR539 exact deployment and Light/Night desktop/mobile production acceptance. P1 now continues on `codex/ets-parts-pricing-matrix-implementation` from `fc92c7b9944a0d07db80399b9f6e1eda13840b87`; the older preparation branch is preserved. Architecture owns canonical incorporation of four accepted wire/deletion clarifications before frontend/backend work begins. Backend owns all backend integration writers and migration together; Frontend owns the shared configuration and workflow UI. Independent gates remain separate.

Local runtime realigned after branch switch: frontend PID52183 serves this checkout/frontend on5174 with explicit API origin8001 and matching served branch/SHA stamps. Docker `dieselbridge_api_ets-workflow-parity`, image `bde2e27ba1f9353127cca22d4643b6fa0dd47336223c739c3bc5e83c9f480ea4`, binds the same checkout/backend on8001. Database identity remains `postgres/truckpitstop_ets_workflow_parity_20261012`, migration173. Direct and proxied readiness database/Redis healthy. Backend/config/flags/data untouched. Preview is aligned but currently browser-unverified for P1: session expired; user asked to restore sign-in. No new feature rendering or policy activation claimed.

Runtime sign-in restored by user; actual Performance Owner / Diesel Bridge Performance Lab dashboard renders `codex/ets-parts-pricing-matrix-implementation@fc92c7b`. Local5174 is aligned and browser-verified for the baseline; P1 feature acceptance awaits completed implementation/migration. Architecture accepted the canonical projection/deletion contract; backend and frontend began assigned implementation. Additional exact configuration/preview envelopes are being finalized before those adapter edits. No P1 completion or release claim.

## Acceptance ledger
Entries are updated from actual evidence rather than inferring runtime success from component tests. Local mobile means responsive/touch browser emulation, not physical devices. Partial cells are not full journey approval.

| Journey | Local Light/Night desktop,390,320,740 landscape | Automated boundary evidence | Production permitted acceptance |
| --- | --- | --- | --- |
| Settings entry, empty state, Back/cancel | Night desktop entry/empty passed; phone Escape closes, focus return correction pending |18 foundation tests independently pass; final negatives pending | Read-only entry/empty/history |
| Matrix draft preview/save/reload | Night desktop samples20→40,25→37.50,100→130/save/reload passed. Night320/390/740 sample/history and one scroll/no overflow passed after input contrast fix; density refinement and Light pending | Bands/config/tenant/CAS foundation covered; final integration pending | Draft preview only; no real policy save/default |
| Default, revision, clear, archive/restore | Night390 inactive archive/restore/revision1→2 and old history retained; invalid gap rejected with draft kept. Default/clear and other cells pending | CAS/ABA foundation passes; PostgreSQL immutability pending | Authorized reads; no guessed activation |
| Fixed price, pricing-cost floor, minimum sale price | Pending | Distinct precedence/null/invalid combo pending | Authorized policy read/draft preview |
| RO direct + bundle add; retained price after revision | Pending | All writer/stock/financial snapshot coverage pending | Historical value unchanged; cancel previews |
| Manual, List/Stock, discount rejection and409 review | Pending | Role/CAS/minimum/atomic rollback pending | Existing editor and cancel; no real price edits |
| Internal/external fleet and restricted roles | Pending | Projection/tenant/assignment negatives pending | Scope/read-only/cancel |
| Counter-sale retained draft and additions | Pending | Immutable IDs/snapshots/tax/return regression pending | Existing gate respected; no real sale |
| Legacy/locked history and account/tenant switch | Pending | Serializer/replay/cache boundaries pending | Read-only historical checks |

Local database checkpoint before any P1 schema changes: `Documents/Codex/ets-priority-preparation-20261015/db132-local-before-migration.dump`, custom pg_dump,3967918bytes, mode0600. Preserves existing populated local database; do not commit or upload database data. Disposable migration proof precedes a coordinated preview upgrade. No production database checkpoint or production financial mutation performed.

## Additive migration174 — local evidence
Backend tested full disposable upgrade,174→173→174 and a seeded173 legacy row: original cost12.34, sale24.68 and stock7 preserved; floorsNULL/fixedfalse/version0, no matrix/default seeded. Logs `/tmp/db132-backend-evidence/{upgrade,downgrade174-173,upgrade173-174,compat-down,compat-seed,compat-up,compat-check}.log`. Root reviewed migration then revalidated the preserved local DB identity and applied173→174 on the backed-up preview database. Alembic confirms174, readiness database/RedisOK. No matrices, default policies, events, configured inventory policies or nonNULL usage snapshots existed immediately after upgrade. ORM implementation now proceeds. This is local schema proof, not production or independent gate approval.

## Local runtime and configuration QA — 2026-10-15 21:41–21:46 UTC

Current branch/HEAD remains `codex/ets-parts-pricing-matrix-implementation@4d6d5b13` with owner source edits; frontendPID52183/source unchanged, served startup stampfc92c7b. A backend reload import failure was fixed by the owner; root restarted only the verified owned container at21:40UTC. Fresh app import, direct8001 and proxied5174 readiness passed; source mount/database identity unchanged, Alembic174. Actual Parts pricing gear/dialog demonstrates served edits. This is aligned and browser-verified for the partial local journey.

Created local synthetic inactive matrix `DB132 QA — matrix`, ID`e76e124b-276f-4f77-8320-b0b442208f7e`, in Performance Lab. Bands0–25@100%,25–100@50%,100+@30%; previews20→40,25→37.50,100→130. Save/reload retained revision1; archive/restore works; changing third markup31 createsrevision2 while revision1 history stays30. Invalid cost gap26 is rejected with draft retained. Default activation confirmation was cancelled; no default or part policy was activated. Existing catalog stock/values unchanged.

Night heading and input contrast failures were returned to Frontend and corrected. Rendered input foreground246/248/251 against background17/31/51, all values visible. Night320×740,390×844 and740×400 sample/history flows fit their viewport with one dialog content scroller and no document overflow. Evidence `/tmp/db137-qa/p1-night-{settings-header-fixed,matrix-390,matrix-320,matrix-landscape}.png`. Focus restoration after Escape and denser mobile bands remain under correction; this is not final visual acceptance.

Local session then rejected appearance saves with401 Invalid authentication credentials. Reload and one normal retry failed; preview was cancelled to restore saved Night appearance. User asked to sign in again; Light and remaining authenticated mutation checks pending. Independent review and owner automated work continue. No production policy mutation.

At21:49UTC normal inventory navigation refreshed the app session; a fresh appearance save returned200 and UI showed “Applied across this account.” No credential or authentication setting was changed, and no additional sign-in is needed. Local Light QA resumes; restore original Night after acceptance.

## Managed local order pass — partial, 21:50–21:55 UTC

After backend's coherent145-test checkpoint, activated the synthetic matrix only in local Performance Lab. Created one synthetic order through the actual new-order UI: `PERF-295757AF-000006`, ID`dd2a606d-1500-4456-8eb0-9997553fd76c`, description`DB132 QA — parts pricing workflow; synthetic local test`. Part0001 actualcost26 resolves to39 at50%markup, review confirmation attaches one line. Quantity1→2 produces78; manual35 requires a reason and then yields70/Manual. LineID`33ae9d9b-cf04-4886-b4b5-561a980075bd`. No quote, invoice, payment, completion or production mutation.

Observed blockers returned to owners: Review parts pricing panel is clipped by the repair-order ancestor at desktop1280 (screenshot `/tmp/db137-qa/p1-light-managed-review-desktop.png`); move only P1 overlays outside the clipping container while preserving theme. Notes GET unexpectedly fails with missing`NOTE_EVENT_TYPES`; backend restoring adjacent definition and notes regressions. List action needs further UI verification; no backend PATCH was observed after selecting it, so no successful restore is claimed. Default remains synthetic-local active for the remaining workflow tests and must be cleared during cleanup.

Light desktop matrix sample works; Escape correctly restores focus to Catalogue maintenance after the fix. Mobile two-row bands are readable and no horizontal overflow; close target width correction44 and “Under” wording landed but final screenshot recheck remains. Light/Night full matrix and managed workflow acceptance is still incomplete.

## Release acceptance plan — not yet executed

- Recheck main ancestry, migration head and open migration-bearing PRs before final candidate. At21:47UTC main remainsfc92c7b9; open PR540/536/534 do not claim migration174. Run protected checks on the final candidate; cancelled or older successful runs do not satisfy the gate.
- Web pre-deploy already runs `alembic upgrade head` and schema preflight. Verify174 completes before the exact merged application starts; inspect relevant worker overlap for missing-column errors. Preserve additive columns and append-only records on rollback.
- Record exact Web deployment/build SHA, readiness, migration and baseline pricing configuration counts. Deployment alone must not create a default matrix or configure inventory policies.
- Production acceptance uses signed-in owner settings entry, existing configuration/history reads, unsaved sample previews and cancellation, existing order/history value comparison, Light/Night desktop1280 and320/390/740 landscape. Do not activate invented pricing, issue quotes or complete counter sales. Any genuinely unavailable role/flag workflow must be identified rather than counted as browser-verified.
- Observe the changed routes and normal order reads after deployment for unexpected5xx, validation failures, privacy leakage or historical price changes. A release failure stops further parity work and returns to the owner. Prior-code rollback is safe only after confirming that it will not bypass any newly activated policies; after real adoption prefer a forward correction or an explicitly reviewed mutation hold. Never downgrade174 or erase pricing evidence in production.

## Coherent local writer checkpoint — 2026-10-15 21:58–22:03 UTC

Frontend portal correction verified in actual Light1280/390 and Night320 views: full title/close/footer remain visible; no ancestor clipping. List is a selection followed by Apply: manual35 correctly restores saveddefault39, qty2total78. Confirming secondpart0002 at40.50 on390 yields118.50; cancellation leaves the part search unchanged and creates no line. Matrixrevision3 changes middlemarkup50→60; existingpart0001 quantity2→3 still uses39, part0002 remains40.50, total157.50. Newpart0003 preview uses44.80 and resultingtotal202.30; cancelled without attachment. This demonstrates retained versus newly resolved prices in the real UI, not only mocked components. Synthetic local default still active; teardown pending. Original local Night appearance restored and saved.

Owner checkpoint:208 frontend tests and application TypeScript pass; differential lint28 files has no new errors. Backend264 focused writer/financial/invoice/quote/notes tests and6 realPostgreSQL checks pass; dependency-free symtable undefined-global scan31 changed Python files reports0. Independent reviewer reproduced correction of all6 findings with24 focused tests and disposable HTTP replay/retained-line probes. These are intermediate checkpoints: small fleet presentation/empty-create adapters remain, and final source/independent/CI gates are still pending.

Fresh runtime: same frontendPID52183/owned API mount and image, direct/proxied readiness healthy, preserved preview database174. Feature-specific matrix and priced-part rendering confirm local source alignment. Source edits during the subsequent policy setup reloaded Vite before mutation; no cost-floor/minimum policy was saved in that attempt.

## Policy acceptance and bundle gate failure — 22:04–22:15 UTC

Local part0003 actualcost28 was configured with costbasisfloor50 andminimum85. New attachment resolves85, total242.50, and manager details show basis50/minimum85. Manual84 with a valid reason is rejected with the draft retained and saved85 unchanged. Part0004 actualcost29/catalog59 configuredfixed/minimum50 resolves59 with sourceFixed; cancelledpreview does not attach it. BothNight andLight320policy panels show readable44pxcontrols, saved values, close/cancel and no horizontal overflow. Synthetic policies must be reset during teardown.

Created local synthetic service `DB132 QA Pricing bundle` / ID38a9a893-e3a7-4df4-9701-c52c78e00476,15min,basepriceNULL,part0004qty1. Actual operationsearch Apply revealed a missing adapter: legacyrepair-ops/apply returned409 without usable confirmation. Frontend now routes service candidates through canonicalflat-service and exposes correct337.75preview (242.50existing +36.25labor+59fixedpart), but actualconfirmedwrite still rejects with pricing_preview_changed / Labor changed while applying this service. No bundlelabor/part orstock was committed. Backend investigating; frontend handling recognized409withoutembeddedpreview via fresh explicit review and persistent errors. This is an unresolved gate, not a passed bundle journey.

Independent review additionally found ad-hoc owner-requestedfleet projection, retainedlegacyzeroreservation andcoreobligationquantity gaps; originalprobes and5newboundarytests independently pass aftercorrection. Counterreceptionist retainedmanualprice validation and finalcompleteUIremain undercorrection. No P1 PR, CI orrelease yet.

## Stable application candidate — 22:19 UTC

Bundle failure reproduced independently with production `autoflush=False`; default test factories had masked a stale reread of computed totals. Explicit flush now preserves totals before reread. ActualUI retry confirms337.75 and saves exactly one15min operation with one59fixed-price bundled part, alongside unchanged242.50standaloneparts. No financial finalization. Owner31 pricing tests and12actualPG cases now useproductionautoflushFalse; completeaffectedrerun pending. Frontendfinal223tests,TypeScript and30-filedifferentiallintpass; [commands](DB132_FRONTEND_HANDOFF.txt). Independentfinalgate andremainingUIcontinue beforemerge.
