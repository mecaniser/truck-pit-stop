# DB149 all invoice versions — preview only (2026-10-31)

Owner: Backend & Integrations. Branch codex/invoice-spacing-qr, draft PR721. User requests preview approval before deployment. No merge or deployment in this follow-up.

Shared read-only payment_summary now drives current staff/guest invoice detail, all three PDF generators (including paid email and fleet exports), and newly rendered issued/paid emails. Native/reconciled settlement projection owns principal balance: principal_total - confirmed_principal; pending is displayed separately and never deducted. Confirmed may include credits, so label payments / credits applied. Legacy paid baselines preserve balance0 but omit unknown tender. Refunded or contradictory legacy evidence remains unknown. Actual cash receipt amounts overlay every PDF generator consistently. Existing messages/downloads remain historical copies.

Checks: payment summary/review/export/access suites57/57; invoice creation, line/snapshot and reminder-race regressions9/9. Actual guest/staff response partial-payment equality tested against isolated database: invoice100, completed40, due60. Zero write-state on read-only loader asserted. Negative tests cover bad currency, negative/NaN, wrong tenant/invoice, refunded or linked legacy evidence, real reconciliation vocabulary. Original21 PDF/QR tests retained. Parent owns frontend tests and visual previews; fresh independent reviewer checks implementation after corrections.

Local runtime preflight remains blocked: missing approved backend configuration and existing unrelated local service preserved. No configured full-stack or production verification claimed for this preview. No provider call, payment write, message send, schema or dependency change.

## Parent integration and previews

Shared frontend summary now drives guest/portal state and balances, uses refreshed settlement data consistently, preserves unknown historical tender and fee/refund notes, and suppresses cancelled/unknown payment UI. Focused frontend13/13, TypeScript/Vite production build and changed-source ESLint pass. Independent fresh invoice_versions_review reviewed final backend57/57 + frontend13/13 and returned offline QA/security GO with no remaining P0-P2 findings. Final label-only change names cancelled header Invoice status and removes cancelled receipt promise.

Seven fictional one-page PDFs generated: paid, unpaid, partially paid, payment awaiting confirmation, cash, overdue, cancelled. All visually inspected with Poppler PNGs; combined7-page review copy under local output/pdf/invoice-versions/all-invoice-versions.pdf. Current QR generation unchanged from exact-URL scan pass. Browser synthetic actual-component checks at390px portal partial and guest pending verify400applied/600due versus400pending/1000due;1280px cancelled has no payment controls. These are fixture checks, not configured full-stack acceptance; missing approved backend environment remains unchanged. No production changes, invoice mutations or messages. Temporary fixture server4179 and browser stopped after checks.

User explicitly requested review before deployment; draft PR721 remains unmerged. Current portal/downloaded PDF can update with payment changes; previously emailed/downloaded copies remain historical snapshots.

## Authorized PR721 production release — 2026-10-31

User explicitly authorized remaining checks, merge/deploy and live verification,
then clarified guest Print must open the actual invoice PDF. Final source includes
inline `?print_view=true` under the unchanged guest token guard; Download remains
an attachment. Native OS print-dialog interaction is not claimed.

- Integrated current main twice as sibling releases landed. Only concurrent
  board additions conflicted; both histories preserved, no source conflict.
- Full CI43a600c1 found one outdated branding fake: it did not recognize the
  payment-summary collaborator's settlement query. A scoped unit collaborator
  fake fixed it; production code unchanged. Independent test-only GO35/35 and
  owner branding/payment/review/access/export60/60. Original independent
  payment QA/security GO57backend+13frontend and Print1backend+1frontend retained.
- All7 final checks PASS in41173020331 on168a2dd3. Normal squash merge
  `eb04531adfeb64a95ed1ee0e812fceabff5746d6` at01:39:18 America/New_York.
  Checked/merged tree`8620a42ead44d9e18cc4928b555904f2b6e19897` identical.
- Production Web`c05c29fe-534b-469e-a67b-4e6affa7e825` and Worker
  `1552cd90-5214-4b88-95b3-ad1d1f04f3fc` SUCCESS on exact merge. Public
  `/build-version` matches and `/health/ready`200 with database/Redis okay.
  No new schema or tenant configuration; existing review URL preserved.
- Read-only NC inventory supports actual cash, paid, unpaid, partial and cancelled
  records. No pending payments or overdue invoice status exists in that shop's
  inspected data; those states retain fixture evidence, no fake records created.
- Five existing actual invoices: deployed invoice-detail payment_summary equals
  actual public guest resolve response; settlement balance verified as principal
  minus confirmed. Actual Print GET returns200 PDF with inline disposition;
  default Download returns200 attachment. Before/after fingerprint of selected
  invoices' total/subtotal/tax/status/paid_at/updated_at unchanged. No financial
  writes, provider capture or role/account changes. Verification invoked no
  customer send/resend; no claim is made about unrelated scheduled traffic.
- All five real PDFs parsed with pypdf: correct payment text/balance,2exact
  review URI annotations each. Paid/cash/cancelled have no Pay Online/Zelle
  prompt. Rendered QR from every real PDF independently decoded by Apple
  Vision to the exact user-supplied review URL. Page counts cash2/unpaid2/paid1/
  cancelled2/partial1; private real PDFs/token URLs omitted from committed evidence.
- One30-minute existing-service guest token per selected invoice supported live
  verification; private files0600, no mail. No minted auth JWT or impersonation.

### Customer portal acceptance and existing historical restriction

Parent CUA verified the user's legitimate signed-in customer invoice: Unpaid,
0applied and654.89due match the recorded reconciled settlement and current PDF.
The pre-existing controls error (“Payment details could not be loaded. Invoice not
found.”) remains separate from the new correct read-only summary. Read-only
relationship checks confirm invoice/order/user/settlement customer/tenant alignment.
The record is `easy_truck_shop_import` and its source repair order is soft-deleted;
`invoice_for_principal` rejects deleted repair orders before the additional ETS
payment-action restriction. No auth widening, source restoration or payment
enablement was attempted. Source-aware historical-payment guidance is a visible
follow-up; do not present that existing controls error as resolved.

Parent native CUA Chrome acceptance: the actual anonymous cash invoice opened
in Chrome's native PDF viewer with2pages and its Print toolbar button. Page1
shows actual line items; page2 shows issued cash total252.70, Cash received252.70,
Balance due0, review label/full exact URL and QR. The guest Print anchor's
`?print_view=true` target was observed; direct opening of that same inline endpoint
was viewer-verified. The extension-driven click attempt did not provide a reliable
event result, so no claim is made that its click event fired. Native OS dialog
confirmation or physical printing is not part of this receipt.

Release acceptance: current payment summary, PDFs, QR and inline Print behavior
are live and verified, including legitimate signed-in customer portal facts. The
pre-existing archived imported-record payment-controls error is explicitly open
as a source-aware guidance follow-up; no payment eligibility or auth rule changed.

Rollback baseline`dd3e023c`: wrong balance, summary drift, bad QR/Print target or
failed readiness would block acceptance; none seen in released changes.
