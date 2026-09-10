# DB-048: individually reviewed sandbox history and full-cash confirmation

Owner: Backend & Integrations implements helpers, tests and operator tooling.
Architecture owns this contract; independent Security/QA approve exact evidence
and implementation. Product & Delivery owns production execution and release.
This is a bounded addition to the cash-panel correction, not activation work.

## Outcome and first scope

An invoice whose historical export attempts are proven sandbox-only may become
eligible for staff full-cash confirmation after a fresh production absence check.
Do not claim that sandbox export never occurred. Preserve that outcome's original
ambiguity and every prior attempt/error/environment field.

Initial reviewed candidate only:
- Tenant `828acd84-38bf-4a66-8fa1-cdf076f4e241`.
- Invoice `8963d01b-9417-47f5-8799-00d7563afc0f`, `INV-828ACD84-000020`.
- Outbox event `40c58a01-0a2e-4c35-a3b8-1b2adf068ae6`.
- Production confirmation realm `9341456094535202`.

These identifiers are an evidence-review target, not permission to assume its
current eligibility. Exact status/count/fingerprints must be verified at apply.
Additional invoices require their own complete independently reviewed manifest;
shared customer/shop or a similar error is not sufficient.

No migration, activation, fee, payment status, balance, reservation or invoice
policy mutation during review application. No invoice is marked paid. Actual
payment remains exclusively the existing staff full-cash confirmation action.

## Proof boundary

The reviewed evidence must cover every possible execution of every attempt for
the exact event: deployment intervals, explicit sandbox accounting environment,
source confirming accounting endpoint selection honors that environment, and
the association between the event and its attempt chronology. Include overlapping
old worker lifetimes or alternate executors if applicable. Missing intervals,
production execution or unknown provenance cannot qualify.

The last sandbox Customer GET 403 corroborates only that attempt. The successful
current production DocNumber query returning no records is supplemental evidence,
not a substitute for full provenance or the confirmation-time absence check.

## Audited event marker

Add only this nested key to the existing event payload:

```text
cash_nonproduction_review = {
  schema: "db048-sandbox-cash-review-v1",
  tenant_id, invoice_id, event_id, event_type,
  event_status, attempt_count,
  original_history_sha256,
  observed_environment: "sandbox",
  confirmation_environment: "production",
  confirmation_realm_id,
  evidence_manifest_sha256,
  reviewed_at, reviewer
}
```

Use shared `sandbox_cash_review_history_digest(event)` and
`validated_sandbox_cash_review(event, invoice)` equivalent helpers. The original
history digest covers all event columns and original payload values, excluding
only the ordinary metadata-update timestamp and this exact marker key. Normalize
timestamps/UUIDs/decimals consistently for stable PostgreSQL round trips. Preserve
nulls, original payload, ambiguity, last error/response, event type, status, count,
aggregate identity, provider IDs, lease fields and attempt timestamps.

Validation checks exact event/invoice/tenant binding, supported schema, exact
environment literals, nonempty realm and evidence digest, bound status/count and
current original-history digest. Reject malformed markers or any drift; do not
silently accept a marker on a different event. A provider success, provider object
ID, active lease/processing state, changed payload or newly recorded attempt is
not cleared by this exception. Any other financial event must independently pass
existing cash requirements or its own valid reviewed exception.

The marker is trusted administrative metadata installed only by reviewed operator
tooling. Do not accept it from staff/customer payment request DTOs. Hashes bind
evidence and drift; they are not a replacement for operator authorization.

## Eligibility integration

Keep all existing cash staff/tenant/lifecycle/positive-full-principal checks,
zero confirmed/pending/refund/credit amounts, zero event sequence and absence of
historical payment/attempt/accounting-link/ledger rows. Preserve existing invoice
QBO ID/synced timestamp, cash_export_review_required and Zelle-pending denials.

Only a valid reviewed sandbox event can bypass its historical export ambiguity
denial and the requirement that its original environment match production. It
does not bypass other cash checks, claim provider success or authorize export.
Historical export hold remains unchanged and is not itself a cash prohibition.
Email delivery retains its existing nonfinancial treatment.

Apply the pending/historical-money safeguards through the complete
`supersedes_invoice_id` ancestry, not only the replacement invoice. Preparation,
operator application and cash confirmation must inspect the same tenant-bound
ancestry and fail closed on missing, cyclic or foreign-tenant ancestors. An
ancestor's unresolved reservation, payment/attempt history or related financial
evidence cannot be bypassed by issuing a replacement or reviewing only its export
event. In particular, the preserved parent reservation of $232.48 remains a cash
blocker; this review never expires, releases or transfers it.

Never set `cash_no_dispatch=true`, clear `cash_export_ambiguous`, rewrite original
realm/environment, reset attempts, delete events or revive a dead/suppressed event
to obtain eligibility.

## Confirmation-time production verification

The full-cash service acquires its existing settlement -> invoice -> outbox locks
and revalidates the marker and all original cash conditions. For every reviewed
sandbox exception, it MUST perform an absence check even if another legacy flag
would otherwise skip provider lookup.

Require the current connected tenant account's realm to equal the marker's exact
production confirmation realm. Verify effective accounting request environment is
production; never query sandbox and call that production absence. Use the existing
safe token refresh and GET-only lookup for both full invoice number and legacy
21-character truncation (deduplicate if identical).

Any matching invoice, malformed response, unavailable token/provider, environment
or realm mismatch, marker drift or other unresolved financial event aborts cash
confirmation with no receipt/payment/local-cash policy change. Do not fall back
to historical absence evidence or guess from a 403. A successful absence check
authorizes only continuation into existing full-cash receipt logic in the same
serialized operation; it does not enqueue QuickBooks writes.

## Individually reviewed local-void ancestors

A cancelled ancestor can have a local `quickbooks_synced_at` timestamp and
succeeded sync/void events even when the deployed cancelled/no-QBO-ID branch
returned an empty result without an invoice write. These fields are not blanket
permission to ignore accounting history. Recognize this case only through an
independently reviewed `db048-local-void-ancestor-review-v1` proof.

Store such proofs as nested `ancestor_reviews` in the active event's
`cash_nonproduction_review` marker. Do not modify ancestor events, timestamps,
statuses, payloads or accounting policy. Bind the exact ordered supersedes chain,
including the active invoice's parent ID, and for each approved ancestor:

- Exact tenant and invoice ID; invoice number and complete relevant state
  fingerprint, including cancelled lifecycle, void timestamp, null QBO invoice
  ID, voided sync status and preserved synced timestamp.
- The COMPLETE financial-event ID set and original-history digest of every
  event, including status, count, provider IDs and lease evidence.
- Specific proof schema, production confirmation realm and evidence-manifest
  hash covering the reviewed local-no-op execution and all earlier attempts.

The proof must establish that the deployed call path completed through the
cancelled/no-ID local return before any invoice write. Current cancelled state
plus succeeded events with null provider IDs is insufficient on its own. Earlier
attempts must also be accounted for; complete reviewed sandbox-only provenance
can exclude production execution without claiming no sandbox invoice existed.

Preparation, application and confirmation re-resolve the whole ancestry and
require exact chain, state and event-set equality. Unlinking/replacing an ancestor,
adding an event or changing evidence invalidates the proof. Missing, cyclic or
foreign-tenant ancestry remains denied. No automatic addition of unreviewed
ancestors is permitted.

Only inside this ancestry review may valid proof explain a local synced timestamp
and succeeded null-provider-ID sync/void events. It does not relax the active
invoice's QBO-link/success checks. All ancestor pending/historical money, payment,
attempt, ledger, accounting-link and reservation exclusions remain unchanged;
the parent's $232.48 pending reservation still blocks cash.

Cash confirmation MUST freshly query full and truncated invoice numbers for
EVERY approved local-void ancestor in its bound production realm, in addition to
the active invoice. Any match, query failure, identity mismatch or proof drift
blocks cash with no receipt or policy mutation. This proof never clears or
rewrites `syncedAt` or original history.

## Operator application

Read-only preparation produces an exact manifest with target IDs, expected
history digests/status/count, proposed marker, evidence references and manifest
SHA256. Independent review approves that exact manifest before application.

Application must compare the approved digest, lock and re-read the exact tenant,
invoice and event, revalidate every invariant, then add only the marker key and
ordinary metadata-update timestamp. Preserve all other rows/columns. Commit once;
roll back on drift. An identical existing marker is idempotent; a conflicting one
requires new review, not overwrite. Emit before/after hashes and exact changed
fields. Tooling never calls a provider or records cash and never bulk-discovers
additional targets to mutate.

## Acceptance and gates

- Valid sandbox-only marker allows otherwise-clean staff cash eligibility while
  preserving historical hold, original ambiguity, dead status and all counters.
- Production/unknown/mixed provenance cannot produce an accepted review marker.
- Wrong tenant/invoice/event, altered original payload/count/status, malformed
  schema, provider success/ID and active lease all fail closed.
- Existing pending/historical money and all other cash denials remain effective,
  including money in superseded ancestors. Preparation, apply and confirmation
  reject the replacement while its parent retains the $232.48 reservation; no
ancestor financial state changes. Missing/cyclic/foreign ancestry fails closed.
- Confirmation makes fresh production GETs for both DocNumber shapes; absence
  passes, either match/error/invalid shape or identity drift records no payment.
- Marker presence cannot route lookup to sandbox, suppress lookup via
  cash_no_dispatch, expose administrative metadata to customers, or accept
  caller-provided proof.
- Operator dry-run/apply compare-and-swap and idempotent replay change only the
  marker/update timestamp. Adjacent financial and other-tenant fingerprints match.
- Existing unreviewed cash scenarios, noncash hold enforcement and genuine full
  cash receipt idempotency continue passing.
- Reviewed local-void ancestor succeeds only with exact nested proof and fresh
  production absence for active invoice AND every reviewed ancestor; changed
  chain/event set, real provider ID, unreviewed success or parent pending money
  remains denied. Ancestor rows remain byte-for-byte unchanged.

Independent gates cover exact code and exact operator manifest separately. Live
acceptance can show cash availability without pressing its confirmation. The user
records actual received cash; review metadata application is not payment consent.
