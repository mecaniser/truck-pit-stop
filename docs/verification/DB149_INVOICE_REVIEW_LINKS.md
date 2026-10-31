# DB-149 invoice review links — October 31, 2026

Owner: Backend & Integrations. Branch: `codex/invoice-review-link`; base `17608d10`.

## Findings and implementation

Source audit found no review invitation. Existing invoices expose shop/customer
identity/contact, invoice and order numbers, invoice/completion/due dates, status,
vehicle identity/mileage, itemized labor/parts, fees, subtotal/tax/discount/total,
payment instructions, notes and a thank-you as applicable to each surface.

Added nullable tenant review URL, existing owner/admin profile save/clear, shared
HTTPS validation and invoice-tenant resolver. All three PDF generators (including
fleet exports), issued/outbox/paid/reminder emails and guest/customer portal invoice
pages use it. Internal invoices, absent/unsafe settings and mismatched shops omit
the invitation. Copy is neutral across payment status. No pricing/access/provider
contract change; no customer mutations or email sends during verification.

## Evidence

- Backend: initial review/line-snapshot/shop-profile suites 25/25. Export/review/reminder-race suites 29/29, plus final actual authenticated+guest response integration test 1/1. All use fictional isolated data.
- Frontend: shared invitation, real customer receipt page and settings suites 44/44; TypeScript and Vite production build pass. Raw ESLint reports 12 existing settings violations; baseline-aware changed-source lint passes across8 changed files.
- Independent fresh agent `invoice_review_gate`: offline QA/security GO after finding/fixing fleet-export omission and reminder body placement. Independently reproduced export 9/9, earlier backend25/frontend11. No remaining P0–P2 finding.
- Migration: sole head194; independent populated SQLite add/remove check preserves row, nullable/no default. Full PostgreSQL chain and deployed migration not verified locally.
- Actual guest and customer portal components bundled with fictional axios adapter (no backend/provider requests): desktop1280 and phone390 have correct hyperlink, noopener/noreferrer, no horizontal overflow; missing setting omits invitation. Screenshots under local `output/playwright/`. Shop Profile input checked at both widths; unit test saves/clears.
- ReportLab one-page and three-page PDFs rendered with Poppler; invitation and readable URL visible and correctly placed. Real PDF URI annotation regression passes. Local fictional previews under `output/pdf/`.

## Runtime receipt and limits

2026-10-31 00:43 America/New_York: intended checkout
`/Users/sergio_m1_promax/.codex/worktrees/invoice-review-link/truck-pit-stop`,
base17608d10 with scoped dirty work. Local app alignment **blocked**: approved
backend/.env absent; Docker8000 source remains machined-sidebar checkout; existing
services preserved. Test dependencies linked; no secrets copied. Frontend5173
not started. Standalone fictional component preview used127.0.0.1:4179 only,
with no database/API access. This is synthetic browser evidence, not configured
full-stack or production acceptance.

The fictional preview server and browser session were stopped after checks.
Draft PR: https://github.com/mecaniser/truck-pit-stop/pull/717.
Credential-in-URL test fixtures were rewritten after a pre-push scanner false positive;
normal guarded push then passed. Final focused fixtures backend18/frontend7 pass.

## Remaining release gates

Protected PR CI, full configured runtime acceptance, approved merge/deploy,
migration and exact Truck Pit Stop review URL save/read-back remain required.
No merge, deployment or production setting change is claimed. See activation
steps and owner-provided URL in the contract. Item stays REVIEW, not Done.

## Authorized production release — October 31, 2026

User explicitly authorized checks, merge/deploy, exact URL configuration and live
invoice verification. All seven checks in41169876826 PASS at exact fd82b862.
PR717 normally squash-merged as `0efda9fb73441cef1dc1683fa061b249ba3ecf9a`
at00:52:56 New York. Merge-commit mode was refused by linear-history policy;
normal allowed squash succeeded, without bypass.

- Production Web `938a9b06-1021-46cd-8af8-0b74a0b87e63` SUCCESS on exact merge.
- Production Worker `73145dee-5039-49b0-bdc5-6c4577682c95` SUCCESS on exact merge.
- Public `/build-version` reports exact merge; `/health/ready`200 with DB/Redis okay.
- Deployed PostgreSQL sole revision `194_invoice_review_url`.
- Exactly NC tenant slug`truck-pit-stop` configured with the user-supplied URL
  `https://g.page/r/CXOAsgPjQkHvEAE/review`; previous value null. Direct scoped
  single-column update affected1row. Fresh read-back matches; all other tenant
  IDs/review URLs compared equal, including Wisconsin (not configured).
- Existing customer invoice`TPS-828ACD84-000018`: deployed invoice-detail handler
  returns exact URL; deployed PDF handler renders two-page PDF with2exact URI
  annotations, visible “Leave a review” and readable exact URL (pypdf checked).
  Invoice total/subtotal/tax/status/paid_at/updated_at compare unchanged before
  and after rendering. No customer messages or payment/financial state writes.
- One existing-service invoice access token generated with process-local30-minute
  TTL for browser acceptance, no email. Access URL and customer PDF retained only
  in private0600 local files, omitted from committed evidence and final links.
- Rollback baseline Web/Worker source`17608d10`; rollback triggers are broken
  invoice page/PDF, cross-shop link, incorrect totals, failed readiness or provider
  delivery regression. None observed so far. No rollback executed.

Live browser acceptance: parent agent used CUA to render the actual token-resolved
paid cash invoice`TPS-828ACD84-000018`, displayed cash total$252.70 and footer
“Share your experience” / “Leave a review” with exact supplied URL in browser
accessibility state. No payment interaction. Live screenshot capture timed out
after successful visible/AX acceptance; the fictional exact-URL invoice preview
already shown to the user remains separate, not represented as a live screenshot.

DB-149 product acceptance is complete: merged, deployed, configured and verified.
This focused documentation receipt follows on its own branch/PR; it introduces no
product behavior or production mutation. No remaining product blocker.
