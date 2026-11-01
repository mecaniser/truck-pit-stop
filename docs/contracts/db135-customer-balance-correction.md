# DB-135 customer overview balance correction

Owner: Backend & Integrations. High-risk financial read-path correction; no writer, schema migration, provider call or source-record reconciliation.

## Response contract

Existing `balance` remains a decimal on CustomerResponse and VehicleResponse. It now means the current native principal balance, not the mixed-source invoice/payment subtraction. Additive `legacy_ets_balance` is the imported recorded remainder, separate from current debt and explicitly not an attestation of collectibility. Account classification/verification remains the separate Account projection; an operational zero does not claim all historical evidence is reconciled.

`Invoice.source == easy_truck_shop_import` or `accounting_policy == historical_export_hold` identifies historical rows. A native replacement with null invoice source stays native even when its repair order or invoice number came from ETS. No prefix heuristic. Legacy rows without an explicit import source are not reclassified by this correction.

Cancelled, voided and soft-deleted invoices contribute neither amount. Draft and internal native invoices contribute zero. Soft-deleted payments are ignored. Paid native invoices contribute zero. Unpaid native invoices use a valid USD, nondeleted, native/reconciled settlement matching invoice, customer, tenant and canonical principal, with confirmed principal within bounds. Otherwise fall back to canonical principal (total minus optional card fee and proportional fee tax) minus completed same-tenant payments. Clamp per invoice at zero: overpayment is not silently applied to other invoices. Pending, failed and refunded payment records do not reduce debt. Existing account credit ledger behavior is unchanged.

Historical ETS remainder uses invoice total less completed same-tenant payments, clamped per invoice, including historical paid-status discrepancies as recorded evidence rather than fabricating payment receipts.

## Read surfaces and boundaries

List, detail, edit response, customer-role profile, equipment list and balance sorting use the same live SQL expressions. Legacy CustomerReadModel money columns are bypassed; its vehicle metadata remains in use. Queries aggregate the bounded requested customer page or equipment page in one SQL request, no application N+1. Sorting uses the same correlated expression. Invoice/order/customer tenant identities must agree; payment and settlement identity must match the invoice tenant. Financial attribution uses immutable invoice billed_customer_id, falling back to repair-order customer only when the snapshot is absent. Equipment totals use that same bill-to identity, preserving prior-owner isolation.

No endpoint permissions or mutation semantics change. New decimal field defaults to zero for compatibility. Financial unknown/classification warnings on Account stay intact; frontend must label this native/current balance and historical ETS separately, not verified collectible.

## Acceptance

Paid cash fee residual zero; optional fee/tax excluded from unpaid principal; valid partial settlement uses confirmed principal rather than gross card payment; pending/failed/refunded not counted; cancelled ignored; historical separated; native replacement retained; overpayment cannot offset another invoice; cross-tenant payment and wrong-customer settlement ignored; list projection and sort equal detail/equipment amounts. Independent QA/security and release evidence required before Done.
