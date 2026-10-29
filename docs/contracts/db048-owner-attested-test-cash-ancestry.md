# DB-048 owner-attested test reservation cash ancestry

Status: Architecture contract v1.1, 2026-10-29. Revision clarifies bounded transaction timestamps and closed evidence schemas after independent gate findings; implementation remains unreleased. Accountable implementation: Backend & Integrations. Architecture author: pending_card_investigation. Implementation, independent QA/Security and release remain separate gates.

## User outcome and authority

The owner explicitly identified a predecessor card reservation as a test unknown to QuickBooks and requested internal reconciliation without provider contact. That exact reservation has already been failed through the existing audited domain transition. Noncash readiness is clear, but local cash still rejects the preserved predecessor attempt/ledger history.

This contract lets the existing cash eligibility reader recognize that narrow completed operational review. It does not fail, expire or erase attempts; contact QuickBooks; establish a provider-verified no-charge fact; record a cash receipt; or waive any other accounting/payment check. Actual payment remains a separate user action.

This fits the requested internal reconciliation because it consumes the audit evidence created by that authorized operation, while preserving every historical row and all existing payment/accounting boundaries. There is no new API, table, migration, customer-visible input or provider call.

## Existing contracts remain authoritative

`cash_eligibility` and `reviewed_cash_ancestry_reason` keep current invoice lifecycle, full-balance/no-payment requirements, permissions, financial/export/outbox checks and replacement-chain validation. Existing signed owner-cash review manifests and `owner_attested_ancestor_snapshot` are unchanged. Do not expand the old `owner_attested_no_card_payment` failure-code allowlist or silently invalidate/reinterpret its fingerprint contracts.

A separate private read-only helper may qualify the new completed operational review. It returns false on any missing, malformed, unknown or inconsistent evidence. Consume that result only to skip the generic ancestor attempt/ledger-exists and nonzero-history-sequence rejection for that qualifying parent. Run all predecessor accounting/export checks first. Every other parent in the replacement chain still passes the existing rules independently. The helper must never turn an existing failed accounting/export review into success.

## Exact eligible scope

For the minimal v1, require exactly one failed attempt and one settlement on a qualifying parent. Supporting multiple attempts or expired states is outside this contract; reject them rather than infer equivalence. This matches the reviewed operation and limits the change.

- Parent invoice is undeleted, cancelled, has `voided_at`, and belongs to the same tenant and repair order as the current invoice. The repair order/customer and tenant are active/undeleted. The parent settlement and attempt have the exact order customer; a nonnull parent billed customer must agree. A legacy null billed customer may inherit only this same checked order customer.
- Parent has no Zelle pending marker, provider invoice ID, synced timestamp or synced/exported accounting state. Existing cash/export review and financial outbox rules still pass; no new outbox exception is introduced.
- Attempt is undeleted, `state=failed`, `rail=card`, `provider=quickbooks_payments`, `failure_code=owner_attested_test_attempt`, and has nonnull `failed_at`. Restrict source to the reviewed `customer_portal` origin. Its parent/tenant/customer/settlement IDs all agree and currency is USD.
- Attempt `received_amount` is null; `payment_id`, provider intent/charge/event/reference IDs are absent. Applied principal, unapplied amount, applied card fee/tax and processor fee are exactly zero. Original quoted principal/card fee/tax/gross remain immutable and may be positive; those are requested amounts, not received money.
- Settlement is undeleted, coherent with parent/customer/tenant, USD and `state=unpaid`. Confirmed principal, active pending principal, unapplied credit and refund pending are exactly zero. No evidence row is deleted or ignored to qualify.
- No Payment, PaymentAccountingLink, PaymentRefund, PaymentOverpayment, PaymentProviderDispute or ProviderSettlementEntry references this parent/attempt. No CustomerCreditEntry targets this parent or derives from an overpayment belonging to its attempt. Query each model through its actual foreign-key shape; do not presume every model has `invoice_id`.
- No new payment/settlement/ledger/provider/accounting history can be present beyond the explicitly validated full set below. A newly inserted pending, failed or expired attempt invalidates the one-attempt proof until separately reviewed.

Do not hardcode production UUIDs, an amount, customer name, actor name, date or private authorization text in application source or fixtures.

## Trusted release event

Exactly one terminal `payment_failed` event must reference the qualifying attempt/settlement/invoice/customer/tenant. Its append-only `evidence_snapshot` must be an object whose exact required keys are shown below. The sole allowed optional key is `executed_by`, a nonempty scalar string. No other keys, nested objects/arrays, provider identities or contradictory provider data qualify:

```json
{
  "failure_code": "owner_attested_test_attempt",
  "schema": "owner-attested-test-reservation-release-v1",
  "classification": "owner_attested_test_attempt",
  "provider_contacted": false,
  "provider_verified": false,
  "operation": "release_exact_internal_test_reservation",
  "attestation": "<nonempty explicit owner test attestation>",
  "evidence_source": "<nonempty authorization reference>"
}
```

`false` means the JSON boolean false, not absence, null, zero or string text. Every displayed string value must be a scalar nonempty string and must match its indicated constant where specified. The attestation/reference text remains private and is never matched to hardcoded production wording. Require a nonempty event idempotency identity and nonnull actor ID. The ledger actor role snapshot must be owner/admin; the referenced actor must exist in the same tenant, be active/undeleted, currently be owner/admin and have payments permission under the existing permission helper. This conservative current-role check means revocation removes this eligibility rather than silently retaining a trusted authority assumption.

Ordinary failure API input supplies only a code and expected version; it does not supply this trusted schema/evidence. Therefore a caller choosing the matching failure code alone cannot qualify. Do not add an endpoint or form field for manufacturing the evidence marker in this change. Matching strings in `manual_evidence`, attempt notes, email or another attempt's event are insufficient.

The recognized event truthfully denotes an owner-attested test release. It is never described as a processor decline, provider cancellation, verified absence of charge, actual payment or revenue.

## Full ledger and conservation

Read the complete ledger for the parent settlement/invoice, not just events attached to the desired attempt. All row IDs must be coherent with the single parent/attempt/customer/tenant/settlement. Null/unrecognized attempt IDs invalidate the proof.

- Exactly one `attempt_created` precedes the release, with pending delta equal to the immutable attempt principal. Its evidence has exactly the keys `source`, `rail`, `provider`; each value is a scalar string matching the qualifying attempt (`customer_portal`, `card`, `quickbooks_payments`). Reject extra keys or nested content.
- Zero or more `provider_reconciliation_failed` events may intervene, but each has zero principal, pending, unapplied and refund deltas. Their evidence has exactly the keys `provider`, `failure_code`, `provider_account`, `provider_intent_id`. `provider` is the scalar string `quickbooks_payments`; `failure_code` is the scalar string `quickbooks_payment_outcome_unknown`; `provider_intent_id` is JSON null. `provider_account` is a scalar string or JSON null exactly equal to the attempt's `provider_account_id` snapshot. That unchanged configuration snapshot is not a charge identity. Reject all extra keys, nested objects/arrays, type substitutions, mismatched account snapshots or nonnull provider intent data.
- Exactly one terminal `payment_failed` has pending delta equal to negative attempt principal, zero other money deltas and the trusted release marker above. It is last in this settlement ledger and agrees with the attempt failed state/time.
- All events have zero principal, unapplied and refund deltas. Pending running balance never becomes negative and finishes at zero. Snapshot confirmed/unapplied/refund values are zero; snapshot pending values agree with the running balance. No missing or unparseable money is treated as zero.
- Settlement sequence is contiguous from one through its `last_event_sequence`; that last sequence equals the complete row count and the release sequence. Require no duplicate/missing/extra events. Preserve sequence and history; do not reset `last_event_sequence` to permit cash.

Any other event type (confirmation, receipt, refund, reversal, credit, provider outcome, fee adjustment, arbitrary audit), nonzero unsupported delta or changed final snapshot rejects eligibility.

### Failure timestamp coherence

Do not require exact equality between the terminal ledger `occurred_at` and attempt `failed_at`. PostgreSQL `NOW()` supplies the transaction-start time for the ledger, while the domain transition supplies Python wall-clock time for `failed_at`; a valid single transaction can therefore have an earlier terminal event timestamp. The eligibility check must normalize timestamps to UTC (treat naive timestamps from SQLite fixtures as UTC), reject missing/non-datetime values, and require:

- attempt `created_at` is present; `failed_at >= created_at` and terminal `occurred_at >= created_at`;
- `abs(terminal occurred_at - failed_at) <= 5 minutes`; either ordering is permitted only inside this bound;
- `created_at`, terminal `occurred_at` and `failed_at` are no later than the evaluation's current UTC time plus five minutes (bounded clock skew, not arbitrary future authorization).

The five-minute interval is an explicit conservative bound for this fast operational transition, not permission to accept a long-running historical transaction. A marker outside it remains review-required. Full sequence, final-state and zero-money checks still apply; a matching timestamp alone grants no exception. No existing history is rewritten to satisfy this rule.


## Concurrency, errors and compatibility

The helper has no writes, network, token refresh, auto-expiry or retry. It returns a qualification boolean (or immutable proof consumed only internally); public response shape and existing unavailable-reason strings remain unchanged.

Read eligibility can use normal reads. Actual cash confirmation must re-evaluate the full helper and existing eligibility checks under the existing tenant financial lock and lock/reload the parent, attempt, settlement and relevant ledger/financial rows using existing conventions. Any version/history drift or inserted event/attempt rejects the operation before receipt creation. Use the same helper for displayed allowed-actions and final confirmation; the display is not authorization.

The cash confirmation's existing full invoice amount, idempotency, tenant/role checks, LOCAL_CASH accounting policy, immutable invoice history and outbox behavior remain unchanged. This contract grants no access to a foreign parent or row and no eligibility to a current invoice with its own historical payment activity.

## Required acceptance and negative gates

1. Synthetic same-tenant cancelled ancestor with the exact one-attempt trusted release and creation/maintenance/failure ledger qualifies for the generic ancestry history exception; current eligible invoice offers Cash. Read calls are mutation/provider-free.
2. Actual fixture cash confirmation under the existing lock creates exactly its existing allowed receipt/invoice effects; predecessor attempt, ledger, quote snapshots and cancelled status remain byte-for-byte unchanged. No QuickBooks dispatch occurs.
3. Partial/pending/confirmed/refunded/reversed or expired attempt, wrong rail/provider/source, multiple attempts, missing settlement, nonzero reserve/confirmed/refund/unapplied or received amount including zero nonnull reject.
4. Matching failure code without marker; malformed schema, classification, operation or attestation; false-like strings; extra or nested evidence keys; nonnull maintenance provider intent; mismatched/nested maintenance provider account; duplicate terminal marker; foreign/different/null attempt marker; missing/foreign/customer/receptionist/deactivated actor or no payments grant reject.
5. Wrong tenant/order/customer/billed customer, deleted parent/attempt/settlement/customer/order/tenant, active/nonvoided parent, replacement cycle/missing parent reject. Fixture marker/customer/tenant identities must not leak into another tenant's allowed-actions.
6. Any Payment, accounting link, refund, overpayment, credit, dispute, provider settlement row or provider identity rejects even if amount is zero, row is historical, or a valid marker also exists.
7. Confirmed/paid ledger, unexpected event, nonzero maintenance delta, hidden provider identity, unbalanced reservation, invalid snapshot, missing/duplicate sequence or a new attempt/event after initial display reject final confirmation. Missing/old-before-creation, more-than-five-minute-inconsistent or arbitrary-future failure timestamps reject. A legitimate terminal transaction-start timestamp within five minutes before the Python failure timestamp qualifies with all other invariants. No false paid state is inferred.
8. Every existing export/accounting restriction still rejects: parent/current QBO invoice/synced/export evidence, unresolved financial outbox, invalid signed review, changed replacement-chain manifest and current invoice's own payment history. Existing owner-review/fingerprint suites must remain unchanged and pass.
9. Independently review the implementation and test evidence (QA and Security) before release, then protected CI, approved focused PR merge/deploy and signed-in actual Cash availability without submitting a real payment.

## Handoff

Architecture to Backend: implement the smallest helper/ancestry integration and focused tests satisfying this contract on a separate focused PR. Root owns board item, runtime alignment and release. Architecture authored no application changes and issues no independent QA/Security approval for its implementation. Return to Architecture if broader states, multiple attempts, new evidence/API fields, signed-review changes or relaxed accounting/provider invariants become necessary.
