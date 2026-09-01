# DB-048 Partial invoice payments, provider reconciliation, and customer credits

- Version: 1.0.6
- Status: Implementation reconciled; independent gates pending
- Accountable implementation owner: Backend & Integrations
- Contract owner: Architecture & API Contracts
- Branch: `codex/db048-partial-invoice-payments`
- Base: `6dbf8110dc92dc0b284bd0fca9b949378bda3603`
- Currency: USD only
- Delivery lane: High risk

Version 1.0.6 does not expand the frozen product scope. It preserves the 1.0.5
Security and accounting corrections and reconciles the verified distinction
between a production-disabled QBP gate and an explicitly authorized sandbox
with payment scope. QBP partial attempts now use direct Intuit tokenization and
an attempt-stable provider idempotency identity instead of silently falling
back to Stripe.

## 1. Product and accounting boundary

DB-048 adds partial and multi-tender settlement to repair invoices. It does not
change the repair-order workflow, invoice line-item snapshot, or invoice
revision/void authority.

The authorities are intentionally separate:

| Concern | Authority |
|---|---|
| Tender attempts, allocations, pending balances, operational audit, and customer-visible balance | DieselBridge |
| Card authorization, capture, refund, dispute, and settlement | The one tenant-selected approved card provider |
| Accounts receivable, accounting records, and CPA reporting | QuickBooks Online Accounting |
| Deposit verification | Bank-feed matching only; a bank feed never creates a payment or income entry |

Scope includes customer card and Zelle plus staff card, Zelle, check, and ACH.
It excludes cash, fleet instruments, external terminals, `other`, accounts
receivable terms, installment financing, counter sales, split card processors,
and unrelated UI work.

QuickBooks Payments production acceptance remains unresolved and its production
gate stays closed. An isolated sandbox may exercise the same provider-resolved
flow only when its environment gate is explicitly enabled and the connected
tenant satisfies the payment-scope and readiness contract below.

## 2. Canonical money model

All persisted money uses `NUMERIC(12,2)`, positive USD values, and `ROUND_HALF_UP`
at each named boundary. Floating-point values are prohibited.

### 2.1 Amount definitions

- `principal_total`: the invoice obligation without a card surcharge or tax on
  that surcharge. It includes repairs, shop supplies, invoice discounts, and
  the existing non-card sales-tax snapshot.
- `principal_amount`: the portion of one tender applied to the invoice.
- `card_fee_amount`: the existing tenant card-fee policy allocated only to a
  card-funded requested principal amount and frozen on the provider attempt.
- `card_fee_tax_amount`: the existing tax attributable only to that card fee.
- `applied_card_fee_amount` and `applied_card_fee_tax_amount`: the portions of
  the frozen surcharge actually earned by principal that still fits on the
  invoice when provider money is finalized.
- `provider_charge_amount`: `principal_amount + card_fee_amount +
  card_fee_tax_amount` for card; `principal_amount` for Zelle/check/ACH.
- `processor_fee_amount`: the provider's actual processing expense. It never
  reduces principal applied to the invoice.
- `confirmed_principal`: sum of confirmed, non-reversed principal allocations.
- `active_pending_principal`: sum of non-expired pending allocations.
- `outstanding_balance`: `max(principal_total - confirmed_principal, 0)`; this
  is the invoice A/R still open before subtracting temporary reservations.
- `allocatable_balance`: `max(principal_total - confirmed_principal -
  active_pending_principal, 0)`; this is the amount a new tender may currently
  reserve or pay.
- `unapplied_credit`: money received but not applied to invoice principal and
  not yet refunded.
- `refund_pending`: unapplied money for which a refund has been requested but
  is not final.

Card fee and fee tax are allocated pro rata from the invoice's frozen maximum
card surcharge snapshots. For principal allocation `P`:

```text
card_fee_amount = round(max_card_fee * P / principal_total, 2)
card_fee_tax_amount = round(max_card_fee_tax * P / principal_total, 2)
```

The final card allocation that exhausts principal receives any cumulative
one-cent rounding remainder, capped by the frozen maxima. A non-card allocation
receives zero card fee and zero fee tax. This preserves the current full-card
total while charging a mixed-tender customer only for the card-funded portion.

If a late or duplicate provider success arrives after the payable principal has
shrunk, the attempt retains its original charge snapshots, while only the
applied principal and applied surcharge are earned. The remaining received
principal, surcharge, and surcharge tax are unapplied customer money and follow
the exact-source refund-first policy in section 7.

The QBO Invoice total is `principal_total`. Each QBO Payment linked to that
invoice is `principal_amount`. Card fee, fee tax, provider fee, refund, dispute,
and payout entries are accounted for separately and cannot alter invoice A/R.

### 2.2 Settlement state

`Invoice.status` remains `draft | sent | overdue | paid | cancelled`.
Settlement is a separate projection:

- `unpaid`: no confirmed principal and no pending allocation;
- `payment_pending`: pending exists and confirmed principal is zero;
- `partially_paid`: confirmed principal is greater than zero and below total;
- `partially_paid_pending`: both confirmed and active pending principal exist;
- `paid`: confirmed principal equals principal total;
- `overpayment_resolution`: invoice is otherwise paid and unapplied or
  refund-pending money exists.

When confirmed principal first reaches `principal_total`, the invoice becomes
`paid`, `paid_at` is set once, the repair order follows its existing paid
transition, and the existing paid-invoice webhook is enqueued once. Pending
money and card fees never independently mark an invoice paid. A reversal or
dispute of applied principal reopens the settlement and invoice unless an
authorized invoice revision already removed that obligation.

## 3. Persistence contract

Migration `133_invoice_partial_payments` is additive after
`132_payment_source_step_up` and must leave one Alembic head.

### 3.1 `invoice_settlements`

Exactly one row per invoice:

- `tenant_id`, `invoice_id`, `customer_id`;
- frozen `principal_total`, `max_card_fee`, `max_card_fee_tax`, tax/fee rates,
  and currency;
- projected confirmed, pending, unapplied, and refund-pending amounts;
- derived settlement state, `version`, `last_event_sequence`, and timestamps;
- `legacy_reconciliation_status` and safe reconciliation note.

The row is a lockable projection, not the audit source. Totals change only in
the same transaction that appends the corresponding ledger event.

The first live DB-048 attempt freezes the settlement's QBO realm and originating
provider-configuration version as a pair. A later attempt may use a newer
configuration only when it snapshots the same QBO realm. Once set, the pair
cannot be replaced or removed; application and database guards reject any
cross-realm attempt or accounting link.

### 3.2 `invoice_payment_attempts`

One durable identity for each customer, staff, or compatibility-adapter
attempt:

- tenant, invoice, settlement, customer, creator principal, and actor snapshot;
- source `staff | customer_portal | guest_token | compatibility_adapter |
  provider_webhook | backfill`;
- rail `card | zelle | check | ach`;
- provider `stripe_connect | quickbooks_payments | manual`;
- principal, card fee, card-fee tax, applied card fee, applied card-fee tax,
  provider charge, received amount, processor fee, and currency snapshots;
- state `pending | confirmed | failed | expired | refunded | reversed`;
- provider account, intent/charge/event/reference identifiers, normalized
  manual evidence, and provider-configuration version;
- idempotency key, request hash, optimistic version, expiry, failure code,
  timestamps, and immutable creation metadata.

Rows are never deleted or repurposed. Amount, rail, provider, account, invoice,
tenant, customer, and configuration snapshot are immutable after creation.
Only state/projection fields transition through the domain service.
Database guards reject hard deletion, any `deleted_at` transition, impossible
state/money envelopes, and a one-sided, cross-invoice, cross-tenant, removed,
or replaced `payments` compatibility link. The reciprocal link is checked at
transaction commit so both the live-confirm and legacy-backfill write orders
remain valid.

### 3.3 `invoice_payment_ledger_events`

This is the immutable financial audit. Each event contains tenant, invoice,
settlement, attempt, customer, actor snapshot, sequence, correlation ID,
idempotency key, occurrence time, event type, prior/new state, and typed money
delta/snapshot. Event types are:

`attempt_created`, `manual_evidence_recorded`, `provider_authorized`,
`payment_confirmed`, `payment_failed`, `payment_expired`, `payment_reversed`,
`overpayment_detected`, `refund_requested`, `refund_succeeded`,
`refund_failed`, `credit_consent_recorded`, `credit_issued`, `credit_applied`,
`credit_reversed`, `accounting_queued`, `accounting_synced`, and
`accounting_failed`.

Database triggers reject UPDATE and DELETE. The attempt transition,
`payments` compatibility row, settlement projection, invoice state, outbox
event, and immutable ledger event commit atomically.

### 3.4 Credits, refunds, and reconciliation

- `customer_credit_entries` is an append-only, tenant/customer-scoped ledger.
  Entry types are `issued`, `applied`, `refunded`, and `reversed`; applications
  point to the target invoice and cannot exceed the available credit.
- `payment_refunds` records amount, source attempt, reason, destination rail,
  automatic/manual mode, provider reference, state, actor, idempotency, and
  retry metadata. It never deletes or overwrites a prior provider attempt.
- `payment_accounting_links` records the single QBO Payment/refund/deposit
  identity, owning writer, account mapping snapshot, sync state, and error for
  each financial object.
- `provider_settlement_batches` and immutable
  `provider_settlement_entries` record Stripe payout/balance-transaction IDs,
  gross receipts, customer fees, processor fees, refunds, disputes, net payout,
  the originating provider-configuration version, QBO realm, writer and account
  mapping snapshots, deposit/journal identity, and reconciliation state. A
  canonical manifest makes an exact payout replay idempotent and rejects the
  same payout ID with different entries or net money.
- `payment_provider_disputes` retains exact source-money reversal and recovery
  lineage; `customer_credit_due_diligence_events` is append-only; and
  `invoice_settlement_backfill_runs` retains resumable tenant reconciliation
  progress and material source checksums.
- Repair orders retain the authorized early-release actor, reason, settlement
  version, and time without changing financial settlement.
- Existing `provider_outbox` is reused for durable provider/accounting work;
  DB-048 does not create a second generic outbox.

Database triggers reject cross-tenant financial identities, mutation of frozen
attempt fields, and UPDATE/DELETE against the immutable audit ledgers.

### 3.5 Tenant provider configuration

`tenant_payment_provider_configurations` is append-versioned. Each version
stores tenant, selected provider, readiness state, effective time, actor,
provider account snapshot, writer strategy, and QBO mappings for Stripe/QBP
clearing, checks, Zelle/ACH, card-fee income, processor-fee expense, sales-tax
liability, and checking.

Provider/account/realm/writer/mapping identity, IDs, version, effective and
creation timestamps, request identity, and deletion state are immutable in the
ORM and database. A version may only make the one-way active-to-deactivated
transition; readiness remains an operational projection. Accounting-link
financial identity, money, writer, mappings, and realm are likewise frozen,
while bounded delivery status/error fields remain mutable.

Only one configuration version is active per tenant. An attempt snapshots its
version. A switch affects only new attempts; webhooks, refunds, disputes, and
reconciliation continue on the snapshotted provider/account.

Deployment gates default as follows:

- `INVOICE_SPLIT_PAYMENTS_ENABLED=false`;
- `STRIPE_CONNECT_INVOICE_PAYMENTS_APPROVED=true` only in environments where
  the existing Stripe deployment is already approved;
- `QUICKBOOKS_PAYMENTS_INVOICE_PAYMENTS_APPROVED=false` in production until
  the external production gate is separately cleared. An isolated sandbox may
  set it true only for explicit acceptance work after the connected tenant has
  granted `com.intuit.quickbooks.payment`.

Tenant `invoice_split_payments_enabled` also defaults false. Readiness requires
both global and tenant split-payment gates, an approved provider gate, provider
onboarding, complete QBO account mappings, a healthy QBO Accounting link, an
exact non-null match between the active QBO realm and its configuration
snapshot, and the latest tenant backfill run in source-current `verified`
state. New legacy invoice/payment/Zelle drift closes readiness.

## 4. Authorization and tenant isolation

All database reads and writes include the authenticated tenant boundary; no
tenant ID supplied by a client is trusted.

- A linked active customer may read and initiate card/Zelle payment only for an
  invoice belonging to that exact active customer and tenant.
- A linked active customer may list and apply only credit owned by that same
  tenant/customer identity to one of that customer's invoices. Guests and
  receptionists cannot enumerate or apply the customer credit wallet.
- A valid guest invoice-access token may read and initiate card/Zelle only for
  its exact invoice. It conveys no broader customer or credit-account access.
- Garage owner, garage admin, and receptionist may read settlement and record
  card/Zelle/check/ACH attempts for their tenant.
- Garage owner and garage admin with the existing `payments` permission may
  confirm manual overpayment refunds, record in-person customer consent, retry
  accounting sync, and authorize vehicle release before full settlement.
- Only garage owner and a garage admin with `payments` permission may change
  tenant provider/account mappings. Receptionists cannot change configuration,
  resolve credits, issue refunds, or authorize early vehicle release.
- Mechanic, fleet manager, driver, unrelated customer, inactive user, foreign
  tenant, and unknown roles are denied.
- Super admin manages the platform provider-approval gate but does not inherit
  tenant tender/refund authority without an explicit tenant context.

Foreign, missing, cancelled, voided, unauthorized, and cross-tenant invoice
lookups return the same generic `404 invoice_not_found`. Logs and exports never
contain card tokens, raw provider payloads, credentials, or full bank evidence.

Customer credit consent must be per overpayment event. It may be recorded by
the linked customer, the exact invoice guest token, or an authorized manager
capturing in-person/phone consent with required channel and note. There is no
tenant-wide implied consent.

Consent provenance is server-derived before idempotency hashing: authenticated
customers are always `customer_portal`, exact-token guests are always
`guest_token`, and authorized managers may record only `in_person` or `phone`.
A client-supplied channel can never impersonate another audience.

## 5. Tender and concurrency rules

### 5.1 Creating attempts

- Amount is a principal allocation, not a provider charge total.
- Amount must be at least `$0.01` and at most the locked
  `allocatable_balance`.
- All mutations require `Idempotency-Key`. The key is bound to tenant,
  principal/token subject, route, and canonical request hash and retained with
  the financial record.
- Same key and same request replays the original status/body. Same key with a
  different request returns `409 idempotency_conflict`.
- Mutations lock the invoice settlement first, then customer credit account,
  then attempts in UUID order. The lock order is invariant across APIs and
  workers.
- Provider event ID plus provider account is unique. Duplicate or reordered
  webhooks are harmless.
- A normalized manual reference cannot silently settle two invoices for the
  same customer. Confirmation returns `409 manual_reference_requires_review`
  until an authorized manager resolves the evidence.

### 5.2 Rail behavior

- Card creates a 30-minute pending provider attempt and reserves its principal.
  Provider success is authoritative; browser confirmation accelerates
  reconciliation but is not required for correctness. Expiry reconciliation
  checks the authoritative provider before it releases a card reservation.
- Customer Zelle creates a pending intent with declared amount, sender evidence,
  and `expires_at = created_at + 24 hours`. It reserves only that amount.
- Staff Zelle/check/ACH may be created pending or recorded confirmed. A check
  number or bank/Zelle trace is required before confirmation.
- The customer may card-pay the remaining allocatable balance while Zelle is
  pending.
- Expiry releases only the reservation. A late provider/manual success is
  reconciled against the then-current balance and may create unapplied money; it
  is never ignored or allowed to make principal negative.
- Provider or manual failure releases the reserved amount and retains the
  failed attempt.
- Cash, fleet payment, external terminal, and `other` return
  `409 payment_rail_disabled` when the DB-048 tenant gate is active.

### 5.3 Vehicle release

The existing release/completion operation reads the settlement under lock. If
principal remains unpaid, only owner/admin with payment permission may proceed,
and must provide an explicit override reason. The override appends an immutable
ledger/audit event. It does not change the invoice balance or mark it paid.

## 6. Provider resolution

The server resolves exactly one card provider from the active configuration and
never accepts a provider choice from customer input.

- Stripe Connect is ready only when its global gate is approved and the
  tenant's connected account onboarding is complete.
- QBP remains `unavailable_external_approval` while its environment approval
  gate is false. When an explicitly authorized sandbox sets that gate true,
  readiness additionally requires a connected matching QBO realm with the
  `com.intuit.quickbooks.payment` scope, complete mappings, verified backfill,
  and the same tenant/global split-payment gates as Stripe.
- UI must render one card experience or a precise unavailable state; it may
  never render Stripe and QBP simultaneously or silently fall back between
  them.
- Card tokens/client secrets never enter application persistence or logs.
- Webhook signature failure, provider/account mismatch, stale configuration, or
  an event for an unknown attempt fails closed and creates an operational alert
  without changing A/R.

Every DB-048 Stripe success, failure, browser confirmation, guest confirmation,
and expiry reconciliation passes one strict historical envelope validator
before money or reservation mutation. Trusted server account identity must
match the attempt; PaymentIntent ID/status/USD amount and received amount,
latest charge, tenant/invoice/customer/attempt/config/account metadata, and
principal/fee/tax snapshots must match exactly. The signed Stripe event ID,
PaymentIntent ID, and charge ID remain distinct durable identities. Historical
attempts validate against their snapshotted configuration even after a safe
provider switch; the current active configuration is never substituted.

Existing `/payments/create-payment-intent`, `/payments/confirm-payment`,
`/invoice-access/create-payment-intent`, and QBP charge routes remain wire
compatible. When DB-048 is enabled they are adapters to the resolver and create
a full-current-allocatable attempt if the legacy request omitted `amount`. They
never bypass the configured provider. QBP compatibility routes return an
environment-gated unavailable response while its platform gate is false.
Provider-native DB-048 card attempts return only Intuit's tokenization URL;
the browser sends raw card details directly to Intuit and then submits the
opaque token to the attempt-scoped charge endpoint. The QuickBooks Request-Id
is derived from the immutable attempt so browser retries cannot create another
charge.

## 7. Overpayment, refund, and credit policy

Normal APIs prevent intentional overpayment. A provider race, duplicate manual
receipt, mismatched Zelle/check/ACH amount, late success, or dispute correction
may nevertheless produce money above remaining principal.

The finalizer must:

1. record the full money received;
2. apply no more than remaining principal;
3. append an `overpayment_detected` event and create unapplied customer money;
4. default to refund, never income or a synthetic Credit Memo.

For a reversible card rail, a durable refund is automatically enqueued to the
original charge. For Zelle/check/ACH, a visible manager refund task is created;
staff records the external refund reference only after money has been returned.
Failed refunds remain retryable and cannot duplicate money or accounting.

Store credit is allowed only if explicit per-event consent is recorded before
the refund is submitted or while a non-reversible/manual refund task remains
open. Once a provider refund is accepted, it cannot be converted to credit.
Credit belongs to the same tenant/customer, has no arbitrary expiry, is
explicitly applied to a future invoice, and is represented in QBO as unapplied
customer money rather than revenue or a Credit Memo.

Credit aging reports include customer, origin, amount, remaining balance, age,
last contact, consent evidence, and disposition. CSV is spreadsheet-injection
safe. The product never silently expires or escheats credit; it supplies
due-diligence/export evidence for the shop and CPA to follow applicable law.

Refunding already-applied principal for a billing correction remains governed
by the existing invoice revision/void authority and is not invented by DB-048.
A provider dispute/reversal is recorded faithfully and reopens the balance.

## 8. QuickBooks and payout reconciliation

### 8.1 Single-writer rule

For Stripe and manual rails, DieselBridge owns QBO Payment creation through the
existing durable outbox. Each confirmed principal allocation creates exactly
one QBO Payment linked to the existing QBO Invoice.

Before QBP can be globally approved, sandbox evidence must freeze one writer:

- `intuit_native`: Intuit creates Payment/Deposit/Fee objects and DieselBridge
  imports/reconciles them; or
- `dieselbridge`: DieselBridge creates them through the outbox.

The configuration cannot be active if the writer strategy is unknown. The
non-owner rejects creation and only reconciles provider IDs.

### 8.2 Durable operations

Outbox event types are:

- `invoice_payment.accounting_sync`;
- `invoice_refund.accounting_sync`;
- `payment_reversal.accounting_sync`;
- `payment_dispute.accounting_sync`;
- `payment_dispute_recovery.accounting_sync`;
- `customer_credit.accounting_sync`;
- `payment_refund.provider_submit`;
- `stripe_payout.reconcile`.

`payment_refund.manual_task` is a durable visible task for a non-reversible
manual rail; it does not pretend that a provider refund was submitted.

Their idempotency keys include tenant, financial-object ID, operation version,
and provider/account identity. QBO outage never rolls back a confirmed external
payment. It leaves the attempt visible as `accounting_sync_pending`, retries
with bounded backoff, and eventually becomes a visible dead-letter requiring an
authorized retry.

Each QBO mutation uses a stable Intuit request ID and a collision fence tied to
the financial object's tenant, exact QBO realm snapshot, object type, and
operation version. A realm mismatch is never retried against a different realm.

### 8.3 Posting rules

- Confirmed principal: one QBO Payment linked to the single QBO Invoice.
- Pending payment: no QBO Payment and no A/R reduction.
- Overpayment: QBO Payment records full money received, links only applied
  principal to the invoice, and leaves the remainder unapplied.
- Store-credit application reuses the exact originating unapplied QBO Payment;
  it links only the chosen amount to the target invoice and does not create a
  second receipt. Reversing source money reopens every target invoice funded by
  that lineage. Dispute recovery reapplies no more than each target's current
  outstanding balance, and any remaining recovered money returns to the
  refund-first overpayment flow.
- Customer card surcharge: separate mapped income/tax entries, not invoice A/R.
- Provider processor fee: mapped expense.
- Refund/dispute: reverses the matching clearing/customer-credit entries and
  never creates a second sale.
- Stripe payout: groups provider balance transactions into one net transfer or
  deposit from Stripe Clearing to checking.
- Bank feed: matches that prepared net deposit only.

Payout ingestion preflights every entry before inserting anything. Charge,
refund, and dispute rows resolve through their exact attempt and historical
configuration; standalone processor-fee rows must resolve to exactly one
configuration effective at occurrence time. Booking uses only the immutable
entry snapshots, never the tenant's latest mappings. Same-realm/same-checking
historical partitions may share one balanced journal with one checking debit.
Mixed realms, mixed checking accounts, ambiguous configuration intervals,
non-DieselBridge writers, or incomplete mappings persist a visible manual
reconciliation proof and perform zero QBO I/O.

Reconciliation must prove for each payout:

```text
gross provider receipts
+ customer card fees and fee tax
- customer refunds
- disputes
- processor/platform fees
= net payout to checking
```

Unmatched, duplicated, amount-mismatched, account-mismatched, or foreign-tenant
objects stop automatic reconciliation and surface an operational exception.

## 9. Public interfaces

All new staff/customer routes are under `/api/v1/payments`; guest equivalents
remain under `/api/v1/invoice-access` and require the existing invoice token.

### 9.1 DTOs

`InvoiceSettlementSummary`:

```json
{
  "invoice_id": "uuid",
  "currency": "USD",
  "principal_total": "834.00",
  "confirmed_principal": "500.00",
  "active_pending_principal": "0.00",
  "outstanding_balance": "334.00",
  "allocatable_balance": "334.00",
  "unapplied_credit": "0.00",
  "refund_pending": "0.00",
  "state": "partially_paid",
  "version": 3,
  "card_provider": "stripe_connect",
  "card_provider_status": "ready",
  "accounting_sync_status": "synced"
}
```

`PaymentAttemptCreate`:

```json
{
  "amount": "334.00",
  "rail": "card",
  "expected_settlement_version": 3,
  "sender_evidence": null
}
```

`PaymentAttemptResponse` returns attempt ID, principal, fee, fee tax, provider
charge, state, expiry, configuration version, provider client secret only when
needed by that principal, and the updated settlement summary. Provider secrets
or raw tokens are never returned.

### 9.2 Routes

- `GET /invoices/{invoice_id}/settlement`
- `GET /invoices/{invoice_id}/allocations?cursor=&limit=`
- `POST /invoices/{invoice_id}/attempts`
- `POST /attempts/{attempt_id}/confirm`
- `POST /attempts/{attempt_id}/fail`
- `POST /attempts/{attempt_id}/refunds`
- `POST /refunds/{refund_id}/confirm-manual`
- `POST /refunds/{refund_id}/retry`
- `POST /overpayments/{overpayment_id}/credit-consent`
- `POST /customer-credits/{credit_id}/applications`
- `GET /invoices/{invoice_id}/eligible-credits`
- `POST /invoices/{invoice_id}/early-release`
- `POST /customer-credits/{credit_id}/due-diligence`
- `GET /customer-credits/aging`
- `GET /customer-credits/aging/export.csv`
- `GET /settings/card-provider`
- `PUT /settings/card-provider`
- `GET /settings/card-provider/readiness`
- `GET /invoices/{invoice_id}/accounting-reconciliation`
- `GET /payout-reconciliations`
- `POST /payout-reconciliations/{operation_id}/retry`
- `POST /accounting-operations/{operation_id}/retry`

Guest-token equivalents are `POST /invoice-access/settlement`,
`/allocations`, `/attempts`, `/attempts/{attempt_id}/confirm`, and
`/overpayments/{overpayment_id}/credit-consent`. They remain bound to the exact
invoice token and cannot list or apply wallet credit.

Provider webhook routes remain provider-specific and unauthenticated only after
signature verification. They accept no tenant identity from an unsigned body.

### 9.3 Error contract

New endpoints return:

```json
{
  "error": {
    "code": "payment_amount_exceeds_allocatable_balance",
    "message": "The requested amount is no longer available to pay.",
    "retryable": true,
    "current_version": 4
  }
}
```

`422` covers malformed amount/evidence. `404` is the generic inaccessible
resource boundary. `409` covers feature/provider disabled, stale version,
invoice not payable, amount conflict, disabled rail, idempotency conflict,
attempt transition conflict, insufficient credit, refund in progress, and
required release override. `502/503` is used only when no safe local durable
record can be created. Compatibility adapters retain their legacy success and
error wire shapes.

## 10. Migration, backfill, and compatibility

The batched, idempotent backfill creates one settlement per existing invoice.
It never initiates a payment, refund, credit, webhook, or QBO mutation.

- Principal total is derived with the existing authoritative non-card checkout
  calculation; maximum card fee and fee-tax snapshots retain the existing
  invoice values.
- Existing completed `payments` are applied chronologically and capped at
  principal. Provider gross above principal is marked
  `legacy_overage_review_required`; backfill never silently creates customer
  credit or sends a refund.
- A paid invoice without trustworthy payment rows receives an explicit
  `legacy_paid_snapshot` baseline event so it is not falsely reopened; it does
  not claim a reconstructed tender/provider.
- Existing Zelle submissions become 24-hour pending attempts when still within
  the window and explicit expired baselines otherwise.
- Backfill runs are tenant-scoped, batched, resumable, and safe to rerun. They
  persist material source counts/checksums and close readiness if later legacy
  invoice, payment, or Zelle drift makes the latest verified run stale.
- Both native invoice constructors add an empty tenant/customer-exact
  settlement shadow in the invoice transaction, independent of rollout gates.
  This lets readiness distinguish a normal post-cutoff invoice from an
  out-of-band legacy invoice without making first read/payment deadlock.
- A later-cutoff run classifies exact reciprocal Payment/attempt links and the
  exact compatibility Zelle submission marker before mutation. Native DB-048
  projections remain visible to reconciliation but are never replayed as
  baseline attempts/events; one-sided, mismatched, or mixed native/unlinked
  sources fail before any financial projection changes.
- Same-cutoff verification hashes baseline-owned immutable evidence rather
  than mutable native settlement/status projections, so legitimate DB-048
  activity does not invalidate an otherwise identical baseline rerun.

Confirmed DB-048 allocations continue to create one existing `payments` row so
current receipts and read models remain compatible. Because legacy balance and
report consumers sum `payments.amount` directly against invoice principal,
`payments.amount` is the principal actually applied. The DB-048 attempt and
ledger retain received/provider gross, card fee, fee tax, processor fee, and
unapplied components separately. Existing Zelle pending columns remain a
compatibility projection for two release cycles and are dual-written from the
new service.

When the tenant gate is off, an empty native shadow with no financial activity
does not block legacy behavior. Any invoice with a DB-048 attempt, ledger event,
baseline, or nonzero projection remains read-only and can never fall back to a
legacy full-balance write. When the gate is on,
legacy payment routes call the new domain service; they cannot mark a partial
invoice fully paid, bypass provider selection, or accept disabled rails.

## 11. Frontend contract and shared fixtures

The staff invoice and customer/guest payment surfaces use the same settlement
summary. They show confirmed, pending, outstanding, currently payable, fees,
accounting-sync warning, and refund/credit state without conflating workflow
status. `outstanding_balance` is never labelled as currently payable while an
active pending allocation reserves part of it, and `allocatable_balance` is
never labelled as the invoice's full outstanding A/R.

Required shared fixtures:

1. unpaid `$834.00`;
2. `$500.00` Zelle pending with `$334.00` card-eligible remainder;
3. `$500.00` confirmed Zelle plus `$334.00` card allocation and card-only fee;
4. three confirmed tenders closing one invoice;
5. failed card with released balance and retry;
6. paid locally with `accounting_sync_pending`;
7. late card overpayment with automatic refund pending;
8. manual overpayment awaiting refund or explicit credit consent;
9. available customer credit applied to a future invoice;
10. QBP unavailable because platform approval is pending;
11. disabled feature, unauthorized role, and generic foreign-invoice 404.

Customer and guest surfaces offer card/Zelle only. Staff additionally offers
check/ACH and confirmation controls. Keyboard/focus recovery, 44px targets,
themes, provider errors, reload recovery, and desktop/compact/mobile containment
are part of the fixture contract.

## 12. Verification and sign-off matrix

One exact candidate SHA must pass:

- Alembic single-head, fresh PostgreSQL upgrade/downgrade/re-upgrade, both
  provider-era and legacy-payment compatibility paths, and safe downgrade
  refusal when financial ledger rows or provider settlement batches exist;
- idempotent backfill reruns, tenant counts/checksums, paid-without-payment and
  legacy-overage truthfulness;
- cross-tenant, foreign customer, deleted/inactive principal, cancelled invoice,
  disabled gate/provider, unauthorized role, and generic-404 tests;
- append-only ledger trigger, atomic projection/event/outbox writes, no-op and
  actor/reason capture;
- two- and three-tender invoices, arbitrary partial amounts, exact rounding,
  card-fee-on-card-only, and paid/reopened transitions;
- `$500` pending Zelle plus card remainder, confirmation, expiry, wrong amount,
  late arrival, and simultaneous confirmation/card success;
- check/ACH evidence, duplicate reference review, failed confirmation, and
  receptionist versus manager authority;
- concurrent requests and webhooks proving no principal over-allocation,
  idempotency replay/conflict, provider/config snapshot stability, and no
  duplicate paid webhook;
- accidental overpayment, reversible auto-refund, manual refund task, failed
  refund retry, explicit credit consent, future credit application, credit
  ceiling, aging, and CSV safety;
- Stripe sandbox success/failure/refund/dispute/duplicate/late-event journeys and
  gross-to-net clearing/payout reconciliation;
- QBO sandbox partial invoice, multiple linked Payments, unapplied overage,
  refund, outage/retry/dead-letter, account mismatch, and bank-feed no-duplicate
  evidence;
- QBP remains unavailable without the environment platform gate; sandbox token,
  partial-charge, retry-idempotency, reconciliation, and refund evidence may
  clear sandbox acceptance, but no QBP production charge is acceptance evidence;
- component and Playwright journeys for staff, customer, and guest across all
  shared fixtures, keyboard/focus, themes, and supported widths;
- focused compile/lint/build/diff checks and protected PR CI;
- fresh independent Security review for tenant authorization, guest tokens,
  secrets/tokens, signatures, exports, refunds, provider switching, and logs;
- fresh independent QA and exact-SHA Release GO.

No real customer charge, refund, provider activation, bank-feed write, QBO
production mutation, or production-data correction is authorized by this
contract.

## 13. Rollout and rollback

Deploy in this order: additive migration; application with all new gates off;
backfill and verify; provider/QBO sandbox evidence; Security/QA/CI/Release gates;
then one explicitly authorized pilot tenant.

The immediate rollback is to disable the global or tenant split-payment gate.
Reads, webhook finalization, refunds, and already-enqueued reconciliation remain
active so money cannot become orphaned. Disabled mode blocks new attempts and
shows the existing settlement read-only with a contact-shop recovery state.

An invoice with any DB-048 attempt can never fall back to legacy full-balance
charging. Application-SHA rollback is prohibited while pending attempts,
partially paid invoices, refund work, or unsynced accounting exist unless the
rollback build contains the DB-048 read/charge guards. Additive financial audit
tables and events are retained on rollback.

Done requires the exact merged/deployed candidate, migration/backfill
reconciliation, target-tenant gate readback, provider/runtime health, and a
CPA-readable QBO result: one invoice, multiple linked payments, correct open
balance, separately booked fees/refunds, and one bank-feed deposit match with no
duplicate income or payment.
