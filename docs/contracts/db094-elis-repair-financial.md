# DB-094 current repair financial manifest and wakeups

Development implementation; no deployment, production grants, credentials or financial changes. This extends the operational-history contract without turning current RO ownership into invoice authorization.

## Complete current-invoice manifest

`GET /api/v1/fleet-invoice-exports/repair-orders/financial` requires the existing active customer-scoped `X-API-Key`. Same-shop active customer, tenant, RO and vehicle boundaries apply. Eligible operational ROs are completed/invoiced/paid, not internal/deleted. Unknown query parameters fail422. The single joined snapshot is bounded at1000; oversized or ambiguous current rows fail409, never partial success.

Envelope exact fields: `version` (`db094-repair-financial-v1`), `shop_id`, `customer_id`, `complete:true`, `count`, `snapshot_id`, `items`.

Row exact fields: `repair_order_id`, `order_number`, `vehicle_id`, `vin`, `unit_number`, `description`, `work_completed_at` (UTC or null), `service_date` (UTC completion date only or null), `authorization`, `invoice`, `revision`.

The unique noncancelled invoice is current, including a draft. Draft yields `not_finalized`; absent/internal/deleted/voided current invoice yields `unavailable`. Do not choose an older visible invoice or cancelled predecessor. Missing immutable bill-to or owner-reviewed historical grant yields `attribution_required`. These blocked rows have `invoice:null`: no financial invoice ID, number, date, amount, line or document metadata is disclosed.

An `authorized` row uses the same invoice/PDF bill-to rule: immutable billed_customer_id matches, or it is null and a same-tenant existing historical mapping matches the target customer. No new grant or ETS exception is implemented here.

Authorized invoice fields: `invoice_id`, `revision`, `invoice_number`, `status:'current_finalized'`, `invoice_date`, `invoice_date_basis`, `currency:'USD'`, `total_amount` decimal string, `line_items` retail labor/parts, `pdf_sha256` nullable. Native issuance uses invoice creation timestamp; an ETS import uses preserved ets_invoiced_at only, otherwise unknown/null. Import timestamps never fabricate an original ETS issue date. Completion date remains preferred by EDG. The manifest does not render PDFs or mutate snapshots. No preserved PDF binder currently exists, so pdf_sha256 is null. The existing scoped PDF route remains the document-access boundary.

Line projection excludes internal unit costs, mechanic/supplier IDs, notes, contact fields and arbitrary snapshot keys. Financial invoice revision hashes only canonical invoice fields, excluding itself. Source payment workflow status, paid_at and updated_at cannot change that financial revision or imply an EDG payment. Row revision excludes itself. Snapshot hash covers exactly version/shop_id/customer_id/items, including row revisions. All SHA256 use sorted compact ASCII-escaped JSON encoded UTF-8.

## Durable notification

Invoice manual/automatic finalization, patch, void, audited tax/charge changes, supported RO description/status changes and completion workflow enqueue `ProviderOutboxEvent` type `fleet.financial.wakeup.v1` in the same outer transaction. Existing provider_outbox table/string event type requires no migration. Capture requires an explicit exact shop/customer destination and an active scoped customer key. Attribution-required invoices do not enqueue. Outbox idempotency includes invoice, customer, kind and source revision; one customer cannot reuse another customer's event identity.

Body exact fields: `{version:'db094-financial-wakeup-v1',event_id,shop_id,customer_id,repair_order_id,kind,occurred_at}`. Kind is invoice_finalized/invoice_changed/invoice_cancelled. No invoice amount, invoice ID, payment status, contact, description or credential is sent. It only wakes EDG to refetch the complete authorized manifest.

Server-managed `DIESELBRIDGE_FLEET_WEBHOOKS` is a JSON array of exact `{shop_id,customer_id,url,secret_env}`. URL must be HTTPS with no credentials/query/fragment and exact receiver route `/api/v1/accounting/dieselbridge/webhooks/{slug}`. `secret_env` references a separately approved signing secret of at least32 characters, never the fleet read key. No configuration/secret has been generated or installed.

A dedicated `process_fleet_financial_wakeups` Celery task runs every10seconds, separately from email delivery, and is a no-op unless `DIESELBRIDGE_FLEET_WEBHOOK_DELIVERY_ENABLED=true`. It processes at most one delivery per task (25second network budget within45second soft limit), leases/commits before I/O, verifies active source scope and configuration before sending, pins vetted public DNS addresses while retaining Host/TLS SNI, disables redirects/proxy environment, bounds time/body and checks lease tokens before completion. Signature headers: X-DBN-Event-Id equals bodyID; X-DBN-Timestamp Unix seconds; X-DBN-Signature `v1=` + HMAC-SHA256(secret, timestamp + '.' + rawbody). Canonical body remains byte-identical across retries; timestamps/signatures are fresh.

Missing configuration/secret/active scope pauses without spending attempts. Paused rows back off60seconds so they do not starve configured customers. Receiver503 is retained pending, also without spending attempts. Other retryable429/5xx/network failures use exponential retry up to12 attempts, then retain a dead event for operator review. Redirects and forbidden/private DNS fail closed. Worker crashes recover via60second lease; stale completions cannot acknowledge a newer lease. No network request or invoice mutation occurs on manifest reads.

## Verification

TDD observed404 RED before source manifest implementation; real invoice-patch outbox count0 RED before capture; existing provider worker succeeded0 RED before signed delivery; cross-tenant mapping and cross-customer idempotency regressions separately RED then GREEN. Focused tests cover15RO/7authorized/8blocked, draft/hidden current nofallback, hashes/privacy/paid-status neutrality, missing dates, revocation, atomic capture/rollback, finalization/void, charge changes, signatures, public DNS pinning/private DNS denial, redirects,503pause, retries, disabled config, lease races and scoped idempotency. Independent gates and any production rollout remain outstanding.

RO correction identity includes completion date/description/status and invoice financial facts, not only invoice.updated_at, so RO-only or same-clock-tick charge changes produce a new wakeup. The existing RepairOrderUpdate API does not expose a work_completed_at edit field; no new date-edit API was added. Completion workflow changes and supported RO edits notify transactionally. Direct administrative database date correction outside these application paths requires a manual complete-manifest sync; consumer must compare rowrevision as well as invoice revision and preserve accepted cost/date for review.

## Settlement-aware manifest v2 — locked Architecture contract (2026-10-30)

This section supersedes the v1 amount/revision rules above. The endpoint and customer/key authorization are unchanged; the envelope version is now `db094-repair-financial-v2`. Financial rollout remains disabled and undeployed. A v1 consumer rejects v2 safely; a v2 consumer rejects v1 rather than treating missing fee facts as zero. Coordinate release; do not silently downgrade. Existing accepted v1 costs remain immutable until reviewed migration/correction, with no automatic replacement.

Invoice `total_amount` remains the original stored quote, including its maximum conditional card surcharge. It is not automatically the cash obligation or a payment. Add exact `breakdown:{subtotal,shop_supplies_amount,service_fee_amount,tax_amount,discount_amount}` to the authorized invoice object, using nonnegative two-decimal USD strings. Stored service_fee_amount means the maximum card-processing surcharge, not a verified earned fee. Preserve all existing invoice identity/date/retail-line fields.

Add exact nullable `settlement` to each row, alongside invoice. Non-authorized rows have **both invoice:null and settlement:null**; no attempt IDs, settlement IDs, methods, dates or amounts leak from blocked8. Authorized missing settlement yields null, never an invented paid/unpaid aggregate. Available source settlement shape (all keys required):

```json
{
  "settlement_id":"uuid",
  "revision":"sha256",
  "status":"available",
  "review_reasons":[],
  "source_state":"partially_paid",
  "principal_total":"1000.00",
  "max_card_fee":"35.00",
  "max_card_fee_tax":"0.00",
  "confirmed_principal":"400.00",
  "pending_principal":"0.00",
  "unapplied_credit":"0.00",
  "refund_pending":"0.00",
  "payments":[{
    "attempt_id":"uuid",
    "revision":"sha256",
    "rail":"cash",
    "state":"confirmed",
    "principal_amount":"400.00",
    "received_amount":"400.00",
    "gross_received_amount":"400.00",
    "applied_principal_amount":"400.00",
    "applied_card_fee_amount":"0.00",
    "applied_card_fee_tax_amount":"0.00",
    "unapplied_amount":"0.00",
    "confirmed_at":"2026-09-13T00:14:37+00:00",
    "actual_paid_date":null,
    "paid_date_basis":"unknown"
  }]
}
```

`status`: available|review_required. `source_state` is the bounded existing settlement state (unpaid, payment_pending, partially_paid, partially_paid_pending, paid, overpayment_resolution); it never changes EDG payment status. Rail: cash|card|zelle|check|ach|fleet_payment. Attempt state: pending|confirmed|failed|expired|refunded|reversed. Payment order is deterministic by attempt_id; uniqueness and exact invoice/settlement/customer/tenant identities are enforced before serialization. All attempts for this invoice, including reversals/refunds/failed/pending, are retained; never filter them to fabricate a clean paid aggregate. Bound each invoice at1000 attempts and the complete joined materialization at10000 rows; fail the complete manifest409 if either is exceeded. Return no provider account/charge/reference, manual_evidence, customer/contact/actor data, internal processor expenses or credential fields.

`confirmed_at` is only the source's recorded confirmation timestamp. `actual_paid_date` is nullable and currently **null** because existing confirmation/creation timestamps do not independently establish cash handover or actual transaction date. `paid_date_basis` is unknown unless a future explicitly verified actual-date field is supported; never derive it from confirmed_at, paid_at or created_at. `received_amount` is the source received-principal field, not gross cash/card charge. Add required `gross_received_amount`: confirmed/refunded/reversed card attempts use stored provider_charge_amount; confirmed/refunded/reversed non-card attempts use received_amount; pending/failed/expired attempts have gross_received_amount:null. For a reversed/refunded record this preserves its historical charge, not a current paid balance or refund amount. All received/gross/applied amounts are observed facts, not new EDG payments. Pending attempts retain received_amount:null and zero applied facts; missing received/gross amount on a confirmed attempt requires review.

Source `status:review_required` and explicit stable `review_reasons` cover unsupported/contradictory money, source reversals/refunds, positive unapplied credit or refund_pending, mismatch of canonical principal/maximum fee snapshot, confirmed-principal sum mismatch, attempt-state/allocation inconsistency, non-card actual card fees, actual fees exceeding maxima. Valid cash-plus-sales-tax source facts remain intact; the consumer separately flags this owner's cash tax-policy conflict rather than changing source tax or claiming the source arithmetic is inconsistent. Never subtract unknown tax or reconstruct missing refund allocations. Do not mutate source to make it consistent. Invalid wire types/currencies/hashes remain consumer502; valid but financially uncertain observations are review-blocked rather than guessed.

Validation invariants: invoice subtotal + supplies + maximum surcharge + tax − discount equals stored invoice total; canonical settlement principal + max_card_fee + max_card_fee_tax equals stored invoice total; max_card_fee equals stored service_fee_amount; confirmed_principal equals sum applied_principal_amount of confirmed attempts; confirmed total and pending do not exceed principal; each confirmed gross_received_amount equals applied principal + applied card fee + applied card-fee tax + unapplied amount, while received_amount is at least applied_principal_amount. Non-card fee components must be zero. Non-card cash received with positive tax is not silently restated tax-free. Unknown legacy payments with no trustworthy complete attempt history remain review_required. A settlement with zero attempts and zero confirmed amounts may still establish the full unpaid principal, provided the remaining snapshot invariants hold.

Independent digests: invoice revision hashes its quote/identity/date/lines/breakdown fields only, excluding revision. Each payment revision hashes its exact payment fields excluding revision; settlement revision hashes all settlement fields excluding revision and includes ordered payment revisions. Row revision hashes all row fields **except revision and settlement**. Snapshot digest continues to hash version/shop/customer/items including settlement. Thus payment-only updates change the settlement/snapshot revision, not the invoice/operational revision. Receiver must observe both independently. No timestamps for mere polling enter these digests.

Wakeups remain the signed amount-free v1 body. Settlement confirmation, partial payment, failure/reversal/refund and cash receipt transitions enqueue in the same transaction as the financial state change, using legacy kind invoice_changed only as a refetch wakeup. Outbox idempotency must include a canonical settlement/payment fingerprint as well as invoice/RO scope so payment-only changes cannot collapse into an earlier invoice wakeup. Authorization must still be checked before capture/delivery. No new key, grant, destination or signing secret is created.

### Consumer cost, payment and review rules

1. With an available consistent settlement, book the **full principal_total plus actual applied card fee and applied card-fee tax of confirmed attempts**, never the partial amount paid and never the maximum uncharged surcharge. Preserve raw invoice total, full principal, actual charged fees, proposed/booked cost, source confirmed/pending/remaining and EDG verified payment totals separately. Before any card payment the full principal is the obligation; a later actually charged card fee changes cost only through review. Fees on pending/failed/expired attempts are zero earned expense. Later fees must not add a second RO tile/bill.
2. With no settlement, raw invoice total is eligible only when the v2 breakdown proves service_fee_amount is exactly0 and the quote arithmetic is consistent. Otherwise require settlement evidence review; never infer a payment rail or remove a surcharge blindly. An invoice with source cash and nonzero tax conflicts with the owner's explicit no-sales-tax cash policy and remains blocked for evidenced correction/review. Do not globally strip tax from card or unclassified invoices.
3. Source settlement/payment facts are informational until existing EDG Finance independently verifies amount, actual date and funding. Source cash does not identify owner-personal versus business funds. Source confirmation timestamp is never an actual paid date. Import/sync itself creates zero payments/reserve withdrawals. Display source received/confirmed amounts and rail distinctly from EDG verified payments/balance; pending is never paid. The existing actual-date, original receipt/transaction, closed-period, tenant and remaining-obligation guards still apply.
4. Extend VerifiedRepairPayment with optional `source_attempt_id` and `source_attempt_revision`, supplied together or neither. A claim must bind the current available confirmed attempt on this exact source RO/customer/shop, reject stale/reversed/refunded/pending/unapplied facts, and equal the **whole gross_received_amount**, which must equal applied principal + actually applied fee/tax when unapplied_amount is0. No split claims in this implementation. Existing EDG proof/date/funding verification remains mandatory. At most one active claim per tenant/shop/source attempt, including concurrent requests; correction appends a full Finance/reserve reversal, preserves original source-reference history, and only then permits another valid claim. Never reset claim history or produce an automatic source-driven reversal.
5. Persist source payment observations and immutable observation evidence separately from the accepted invoice/cost and notes. On payment-only refresh with unchanged resolved cost and no claimed-attempt conflict, update observed source facts without rewriting the bill or entering a fake invoice-change review. If resolved cost changes, preserve the booked cost and require normal cost correction review. If a claimed source attempt changes or reverses/disappears, flag source-payment review, preserve EDG payment/reserve/journals, and block new projections until explicit correction. A source reversal is not an evidenced local bank refund/date. Revoked source access withholds current source facts while preserving the booked audit history.
6. Public financial state adds `source_invoice_total` (raw quote, existing field), `booked_cost`, `source_settlement` (latest authorized shape above or null), `source_payment_review_required:boolean`, and `source_payment_review_reasons:string[]`. Existing invoice_total remains booked/accepted cost for backwards-compatible tile behavior. Frontend labels quote/principal/actual fees/source confirmed/source pending separately, shows rail/gross_received_amount and received principal separately/status/recorded timestamp/actual-date unknown, and offers optional source-attempt linking within the existing verified-payment form. Do not prefill actual paid date from confirmation time or choose personal/business funding from source cash.

Acceptance fixtures: RO41 quote5057.40 / principal4886.38 / max fee171.02 / confirmed staff_cash4886.38 / actual fees0 produces one4886.38 cost and zero automatic reserve; full card1035 on1000 principal incurs35 actual fee; mixed partial card+cash preserves full principal plus only earned fees; pending/failed has no paid amount; missing/contradictory settlement, cash tax, source reversed/refunded and overpayment require review; exact replay/claimed-attempt concurrency cannot double-withdraw; no date/funding inference; unauthorized8 expose no new settlement facts. All production financial and historical reconciliation holds remain unchanged.
