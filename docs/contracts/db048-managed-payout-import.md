# DB-048 follow-up: managed QuickBooks payout evidence

Required follow-up implementation contract; the guard PR records this dependency, not its completion. Owner:
Backend & Integrations; independent Architecture/Security and QA review required.
This artifact authorizes no activation, provider call or financial mutation.

## Why this is a separate required capability

The guard release deliberately excludes managed shops from
`backfill_quickbooks_cdc`. That function currently supplies the only production
call to `qbp_settlement_window` -> `reconcile_qbp_native_settlements`.
Consequently a managed invoice/payment may be exported correctly while the
platform has no corresponding authoritative fee/net/deposit evidence.

The existing importer creates local `ProviderSettlementBatch` and
`ProviderSettlementEntry` records, preserving deposit ID, source payment/charge
IDs, actual processor fee, net payout, mapping/configuration snapshots and an
immutable entry manifest. Reports aggregate matched/synced batches; the settlement
API lists those batches. This follow-up reconnects that evidence flow for admitted
new transactions without importing or changing held historical invoices.

`matched` means the QBO-native deposit, linked payments and fee evidence reconcile.
It does NOT prove a bank-feed transaction was matched, bank statement cleared, or
money physically arrived. Preserve that distinction in delivery claims. Automated
bank-feed matching is not added by this item.

## Minimal scope

1. Add an activation-specific read-only QBP payout collector, separate from legacy
   CDC. Keep managed legacy CDC excluded; no changes to legacy connection cursors
   or historical invoice/payment sync timestamps.
2. Extend the existing importer with explicit managed admission for every local
   payment and credit/adjustment lineage before writing local settlement evidence.
3. Reuse native Deposit/Purchase/Payment/JournalEntry evidence, manifest checks,
   exact-fee rules and existing report/API projections. Do not create QBO deposits,
   fee journals, purchases, customer records or payment records.
4. Preserve all existing activation/hold rules and other-tenant behavior. No new
   UI, tender, surcharge rate, refund or bank-feed integration.

## Read capability and identity

Add a narrowly scoped `managed_qbp_payout_read_scope(db, activation, connection,
window)` equivalent beside the current activation dispatch helper. It must not
pretend to be an invoice-write admission context. Validate exact tenant, immutable
activation ID, realm, environment, approved writer and enabled state.

Permit only GET queries for bounded Deposit/Purchase windows and GET lookups for
linked Payment/JournalEntry records required to explain those deposits. Use the
existing safe token refresh for that exact connection. Explicitly deny POST and
unrelated resource queries in this capability. Validate request environment using
per-operation scope; never flip shared worker settings. Reset context on success,
error and cancellation. Recheck activation before saving local results.

If the connection realm, writer or provider configuration no longer matches,
return a structured identity-review result, do not query another company or
rewrite snapshots. Disabled activation performs no scheduled reads/imports.

## Collector and cursor

Proposed helper: `collect_managed_qbp_payouts(db, activation_id, *, now, limit)` in
`quickbooks_sync_service.py` or a small dedicated service. Add one bounded scheduled
entry point, or call it alongside legacy CDC while preserving legacy exclusions.

Persist an independent cursor keyed by activation ID (one small cursor model/table
or additive activation fields). Track last successful scan and earliest unresolved
retry date. Do not reuse `QuickBooksConnection.last_cdc_at` or `last_cdc_error`.
Use a bounded overlapping query window to observe fees arriving after deposits;
derive initial scope from activation cutoff and admitted captured attempts, not
from historical settlement timestamps. Invoice enrollment, not deposit date,
remains authoritative.

Paginate with existing `qbp_settlement_window` behavior. If a batch/page budget is
reached, retain continuation or repeat safely; never advance beyond unread work.
Serialize one collector per activation with a lease/advisory lock and token-fenced
cursor updates. Advance successful scan position only after its local transaction
commits. A malformed or deferred deposit retains an explicit retry position;
clock advancement cannot silently abandon unresolved evidence.

## Admission and whole-deposit classification

For each deposit, fetch linked provider records and resolve using existing exact
charge/payment/customer/invoice matching, then validate all resolved local invoices
and credit targets against the same activation. Require standard policy, explicit
enrollment, post-cutoff native lineage, correct realm/configuration/writer, and
valid preserved financial identity. A newly dated payment cannot admit an old
invoice; a replacement cannot bypass held ancestry.

- No admitted component: skip without creating local settlement rows or touching
  historical state.
- Every component admitted and all existing equation/fee checks pass: persist the
  existing immutable matched batch/entries.
- Any held, historical, unmatched, missing or cross-activation component: do not
  persist a matched batch, do not allocate the full deposit fee to its admitted
  subset, and do not call the unrestricted legacy importer as a fallback.

Minimal first implementation may defer mixed/unknown deposits with structured
review reason and retry evidence instead of persisting their financial entries.
If durable review visibility is required, store only activation/deposit identity,
reason and safe evidence hash in a separate review record; do not contaminate
matched totals or attach historical attempts as admitted entries. Review must
not be represented as confirmed bank matching.

Existing importer supports manual-reconciliation batches after resolving at least
one local charge, but that alone is NOT sufficient managed admission: its current
lookup can find historical attempts, and it can persist unmatched components.
Introduce the managed gate before normalization/persistence rather than filtering
returned rows after a write.

## Preserve existing manifest semantics

Retain exact existing fee-account/vendor checks, fee-arrival grace period,
configuration consistency, gross allocation checks, explicit journal-component
validation, component reuse detection and immutable replay verification. Existing
matched records with changed semantic hashes must raise/review, never be silently
overwritten. Missing fee evidence is unknown/deferred, not a zero fee or an
advertised-percentage estimate. Do not mutate historical batches with the same
provider deposit key to make them fit the new activation; report a collision.

## Files and bounded work split

- Activation read context/request validation: `quickbooks_shop_activation.py`,
  `quickbooks_accounting_service.py`.
- Collector/task and independent cursor: `quickbooks_sync_service.py`, existing
  QuickBooks task module, one additive model/migration if needed.
- Managed lineage gate and importer reuse: `db048_accounting_reconciliation.py`.
- New focused tests: managed payout admission/collector test module. Reuse fixture
  suites `test_db048_accounting_reconciliation.py`,
  `test_db048_qbp_explicit_components.py`, `test_db048_qbp_component_wrapper.py`,
  and `test_quickbooks_accounting_lifecycle.py`.

One backend owner implements these files. Independent QA/Security reviewers must
not implement the correction they approve. Root owns intake, board and release.

## Required independent evidence

- Happy path: actual scoped collector -> real importer -> existing report/API
  projection using mocked HTTP transport only; exact fee/net/deposit IDs agree.
- Managed disabled/missing-enrollment/wrong realm/wrong environment and other
  tenant produce zero managed reads or writes as appropriate; legacy stays intact.
- Full admitted, entirely historical, mixed held/admitted, unmatched component,
  cross-activation credit target and held replacement ancestry cases.
- Deposit arrives before fee, fee arrives in overlap, pagination/restart and
  delayed evidence beyond ordinary overlap; no lost retry or premature manifest.
- Same deposit replay is idempotent; changed amount/component/hash and reused
  provider component cannot rewrite existing evidence.
- Exact fee-account/vendor mismatch, missing/ambiguous fee and explicit journal
  composition cases remain fail-closed.
- Two collectors and disable-during-read retain fenced cursor/local-commit rules.
- Outbound request spy proves GET-only provider behavior, scoped token refresh
  and no provider customer/invoice/payment/deposit/journal creation.
- Before/after fingerprints for historical holds, pending reservations, legacy
  cursor, excluded settlements/outbox and other tenants remain identical.
- No test or delivery text equates payout reconciliation with bank-feed matching.

## Release boundary

Implement after guard release as a separate focused item/PR. Deploy with zero
activation rows unchanged; do not create/enroll/enable the shop as part of this
follow-up. Read-only runtime verification confirms scoped collector availability
and no work when no activation exists. The end-to-end activation-readiness claim
requires this capability or an explicitly agreed manual evidence procedure; the
guard-only release alone is not full payout matching readiness.
