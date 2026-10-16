# DB133 / C1 customer pricing defaults

Accountable: Backend & Integrations. Status: **Local workflow and integration checks complete; final protected CI before release**. Selected after completed P1 in the [parity tracker](../ETS_PARITY_TRACKER.md). Branch: `codex/customer-pricing-defaults`, from P1 release-record195c7f3a (application70530bda).

## Acceptance before implementation

- Owner/admin can set, clear and reload a customer agreed labor rate and parts pricing default within Business settings; blank inherits shop settings. Preserve the existing tax-exemption workflow and permissions.
- New external repair orders use the customer agreed labor rate, otherwise the shop billing rate, including external fleet/PM creation. This fallback was explicitly approved by the user. Internal work retains its existing internal cost rules.
- Pin terms and their source on new orders. Later customer/shop/matrix edits do not silently rewrite existing orders or saved lines. Preserve manual labor/parts overrides and P1 price review semantics across direct, service, recommendation and fleet writers.
- Customer configuration uses dedicated tenant-scoped owner/admin contracts, optimistic concurrency and audit; generic self-service customer updates cannot mutate pricing. Foreign or deleted resources, archived matrices, stale writes and restricted roles are covered by negative tests.
- Compact accessible settings and readable pricing origin preserve customer search, cancel/back navigation, desktop density, one mobile scroll area and complete Light/Night desktop/portrait/landscape journeys.
- Additive migration, focused automated checks, independent QA/Security, protected CI, merge/deploy and permitted production acceptance are required before Done. Production QA must not activate invented account agreements or reprice real work.

## Runtime alignment — 2026-10-15 local / 2026-10-16 UTC

Mandatory runtime skill reapplied on branch switch. Frontend5174 was already the owned checkout; only its verified PID52183 was gracefully stopped to refresh its branch stamp. New PID39898 serves this checkout/frontend with explicit API origin127.0.0.1:8001 and stamp `codex/customer-pricing-defaults@195c7f3`.

Backend container `dieselbridge_api_ets-workflow-parity` remains9d8774b7, imagebde2e27b, bound to this checkout/backend on8001; it was not restarted. Database remains `postgres/truckpitstop_ets_workflow_parity_20261012`, schema174. Direct and proxied readiness pass. Actual signed-in Performance Owner customer/settings UI shows the new branch stamp. http://127.0.0.1:5174 is aligned and browser-verified for the existing baseline. No C1 functionality exists yet; no database, flags, provider configuration or production values changed.

## Handoff

Architecture owns the contract before parallel frontend/backend work. [Readiness notes](DB133_CUSTOMER_PRICING_READINESS.md) preserve the inspected writer inventory and approved fallback. Root owns this receipt, board and release coordination. Independent QA/Security remains separate from implementation.

Before any C1 migration: preserved local schema174 custom-format backup at `/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/db133-local-schema174-before-c1-20261016T0241.dump`, mode0600,4012909bytes; pg_restore lists1755 archive entries. This is a local backup only and is not committed/uploaded. No migration has been applied; disposable upgrade/downgrade and legacy preservation proof must precede any preview upgrade.


## Accepted contract and ownership handoff

Product accepted [Architecture contract](../contracts/db133-customer-pricing-defaults.md) after narrowing it to account defaults, frozen new-order terms, existing manual-rate controls and current P1 counter behavior. No compulsory labor-edit reason or new labor CAS protocol; no payment/import/financial-merge rewrite. The conservative C1 merge guard requires retaining identities with C1 pricing history/references, rather than deleting their provenance. The pre-existing generic financial-merge concern remains separately recorded in readiness notes and is not claimed fixed.

Backend owns all backend models/migration/services/endpoints/serializers/tests as one contract integration; Frontend owns customer settings/types/hooks and narrow order/fleet/counter/source adapters/tests. They must not edit each other's files, reset unrelated changes, commit/push or migrate the preserved preview without coordination. Independent QA/Security begins after the integrated source and focused evidence are ready; root owns browser QA and release.

## Local additive migration — 2026-10-16 02:52 UTC

Applied revision175 only to the preserved local preview after the existing custom-format backup and disposable174→175→174→175 compatibility proof. The migration's SHA256 was `e7a37d49cba996cddea83999d9f90d435a1952047ff0d6da27dc4d14edfa169d`. Direct PostgreSQL tests reject six malformed snapshot shapes and NaN/zero/negative account rates, while accepting the maximum valid rate. Mapped ORM activation was held until this upgrade completed.

Before/after hashes of every pre-existing column and row matched for customers631, repair orders2815, counter sales0, labor3837, inventory1334, part usages2894 and invoices2056. No agreement, price or money backfill occurred. Direct8001 and frontend-proxied5174 readiness both pass; frontend39898 and backend9d8774b7 still serve this checkout. The existing signed-in customer workspace is browser verified; new C1 workflow acceptance remains pending coherent implementation.

Evidence: `db133/local-schema-before.json`, `db133/local-schema-after.json`, and backend disposable receipts. Independent schema review is underway separately from implementation. No production migration or feature release has occurred.

## Runtime acceptance plan

Use the local Performance Lab only for synthetic agreement writes and new test orders; restore its active customer/shop settings and soft-delete synthetic orders afterward. Retain required immutable audit evidence. Production acceptance uses read-only defaults/history, unsaved editor drafts with cancellation, source displays and historical-order retention; it does not configure fictional customer agreements.

| Journey | Required actual UI result |
| --- | --- |
| Customer settings | One Business settings disclosure; existing Tax permission unchanged. Set/reload rate and matrix, blank inheritance, validation and repeated error visibility, Save/Cancel/Escape and history. |
| New and existing work | New external order captures customer terms, ordinary manual labor and service use those terms; a later settings change affects only a future order. New additions and manual edits on the earlier order keep saved terms after reload. Legacy saved prices stay unchanged. |
| Draft recovery | Changed-account conflict retains customer/truck/work, exposes the current terms for deliberate retry and creates at most one order. Cancel returns to the preserved customer search. |
| Fleet and recommendation | Permitted external fleet work uses billing defaults, restricted projection stays free of private rate/matrix data, recommendation conversion keeps linkage and saved price on retry. |
| Boundary controls | Matrix archive assignment guard and customer merge provenance guard return clear recoverable messages. Existing tax, order completion/time tracking and P1 review behavior remain intact. |
| Layout | Light and Night Shop at1280×900,390×844,320×740 and740×400; readable source/actions/errors, no horizontal document overflow, compact desktop, one mobile scroll area and visible focus. Browser emulation is not physical-device verification. |

Automated API/HTTP/PostgreSQL coverage handles role changes, simultaneous writes, request replay, every writer and unavailable feature-flag cells that cannot be honestly exercised in the signed-in local/prod UI. Those cells are recorded separately, never counted as browser passes.

## Early runtime and independent findings

Night Shop read-only settings render at desktop,320×740 and740×400. Invalid zero and repeated identical validation remain visible and focused in the single customer scroller; no horizontal document overflow. History correctly shows no pricing changes. No agreement was saved. Screenshots are retained locally at `/tmp/db133-night-320-draft-validation.png` and `/tmp/db133-night-landscape-draft-validation.png`; these are early implementation evidence, not final acceptance.

Cancel/Escape initially lost focus to the document body; Frontend supplied a correction, pending browser recheck. A second actual path—Business settings → Edit pricing → Manage matrices → Escape—collapses Business settings while leaving the portal dialog open. Returned to Frontend with exact reproduction; no final UI approval.

Independent schema review reproduced two counter snapshot guard holes (14/16 probes pass). Backend must reject policy clearing and replacement during finalization. Root will align only the corrected function in the preserved local preview after the same disposable probes pass, preserving all data. Production175 has not been deployed.

## Schema correction independently closed — 2026-10-16 03:01 UTC

All16 independent PostgreSQL probes now pass on corrected migration175 SHA256 `2dcf08c6b502917e303ac89f21d0e438338a5abef9c014dc4e962f0f302b5f66`. The guard requires both old/new counter status to be draft, an actual buyer change, and a non-NULL replacement policy. Root extracted only that exact migration function and applied `CREATE OR REPLACE FUNCTION` transactionally to the preserved preview. All seven full legacy-data hashes remained unchanged. This closes the schema-only findings; integrated C1 QA/Security and final UI/release remain open.

P1 release-record PR545 merged normally at2026-10-16 03:04:31UTC as `ef936b8b05971a3217a4d4943a31fd26f62063cd` after all six contexts in run38841002264 passed on exact head195c7f3a. It contains documentation/evidence only. C1 implementation will incorporate this main ancestry before its final protected CI run; no checkout switch occurs during parallel edits.

Early UI correction recheck: local Light Shop390×844 now closes the inner Parts pricing dialog with Escape, retains the zero-rate unsaved draft and expanded Business settings, and restores focus to Manage. Cancel restores focus to Edit pricing. Manage sits beside the matrix selector. Light validation is focused and visible at632–680px with document width390; Save pricing computes white on#115e59. These checks do not replace final saved-workflow acceptance. Local appearance is temporarily Day/Cyan/Geist/default for testing; original Night must be restored at cleanup.

## Retry contract and ongoing independent review

Architecture clarified the separately created truck path: retain the actual customer/truck IDs, submit the originally reviewed customer-only pricing token, and parse any conflict against those exact submitted identities. A valid NULL-vehicle token remains customer-bound; changed terms require deliberate review. No duplicate prerequisite creation or silent replacement of reviewed terms.

The accepted signed-call amendment reuses existing P1 receipt storage solely for known-success reservation recovery. Current authorization and original customer/vehicle bindings precede reuse; a narrow reservation-only transaction persists the validated provider UUID before final order creation. It does not store raw tokens, alter the provider protocol, send notifications, or promise exactly-once external calls across a crash/network failure before the receipt is durable.

Independent HTTP configuration negatives passed14 cases. Saved-policy validation findings remain with Backend: partial catalog shape, malformed rate and out-of-range rate must all fail with `account_pricing_unverified`, without adopting current defaults. Final source approval remains pending.

## Integrated gate corrections and saved workflow — in progress

Independent saved-policy and signed-call probes now pass 19/19, and the frontend manifest passes 241/241. Review then reproduced a compatibility defect: valid shop rate zero created an order but returned a failed snapshot response. Backend owns the narrow correction; configured customer agreements remain positive, while inherited shop zero remains valid. This is not a release approval.

Root source review also reproduced a recommendation Add again mismatch: the UI retained the completed manual draft while resetting its submission intent. Frontend clears completed hours after success so a new draft initializes the current default, preserving Cancel/Escape unsaved manual drafts. The focused 31 tests, application TypeScript and two-file strict lint pass.

Actual local UI has saved and reloaded a synthetic Performance Carrier 001 agreement of137.50 with an explicit DB133 QA reason. History shows the actor, timestamp and old/new rate. Baseline was no account rate or matrix (shop145/catalog); restore active inheritance during cleanup. Created only local QA order `PERF-295757AF-000012` / `107530d1-52cc-40c8-ac14-64383481d6de`, description DB133 local QA A — retained customer agreement test. New-order preview showed account137.50. Saved-line, changed-agreement, matrix, mobile and cleanup checks remain in progress. No production agreement or order mutation.

## Saved local workflow evidence — 2026-10-16 03:21–03:31 UTC

Light desktop: agreement137.50 saves, reloads, and appears in actor/timestamp/change history. OrderA (`107530d1-52cc-40c8-ac14-64383481d6de`) captures that rate; existing QA PM Add-on service saves0.25h×137.50=34.38. Typed1.5h persists206.25. On390mobile the account changed to151.25, yet returning toA retains137.50. Manual125 onA saves187.50 with Manual source. A newly converted Monitor uneven steer-tire wear recommendation still uses A's pinned137.50; total325.00 with exact source link.

Created local-only matrix `DB133 LOCAL QA customer matrix` (20%markup, no shop default); assigned it to the synthetic account. New orderB `PERF-295757AF-000013` / `582d9f08-2963-4eb2-a66f-f04a59b5fe6e` captures151.25 and the account matrix. Service0.25h saves37.81. Adding Performance replacement part0001 reviews31.20 with Account matrix, confirms the same31.20, total69.01. Attempting to archive the assigned matrix is rejected, leaves it intact, and focuses the clear explanation.

Root independently reproduced the blank-hours manual recommendation draft concern: enter125 before hours, Cancel then reopen displayed137.50. Root now shares frontend implementation ownership for the narrow `!rateEdited` reset guard and two Cancel/Escape regression cases.33 focused tests, application TypeScript and strict two-file lint pass; actual390 UI now preserves125 through both dismissal routes. Independent gate remains separate.

Read-only geometry reports document390/viewport390. Captures: `/tmp/db133-light-desktop-order-a.png`, `db133-light-mobile-agreement-history.png`, `db133-light-mobile-manual-rate.png`. These are local QA, not production evidence. Source HMR during owner corrections reset unsaved forms as expected; no ambiguous saves were resubmitted. Remaining: Night/responsive checks, active-config/stock cleanup, final independent candidate, CI and production.

## Final local runtime gate returned — Night contrast

At320×740 with actual `data-appearance-mode=dark`, Customer Pricing Labor and Reason fields computed foreground/background both rgb(246,248,251), making typed values unreadable. The selected matrix text was also invisible; Tax labels inside Business settings were too dark. Screenshot `/tmp/db133-night-320-settings.png` is failure evidence, not acceptance. Frontend owns a scoped token correction and explicit Light/Night color/value recheck. Earlier checks proved error focus/visibility only and must not be treated as full Night form acceptance. Independent review reproduced the visual finding.

Other completed local paths: after account inheritance was restored (both fields NULL), the test matrix archived successfully. OrderB retained its archived revision: adding another part reviewed32.40, kept the earlier31.20 line unchanged, and saved total101.41. Two-tab intake stale-policy check returned focused changed-terms145/catalog, retained actual customer/truck/work, and enabled retry only after Use current defaults. Root cancelled without creating another order. Frontend additionally corrected the stale generic pricing error left after explicit acceptance (52focusedtests/typecheck/changedlintpass), pending final browser recheck.

Current cleanup state: synthetic account active defaults restored, shop default unchanged, test matrix archived. Only local ordersA/B and their parts usage require cleanup. Source application commits a5cd369b and ancestry-only0deba3ed; final intake and contrast corrections will be committed before protectedCI.


## Final local acceptance and cleanup — 2026-10-16 03:52 UTC

The scoped Business settings theme correction passed actual desktop1280×900, Night320×740/740×400 and Light390×844 checks. Labor rate137.50, Reason, selected matrix option and Tax help are readable. Computed field colors: Night rgb(246,248,251) on rgb(17,31,51),15.57:1; Light rgb(20,36,58) on white,15.63:1. Night320 document width equals viewport320; landscape Save remains reachable within the customer scroller. Independent reviewer inspected all five corrected captures. This closes the earlier Night failure rather than counting its screenshots as passes.

Final two-tab mobile retry: draft reviewed shop145; the synthetic account changed to137.50. Create returned409 and retained the exact customer, truck and work description. Use current defaults cleared both the focused pricing notice and matching generic error, enabled Create, and did not auto-submit. Cancel returned to the original customer workspace. No third order was created. Active customer defaults were restored to NULL/NULL, version6. The selected local Night appearance was restored and temporary device/touch overrides cleared.

[Read-only cleanup receipt](db133/local-cleanup.json) confirms both A/B soft-deleted, zero remaining part usages, archived test matrix and no active customer agreement. The immutable stock events for B independently connect both part quantities102→101 on reservation and101→102 on release; final stock is102 each. This corroborates cleanup without pretending that a separate pre-test per-row database baseline was saved. Immutable pricing/audit/history evidence remains intentionally retained. No invoices, estimates, payments or completed real work were created.

Final source checks: Backend335 affected regressions,89 overlapping final-delta checks and11 real-PostgreSQL tests; final30-file manifest cafa79e290dafe731b92da3b26c8c2b775be4f5df6ac99344c89015e84349a0e. Independent16 schema probes,20 supplementary HTTP probes,1 sublet case,93 writer/fleet,11 PostgreSQL and33 recommendation cases pass. Frontend241 initial integrated tests plus later33 recommendation,32 counter,52 intake and47 settings tests pass (overlapping counts). Independent final UI delta83/83 passes. TypeScript, changed-source lint and CSS parse pass. Full protected CI is still required on the committed final candidate.

Evidence images in [db133](db133/): `night-desktop-settings-fixed.png`, `night-320-settings-fixed.png`, `night-landscape-settings-fixed.png`, `light-desktop-settings-fixed.png`, `light-mobile-settings-fixed.png`, `mobile-intake-accepted-fixed.png`, `light-mobile-agreement-history.png`, `light-mobile-manual-rate.png`, `night-desktop-retained-order.png`, `night-mobile-order-b.png`. The Price Builder intentionally remains a light working sheet in Night mode; the retained-order image shows its dark surrounding queue. Browser viewport emulation is not physical-device testing. Counter optional-flag cells and restricted-role flows are covered by automated/API/PG checks, not claimed as actual signed-in browser passes.

Production remains the P1 application at PR545 documentation merge ef936b8b, deployment6c2e0321-5ca4-4f96-a7dc-d0413aaf602c, public build and readiness verified. C1 has not been merged/deployed or production verified yet.


## Release candidate

Independent local QA/Security GO applies to application candidate929f2d4e55e220f09aedfbb28e4bae41eb12f99b. The subsequent gate-only commit948c9a43df7480a90e96398700d3ce574d0506fc is [PR550](https://github.com/mecaniser/truck-pit-stop/pull/550)'s exact protectedCI candidate, run38847883650. All six contexts must pass before normal merge. No direct-main push or bypass.

Rollback boundary: migration175 is additive and retains historical rates/charges. Once any C1 defaults/snapshots exist, P1-only code cannot safely ignore them: use a forward correction, retain a compatible policy reader, or pause affected new-work creation. Do not destructively downgrade adopted pricing evidence. Post-deployment checks cover schema/build/health, fixed-baseline finance retention, aggregate no-backfill state and actual permitted production UI.

New-local-day runtime receipt,2026-10-16 04:01UTC: intended branch948c9a43 with release-documentation-only edits; frontend39898 serves this checkout/frontend at5174, effective proxy8001. Backend9d8774b7 imagebde2e27b binds this checkout/backend,development postgres/truckpitstop_ets_workflow_parity_20261012/schema175. Direct and correctly proxied /health/ready pass. Reloaded customer Business settings visibly shows C1 Pricing with145/shop/catalog and restored Night mode. Existing branch stamp195c7f3 is corroborated by source process/mount and actual feature; no server restart, migration or data change. Local5174 is aligned and browser-verified.

Main integration: PR548/e3ff99e0 landed during C1 CI. The only conflict was the board's prepended history; both records retained. C1 application source and accepted contract are unchanged, and the incoming Motive changes retain their own review. Five of six checks passed on948c9a43 but the unfinished run is superseded, not a complete pass. Fresh protected checks on the merged revision are required.

## Customer-contact migration integration — 2026-10-16 05:00 UTC

PR549 merged as d5cb662839f82789184be846bc0db876c860594e while C1 CI was queued/running. It adds nullable customer contact JSONB through a distinct175 revision from the same174 parent. Preserve both175 files byte-for-byte; use a no-op merge revision176, following existing137/167 repository precedent. Do not renumber the already-applied local C1 migration or stamp over its evidence. The prior C1 run38850524237 is cancelled and cannot count as a full pass.

The preserved preview remains on175_customer_pricing_defaults with the old Customer model active. Frontend39898/source/proxy5174→8001 and backend bind/image/database identity remain aligned; direct/proxied readiness passes. No restart or new migration has occurred at this checkpoint. New pre-integration backup: `Documents/Codex/ets-priority-preparation-20261015/db133-preview-before-contact-merge-20261016T0504.dump`,0600,4,035,046 bytes,1,775 archive entries,SHA2569fc3ee7b1abb028ef6dfa2eb2c2b37a9e3da55ad6c77bff2eaa9df1ad5caf1c3. It includes the completed C1 QA history absent from the older174 backup.

Required before release: disposable upgrade/retention proof from174 and each175 branch, independent review, normal preview upgrade before new model activation, fresh final-head CI, and a fresh production baseline after PR549 deployment. Existing v2 baseline remains historical evidence; it is not silently rewritten or reused as if taken after549. No C1 production agreement, backfill or financial mutation has been made.

Preview integration completed after independent GO: normal upgrade175pricing→176 applied the missing contact branch before activating the incoming Customer model. Read-only, repeatable-read before/after evidence shows all10 normalized table fingerprints identical: customers631, repair_orders2817, labor3840, parts_usage2894, inventory1334, invoices2056, counter_sales0, counter_sale_lines0, account_pricing_events10, parts_operation_idempotency39. No data cleanup, stamp or downgrade. Independent nine-path disposable migration proof and the reviewed v3 production-capture helper are accepted; final source integration and exact-head gates follow.

Integrated source4cbdc3e8 includes main d5cb6628. The Customer conflict retains both import sets; only incoming nullable contact JSON is added to the accepted C1 model. Signed-in preview reload and Business settings pricing recheck pass after model activation:145/hr Shop, Catalog Shop, Edit pricing/History present. Frontend39898 remains bound to this checkout with proxy8001; backend image/mount/database unchanged, schema176, direct/proxied readiness passes. No browser draft or data mutation.

Fresh production baseline v3 captured after PR549 Web582d69ad SUCCESS and public exactd5cb6628/readiness200. Cutoff2026-10-16T05:12:44.974006+00:00; exact175 contact schema, C1 fields/events absent. Seven fixed cohorts include one counter header and line. Sanitized [v3 summary](db133/production-before-v3-summary.json); full opaque-row manifest retained privately with0600 permissions. Historical v2 summary is superseded for this release, not deleted. Post-deploy comparison must use this exact v3 cutoff and manifest.

Merged-model PostgreSQL recheck:11/11 passed on4cbdc3e8 using disposable schema176. All29 unaffected C1 backend files and all6 UI files retain accepted hashes; Customer differs only by the incoming contact field/imports. No broader retest was required for this integration delta; protected full suites still gate the final pushed revision.

## Release blocker — 2026-10-16 07:31 UTC

Final candidate0d427576 is pushed in PR550; run38854713548 is queued, not passed. Local CI registrations dropped to zero after host/network interruption. Previous main backend full-suite execution was cancelled on its worker and supplies no failure traceback or passing evidence. Both disposable worker replacements repeatedly exceed the normal180-second boot timeout before SSH readiness. Host load averages exceeded500; disk capacity and CLI GitHub authentication are available. A graceful restart of only the installed com.dieselbridge.ci supervisor restored its process and cloned fresh workers, but boot readiness still timed out. No runner isolation, check, billing, host application, database or production configuration was changed. Release & Reliability owns resumption after host responsiveness recovers. User notified because stopping unrelated work or restarting the host is outside routine task recovery.

C1 remains locally verified and unreleased. PR550 is not merged; production still requires migration176, comparison to the fixed v3 baseline and Light/Night desktop/mobile acceptance. Production browser currently shows login; request sign-in near deployment, not repeatedly while CI is blocked. M1 remains queued; only read-only preparation is retained.

## Release resumed — 2026-10-16

User confirms host responsiveness restored. Both db-ci workers are online. Prior38854713548 is failed/interrupted, not a passing gate: frontend full-suite execution was cancelled; migration job stopped during dependency installation before its graph test. Main2f093ca3 adds only Motive cadence configuration/contract/board, without C1 application/schema changes. Preserve blocker history, integrate main, rerun all exact-head protected checks and then complete production acceptance. Local39898/frontend5174/proxy8001/backend mount and readiness remain aligned; fresh browser acceptance follows where needed.

Release dependency found during resumed verification: Worker currently runs e3ff99e0 after rollback from549's reported scripts-namespace import failure. Candidate91e37cf4 still contains the affected imports and changes backend files, so the skipped configuration-only2f093ca3 Worker deployment cannot establish safe C1 auto-deploy behavior. Architecture recommends existing PR551 before550. Its two helpers are byte-identical relocations with import/collector compatibility corrections and isolated tests; no pricing/schema/config changes. User approval requested for this additional separate export-workflow release. No merge, provider setting or Worker change made. Repository Dockerfile copies the backend tree; exact production packaging cause must not be inferred as app-only from it.

User explicitly approved releasing551 before550. Independent551 review passed both isolated import tests with network denied and byte-identical helper checks. Candidate da1bc206 integrates main2f093ca3 with only board/config additions, application tree unchanged. CI38917224328 is pending. Superseded C1 run38915187342 passed migration, frontend, full frontend and Playwright before cancellation to prioritize its release prerequisite; it is not an all-green final gate. Full exact-head C1 CI will restart after551 integration.

Reader/writer release ordering correction: actual ETS service6b1f4f0b watches collector paths and has existing five-minute cadence. Its active old image9fe12ab/deployment10764d7a remains buildOnly/stopped. To avoid activating the writer before corrected readers, Architecture narrowed551 at941a7fcf: original collector helpers remain unchanged; byte-identical copies plus imports live in app/services. Final diff matches no actual ETS watch pattern. Both standalone/application import tests and exact-head CI are repeated. No service setting, cadence, collector activation or off-schedule scrape is changed. Original owner checkout remains preserved.

CI fixture follow-up: PR551 run38919805146 reproduced an existing frontend test timing race (1failed/1731passed). The test waited for search request invocation, then clicked disabled Next before results settled. A deterministic delayed response reproduces the exact missing page2 assertion. Durable correction is assigned to C1 because it verifies this customer journey: immediate+delayed cases retain all cancellation/search/page assertions, prove disabled paging makes no request, then wait for enabled Next. Adaptation preserves C1 pricing request options;40 tests and strict single-file lint pass. Independent reviewer permits one unchanged551 full-suite rerun, not a waived gate or repeated rerun-until-green. No application source change.


Release preparation at15:50UTC: user authorized coordination with the Motive chat; it acknowledges holding further merges/deploys until551→550 immediate schema/financial-retention checks pass. After main4061aaa8 advanced,551 integrated it and adopted the reviewed pagination-test fix itself at52683b19;38/38 focused cases and independent source GO pass. Fresh all-six run38925629657 is active; the superseded38919805146 run is cancelled and is not a pass.

C1 locally integrates that reviewed prerequisite at8d67c4bb before release. The only conflict was the test mock call; retaining `base(url, options)` leaves the entire C1 customer test file byte-identical to4c85e71e. No C1 application, contract or migration changed. Incoming backend changes are only551's approved four helper/import files and isolated import test. Protected550 CI will start only after551 is merged and its readers verified. Runtime stays frontend39898/source5174→8001 and the same backend bind/database, schema176; direct/proxied readiness pass after normal development auto-reload.

Interim production read at2026-10-16T15:45:41.270834Z still shows exact175contact with C1 absent. Private v3 receipt digestf6b96c2d8d7f71c522a7a07c1fbf3be540b97803915ba2db94ba832313637afd compares all original row identities to the05:12 baseline: zero changed financial/source hashes, missing or additional rows, or timestamp-only changes across all seven cohorts. This is an interim pre-to-pre observation, not post-deploy proof; capture a final fresh baseline immediately before550 merge. Original receipt retained.

Actual signed-in local customer Business settings recheck after8d67 integration passes:145/hr Shop, Catalog Shop, Edit pricing and History render from the same verified backend; no draft/data mutation. The old startup branch badge195c7f3 is corroborated by current PID/cwd/bind mounts and rendered source, not treated as current HEAD proof. Preview5174 is aligned and browser-verified for this unchanged C1 journey.


Pre-cutover schema ordering: fresh Railway Worker manifest confirms no preDeploy command or health gate, and starts Celery/beat directly. Architecture traced full Customer/RepairOrder reads in shop-history capture and QuickBooks sync; the latter commits a lease/attempt before that read, so relying on build order or normal task retries is unsafe. Proposed controlled sequence: after final550 CI, capture final175contact baseline, apply the byte-verified additive175pricing/176 artifact through one isolated normal Alembic run while compatible551 services remain running, verify schema/retention, then merge550/autodeploy. Backend is preparing a private staged runner and disposable rehearsal. Exact runner/artifact independent approval is required before production execution. No production schema/settings change has occurred, and no new application implementation or gate waiver is implied.


## Final reader release and normal migration ordering — 2026-10-16 16:11 UTC

PR551 passed all six protected contexts in38925629657 at52683b19, then squash-merged6471943f at16:08:11UTC. Its merge tree is identical to the checked candidate. Railway Web752f4d70 and Worker1777d45a are building that exact SHA; ETS7c7aaa00 is explicitly SKIPPED. Runtime acceptance is pending. C1 integrated the squash at e315ed16; its entire tree remains identical to8d67c4bb after retaining the C1 test mock's `base(url, options)`.

The private controlled migration approach is superseded and was never executed in production. Independent review rejected unbounded migration-session locking and uncertain commit reporting; Architecture also identified an old551 restart gap after preapplying176. Instead, add a narrowly scoped read-only Celery `worker_init` gate in550 that waits boundedly for the migration head before Beat/consumer startup. Web remains the sole migration owner through its existing normal preDeploy command. Backend owns this correction; final exact-source independent QA/Security and all-six CI gate it. This does not alter C1 pricing, migration bytes, collector schedule or production settings.

After ancestry-only integration, runtime e315ed16 is aligned: frontend39898 from this checkout/frontend,5174 with effective8001proxy; backend imagebde2e27b binds this checkout/backend, postgres/truckpitstop_ets_workflow_parity_20261012 at176. Direct and correctly proxied `/health/ready` pass. No service restart, migration or data mutation. Feature render recheck follows the prior unchanged C1 receipt.


PR551 reader runtime GO at16:20UTC: [release receipt](db133/pr551-reader-release.json) records successful exact6471943f Web/Worker deployments, public build/readiness,36 natural paid-invoice task successes (zero claims) and successful16:19:02 shop-history capture (50scanned/0captured), with zero import errors in the bounded log. Task success is not a new provider/business outcome. The queued duplicate post-merge main run38929538626 was cancelled after confirming merge-tree identity to all-six-green52683; it supplies no passing claim.

Architecture confirms the collector uses explicit SQL compatible with both175contact and176 and preserves C1 fields; historical imports intentionally omit invented C1 provenance. With both chats coordinated, the export owner may release its reviewed one-field cron-parityPR557 after protectedCI, then provide its mergeSHA for integration before final550CI. It owns the natural collector/ELIS acceptance. Fresh C1 before/after receipts must separately attribute any normal import changes. Motive releases remain held until550 immediate schema/retention checks. No off-schedule scrape, provider resend, manual production migration or pricing activation was performed.

Read-only production UI before C1: TPS-828ACD84-000055 retains45m at100/hr=75 labor, part35.73, order110.73 and invoice112.98. Actual signed-in local Business settings aftere315 ancestry integration still renders145/hr Shop, Catalog Shop, Edit pricing/History; preview5174 is aligned and browser-verified. Root has not used the stale startup badge as a currentHEAD assertion.
