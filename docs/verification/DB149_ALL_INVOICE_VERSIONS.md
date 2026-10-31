# DB149 all invoice versions — preview only (2026-10-31)

Owner: Backend & Integrations. Branch codex/invoice-spacing-qr, draft PR721. User requests preview approval before deployment. No merge or deployment in this follow-up.

Shared read-only payment_summary now drives current staff/guest invoice detail, all three PDF generators (including paid email and fleet exports), and newly rendered issued/paid emails. Native/reconciled settlement projection owns principal balance: principal_total - confirmed_principal; pending is displayed separately and never deducted. Confirmed may include credits, so label payments / credits applied. Legacy paid baselines preserve balance0 but omit unknown tender. Refunded or contradictory legacy evidence remains unknown. Actual cash receipt amounts overlay every PDF generator consistently. Existing messages/downloads remain historical copies.

Checks: payment summary/review/export/access suites57/57; invoice creation, line/snapshot and reminder-race regressions9/9. Actual guest/staff response partial-payment equality tested against isolated database: invoice100, completed40, due60. Zero write-state on read-only loader asserted. Negative tests cover bad currency, negative/NaN, wrong tenant/invoice, refunded or linked legacy evidence, real reconciliation vocabulary. Original21 PDF/QR tests retained. Parent owns frontend tests and visual previews; fresh independent reviewer checks implementation after corrections.

Local runtime preflight remains blocked: missing approved backend configuration and existing unrelated local service preserved. No configured full-stack or production verification claimed for this preview. No provider call, payment write, message send, schema or dependency change.

## Parent integration and previews

Shared frontend summary now drives guest/portal state and balances, uses refreshed settlement data consistently, preserves unknown historical tender and fee/refund notes, and suppresses cancelled/unknown payment UI. Focused frontend13/13, TypeScript/Vite production build and changed-source ESLint pass. Independent fresh invoice_versions_review reviewed final backend57/57 + frontend13/13 and returned offline QA/security GO with no remaining P0-P2 findings. Final label-only change names cancelled header Invoice status and removes cancelled receipt promise.

Seven fictional one-page PDFs generated: paid, unpaid, partially paid, payment awaiting confirmation, cash, overdue, cancelled. All visually inspected with Poppler PNGs; combined7-page review copy under local output/pdf/invoice-versions/all-invoice-versions.pdf. Current QR generation unchanged from exact-URL scan pass. Browser synthetic actual-component checks at390px portal partial and guest pending verify400applied/600due versus400pending/1000due;1280px cancelled has no payment controls. These are fixture checks, not configured full-stack acceptance; missing approved backend environment remains unchanged. No production changes, invoice mutations or messages. Temporary fixture server4179 and browser stopped after checks.

User explicitly requested review before deployment; draft PR721 remains unmerged. Current portal/downloaded PDF can update with payment changes; previously emailed/downloaded copies remain historical snapshots.
