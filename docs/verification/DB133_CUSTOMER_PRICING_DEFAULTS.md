# DB133 / C1 customer pricing defaults

Accountable: Backend & Integrations. Status: **Accepted contract; implementation handoff**. Selected after completed P1 in the [parity tracker](../ETS_PARITY_TRACKER.md). Branch: `codex/customer-pricing-defaults`, from P1 release-record195c7f3a (application70530bda).

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
