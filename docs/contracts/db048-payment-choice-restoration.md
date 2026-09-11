# DB-048: payment choice with receipt-scoped accounting authorization

Owner: Backend & Integrations implements code/tests; Architecture owns contract;
Product & Delivery owns release. Base `043b5745`. No PR372 activation or shared
worker environment change. Historical export isolation is NOT a cash-only choice.

## Required outcome

Offer ordinary card/Zelle/check/ACH according to existing audience/readiness rules,
alongside independently eligible FULL cash. New noncash confirmation must produce
normal invoice-and-receipt reconciliation, not an indefinitely held new receipt.
Keep historical invoice policy and all original events held. Do not set invoice
policy to standard, replay history, clear the $232.48 reservation, or record money
during release testing. Full cash remains optional, not a default or restriction.

## Minimal durable distinction: new receipt authorization

Add one nullable server-owned immutable JSON snapshot on InvoicePaymentAttempt,
for example `new_receipt_accounting_authorization`. Existing rows remain NULL;
no backfill or non-null server default. Include version `new_receipt_v1`, tenant,
invoice and attempt IDs, issued timestamp, configuration version, exact realm,
accounting environment and writer. Bind identity to existing attempt/configuration
snapshots; writer must be the current approved canonical writer.

Set this only when genuinely creating a new live attempt under the existing
settlement/invoice locks, after ordinary identity/readiness/amount validation.
Never take it from sender evidence, client DTOs, imports, retries, idempotent
replays, callbacks or existing unmarked attempts. Persist before capture. Permit
no reassignment/update after insert; extend existing model immutability checks.
Old verified callbacks still preserve real provider facts but do not receive this
new authorization and cannot replay historical accounting.

## Admission and normal confirmation

Split new-payment admission from global invoice exportability. Historical hold
alone no longer denies new native attempts. Local_cash_only, cancelled lifecycle,
permissions, balance/reservation, provider readiness and tenant gates still apply.
Cash eligibility and its proof requirements stay unchanged.

Confirmation validates the immutable authorization against exact attempt, tenant,
invoice, configuration, realm/environment and confirmed provider/staff evidence.
The canonical PaymentAccountingLink and its new outbox event bind that exact
attempt and snapshot. Only this valid newly confirmed receipt may enqueue pending
accounting despite historical invoice hold. Unmarked/old confirmations retain
existing held suppression; no historical outbox event is modified or resurrected.

Preserve retries/idempotency for the new event. Manual invoice synchronization,
issuance queues, legacy reconcile and arbitrary direct invoice writer calls still
honor the global hold even after the new receipt has synchronized. An invoice
acquiring a QBO ID through a new authorized receipt does not release old jobs.

## Receipt-scoped provider writes and environment

Add a bounded canonical accounting context/explicit scope validated from the
leased event, immutable link and confirmed authorized attempt. The central invoice
export guard can recognize that scope for that exact invoice only; never treat
mere presence of any authorized attempt as a blanket invoice release.

Scope binds tenant, invoice, attempt, realm, configuration, writer and environment.
The deployed API uses production accounting while the shared worker uses sandbox;
the authorized operation must use its snapshotted production environment, NOT
the worker global default. Extend request construction with a context-resetting
scope or explicit immutable arguments; compare the request connection tenant and
realm before each call. Concurrent/unrelated requests retain their legacy base
URL. No global settings mutation, connection-attribute hacks or general shop
activation framework. Wrong/changed identity fails before capture where knowable,
and before any accounting dispatch in all cases.

## Clean legacy-invoice projection normalization

An existing `legacy_principal_v1` settlement is NOT itself an admission failure.
The live INV000020 and TPS000001 examples both carry that historical label;
blanket rejection would reproduce the payment-choice defect. Preserve the stored
immutable composition and all existing totals/history. At first genuine new
attempt creation, validate a clean unpaid base under the existing locks, then
bind `effective_composition: gross_invoice_v1` into its immutable new-receipt
authorization. This normalizes future receipt accounting, not historical rows.

Clean means no unapproved confirmed historical money, QBO linkage or accounting
payment links, no unresolved competing reservation/financial obligation through
the supersedes lineage, and principal/fee-base values verified against the
existing invoice-money snapshot. Individually reviewed local-void ancestor proof
may explain no-op accounting history but cannot excuse pending money. Preserve
all reservation values. INV000020 must pass if those actual checks pass;
TPS000001's parent reservation must yield its specific unresolved-payment reason,
not a cash-only or generic legacy-composition restriction.

Within the validated new-receipt accounting scope, select the gross serializer
even when the immutable settlement label remains legacy. Resolve the same
effective composition from validated authorization for subsequent authorized
partial payments, adjustments/refunds and payout evidence validation. Centralize
this rule: raw settlement-label checks in the existing native payout importer
must not misclassify the new authorized gross receipt as a legacy receipt.
Standard legacy invoices without authorization retain their existing behavior.
Do not infer permission from a client marker or change composition while evidence
is ambiguous. Subsequent receipts may use earlier authorized receipts as their
accounting lineage; they need not pretend the invoice is still pristine.

## Projection and financial completeness

The first new receipt exports the current full invoice principal and applicable
earned fee lines, then applies the newly confirmed receipt. Subsequent authorized
receipts update that same invoice/receipt composition under existing idempotency.
Gross projection must exclude unapproved historical receipt, fee, refund and
credit components; do not use a broad all-attempt scan as an accidental replay.

If existing confirmed historical money means full principal minus only admitted
receipts would misrepresent the outstanding balance, fail new admission with a
specific historical-balance review reason before collecting money. Do not hide
this difference or call the invoice cash-only. Clean unpaid held invoices and
successive authorized partial receipts follow the ordinary new-payment flow.
Existing reservations still limit allocatable balance and remain untouched.

Refund/reversal/dispute accounting derived from a newly authorized receipt must
retain the same lineage and environment, with no grant to historical sources.
Keep existing authorized money-return behavior; this contract does not permit
refund execution during verification. Cross-invoice credit is not an implicit
authorization transfer: require each target's independently valid scope or retain
its explicit review denial. Never enable generic historical accounting retry.

## Presentation

Remove blanket historical-hold suppression of new-payment controls when the new
admission rules pass. Keep audience rails (staff card/Zelle/check/ACH; customer
and guest their currently permitted methods). Show full cash independently when
eligible. Use a specific unavailability reason only for an actual failed rule;
customer/guest wording remains contact-shop appropriate. Existing financial
history and receipt review remain visible. Server checks remain authoritative.

## Acceptance and release gates

- Clean unpaid historical-held invoice offers ordinary noncash plus eligiblecash.
- New staff and portal/guest attempts persist immutable authorization; old replay,
  backfill, caller-supplied marker and old callback cannot acquire it.
- New confirmed receipt -> actual canonical loader/writer with mocked HTTP sends
  correct full principal/new fees and only new payment to correct productionrealm.
- Two authorized partial receipts reconcile without re-exporting old payments.
- Clean held legacy_principal_v1 invoice accepts normal new choices, exports the
  correct gross composition and retains its immutable historical label/totals;
  native payout validation and receipt-derived adjustments interpret that same
  authorized composition. Legacy label alone never denies admission.
- Ancestor reservation produces a precise unresolved-payment failure before a
  competing collection; the parent $232.48 value/history remains unchanged.
- Old dead/deferred/suppressed/manual invoice jobs remain blocked after newreceipt,
  even with a newly stored QBO invoice ID. Historical fingerprints unchanged.
- Old confirmed-money conflict blocks collection specifically; pending reservation
  still counts; fullcash never mixes with any partialpayment/history.
- Tenant/realm/config/environment mismatch and unrelated concurrent sandboxwork
  prove no cross-scope provider calls. Context resets after errors/cancellation.
- Idempotent retry, duplicateworker and newreceipt-derived adjustment/refund paths
  retain correct lineage; oldsources and unauthorizedcredittargets remainblocked.
- No production payment, refund, activation or bulk history release in acceptance.

Independent Architecture/Security and QA review exact candidate. Deploy nullable
schema -> guarded worker -> API/UI. Migration introduces no authorizations for
old rows. Read-only live acceptance checks offered choices; the user records any
actual payment. Do not claim complete restoration with new receipts collecting
successfully but permanently suppressed or sent to the wrong environment.
