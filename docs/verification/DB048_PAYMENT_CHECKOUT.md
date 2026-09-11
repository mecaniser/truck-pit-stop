# DB-048 payment checkout restoration

Owner: root; backend implementation pending_attempt_trace; independent gate
tax_exemption_gate. Base cbea6e2a, branch codex/db048-payment-checkout.
Contract: ../contracts/db048-payment-checkout.md.

## Observed defect

Read-only production inspection found eight unrelated imported invoices without
matching settlement projections. The tenant-wide readiness scan hid all noncash
tenders on the already-reconciled target. No production rows were changed.

## Implementation and gates

- Staff sees card, Zelle, Check and ACH even when genuinely blocked, plus inline
  full-only Cash where the server exposes the cash contract. Availability remains
  server-controlled and denial reasons remain visible. No Fleet Check/Code
  mapping or canonical schema expansion is included.
- Invoice totals show services/parts, discount when present, supplies, principal
  sales tax, and principal total. Read-only quote calculates selected payment
  principal, card fee and fee tax, total to collect and remaining invoice balance.
- Quotes bind invoice/version/rail/amount; stale, loading and failed quotes block
  submission. Amount edits debounce reads; selecting a tender never creates an
  attempt. Tax exemption editing pauses submission but not tender selection.
- Cash retains exact full-only, local receipt, no export and no mixing rules.
  Exemption remains separately applied and audited; it is never inferred from
  cash selection. Financial submissions were not exercised in production.
- Initial independent gate caught predecessor legacy-payment omission in scoped
  readiness. Returned to Backend for tenant-safe ancestry correction and fresh
  quote/actual-attempt negative tests. Final gate is required on successor SHA.
- Frontend focused suite: 56 tests passed, TypeScript and changed-source ESLint
  passed. Backend baseline affected suite184 passed and focused checkout21 passed;
  successor ancestry results will be recorded at final gate.
- In-app browser isolated fixture: desktop full-card, Zelle zero fee, partial
  card100 + fee3 + fee-tax0.25, full cash, exemption apply/cancel and tender
  switching passed. Example tax exemption reduces1160.49 to1072.05, preserves
  supplies24.00 and shows zero tax/card fee on cash. These are synthetic fixtures,
  not provider fee claims or production financial execution.
- Mobile390x844: five tenders remain visible,52px controls, no horizontal
  overflow (scrollWidth390). Local screenshots output/checkout/. Viewport reset.

## Release boundary

No migration or worker/write-policy change. Historical holds, pending reservation,
stored financial history, tax exemptions and activation settings remain intact.
Release through focused PR/protected CI, then verify deployment SHA, authenticated
target selector and quotes without pressing financial actions. Roll back to
cbea6e2a if checkout admission, quote integrity or service health regresses.
Not yet marked released; final gate/PR/deploy evidence follows below.
