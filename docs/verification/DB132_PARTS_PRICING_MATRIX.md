# DB132 / P1 parts pricing matrix

Accountable: Backend & Integrations. State: **Production acceptance — pricing deployed; mobile preview feedback correction pending**. Selected second in the [parity tracker](../ETS_PARITY_TRACKER.md), after R1 production closure.

## Current result

The final full-suite CI return was corrected and independently re-reviewed. Local QA/Security GO is restored on the six-file manifest recorded in the independent receipt. All15 findings are closed. The earlier baseline evidence remains: Independent runs passed269 affected backend tests,269 focused frontend tests and12 PostgreSQL boundary/concurrency tests. TypeScript and changed-source lint passed.

Actual local Light/Night desktop and browser-emulated mobile checks cover matrix configuration, saved-price retention, part policies, manual/List/Stock edits, bundle attachment, create-once service recovery and readable fleet quantity controls. Six synthetic orders were soft-deleted; stock, policies, default and service availability returned to baseline. One zero-stock ad-hoc placeholder remains as recoverable local evidence. Restricted-role and counter-sale journeys have automated coverage; they are not claimed as authenticated UI passes.

PR542 has passed all six CI contexts and is merged/deployed with migration174. **Still required:** protected CI, merge and deployment of the frontend feedback correction, then final authenticated production desktop/mobile acceptance. Production pricing remains inactive unless a shop owner explicitly configures it.

## Scope and acceptance
[Architecture contract](../contracts/db132-parts-pricing-matrix.md) defines acceptance, writer coverage, privacy, tenant/concurrency boundaries and production verification limits. Reuse existing inventory settings and price controls; preserve compact desktop and complete mobile journeys. No existing prices, inventory valuation, financial records or shop defaults change merely from deployment.

## Source and preparation
Branch `codex/ets-parts-pricing-matrix` begins at R1 merge7b3dc4b3. Preparation reviewed21546789; full application tree is identical. Backend/frontend integration handoffs and later C1/M1/B1/A1 drafts are preserved in `/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/`; those are preparation, not completion receipts. Canonical tracker retains all29 discoveries and selected order.

## Remaining gates
The full-backend regression correction now has independent QA/Security GO. Fresh exact-final CI, release and production acceptance remain. No invented real-shop pricing activation. P1 remains local and unmerged.

## DB137 prerequisite closure and implementation handoff — 2026-10-15
Compact controls DB137 are Done after PR539 exact deployment and Light/Night desktop/mobile production acceptance. P1 now continues on `codex/ets-parts-pricing-matrix-implementation` from `fc92c7b9944a0d07db80399b9f6e1eda13840b87`; the older preparation branch is preserved. Architecture owns canonical incorporation of four accepted wire/deletion clarifications before frontend/backend work begins. Backend owns all backend integration writers and migration together; Frontend owns the shared configuration and workflow UI. Independent gates remain separate.

Local runtime realigned after branch switch: frontend PID52183 serves this checkout/frontend on5174 with explicit API origin8001 and matching served branch/SHA stamps. Docker `dieselbridge_api_ets-workflow-parity`, image `bde2e27ba1f9353127cca22d4643b6fa0dd47336223c739c3bc5e83c9f480ea4`, binds the same checkout/backend on8001. Database identity remains `postgres/truckpitstop_ets_workflow_parity_20261012`, migration173. Direct and proxied readiness database/Redis healthy. Backend/config/flags/data untouched. Preview is aligned but currently browser-unverified for P1: session expired; user asked to restore sign-in. No new feature rendering or policy activation claimed.

Runtime sign-in restored by user; actual Performance Owner / Diesel Bridge Performance Lab dashboard renders `codex/ets-parts-pricing-matrix-implementation@fc92c7b`. Local5174 is aligned and browser-verified for the baseline; P1 feature acceptance awaits completed implementation/migration. Architecture accepted the canonical projection/deletion contract; backend and frontend began assigned implementation. Additional exact configuration/preview envelopes are being finalized before those adapter edits. No P1 completion or release claim.

## Acceptance ledger
Entries are updated from actual evidence rather than inferring runtime success from component tests. Local mobile means responsive/touch browser emulation, not physical devices. Partial cells are not full journey approval.

| Journey | Local Light/Night desktop,390,320,740 landscape | Automated boundary evidence | Production permitted acceptance |
| --- | --- | --- | --- |
| Settings entry, empty state, Back/cancel | Night/Light entry, close and Escape focus return passed | Final frontend223 independently pass; scope/role reset covered | Pending deployed read-only entry |
| Matrix draft preview/save/reload | Night desktop samples20→40/25→37.50/100→130; revision/save/reload/history. Final Light320/740 and Night320/740/1280 readable, no document overflow | Bands/config/tenant/CAS; production-mode PostgreSQL12 pass | Pending draft-only preview |
| Default, revision, clear, archive/restore | Explicit local default; revision2→3; gap rejection retains draft; clear default and archive verified | ABA/default/archive races and append-only history pass | No guessed activation |
| Fixed price, pricing-cost floor, minimum sale price | Floor50/min85 on actualcost28 resolves85; manual84 rejected; fixed59 overrides matrix, both-theme320 policy forms pass; baseline reset | Precedence/null/bounds/atomic validation pass | Pending policy read/cancel |
| RO direct + bundle add; retained price after revision | Direct390 and bundle1280; reload337.75; mobile bundledqty1→2 keeps59/total396.75. Template reapply resets qty to1 with retained59/one operation. New-order cancel/retry creates once | All writers, reservation/core and historical financial snapshots pass | Pending historical reads/cancel only |
| Manual, List/Stock, discount rejection and409 review | Manual requires reason; minimum rejection retains draft; List39 and Stock26 verified. Actual409 uncovered and fixed production autoflushFalse bug | Explicit409 re-resolution/reacceptance, role/CAS/minimum/rollback pass | Pending editor/cancel only |
| Internal/external fleet and restricted roles | Owner fleet internal directpart26/qty2total52 passes. Per-line money controls absent. Narrow-name mobile defect returned for correction. External/restricted accounts unavailable; no role alteration | Tenant/assignment/projection/current-role retry negatives, internal actualcost semantics pass | Read-only/cancel where available; no claim of restricted-role UI |
| Counter-sale retained draft and additions | Counter-sale entry not exposed for local fixture; flag unchanged, no browser claim | Retained snapshots, receptionist manual-price carry-forward, tax/return and scope tests pass | Existing gate respected; no real sale |
| Legacy/locked history and account/tenant switch | Existing order history reads unchanged; no real financial finalization | Serializer/replay/cache/lock guards covered; CI void-revision regression correction underway | Pending unchanged-value read |


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

## Final local journeys and CI handoff — 22:22–22:32 UTC

Application candidate23c3f9a0 synced unrelated main1063e26e asf04c318d; board conflict preserved both owners. PR542 opened draft; frontendchecks passed. Initial full frontend suite1687passed/3failed in void-revision summary mocks/call counts; correction assigned to Frontend without weakening lock coverage. Independent269backend/223frontend/12actualPostgreSQL passed and findings1–12 closed, final runtime closure pending.

Fresh runtime: frontendPID52183/same checkout5174, owned API source mount8001/imagebde2e27b, preserved databasepostgres/truckpitstop_ets_workflow_parity_20261012/schema174, both readiness paths healthy. Rendered feature proves current edits despite startup stampfc92c7b.

New-order mobile390 createdPERF-295757AF-000007/1769a531-11e7-4467-8699-ff31fbf7029c once; cancelling price review retained that order, Retry remaining confirmed95.25 on same identity with one15minute operation/onepart. Both000006 and000007 soft-deleted via actual UI. Ad-hoc12.50withblankcost saved Unknown, Stockdisabled; knowncostStock26/List39 preserved originalrevision2 default. Notes touchclick expanded successfully after backend adjacent regression fix.

Fleet owner route is accessible; created synthetic000008 with complaintDB132QA localfleetpricingverification, directpart0001cost26, quantity2total52. Per-line pricing management is absent, existing owner house-account total remains visible. Soft-deleted through fleetdialog. At390pxpartname squeezed to~35px besidecontrols; frontend correction now wrapsname/SKUabovecontrols while preservingdesktop. Final screenshot and independent review pending.

Cleanup: synthetic matrix archived and defaultcleared; part0003/0004 floors/minimumsNULL/fixedfalse, catalog58/59retained. Syntheticservice unchecked and inactive verified after autosave completes. Initial read-only comparison to pre174backup confirms stocks102,102,104,105,104,106 and costs26–31/catalog56–61 unchanged; final fleet teardown recheck pending. A zero-stock ad-hoc placeholder remains local for recoverable audit history; no supported per-item archive action exists. OriginalNight preference restored. No quote/invoice/payment/completion or production pricing mutation.

## Responsive correction accepted locally — 22:35 UTC

Fleet PartRow now wraps name/SKU onto a full-width first row at≤680px, with44pxquantity/removecontrols below;1280desktop remains onecompactrow. Actual synthetic000009 directadd/quantity1→2 yields52,390and320 screenshots showcomplete readablepartname andnooverflow, desktopdensityretained.000009softdeleted andfleetattention empty. Evidence`db132/night-fleet-final-{390,320}.png`,`db132/fleet-final-desktop.png`. Existingfleettheme is independent ofshopappearance; this owner-in-fleet check does not establish restricted-role access.

CI3failures reproduced as stale test assumptions after actor/session-scoped querykeys and gcTime0. Test locates active scoped summary and requires a fresh server read after void while preserving all lock/capability assertions. Final226focused tests,TypeScript,changedTSXlintpass; independent review and finalCIpending. Production sessionexpired; user asked tosign in whileCIcontinues.

## Recovery/footer correction — final local acceptance, 22:40 UTC

Independent finding13 reproduced from the original390 screenshot and source: recovery/inlineerrors were directgridchildren, so noticeheight preceded a fullheightpanel. Movedboth into existing PriceBuilder workscroller; whenclosed, the same notice staysinsideledger. Desktop2columns unchanged. ActualNight1280/390/320 andLight1280/320 screenshots pass. Measured390viewport844: primaryfooter top794/bottom838;320viewport740: top690/bottom734. Documentwidth equalsviewport, recovery closest existing `.db-workspace-scroll` true.

Nightfixture000010/6e888f0d-726d-40d8-9b4b-4fdcdc3f0ff2: cancelreview, close→ledgernotice, Retry reopenssameorder, cancel, Keepcurrent clearsnotice andretainsidentity. Lightfixture000011/652cf9b9-6892-4309-95f3-e851e1f51fc3: cancelreview, visiblefooter, Retry→Confirm savesone15minuteoperation+59part/95.25sameorder. Bothsoftdeleted. Fixedpolicy0004clearedagain, serviceinactive/autosavechecked, originalNightrestorationnext; freshcleanup receipt supersedes22:34checkpoint. Noquote/invoice/payment/completion.

Owner269focusedfrontend (previous226plusrecovery/ledger),TypeScript,differentiallintpass. Independent269rerun andfinalcleanup gate pending. Backendsource unchanged fromindependentlyreviewed candidate. ProtectedCI mustrerun onthisfinal correction; olderpasses/cancellations are notfinalapproval.

## Final local teardown — 22:41 UTC

[Read-only cleanup receipt](db132/local-cleanup.json) verifies all11 invariants: sixQAorders000006–000011softdeleted,13reserved/13released/netzero,0activereservations,0quotes/invoices/payment/completionartifacts. Allsixinventoryquantities/costs/catalog/corevalues equalpre174backup. Matrixarchived/defaultNULL;policiesreset;serviceinactive. Onezero-stock unknown-cost ad-hocplaceholderretainedlocallyforrecoverableevidence. OriginalNightappearance saveconfirmed. Local QA isfinished; nofurtherfixturemutationplanned.

Mainadvancedwith unrelatedPR54113d5c867; mergedas d94133a0 preservingbothboardentries, P1applicationmatchesfacf1482. Productionbaseline at173hasnoneofthenewpricingtables; selecteddeletedQAorderTPS-828ACD84-000056remains0.00/in_progress/deleted. Production hasnoP1activation. FinalindependentGO/protectedCI/release stillseparate.

## Final CI gate returned — 2026-10-15 23:39 UTC

Run38819011151 on ad99dff0 passed migration, frontend checks/build,1693 frontend tests,530 critical backend tests/11skipped and Playwright smoke. The full backend job failed17 tests, with3300passed/181skipped. Overall workflow success does not override the failed required job. No merge or deployment occurred.

The real HTTP regression is `test_db003_additive_tenant_boundary.py::test_cross_tenant_mechanic_additive_http_paths_are_generic_404_and_noop`: the new initial price-build load raises uncaught PriceBuildNotFoundError instead of the generic404 response. Fifteen fractional-part direct-call tests and one legacy fleet service-checklist direct-call test also fail with a Depends value where the actor was expected after the signature change. Backend owns diagnosis/correction without weakening tenant/no-op/stock assertions; independent QA/Security has been reopened for the delta. Log retained locally at /tmp/db132-final-full-backend-ci.log.

Production sign-in restored. Pre-release read-only fingerprints captured at23:16:59UTC for existing inventory1612, saved part lines2934 and invoices2424, fixed cutoff23:15UTC; no production records changed. Existing invoiced order000055 was visually read without editing for post-release price comparison. P1 production acceptance still pending.


## CI correction owner handoff — 2026-10-15 23:47 UTC

Backend corrected catalog and ad-hoc pre-replay error mapping to preserve generic404 for foreign, missing and soft-deleted orders. Negative HTTP coverage verifies no inventory, reservation, pricing audit, idempotency or notification side effects. Existing direct-call fixtures now supply the named dependency arguments; assertions remain intact. The corrected tests exposed and fixed an unmanaged stock-only compatibility issue: original insufficient_stock400 and explicit shortage acknowledgment are retained, while managed/manual prices and supplied stale fingerprints still require exact pricing review.

Owner affected suites:101passed/39warnings; broader pricing/financial/fleet regression:338passed/39warnings (collected before the final additional HTTP replay test). Six-file source manifest is retained locally at /tmp/db132-backend-evidence/ci-correction-manifest.json. Fresh independent review and final protected CI remain required.

Runtime rechecked after code reload: frontendPID52183 serves the implementation checkout at5174; Docker source bind matches at8001; preserved postgres/truckpitstop_ets_workflow_parity_20261012 is at174. Direct and proxied readiness pass. Signed-in local Parts pricing renders No default and no active matrices; previous synthetic cleanup remains preserved. Local preview is aligned and browser-verified.


## Fresh independent correction gate — 2026-10-15

Independent reviewer passed339 affected backend tests,12 real PostgreSQL boundary/concurrency tests and3 disposable HTTP probes for manual/Stock intent and invalid-fingerprint rejection despite shortage consent. All six file hashes match the owner manifest before and after review. Findings14/15 closed; local QA/Security GO restored. Fresh six-context CI on the next committed revision is mandatory. Frontend and existing browser acceptance are unchanged by this backend-only correction.


## Protected merge — 2026-10-16 00:13:58 UTC

PR542 merged as53eb98031d9247629e8300f14d0447c6d8b0d046. Its tree exactly matches final060bba1bd9842404e56c6225b3e0196a21e5301f. Run38825768055 passed all six required contexts: migration graph, frontend lint/build/207critical tests,1693 full frontend tests,530 critical backend/11skipped,3319 full backend/181skipped and5 browser smoke cases. GitHub merge state was CLEAN; no bypass used. Local CI log /tmp/db132-corrected-ci.log. Production release acceptance is still pending.


## Production UI return — 2026-10-16

Web409f8937-8151-4b30-8f3d-bbbceec46252 and Workerc9a9bf0c-467d-445e-887b-3e9d3eb97648 are SUCCESS at53eb9803; public build matches and schema174 is present. Financial fingerprints for1612inventory,2934saved part usages and2424invoices exactly match the fixed baseline. All pricing tables are empty, no default or inventory policy configured; synthetic zero order remains deleted and unchanged. Production matrix sample previews20→40,25→37.50,100→130 pass without saving.

Actual390×844 Light UI rejects band gap26 but places the alert above the visible scroller (top−145,bottom−106). Screenshot retained locally /tmp/db132-prod-light-390-validation.png. Returning this existing-contract UI feedback defect to Frontend before completion. Draft is retained and no invalid save occurred, but rejection feedback must be visible. Initial route loading during the version switch resolved on fresh navigation; source/build investigation found no persistent defect or module cycles. No fix claimed for that transient observation.

Branch switch preflight: same frontendPID52183/source5174 and backendbind8001; preserved postgres/truckpitstop_ets_workflow_parity_20261012/schema174, proxied readiness healthy. Branch `codex/parts-pricing-visible-validation` at53eb9803 contains only release documentation edits before the UI owner starts.

Successful sample feedback has the same visibility issue at320×740: after Preview, Proposed$130.00 sits at top728/bottom755, partially below the viewport. Correction acceptance includes fully visible successful results and invalid feedback. Part-policy read/draft Cancel and Escape pass at1280desktop,390/320portrait and740landscape with footer inside viewport. All policy values remain unchanged.

## Feedback correction — local acceptance

Frontend & UX completed the existing-contract correction on `codex/parts-pricing-visible-validation`. Preview feedback is next to the action; responses receive focus without page scrolling and reveal their full bounds inside the existing panel scroller. Matrix/policy save errors share the same behavior. Repeated identical errors reveal again without clearing the draft. Saved-price labels inherit their repair-order cell's text color so they remain readable on its existing white surface in Night Shop.

Owner validation: 42 parts-pricing tests across four files, application TypeScript, changed-file ESLint and diff check passed. Actual local signed-in checks passed: Night 320×740 three-band success (feedback top683/bottom732), repeated invalid gap with draft retained, landscape740×400 success (top343/bottom392), Light1280×900 result and390×844 rejection/recovery, named Close and Escape returning focus to Catalogue maintenance. Night desktop retained-price label is rgb(75,85,99), matching its cell. Screenshots retained in `/tmp/db132-local-{night-320-feedback,night-landscape-feedback,light-desktop-feedback,light-390-error,night-desktop-saved-price}.png`. Local Night appearance restored; all matrix drafts were discarded and no pricing configuration or order values changed. Protected CI and production acceptance of this correction remain required.

The production Night policy action also exposed white text on cyan #22d3ee (1.81:1). PR544 now uses the existing action fill/foreground token pair within parts-pricing only. Owner pricing/theme suites: 56 passed; TypeScript and CSS parse passed. The actual local action in both Light and Night computes to #07101d on #0891b2 (5.18:1); desktop Night and390px Light screenshots confirm readable controls. Invalid cost-floor text produces a focused visible error and retains the draft; Cancel leaves saved values unchanged. Production Night policy draft/cancel/reopen and landscape footer checks passed with no saves; historical order labor75.00, part35.73 and total110.73, invoice112.98 remain unchanged across Light/Night desktop and mobile reads. Final corrected production contrast/feedback acceptance remains open.
