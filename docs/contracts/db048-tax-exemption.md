# DB-048: staff invoice tax exemption before payment

Owner: Backend & Integrations; Frontend owns the control above tender selection.
Architecture contract v1, 2026-09-11, baseline e569890c. Independent QA/Security
review the integrated candidate. No production data mutation is authorized here.

## Outcome and boundary

Staff can apply a one-time invoice-level sales-tax exemption, with a reason and
supporting reference, before collecting payment. It is independent of tender:
cash does not imply exemption, exemption does not select cash, and supplies are
never removed. Staff attests applicability; the application does not decide legal
eligibility or validate an exemption certificate. Reference is text, not an upload.
Reversal/editing of an applied exemption is outside v1.

## API contract

Add `tax_exemption` to `InvoiceSettlementSummary` (and matching frontend types):

```text
{
  applied: boolean,
  can_apply: boolean,
  unavailable_reason: string | null,
  current_tax_amount: Money,
  removed_tax_amount: Money,
  exempt_principal_total: Money,
  reason: string | null,
  support_reference: string | null
}
```

Use Decimal/money strings, not browser arithmetic. Reason/reference are exposed
only to authorized staff; customer/guest summaries receive null. `can_apply` is
false outside authorized staff. All fields default safely for older fixtures.

`POST /api/v1/payments/invoices/{invoice_id}/tax-exemption`, Idempotency-Key:

```text
{ expected_settlement_version: integer >= 1,
  reason: trimmed string length 3..500,
  support_reference: trimmed string length 1..255 }
```

Response: updated canonical `InvoiceSettlementSummary`. Reuse existing tenant
and invoice resolution and money permissions; allow GARAGE_OWNER, GARAGE_ADMIN,
with payments permission (not receptionist). Customer, guest, foreign/deleted/missing
targets get existing generic denial. Validation errors 422; stale version 409
with current_version; conflicting idempotency 409; other guards 409 with stable
`tax_exemption_unavailable` and specific safe explanation. No new public/guest
mutation route. A replay of the exact persisted idempotency key/request hash
returns the current canonical summary without changing timestamps or versions;
an already-applied exemption with another request is rejected.

## Data, money and audit

One additive nullable JSONB `invoices.tax_exemption` column, existing rows null;
next migration after 142 (verify current head before naming). It records schema
`invoice-tax-exemption-v1`, tenant/invoice IDs, UTC applied_at, actor ID/name/role,
reason, support_reference, idempotency_key, canonical request_hash, before/after
invoice money snapshots, and before/after settlement version. A single application
is immutable through supported APIs; do not expose this JSON as a generic update
field. No new table, provider object, payment or payment-ledger event is needed.
Payment-ledger history must not be invented for a pre-payment invoice adjustment:
cash currently interprets any such event as existing payment activity.

Set `tax_amount = 0` and `total_amount = old_total - old_tax`, Decimal cents.
Keep subtotal, shop_supplies_amount, service_fee_amount, discount_amount, line
snapshots and all fee configurations unchanged. This removes the invoice's
existing sales tax, including its surcharge tax portion, but not the surcharge.
Reject inconsistent/negative snapshots rather than clamping. Recompute existing
settlement principal_total, max_card_fee, max_card_fee_tax,
sales_tax_rate_snapshot and card_fee_rate_snapshot with `invoice_money_snapshot`;
bump settlement.version once. Do not change accounting composition, provider or
realm binding, event sequence, receipt amounts or invoice/order status.

Example: total232.48, existing tax17.72, fee7.26, supplies6.00 => total214.76,
tax0, fee7.26, supplies6.00. New principal207.50 and fee tax0. Exact amounts come
from stored invoice facts, not this illustrative example or current tenant rates.

## Eligibility and serialization

Require active billable external invoice SENT/OVERDUE, positive stored tax,
unpaid positive coherent total, healthy tenant/order/customer. Merely already
issued/sent or imported is not a denial. Existing historical_export_hold,
cash_export_review_required and sandbox export reviews remain unchanged and
independently govern collection/export; do not clear them to apply exemption.

Under the existing settlement -> invoice policy serialization locks, refresh all
facts and check expected settlement version. Reject any current-invoice attempt
(including failed/expired), payment, accounting link, credit/refund/dispute,
settlement financial/ledger activity or pending Zelle. Inspect the complete
same-tenant supersedes ancestry: unresolved pending/received money or provider
facts block adjustment; missing/cyclic/foreign ancestry fails closed. Proven
no-money failed ancestry is not itself a reason to rewrite historical records.

Reject QBO invoice ID/synced timestamp, succeeded export/provider object, active
export lease/processing or unverified dispatched export outcome. Pure pending,
deferred/suppressed no-dispatch exports may remain, untouched. Valid existing
sandbox-only reviews may retain their separate proof, but any fingerprint tied
to old invoice money becomes stale and must be reported as requiring fresh review;
never silently regenerate administrative attestation. Do not automatically push
tax edits into an already-exported QBO invoice, void it, or create a replacement.

Use the same lock boundary as payment creation, cash confirmation and exports;
refresh after locking so concurrent payment/tax requests cannot use old money.
Two concurrent exemption applications have one winner. Never alter an attempt's
immutable amount to accommodate a tax change.

## Integration seams

- Model: backend/app/db/models/invoice.py; additive Alembic migration.
- Service: focused invoice_tax_exemption.py using invoice_accounting_policy's
  locked_policy and invoice_settlement_service's invoice_money_snapshot.
- Schema/routes: schemas/invoice_settlement.py, endpoints/invoice_settlements.py.
- Summary projection: canonical settlement_summary; avoid duplicating eligibility.
- Invoice detail/list read models and emitted PDF/email totals must reflect the
  updated stored invoice values; include a plain Tax exempt label where existing
  invoice tax display would otherwise imply merely missing tax. Keep supporting
  reference private to staff. Verify existing database projection triggers handle
  the new invoice money update; do not leave cached pre-exemption totals.
- Frontend: features/payments/{types.ts,api.ts,StaffSettlementDialog.tsx} and a
  focused control after the settlement summary and before tender selection.
- On success invalidate settlement, allocations, invoice and repair-order query
  owners; show authoritative new total before any next payment. No automatic
  charge, receipt, cash confirmation, close, or tender selection.
- Existing QBO gross writer derives principal/fee tax from settlement. Test an
  exempt future noncash receipt emits zero tax, preserves supplies/fee, and never
  restores tenant default tax. Existing local cash continues provider-write-free.

## Acceptance and negative tests

1. Exact tax-only delta, supplies/fee/discount retained, zero tax snapshots,
   version increment, persistent immutable audit and accurate reloaded totals.
2. Same tax decision for card/check/ACH/Zelle/cash; no tender implied; applying
   exemption alone leaves invoice unpaid and creates no receipt/provider work.
3. Trim/required/length validation; no reason/reference in guest/customer views.
4. Tenant/role/permission negatives; internal/cancelled/voided/paid/partial-paid,
   pending Zelle/card/manual, received ancestry and inconsistent money denied.
5. Same-key replay, changed payload conflict, duplicate apply, stale version,
   true PostgreSQL payment/exemption and exemption/exemption serialization.
6. QBO linked/succeeded/processing/ambiguous export denied; untouched historical
   holds and existing export events; stale administrative fingerprints fail safe.
7. Cash and future noncash/QBO payload regression; no default tax reintroduced.
8. Desktop/mobile control labels, keyboard, save pending/error/retry, updated
   totals and unchanged tender availability. Root owns browser acceptance.

Production migration/deployment and applying this control to a particular real
invoice are distinct from local implementation. No existing pending reservation
is released, and no production exemption is applied by this contract.
