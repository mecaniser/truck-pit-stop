# DB-048 owner-attested historical cash review

Owner: Backend & Integrations. Architecture owns this contract. Independent
Security and QA approve the exact implementation before release.

## Outcome

An exact historical invoice may become eligible for the existing full local
cash action when the shop owner explicitly attests that no provider payment
occurred and the transaction was cash. This is an owner risk acceptance, not
provider verification. It never records a receipt, clears history, or writes to
QuickBooks. Cash confirmation remains a separate staff action.

## Durable review

Reviewed operator tooling adds only `cash_owner_attestation_review` to the exact
held replacement invoice's ambiguous invoice-sync outbox payload. The marker binds
its tenant, invoice, current invoice digest, event, status, attempt count, original
event digest, exact replacement chain, and complete financial snapshots of every
ancestor. It records the normalized statement
`no_provider_payment_cash_received`, the attestation source, reviewer, timestamp,
and `provider_verified: false`.

The event digest excludes only ordinary `updated_at` metadata and the two trusted
review marker keys. Any original payload, status, lease, provider ID, attempt
count, invoice, settlement, attempt, payment, ledger, accounting, refund, credit,
provider-settlement, or ancestry drift invalidates the review.

The marker is installed only through an exact manifest plus reviewed SHA-256;
payment request DTOs cannot supply it. Conflicting metadata cannot be overwritten.

## Eligibility boundary

All existing active-invoice, staff permission, same-tenant, full-positive-balance,
idempotency, version, no-mixing, no-Zelle-pending, and no-current-payment-history
checks remain. The exception requires `historical_export_hold`, a replacement
ancestor, and an exact `cash_export_ambiguous` QuickBooks invoice-sync outbox
event. An owner review can resolve only that historical ambiguity and the exact
ancestor evidence it snapshots.

An ancestor snapshot is eligible only when there is no received/applied money,
payment, accounting link, refund, credit, overpayment, or provider settlement;
no submitted Zelle reservation;
all attempts are terminal failed/expired with no provider transaction identity;
the settlement has zero confirmed, pending, credit, and refund amounts; ledger
events are limited to creation and terminal failure/expiry for those attempts;
and no financial outbox event is processing, leased, succeeded, or provider-bound.
The explicit `owner_attested_no_card_payment` terminal code is required for every
historical attempt.

Unlike independently verified sandbox review, owner attestation does not trigger
or masquerade as a production provider absence lookup. The original export holds,
errors, ambiguity flags, and history remain. Only a later successful full-cash
confirmation converts the active invoice to local-cash-only and suppresses its
export event under the existing serialized transaction.

## Checkout presentation

The API continues returning separate `card_fee_amount` and
`card_fee_tax_amount` values for immutable accounting. Staff checkout displays
their sum as one `Card processing fee` line and keeps `Amount to collect`
unchanged. Noncard tenders remain fee-free.
