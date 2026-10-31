# DB149 all invoice versions — preview only (2026-10-31)

Owner: Backend & Integrations. Branch codex/invoice-spacing-qr, draft PR721. User requests preview approval before deployment. No merge or deployment in this follow-up.

Shared read-only payment_summary now drives current staff/guest invoice detail, all three PDF generators (including paid email and fleet exports), and newly rendered issued/paid emails. Native/reconciled settlement projection owns principal balance: principal_total - confirmed_principal; pending is displayed separately and never deducted. Confirmed may include credits, so label payments / credits applied. Legacy paid baselines preserve balance0 but omit unknown tender. Refunded or contradictory legacy evidence remains unknown. Actual cash receipt amounts overlay every PDF generator consistently. Existing messages/downloads remain historical copies.

Checks: payment summary/review/export/access suites57/57; invoice creation, line/snapshot and reminder-race regressions9/9. Actual guest/staff response partial-payment equality tested against isolated database: invoice100, completed40, due60. Zero write-state on read-only loader asserted. Negative tests cover bad currency, negative/NaN, wrong tenant/invoice, refunded or linked legacy evidence, real reconciliation vocabulary. Original21 PDF/QR tests retained. Parent owns frontend tests and visual previews; fresh independent reviewer checks implementation after corrections.

Local runtime preflight remains blocked: missing approved backend configuration and existing unrelated local service preserved. No configured full-stack or production verification claimed for this preview. No provider call, payment write, message send, schema or dependency change.
