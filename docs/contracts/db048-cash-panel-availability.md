# DB-048: truthful cash and non-cash payment-panel availability

Owner: Backend & Integrations owns all implementation and tests, including shared
frontend consumers. Architecture owns this contract; Product & Delivery owns the
board and release. Base: `89e66d40fc5b343ded763c2e0b9fbc4b885bce59`.

## User outcome

A historical-export-held invoice must not advertise a new non-cash payment that
the server will reject. Cash remains a separate full-payment option governed by
its existing eligibility checks. This change does not clear historical evidence,
authorize a cash receipt, or release any export hold.

No migration, activation, provider write, money/reservation change, fee change,
new payment method, history clearance or unrelated settings redesign.

## Additive shared DTO

Add to `SettlementAllowedActions` and its shared frontend type:

`payment_unavailable_reason: string | null = null`

This is an explanation for invoice-level non-cash unavailability, not provider
readiness, a cash-denial reason, or an instruction to change connection settings.
Existing clients may ignore it. Missing/null values preserve previous behavior.

`settlement_summary` must use the actual invoice policy, loading the invoice with
the settlement's exact invoice and tenant identity. Keep endpoint authorization
and tenant-safe not-found semantics; never read another tenant's invoice policy
or disclose it through a reason. Share this projection across staff, portal,
guest and attempt-response consumers rather than implementing audience-specific
eligibility independently in the browser.

## Historical hold projection

When invoice policy is `historical_export_hold`, override only these actions:

| Field | Value |
|---|---|
| `create_attempt` | false |
| `rails` | [] |
| `confirm_manual` | false |
| `apply_customer_credit` | false |
| `retry_accounting` | false |

Staff explanation:
> Non-cash payments are paused for this historical invoice until accounting review is complete.

Customer and guest explanation:
> Payment is unavailable for this invoice. Please contact the shop.

Do not disclose provider realm IDs, internal holds, raw errors or investigation
details to customer/guest audiences. Preserve existing role permissions for
`configure_provider`, `authorize_early_release`, and `resolve_overpayment`; this
item does not invent new refund restrictions or alter prior money facts.

Compute `confirm_cash` and `cash_unavailable_reason` independently using the
existing `cash_staff` and `cash_eligibility` checks. A historical hold alone is
NOT a cash denial. Existing actual payment activity, ambiguous export evidence,
QBO linkage, invoice lifecycle or insufficient permission may still deny cash,
and must retain their existing accurate explanation. Local-cash settled invoices
retain their current all-payment-actions-disabled projection.

Standard-policy invoices retain normal readiness/amount/role-driven non-cash
actions, with null `payment_unavailable_reason`. Do not hide ordinary card/Zelle/
check/ACH choices as a side effect of fixing held invoices.

## Existing UI controls

When non-cash creation is unavailable with the new reason, replace the misleading
new-payment amount/tender/Continue controls with the audience-appropriate reason.
Do not retain a selected card provider or enabled submit/credit/retry action that
contradicts `allowed_actions`. Preserve the cash card and its independent eligible
or unavailable state, settlement totals, existing payment history and unrelated
permitted controls. Customer/guest pages never offer staff-only cash confirmation.

Use the server projection, not frontend guesses from invoice status, invoice
number, age, shop identity or provider connection health. If availability changes
after rendering, existing server guards remain authoritative and the response
must refresh the displayed state. Do not weaken mutation guards to match stale UI.

## Acceptance and negative cases

- Staff held invoice with clean cash eligibility: non-cash/credit/retry disabled,
  specific reason visible, full-cash action still available.
- Held invoice with ambiguous export or pending/historical payment activity:
  non-cash disabled, cash denied by its genuine existing reason; no mutation.
- Customer/guest held invoice: generic contact-shop message, no new card/Zelle
  submission, no internal accounting reason or cash confirmation action.
- Standard unpaid invoice: existing rails and amount/Continue behavior unchanged;
  standard unavailable/readiness states preserve their existing explanations.
- Existing local-cash receipt: no accidental re-enabled payment/credit/retry.
- Permission-limited staff and other-tenant invoice: no action or data leakage.
- Shared summary/attempt responses and all three UI audiences consume the same
  additive DTO correctly, including null/missing compatibility.
- Direct/stale-client attempt, manual-confirmation, credit and accounting-retry
  requests still encounter the existing hold enforcement with no provider call.
- Focused tests prove rendering plus server projection; read-only signed-in live
  acceptance never presses a financial confirmation or creates a payment attempt.

Independent QA/Security review the exact change because this is payment-action
presentation. Protected CI and deployed read-only panel evidence complete this
bounded correction; historical cash-clearance investigation remains separate.
