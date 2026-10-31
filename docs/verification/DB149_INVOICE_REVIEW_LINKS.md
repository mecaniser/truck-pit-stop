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
