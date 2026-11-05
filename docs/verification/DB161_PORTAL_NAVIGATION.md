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
