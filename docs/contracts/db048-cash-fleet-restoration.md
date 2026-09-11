# DB-048 Cash-only invoices and fleet-instrument restoration

Fleet follow-through is now implemented locally under
[`db048-fleet-tender-v1.md`](db048-fleet-tender-v1.md) as part of the active payment
journey. That versioned contract supersedes the Fleet-backlog status below; its
independent gate and release remain pending. The earlier cash release record is
retained here unchanged.

Status: cash-only slice implemented and locally tested; not committed or released.
Independent Security/local QA and PostgreSQL gates passed. Fleet/analytics are backlog.
Accountable owner: Backend & Integrations. Architecture & API Contracts: root.
Source baseline: a5f243ca0e1d7fc83a5b13149246446fbc9ab26a.

## Approved product direction

- Cash pays the full invoice only. No mixed cash/card, cash/Zelle, cash/ACH,
  cash/check or cash/fleet allocations. Cash is staff-confirmed, local-only.
- Standard invoices support partial card, Zelle, ACH, check and fleet-instrument
  receipts with corresponding QuickBooks accounting records.
- Fleet instruments: EFS / MoneyCode, Comchek, T-Chek, Other provider.
- Receiving cash does not mean changing taxes, revenue, or invoice obligations.
  Preserve the invoice tax snapshot and exclude only the unearned card surcharge.
- Do not erase, reduce, write off or void an existing QuickBooks invoice to hide
  a local cash payment. Do not relabel cash as another tender.

## Verified implementation boundaries

- `backend/app/api/v1/endpoints/invoices.py` queues invoice export when issuing.
- `backend/app/services/quickbooks_sync_service.py` owns durable invoice export.
- `backend/app/services/invoice_settlement_service.py` permits only card, Zelle,
  check and ACH; confirmation maps those rails into Payment and accounting outbox.
- `backend/app/api/v1/endpoints/invoice_settlements.py` advertises those rails.
- `frontend/src/features/payments/SettlementPaymentPanel.tsx` consumes allowed rails.
- `frontend/src/features/repair-orders/RepairOrdersPage.tsx` retains the old
  Fleet Check / Code provider choices. Reuse terminology, not old payment writes.

## Invoice accounting policy (proposed new persisted contract)

Introduce invoice `accounting_policy`: `standard` or `local_cash_only`.
Default/backfill every existing invoice to standard. No historical reclassification.
Policy may be selected before issuance OR by the atomic full-cash confirmation
at payment time, using existing staff payment authority. Issued status alone is
not a rejection reason. Payment-time conversion requires verified export safety
and absence of incompatible payments, as detailed below.
For standard, preserve every existing checkout/export behavior.

For local_cash_only:
- Label the payment action: Record full cash payment — kept in DieselBridge only.
- Freeze local policy when cash is confirmed. Preserve the same issued invoice,
  numbering, tax snapshot and customer history; do not require reissuing solely
  because it was already sent.
- No QBO invoice, customer, payment, refund or credit export from this invoice.
- Gate at enqueue AND consumer/posting boundaries, including retry, reconciliation,
  OAuth backfill and legacy adapters. A UI flag alone is insufficient.
- Explicit sync state `not_applicable_local_cash`, never success or pending.
- Expose staff cash confirmation only; customer/guest views are read-only for payment.
- Preserve normal invoice/receipt numbering, lines, taxes and tenant reporting.
- Standard invoices may transition at cash confirmation only under the eligibility
  protocol below. No bulk or historical automatic reclassification.

### Payment-time export safety

| Observed state | Local-only full cash action |
| --- | --- |
| Never queued/exported; no payment activity | Eligible under lock |
| Pending export with no prior provider attempt | Eligible only if atomically suppressed before any worker can claim/send |
| Failed/dead export with prior attempts | Require provider-side reconciliation and no active/ambiguous request before eligibility |
| Active worker lease, in-flight request or unknown provider result | Temporarily unavailable; resolve export outcome first |
| Existing QBO invoice/link or provider-side match | Not eligible for automatic local-only conversion; preserve QBO records |

Use a shared invoice/policy serialization boundary across cash confirmation,
export enqueue, worker claim/send and manual retry/backfill. An expired worker
lease is NOT proof that a remote create never completed. A null provider ID or
local sync error alone is NOT proof of absence. Reconcile deterministic IDs,
document number, realm and immutable source markers where available. A failed
lookup or unresolved collision is unknown, not absent. Never perform a remote
write to test eligibility.

Suppress safe queued/retry export events with a distinct terminal audit reason,
not a forged successful export. Preserve the original attempt/error history.
Commit suppression, accounting-policy change and cash receipt atomically; a worker
must recheck the policy/lease before dispatch. Race tests must prove no remote
invoice can appear after cash confirmation has been accepted as local-only.

Manual `POST /quickbooks/accounting/invoices/{invoice_id}/sync` must use the same
durable export queue, not bypass attempt evidence with a direct provider send.
It retains its existing response shape and permission/finalization checks, but
returns `status: pending` for queued work rather than claiming synchronous success.
The worker is the sole invoice-export dispatcher. No frontend caller was found.

For invoices already in QBO, do not silently accept a payment that leaves an
unexplained receivable. A separate explicit local-cash/manual-CPA-resolution path
may be designed later; it must visibly track the QBO discrepancy and must not
claim full book reconciliation. That exception is not authorized by this draft.

### Read-only example checked on 2026-09-10

An issued production invoice had QBO sync error, null provider invoice ID and
synced timestamp, and an export event dead after five attempts. There were no
canonical payment attempts or accounting links. Identifying details remain local.
Authenticated current-realm QBO Invoice query by exact DocNumber returned no matches.
This does not prove cash eligibility: historical export attempts lack original-realm
and per-attempt outcome evidence, and the legacy writer could truncate DocNumber.
The cash safeguard must leave this historical invoice review-blocked unless all
prior attempts can be shown determinate and reconciled. Current exact DocNumber
absence alone is insufficient. Safely unexported issued invoices remain eligible;
issuance itself is never the rejection reason.
No invoice, payment, queue or provider record was changed during inspection.

## Cash confirmation

### Implementation API slice (2026-09-10)

Cash-only slice now authorized; Fleet and dedicated analytics remain separate.
Extend summary.allowed_actions with `confirm_cash: boolean` (default false) and
`cash_unavailable_reason: string|null` (bounded human-readable reason). Staff-only
visibility; availability is advisory, POST revalidates under export/payment locks.
POST `/payments/invoices/{invoice_id}/cash-confirmation`, authenticated payment
staff, Idempotency-Key header, JSON `{expected_settlement_version: integer>=1,
note?: string<=1000}`; no client amount, tenant or policy. Response
`{payment_id: UUID, settlement: InvoiceSettlementSummary}`. Structured existing
error envelope on 403/404/409; repeat idempotent success returns same payment.
Do not add cash to the generic partial-attempt creation API.
Canonical history may expose rail `cash`; amount fixed to full server principal,
zero card surcharge. Display `Paid in cash` and `not_applicable_local_cash` accurately.
Local-only cash refunds/credit/retries fail closed until their own supported paths.

Reuse canonical settlement/payment audit and idempotency infrastructure, not the
legacy mark-paid shortcut. Contract naming is proposed pending implementation review:
authenticated staff confirmation receives invoice ID, expected settlement version,
idempotency key and optional bounded receipt note. Server calculates exact full
amount; no editable partial amount and no client-selected tenant/accounting policy.

Under invoice/settlement lock require all of:
- active owned invoice/customer/order, allowed staff role and payment permission;
- local_cash_only policy, or a safe standard-to-local transition in this transaction;
  no QBO invoice identity/accounting binding and no unsuppressed/ambiguous export;
- positive full balance; no prior confirmed or pending allocation, refund, credit
  application, or incompatible legacy payment;
- no cancelled/voided invoice and no concurrent policy/payment change.

Atomically record full cash receipt, allocation, actor/time, receipt number, invoice
paid transition and audit. Zero card surcharge, processor fee or provider request.
Replay returns the same receipt; conflicting replay/version fails without mutation.
No customer/guest cash confirmation. No overpayment/store credit/change calculation.
Do not use the early vehicle-release exception as payment confirmation.

Cash refunds, if exposed, remain local audited reversals linked to the receipt,
bounded by received/unrefunded cash. Never auto-charge another rail or export them.
Until those semantics are implemented and verified, do not expose a refund action
that invokes the standard QuickBooks refund path for local-only cash.

## Fleet Check / Code

Add canonical `fleet_payment` rail, manual provider, staff-only. Partial and full
amounts allowed on standard invoices. Require provider type and bounded instrument
reference; Other requires a provider name. Capture confirming staff and timestamp.
Instrument receipt/verification is distinct from deposited/cleared bank status.
Do not collect reusable secret authorization codes beyond the required trace.

Carry provider/reference through immutable attempt evidence, Payment projection,
accounting link, QBO payment reference/memo, reconciliation and tenant export.
No card surcharge. Do not invent processor fees. Use the existing manual-payment
account mapping and require valid configured accounting destination before posting.
Reference collisions must be tenant/provider scoped and checked without treating
two partial allocations of one verified instrument as two independently received sums.
Implementation must explicitly define instrument reuse vs duplicate rejection tests.
Manual correction/refund uses auditable existing authority, never silent edits.

## Allowed methods

| Invoice policy / audience | Methods |
| --- | --- |
| Standard / staff | card, Zelle, ACH, check, fleet payment; full cash only when server export-safety checks permit atomic local conversion |
| Standard / customer or guest | existing card and Zelle only |
| Local cash only / staff | exact full cash confirmation |
| Local cash only / customer or guest | no online payment actions |

Card means the supported provider credit/debit flow; do not add a separate debit
processor or infer card type from staff input. Existing provider controls apply.

## Analytics

Tenant-scoped Cash receipts view: date range, invoice/customer, receipt, amount,
recording staff, refunds/reversals, net receipts, CSV export with existing permission.
Label: Cash collected / Cash refunded / Net cash receipts. Clearly identify records
excluded from QuickBooks sync; retain them in local invoice/revenue/tax reporting.
Do NOT label net receipts cash on hand or available liquidity. A full cash drawer
ledger with opening balance, deposits, withdrawals and reconciliation is separate.

## Delivery slices and gates

1. Backend policy migration, payment-time export interlock and all QBO producer/consumer exclusions;
   cash confirmation and negative/concurrency tests. No user-visible option until safe.
2. Fleet rail/evidence, accounting mapping, reference preservation and replay/refund
   regression. Preserve existing card/Zelle/ACH/check behavior.
3. Payment-time full-cash action with eligibility explanation, fleet inputs and local cash receipts view.
4. Independent Security/QA, protected CI, migration checks, sandbox provider evidence,
   then separately authorized release/activation. No real cash receipts or payments
   are created just to test production without specific transaction approval.

Required acceptance: second-tenant/role/customer denial; existing invoices default
standard with explicit safe payment-time conversion only; exact-cash-only enforcement;
issued-unsynced acceptance, unattempted-queue suppression, attempted-error reconciliation,
already-exported/in-flight/unknown denial; concurrent cash/noncash/export exclusion;
zero QBO side effects including retry/backfill for local invoices; unchanged taxes;
healthy standard rails; fleet references survive QBO mapping; duplicate/replay safety;
cash receipt/refund analytics arithmetic and no false cash-on-hand claim; desktop/mobile.

Completion requires implementation evidence, not this document. Production remains
unchanged while this contract and the implementation slices are prepared.

### Cash-only release boundary

This implementation covers slice1 and the full-cash staff action from slice3.
Fleet inputs, dedicated cash-receipts analytics/CSV and cash reversal UI are backlog,
not hidden release requirements for this slice. Canonical local receipt/history is
required now. Existing noncash flows must remain unchanged.

Apply the additive migration first, then deploy and verify every invoice-export
worker on the guarded revision **before** exposing the new cash-confirmation API/UI.
Do not allow a new cash writer to coexist with an older unguarded export worker.
Verify migration head, worker/API identities and scoped staff capability before
activation; production receipt creation is not a deployment smoke test.

After any cash receipt exists, do not roll workers/API back to unguarded code or
downgrade the migration. Hide/disable the cash entry point and forward-fix while
retaining local-only export guards. A frontend-only rollback can hide the control
without discarding receipts. The migration must refuse downgrade with cash data.
