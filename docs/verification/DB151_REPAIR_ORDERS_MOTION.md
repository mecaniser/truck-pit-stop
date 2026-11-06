# Repair Orders motion — local review

Owner: Frontend & UX. Fast UI lane. Branch: `codex/repair-orders-motion`, base `36980c15`.

## Current release scope
- Trigger-origin menus:200ms entrance,160ms exit,0.95 start scale; compact press0.97; reduced motion disables transforms/delays.
- Stationary ledger rows; selected row hides its redundant Preview. No row entrance/stagger remains.
- URL-owned selection prevents old/new/old record rebound. Initial body reveals once after first reads settle, with no bright skeleton or borrowed record data.
- Deep-link focus waits for reveal, including linked operations, recommendations and restored issue rows.
- Theme tokens reach invoice details, popovers and new-order dialog. Creation dialog stays stationary across selections; danger sheet clips rounded corners.
- Existing backend, authorization and financial mutation contracts unchanged.

## Verification
- Five focused Vitest suites: 191/191 pass (ledger, authorization, abort, customer, pending feedback including intake Escape/reopen).
- Changed TSX/test ESLint passes. Build/typecheck/shared controls run recorded in local logs.
- Signed-in synthetic local shop, frontend 5298, backend8198, disposable database dashboard_lifecycle_disposable; runtime branch verified.
- Desktop: exact selected order opens; Next changes BOARD-PAYMENT-1 to PRIVATE-A-1049, Previous restores it; close restores ledger and originating row focus.
- 390px: no document horizontal overflow; detail opens/closes; repeated preview open/close/open works; Checked In produces zero matches and Any status restores both rows.
- Night shop: list filter and both detail portals use dark surfaces. Truck intake values remain readable.
- Reduced-motion emulation: rows animation none; menu duration0s; record close/focus and filters remain operational. Emulation cleared after QA.
- Menus use200ms normal duration; invoice origin top-right. No financial action submitted.

Local screenshot: /tmp/repair-orders-motion-local.png. Preview left open. No PR, merge or deployment claimed. Release checks and production acceptance remain pending.

## Review corrections — 2026-11-06
User acceptance found issues missed by the initial pass. Prior motion claims are superseded where noted below.
- Removed decorative row translation/stagger and preview child entrance replay; explicit menus/disclosures retain restrained motion.
- Fixed invoice settlement's hard-coded light tone, added theme-aware invoice wrapper/text, and passed dark tone to the checklist.
- Fixed intake label at96px on desktop: measured x467.21875/y199 on both orders, instead of content-driven repositioning.
- New Order desktop dialog retains a stable900px/max90dvh frame. Measured x205.5/y206.5/height900 before and after customer/truck selection; mobile390x844 remained x0/y0/390x844. Existing form body scrolls.
- Empty cached checklist refresh no longer inserts/removes an expanded card; accessible refresh status remains, and failures still show an unverified warning. Added a regression covering both paths.
-161 focused tests pass, changed-source ESLint and production build/typecheck/shared-control checks pass; existing chunk-size warning remains.
- Browser acceptance: dark invoice totals use rgb237,240,246 on dark surfaces; desktop next/previous exact IDs; mobile invoice no horizontal overflow; create dialog customer/truck selections stable in normal/reduced motion. No order created and no payment submitted. Emulation restored.
- Runtime receipt: November6, branch codex/repair-orders-motion, base36980c15, owned dirty changes; frontend5298 PID19013 cwd owned worktree/frontend; API8198 container source owned worktree/backend; postgres/dashboard_lifecycle_disposable, migration204 head; readiness DB/Redis healthy. Served CSS and signed-in rendered corrections verified. Aligned and browser-verified.
- Screenshot /tmp/repair-orders-invoice-fixed.png. Local only; no merge/deploy.

## Actual selection flicker correction — November6
Prior review missed selected-row preview insertion/removal and initial price-build skeleton. Preview trigger and brief mounting now depend only on explicit preview state, not selected record. The redundant Open action reserves its space when hidden. Three bright pulsing fake rows replaced by a quiet loading status; prior-record data is never retained as the new record. Browser1200ms network delay captured Loading work details with zero pulse elements; both ledger rows remained104px high at y182/y290 before, during and after repeated next/previous. Network emulation restored. Screenshot /tmp/repair-orders-loading-fixed.png.125 focused tests passed, then added selected-preview persistence regression; ledger final result in /tmp/ro-ledger-final.log. Build passed; local only.

## Repeat-navigation stutter — November6 follow-up
Found price-build gcTime0 evicting each order on departure, forcing repeated initial loading. Retain exact order+pricingScope cache for5minutes with normal background revalidation; pricingScope remains tenant/actor/role/session epoch. Background reads no longer start calculation animation; total-change baseline resets per order. Compact loading matches empty-work height.
Browser90-frame next-order sample:0 loading replacement frames; only one ledger layout throughout ([[182,104],[290,104]]). Both warm records under1200ms delay rendered immediately without Calculating. Emulation restored. Regression verifies cold order cannot borrow cached work and new session epoch cannot reuse prior work.80 panel tests pass plus prior authorization/abort suites25 tests; lint/build checked. Screenshot /tmp/repair-orders-warm-navigation.png. Local only; do not represent this as production release or every possible journey being stutter-free.

## Full cold-load investigation and coordinated reveal — November6
Earlier warm/list-only checks were insufficient. Full-body trace with600ms network delay exposed two independent causes:
1. Immediate applyDetailState in openDetail raced the router's selected-URL effect: old→new→old identities could render on a single click. openDetail now seeds the exact scoped snapshot, and the committed URL alone selects the record. Existing history/replace semantics retained.
2. Cold invoice load rendered checklist94px, later inserted invoice86px, then removed empty checklist110px including margins. In before trace Truck issues moved y494→580→470.
The new initial readiness gate mounts child queries concurrently and holds the body/financial footer hidden until initial work, invoice/settlement, checklist, operation, recommendation and issue reads settle. It reveals once in180ms, respects reduced motion, and never conceals already-open data for background refresh. Error states reveal when reads terminate; no previous-order content is borrowed. Recommendation refresh status remains accessible without inserting layout height.
After trace: selected record changed once; body hidden at61ms through1261ms invoice insertion and1300ms checklist removal, visible at1966ms with all sections at final positions. No visible intermediate section positions. Normal-network timing is faster; measured times include600ms per request. Header/navigation remain available while preparing.
Verification:83 panel/readiness tests,66 route authorization/abort/customer tests; final16 abort/navigation tests rerun with concurrent-router behavior and selection-rebound regression. Changed-source/test ESLint and build pass. Mobile390px no overflow; reduced motion animation none. Normal media/network/desktop restored.
Evidence: /tmp/repair-order-cold-load-traces.json and /tmp/repair-order-coordinated-reveal.png. Local preview5298 aligned same owned branch/source. No merge/deployment.


## Cleanup after root-cause confirmation — 2026-11-06

User requested removal of unsuccessful speculative fixes. Restored original price-build gcTime=0 and original calculation/read feedback and total-change effect. Removed fixed 96px intake label width, redundant inner loading placeholder/CSS, and the test requiring five-minute cache retention. The coordinated surface now owns initial loading feedback; bright skeletons are not restored.

Retained URL-owned record selection and coordinated initial reveal. Also retained separately verified fixes: Preview stays mounted across selection, create dialog stays stationary, dark invoice/portal/checklist styling, empty checklist refresh stays out of layout, and recommendation refresh status stays out of layout. These address distinct observed defects. Decorative row movement remains removed.

Validation after cleanup: 155 tests pass across PriceBuilderPanel pending feedback, readiness hook, route abort/navigation, ledger, and checklist suites. Changed-source ESLint and production build pass; diff whitespace check passes. Browser on existing local5298 runtime, Night theme: 600ms network latency next navigation changes BOARD-PAYMENT-1 to PRIVATE-A-1049 once, hides intermediate section insertions, reveals final body at1409ms. Return to invoice reveals once with stable section geometry.390px close/list/exact-record reopen passes, document width390, reduced-motion body animation none. Temporary network/device/media overrides restored. No financial mutations, commit, PR, merge, or deployment.

Earlier cache/label workaround notes above are historical and superseded by this cleanup.

## Selected-preview and sheet correction — 2026-11-06
User correctly identified that preserving the selected-row Preview was an unintended behavior change. Restored original selected-row suppression, brief suppression, and conditional Open action. Added selected/unselected regression. Danger sheet now clips its child surfaces within its16px rounded top corners. Live local Night browser confirms selected PRIVATE-A-1049 has no Preview; unselected BOARD-PAYMENT-1 retains Preview. Computed sheet overflow hidden/radius16px and screenshot /tmp/repair-order-preview-corners.png confirm clipping.126 ledger/panel tests and changed-source lint pass. No delete action submitted. Local only. This supersedes the previous decision to preserve selected Preview.

## Final regression and review — 2026-11-06
Owner Frontend & UX; release authorized by user. Existing runtime5298/API8198 rechecked: frontend PID19013 owned source, backend owned bind mount, test environment readiness DB/Redis healthy; local UI aligned and browser-verified. Base/main36980c15 current at intake.

Browser matrix:1300x900 and390x844, Day/Night shop, normal/reduced motion: invoice disclosure, invoice menu Escape, truck/customer portal placement all passed, no horizontal overflow; menus200ms normally and0s reduced. Desktop customer/vehicle/service creation selection preserves exact panel geometry (Day810px tall at y45; Night900px at y206.5); mobile panel390x844 remains viewport-sized. Cancel creates no order. Selected Preview hidden; unselected preview and interrupted disclosure work; next/previous exact IDs, mobile edit cancel/close, empty Checked In filter and Any status recovery verified. Delayed cold navigation traces from prior pass retained. No live payments, invoice revisions, deletion, email or customer mutations submitted.

Wider suite exposed readiness/transition timing assumptions. Tests now await visible/ready UI rather than DOM presence.435 repair-order/checklist tests expanded to465 with vehicle-issue and deferred focus coverage:462 passed in full serial run, remaining3 invoice-revision tests passed after their helper awaited real readiness. Production build passes; changed-source lint passes with two existing page hook warnings.

Independent read-only reviewer found hidden-body deep-link focus could be consumed before reveal. Corrected operation/recommendation effects and nested issue restoration using OrderSurfaceContext; deferred invoice-focus regression proves no focus until ready. Re-review: no remaining actionable findings. PR CI and production receipt pending.
