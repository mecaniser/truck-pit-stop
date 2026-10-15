# DB-123 — Native paid-outcome capture evidence

Backend & Integrations owns this high-risk financial capture change. It changes
capture admission only; the v2 signed payload, destination, idempotency identity,
retention, worker delivery and existing events remain unchanged. Newly captured
amounts use confirmed principal plus actual earned card fee and fee tax from
immutable confirmation ledger evidence, excluding unearned fees/overpayments.
Cash and applied customer credit add no card fee. Missing fee provenance or
correction/recovery history holds new capture for reconciliation. Native paid
history uses this same amount; absent evidence marks history uncertain with
unknown payment precision. ETS history totals are unchanged.

## Admission

A new v2 `repair_order.paid` event requires native invoice/order source, matching
tenant/invoice/customer identities, positive fully confirmed principal, no pending
refund and an aware nonfuture `paid_at`. Principal is the existing authoritative
`invoice_money_snapshot` amount (invoice maximum card surcharge is not principal).
The native settlement must be undeleted. Its append-only ledger must have all
sequences 1 through `last_event_sequence`, principal deltas summing to confirmed
principal, and a positive payment-confirmed, cash-confirmed or credit-applied event.

The payment and credit paths append their ledger before capture, in the same
transaction; capture flushes pending ledger writes because the production session
has autoflush disabled. Failure to meet admission creates no event. A transaction
rollback removes financial mutations and capture together. Existing outbox replay
returns its original record without replacing payload or scheduling new work.
Corrections retain their separate existing contract; no paid conversion is emitted
for a dispute recovery by this change.

## Scope boundary

ETS day-only history, legacy status-only rows and deleted/mismatched resources
cannot become native settlement evidence. No timestamp is synthesized. No migration,
source backfill, outbox recovery, Google submission, provider or campaign setting
change is included. The resulting invoice-settled snapshot is not a profit claim; delivery policy
remains owned by ELIS and is outside this change.

## Verification

Required: native cash rollback/replay, payment and credit settlement regressions,
rejection of partial/absent/naive/future-time/refund/identity/ledger gaps, imported
source exclusions and original outbox preservation. Independent QA and Security
must approve before merge. Local frontend/backend are owned by other worktrees;
no UI changes or claim of aligned local browser acceptance. Backend isolated tests
exercise this transaction-only change.


## Local acceptance receipt — 2026-10-14

Implementation `488df0f6`: owner 144 focused tests passed across outcome contract,
source history, cash and invoice settlements. Independent QA/Security GO:115 cases
passed plus the corrected customer fixture passed separately. Two review findings
were fixed: capture follows all overpayment/refund evidence; supplied customer must
be the order customer. Diff integrity passes. No production mutations or recovery
were executed. PR526 requires protected CI and explicit release evidence; none is
claimed here. The local frontend and Docker API belong to unrelated worktrees and
were preserved. No local browser/runtime alignment claim is made.
