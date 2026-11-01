# DB149 historical customer invoice guidance — November 1, 2026

Owner: Frontend & UX. Existing-contract Fast UI correction, branch `codex/historical-invoice-readonly` from `4645ea6a`.

## Reproduction and correction

The authorized archived Easy Truck Shop invoice has readable invoice detail, payment summary and PDF, while the payment-action contract intentionally rejects archived repair orders. Known imported invoices cannot use DieselBridge payment actions regardless of archive status. The customer page nevertheless queried settlement, archived repair-order details and provider availability, then showed the resulting payment-control404 as if the invoice could not be found.

Use existing `InvoiceDetailResponse.source` to recognize `easy_truck_shop_import`. Keep the real invoice summary, PDF and review link. Show a historical read-only/contact-shop explanation. Do not request settlement, allocations, archived order details, Zelle destination or card-provider availability; no online payment controls. Charge breakdown uses the available invoice subtotal rather than inventing labor/parts from unavailable archived details. An older response missing payment_summary labels its amount as recorded invoice total, not a verified balance. Native/null/unknown sources retain their original settlement error handling.

No backend, auth, tenant, source-ownership, payment, financial record or archive contract changed. No provider call, restored repair order, payment attempt or message send.

## Owner checks

- Historical real-hook regression7/7: paid/unpaid/cancelled, unknown balance, older response without summary, and native/null-source404. Imported cases assert invoice-detail is the only API request and no mutation occurred; summary/PDF/review remain visible.
- Existing cash5/5 and shared payment-summary7/7: total19/19 focused assertions pass.
- TypeScript noEmit passes; changed-source ESLint0 errors; Vite production build passes; diff check clean.
- Fictional actual-component preview available at `http://127.0.0.1:4181/?status=sent` (paid/cancelled variants), axios adapter rejects all endpoints except fictional invoice detail. Parent CUA acceptance passes actual-component desktop1280/mobile390: confirmed0, balance654.89, historical read-only/contact-shop guidance, PDF retained, no payment/error UI and no horizontal overflow. Screenshots: local `output/playwright/historical-guidance-desktop.png` and `historical-guidance-phone.png`. Preview uses no backend/database/provider and owned4181 server stopped after verification.

## Runtime receipt and release limits

Nov1 intended worktree `/Users/sergio_m1_promax/.codex/worktrees/invoice-review-link/truck-pit-stop`, branch above, base4645ea6a with task-local changes and pre-existing output/tmp preserved. Local full app alignment is **blocked**: approved backend/.env absent. Frontend5173 PID3456 belongs to my-shop-nav-stability worktree; Docker8000 PID3415 binds machined-sidebar backend. Existing services/settings preserved; default frontend proxy remains127.0.0.1:8000. No migration or database operation. Standalone4181 is only a fictional component preview, not an aligned full-stack application.

Configured/signed-in runtime acceptance, protected CI, merge and deployment are not claimed here; parent coordinates release authority and live customer verification. This fix remains reviewable, not Done.

## Authorized release — November 1, 2026

Current user requested correction and live portal verification; release followed
that authority without another permission request. PR737 confirmed already merged.
Integrated main0b902552; only concurrent board prepends conflicted and both
histories were preserved, no invoice source conflict. Post-integration19 focused
tests, TypeScript and baseline-aware ESLint2files pass.

All seven protected checks in41343268711 PASS at exact49736297. Backend gates
are correctly scoped by CI for a frontend-only diff; no unrelated suites were
rerun manually. PR738 normally squash-merged as
`29f0b21f2952c489b3f1334671e8a80c380c1dbc` at14:52:29EST. Checked/merged
tree`f2a57a5899870ce5fbb1a2ea2e567c1a7d3641d9` identical. Production
Web deployment`de5c5bb5-a422-4ef5-ae49-b00ae555556e` started on exact merge.

At initial release, signed-in customer acceptance was pending: the parent-controlled Chrome
profile is currently staff and redirects the requested portal invoice to the
staff dashboard. User has been asked to complete normal customer sign-in in
the identified Chrome group. No impersonation, account/role change or minted
auth token is used. Actual-component fictional desktop/mobile acceptance is
retained separately; it is not represented as authenticated live acceptance.

### Deployment proof and remaining live gate

Production Web`de5c5bb5-a422-4ef5-ae49-b00ae555556e` SUCCESS at exact merge
`29f0b21f2952c489b3f1334671e8a80c380c1dbc`. Public `/build-version` matches.
One read-only smoke of the requested `/portal/invoices/...` app route returned
HTTP200 with the app bootstrap and served asset references. This proves delivery,
not authentication or changed customer rendering. No worker inspection, extended
canary, financial query/mutation, restored record, provider operation or send was
performed for this Fast UI correction.

At that initial release checkpoint, the parent's browser inventory had no signed-in customer `/portal` tab across
the three Chrome profiles. The identified handoff Chrome3 tab/group remains
available for normal customer sign-in. A staff redirect is not customer acceptance.
The item was RELEASED with live customer gate pending, not Done. After customer
sign-in, the agent must verify the same authorized historical invoice's balance,
PDF/review access, plain read-only guidance, and absence of the blocked payment
requests/error UI. User is asked only to authenticate, not to perform regression
testing. No impersonation or credential workaround is appropriate.

Rollback baseline served at release intake`4645ea6a`; current integration also
includes already-merged PR737. Incorrect native error handling or missing historical
summary/PDF would fail acceptance; focused fixtures cover those cases. No live
customer result was inferred while normal customer authentication was unavailable.

## Final signed-in live customer acceptance — November 1, 2026

User explicitly confirmed customer sign-in in the in-app browser. Parent CUA
observed the actual customer dashboard and followed its legitimate invoice link
to the currently available historical invoice`ETSINV-1182` / order`ETS-0759`
(ID`6e6b72ca-8382-4b54-97ec-ac24d8ca13b5`). The live page displays:

- Unpaid;0applied and314.02balance due.
- Historical invoice heading, read-only/no-online-payments/contact-shop guidance.
- Invoice PDF link and the existing review link retained.
- No “Payment details could not be loaded” or “Invoice not found” message.
- No payment controls.

Actual screenshot verified on disk:
`output/playwright/historical-guidance-live-customer.png`; the browser tab is
marked as the deliverable. This is actual signed-in live acceptance, separate
from the earlier fictional desktop/mobile previews. No service, financial,
provider, record-restoration or message operation was performed for this check.

An earlier direct full navigation to the previously inspected invoice returned
to login; returning to the current customer dashboard restored the authorized
session and its own invoice link was used. No assertion is made that the old
invoice remains available or still has the earlier654.89balance. The current
customer portal exposes one unpaid invoice with314.02due.

The required live customer gate is now cleared. DB149 historical guidance is
DONE: implementation, focused checks, protected CI, merge, exact deployment,
served-build proof and authenticated customer acceptance are recorded.
