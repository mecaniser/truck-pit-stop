# DB-112 production workflow verification — 2026-10-13

Accountable owner: Frontend & UX. Fast UI verification of the released shared customer and repair-order layout. ETS parity remains paused for the workflow findings below.

## Release identity

- [PR513](https://github.com/mecaniser/truck-pit-stop/pull/513) merged as `1ee17305e5eaaab55413bf554f4fb0443388a150` at22:58:05 UTC.
- All six protected checks passed on final source `f173be6f9709cd18ea628c5f6f6e2c69fbaf9841` in [run38478795319](https://github.com/mecaniser/truck-pit-stop/actions/runs/38478795319).
- Railway Web deployment `2d5b3679-2ba9-499b-b3fe-4e6148a879a4` reached SUCCESS at the exact merge. Production initially served34661ad8 while the build ran; acceptance began after successful deployment and a browser reload.
- `https://www.dieselbridge.com/health/ready` reports production ready with database and Redis healthy. Browser loaded `index-Dlteg12U.js` and the new mobile frame/back-label/More controls.

## Scope and data handling

Actual authenticated production Chromium UI; measured1280px pointer desktop,390×700 and320×700 portrait,740×400 coarse-pointer landscape. Records included a completed order with11 service/parts groups and18 standalone parts, a customer with33 linked trucks, and a native invoiced order with a long operation summary and5 parts. This checks populated real workflows, not mocked responses.

No production records were saved, created, merged, deleted, invoiced, reassigned, completed, or paid. Unsaved customer, contact, work-request and new-order text was cancelled. No resend, provider continuation, release-vehicle or financial confirmation action was taken. Local mutation/save-reload acceptance remains in [DB112 local evidence](DB112_MOBILE_WORKSPACE.md); it is not claimed as production mutation evidence.

## Passed production checks

- Desktop queue and dense service rows remain intact; customer facts and inline footer controls remain visible.
- Completed order → customer → linked truck → repair history → original order works on desktop. Expanded labor/parts stay read-only for finalized work.
- Customer and work-request editors accept draft text and Cancel retains the original display. Mobile customer editor has a full-height frame, one form scroller, visible Save/Cancel, and Escape dismissal. Contact editor opens and cancels without changing the record.
- At390×700, the completed repair order has a76.5px header,57px footer and567px content scroller, no horizontal overflow. More and pricing stay within320px bounds; focusing them does not move the fixed header.
- Mobile customer → truck → customer → order → Close returns to Shop Work with app navigation restored. Closing no longer reopens a historical selected order.
- Standalone Customers search opens the intended record; tax exemption remains under Business settings. A3300+ order archive and733-customer directory remain navigable without changing the records.
- Customer → truck → New repair order carries the selected customer/truck. Cancellation returns to the same truck. See the search-context finding below.
- At390×700, standalone customer content has one586px vertical scroller and no horizontal overflow. At740×400 touch landscape it has one278px content scroller, with header/actions still visible.
- Native invoice at320px retains readable long operation summary, read-only duration/rate and parts, disabled add-part control, direct Record payment and secondary Resend/Void actions in More. The settlement dialog opens and closes; existing accounting-review and disabled-charge guards remain intact. No financial action is submitted.
- At740×400, the native invoice with a quote reference has a97px header,57px footer and246px body; one vertical scroller and no horizontal overflow.
- Browser error/warning log was empty during these journeys.

## Findings: production workflow gate remains open

### DB-113 — Preserve the customer-directory search across new-order detours (P2)

Reproduction: Customers → search for a company → open its record → open a truck → New repair order → Cancel → Back to customer → Back to Customers. The correct truck is restored after Cancel, but the directory returns to its unfiltered first page instead of retaining the typed search.

Source: `CustomersPage.tsx` holds `searchQuery` only in component state; `startCustomerOrder` stores location query/customer/truck in `RepairOrderReturn`, so the search is lost when the route unmounts. This file is unchanged by PR513. Expected: retain search and list position/context through both cancel and normal return without restoring stale customer or truck identity.

Owner: Frontend & UX. Status: Open; correction and regression verification required before resuming ETS parity.

### DB-114 — Make customer merge dismissal keyboard accessible (P2)

Reproduction: open customer → More → Merge → press Escape from the search field. The dialog remains open. The visible X successfully cancels, but its button has no accessible name and the overlay has no dialog semantics. No merge was attempted.

Source: the existing merge overlay in `CustomerFormModals.tsx` uses plain divs and an unnamed icon button; the new customer-edit Dialog does not cover it. Expected: named dialog/close control, Escape dismissal, focus containment/return, unchanged merge selection and confirmation guards.

Owner: Frontend & UX. Status: Open; correction and regression verification required before resuming ETS parity.

## Evidence boundaries

The shared layout is deployed and its desktop/mobile browser behavior passes the listed checks. This is not an unconditional workflow sign-off while DB-113/114 remain open. Physical iPhone/Android, native Safari and real software-keyboard behavior were not tested. Production assignment/completion/save/payment mutations were intentionally not performed; those existing-contract write paths retain separate local automated and authenticated runtime evidence.

Production screenshots stay local, not in a remote PR, because they contain live business records:

- Desktop: `/tmp/db112-production-desktop.png`
-390px order: `/tmp/db112-production-order-390.png`
-390px customer: `/tmp/db112-production-customer-390.png`
-320px native invoice: `/tmp/db112-production-invoice-320.png`
-740px invoice landscape: `/tmp/db112-production-landscape.png`
