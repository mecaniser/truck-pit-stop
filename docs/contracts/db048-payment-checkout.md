# DB-048 invoice-scoped checkout readiness and read-only quote

Architecture / Backend owner; root owns frontend and release. Baseline cbea6e2a.

## Scope

Checkout admission evaluates reconciliation for its invoice and every same-tenant
superseded predecessor, not unrelated tenant invoices. Missing/deleted/foreign or
cyclic ancestry fails closed. Any predecessor payment (including legacy Cash),
pending attempt/reservation, received money/provider identity or legacy Zelle
submission blocks replacement collection. Transactional admission locks and
refreshes the chain. Invoice-specific early release uses the same chain-scoped
readiness in both invoice and repair-order routes, retaining manager/business
guards. Provider configuration/settings/activation retain full-tenant readiness.
Verified tenant backfill, provider approval, identity, accounting mappings and
writer gates remain mandatory. Target missing/mismatched settlement, unreconciled
legacy payment or Zelle still fails closed. This does not repair/backfill invoices.
Existing invoice policy, reviewed ancestry, pending reservation, historical export
hold and confirmation safeguards are unchanged. No production record changes.

## Wire

Settlement summary adds optional `breakdown` with Money strings: `subtotal`,
`shop_supplies_amount`, `sales_tax_amount`, `discount_amount`, `principal_total`.
Subtotal is stored repair subtotal before separately stored discount; supplies
remain separate. Sales tax is principal tax (stored invoice tax less snapshotted
maximum card-fee tax); principal_total is authoritative settlement principal.
Do not subtract discount twice or include the card fee in principal.

Staff-only `GET /api/v1/payments/invoices/{id}/quote` takes required `rail`
(`card|zelle|check|ach|cash`), `principal_amount` (positive finite cents), and
`expected_settlement_version` (integer >=1). Response Money fields:
`settlement_version`, `rail`, `principal_amount`, `card_fee_amount`,
`card_fee_tax_amount`, `total_amount`.

Require authenticated payment-capable staff and active same-tenant invoice,
customer/order/tenant; customers and guests cannot use this staff endpoint.
Read existing settlement only, under settlement/invoice locks for a coherent
version. No lazy initialization, attempt, ledger, reservation, provider operation,
or commit. Card quote reuses `_card_fee_allocation`; noncard fees are zero.
Cash requires exact full allocatable principal and existing cash eligibility.
Other rails require invoice-scoped readiness and existing standard-payment policy.
Invalid amount/rail 422; stale version 409; unavailable/payment-policy failure409;
inaccessible/missing invoice or settlement404. Quote is advisory, not idempotent
financial execution: POST independently checks version and recalculates fees under
existing locks and existing Idempotency-Key contract.

Fleet Check / Code is legacy-only today; canonical rail and database constraint
exclude it. No mapping to another tender or migration is included in this patch.

## Acceptance

Unrelated missing tenant settlement leaves settings readiness red but does not
disable a reconciled target's admission; target mismatch/payment/Zelle remains
blocked, as do unverified backfill and provider configuration failures. Confirm
actual attempt creation, not just summary. Preserve tenant/auth, stale version,
duplicate request and pending/ancestor/export guards. Quote partial/full card
including cumulative fee rounding, noncard zero fees, full-only Cash, amount
limits, reference-free read-only behavior and exact breakdown. All selection and
quote reads must leave financial record counts and projections unchanged.
