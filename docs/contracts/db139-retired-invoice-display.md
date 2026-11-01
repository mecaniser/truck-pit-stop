# DB-139: retired ETS backfill copies in the staff billing display

Owner: Backend & Integrations. Architecture contract approved 2026-11-01;
independent Security/QA and release verification remain separate gates.

The staff repair-order list and detail reader may recognize historical duplicate
invoice copies as display artifacts. The generic `supported_invoice` selector,
completed-outcome writer, aggregates, exports, API shape and financial records
are unchanged. There are no migrations or data writes.

Acceptance requires one live imported canonical invoice in an exact tenant/job
and active imported customer/vehicle-consistent operation group. Every other
invoice must be cancelled and deleted, owned by a different operation, named
exactly `canonical invoice number + '-' + operation order number`, and carry the
exact historical backfill-cleanup reason and matching deletion/update timestamps.
Bill-to and total must equal the canonical invoice; canonical total must also
match the fully validated fresh singleton ETS source observation. Copies must
have no source evidence, native invoice metadata, revision links (either
direction), or financial references. Retired payments must be imported, failed,
positive exact-cent amounts, deleted/updated at the copy retirement instant,
with no provider, refund, accounting or attempt evidence. Their amounts are never
added to the canonical payment evidence.

The canonical invoice must independently pass the existing full source and
payment summary, yielding paid, partially paid or unpaid with an ETS snapshot
basis. Canonical failed/deleted/refunded or otherwise conflicting payment evidence
keeps the original entire-group `deleted_invoice_evidence` hold. Unknown
provenance, actual cancellation, extra active invoices, foreign/native/deleted
operation conflicts, source mismatch, stale evidence and unsupported source
payments likewise preserve that hold. No arbitrary deleted-row filtering occurs.

Candidate and payment loading are batched per page, with one additional
scope-limited UNION for native references only when retired candidates exist.
Every reference branch includes the selected tenant. The same resolver serves
list and detail, including off-page invoice owners. Read-only calls must emit
only SELECT statements and preserve invoice/payment ownership and all amounts.

Production read-only discovery found 1,076 held operation rows in 330 jobs:
723 cancelled copies and 802 retired payments, all carrying the August 23 import
cleanup provenance. Whole-reader shadow validation corrected the preliminary
estimate: 313 jobs / 1,015 rows qualify (1,013 paid, 2 unpaid). Seventeen jobs /
61 rows remain held. The two additional conservative exclusions are a negative
retired payment and a copy attached to the canonical owner's own repair order.
These are evidence-driven holds, not reasons to relax the predicate.

Focused coverage includes paid/partial/unpaid, exact balances, immutable generic
selection, list/detail equivalence, off-page ownership, bounded reads, source and
identity failures, canonical hard payment conflicts, retired provider/refund and
negative-payment evidence, native settlement/accounting references, reverse
revision links and tenant isolation. Full production shadow comparison uses a
read-only transaction and fingerprints all invoice, payment, settlement, ledger
and repair-order rows before and after. Private source data and receipts stay
outside Git. Rollback is code rollback; no financial rollback is required.
