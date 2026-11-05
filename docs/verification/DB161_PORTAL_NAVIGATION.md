# DB-161 customer portal navigation refinement

Frontend & UX is accountable. This is the Fast UI lane: existing customer routes, APIs, visibility guards and payment contracts are preserved. User requested a review of the remaining portal and fixes using Hick’s and Jakob’s principles. No production deployment is claimed for this item.

## Findings and changes

| Surface | Observed problem | Implemented correction |
| --- | --- | --- |
| Repair sections | Current, Appointments and History looked like equivalent action buttons; active matching depended on exact query ordering and failed for deep links. | Destination links now use clear labels, a distinct selected treatment and aria-current; active matching uses pathname and the view parameter. |
| Repairs | Selected vehicle context could not be changed in the list. History duplicated navigation as a header action; the empty-state booking link dropped vehicle scope. | Vehicle scope and one Book a service action share the page header; clearing vehicle scope preserves Current repairs. |
| Repair history | A PDF link was nested inside a details button, mixing two destinations in one interactive target. Mobile descriptions were cramped. | One details button plus a sibling Invoice PDF link, explicit accessible names and a download icon. Mobile titles wrap and status/amount follow the description. |
| Appointments | Book a service appeared below the list; scope was missing for valid selections; filters occupied the action area. Specific reservations lacked an All visits recovery link. | Header scope and booking action, separate selected filter group, All visits for request and reservation deep links. |
| Services and booking | Catalog lacked a direct return to appointments. | Scoped Back to appointments link. Existing progressive booking choices and Choose another service are retained. |
| Invoice overview | Settled and unpaid/unverified invoices shared one undifferentiated list. | Invoices to review and Invoice history groups, preserving all existing payment eligibility, amounts, queues and destinations. Unknown balances remain unavailable, never zero. |
| Account and invoice detail | Reviewed existing navigation, grouped account sections, and invoice Back to Invoices return. | Existing behavior retained; no additional defect established in this pass. |
| Unknown portal route | No route fallback, leaving empty content. | Page not found with a scoped Back to Home action. |

Filter pills now announce pressed state; date captions have readable muted text. Desktop page actions stay at the right of the header; mobile booking actions align left, matching the vehicle-page pattern. Four history filters wrap instead of requiring horizontal scrolling. No unnecessary animation or new menu was added.

## Local runtime receipt — November 5, 2026

Checkout `/Users/sergio_m1_promax/GitHub/truck-portal-overview`, branch `codex/portal-navigation-consistency`, base `1365e583674c923cbee23dee1847f51454054dd1`, with the item’s uncommitted source changes at acceptance. Vite restarted for the branch on127.0.0.1:5173, PID6509, cwd is that checkout’s frontend; validated runtime branch/SHA and proxy target8020 supplied explicitly. Backend container portal-overview-preview-api retains the same checkout’s read-only backend mount on8020. Backend source is unchanged from the already-running version, so no API restart/migration was needed. Database is isolated portal-overview-pg/portal_overview_current; environment test, live provider keys absent. Populated fixture and provider settings preserved.

API and frontend-proxied `/health/ready` return ready with database/Redis healthy. Signed-in synthetic customer browser rendered the changed section links and header actions. Local preview is aligned and browser-verified. No customer records, appointment requests, authorizations or payment state were written during this review.

## Verification

-61 focused tests across five files passed: selected navigation independently of query order and detail parameters, separate PDF/details controls, history filters, vehicle-scope clearing preserving the current view, grouped invoice actions including pending/unknown/zero balances, reservation return link, unavailable reads and unknown-route recovery.
-Production build, TypeScript and shared-control checks passed. Explicit ESLint on every changed TypeScript file reports0 errors and9 existing mixed-export Fast Refresh warnings in portal-ui.tsx; export structure was not changed. The lint:changed helper saw no committed changes before commit and is not counted as source lint evidence.
-Real signed-in synthetic browser at1380/390/320px: history and appointments main scroll width equals client width, booking action at16px on both compact widths, history filters fit their container, no nested button/link actions. Screenshots inspected in a bounded initial pass, one batch correction and final confirmation. Browser measurements/screenshots remain private outside Git.
-Reviewed catalog common needs, Choose entry into the actual booking flow, existing unavailable-reservations/request distinction, invoice return to Invoices, and Account section navigation without submission. Focused HTTP mocks cover unavailable invoice reads; no production mutation or new backend test is necessary for this presentation-only change.

Protected PR CI, merge and release remain pending. DB161 is Review, not Done. PR805 payment-request internals are separately owned and untouched.

## Detail-navigation regression

Final runtime acceptance reproduced an additional existing bug: after opening a repair detail, Current repairs updated the URL and selected navigation while retaining the previous detail. A new regression first failed (1 failed/5 passed). The selected-detail cleanup now includes the active/history view, so changing sections returns to the requested list. The regression passes, and the same signed-in synthetic browser journey confirms the fix. This changes only local presentation state; authorization checks, requests and mutation handlers are unchanged. Focused total is61 passing tests.

## Authorized underline correction and release

User authorizes PR808 merge/deployment after correcting its selected underline. Reproduced in the local browser: focused selected Appointments has box-shadow none, while blur restores the inset purple shadow. Shared db-controls focus resets intentionally remove shadows. The selection indicator now uses a reserved two-pixel bottom border with aria-current coloring, independent of focus/blur; shared keyboard focus treatment is retained. Verify selected border and focus outline in the actual browser before exact-head CI and release.

Local acceptance after the correction: mouse-focused, blurred and keyboard-focused selected Appointments all report a two-pixel solid purple bottom border and44px height. Keyboard focus additionally reports a visible two-pixel outline; no layout shift. At390px the selected border remains and main scroll/client widths both equal390px. Screenshots stored privately. The61 focused regressions pass. Existing local5173/PID6509 and API8020 source mounts/isolated database remain aligned and browser-verified; readiness healthy. No server configuration or data changed.

## Protected merge and automatic deployment

All seven protected checks passed on final head `5099a02427c52c5cf55926854030a2c61863303b`, run42121325182. Frontend critical/build, full frontend and Playwright smoke actually executed; backend gates used the existing frontend-only scope classification. User-authorized squash merge `9fc64b3976cebc66564090e92c5dc9ea32711e10` completed on2026-11-05 at22:33:24UTC. Merged application/configuration trees match the checked head. Automatic Railway deployment `e66197ac-0651-450c-b446-948390eb6e4c` targets that exact SHA. No branch-protection bypass, forced deployment, migration, provider operation or customer-data mutation was introduced. Prior successful deployment is2b462e3d on1365e583. Final live acceptance pending.

Deployment e66197ac is SUCCESS. Public `/build-version` matches9fc64b3976cebc66564090e92c5dc9ea32711e10, built at2026-11-05T22:35:17.516Z. `/health/ready` reports ready, database/Redis healthy. Production browser reload reached Login because the existing customer session expired; signed-in acceptance is pending the user restoring that session. No credentials requested in chat and no authentication bypass attempted. This is not a failed application-health check or completed customer acceptance.

## Signed-in production acceptance and closure

The user restored the real customer session. Signed-in acceptance passed on the deployed9fc64b39 release: Home loaded; Current repairs and Appointments expose the header scope/booking action; Appointments retains a two-pixel purple selection border both mouse-focused and blurred, at44px height. Keyboard activation retains that border plus a separate visible two-pixel focus outline. At390/320px, main scroll/client widths match the viewport and the selected border persists. Temporary viewport reset.

Repair history rendered16 separate details buttons and16 sibling PDF links, with zero nested interactive controls. Opening a repair shows its exact record; switching to Current repairs returns to the list. Invoice overview renders both Invoices to review and Invoice history. Book a service opens the catalog; Back to appointments returns to the expected route. No browser console errors were captured. Screenshots and measurements remain private outside Git.

Production acceptance was read-only: no customer labels, appointment requests, quotes, invoice state or payments changed. No unresolved release blocker remains. DB161 is Done, with Frontend & UX accountable.
