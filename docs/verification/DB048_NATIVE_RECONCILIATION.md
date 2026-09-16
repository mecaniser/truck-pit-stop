# DB-048 native payment reconciliation

Owner: Backend & Integrations (root). High-risk payment lane. Intake 2026-09-16.
Branch: `codex/native-payment-reconciliation`, base `49c891239e5fb146f4bc1a756a697dcd905a25e6`.

## Acceptance and contract

Architecture audited confirmation/failure, refund/consent/manual resolution, legacy invoice preparation, card maintenance and cross-invoice credit/dispute writers. Inverse row-lock order exists on the base. Invoice-only locking cannot protect cross-invoice credit operations.

A tenant-scoped PostgreSQL transaction advisory try-lock must precede financial row locks, autoflush or mutation. Tenant identity is discovered with nonlocking tenant-filtered reads, then protected objects are refreshed and state/version/idempotency checked. Nested acquisition is transaction-scoped and reentrant; ownership must not survive commit/rollback. Contention returns a retryable conflict to API callers and defers workers. Batch work must avoid cross-tenant lock-order inversions. This serializes concurrent financial mutations within a shop, including any existing provider IO held in the transaction; independent shops remain concurrent. Existing authorization and API payload contracts remain mandatory. PostgreSQL testing exposed a preexisting cross-invoice credit-link integrity mismatch. Migration147_credit_link_identity replaces only the attempt/invoice identity guard with an exception for a proven applied → issued → overpayment → source-attempt chain belonging to the same tenant/customer and target invoice. All other original trigger guards remain unchanged. No financial-policy change.

Required evidence: actual two-session PostgreSQL service tests for lazy creation, confirmation/failure/expiry, refunds/credit consent/manual resolution, credit overspend, worker/API contention, stale state, idempotency, tenant negatives and lock release. UI must prohibit competing resolution submissions, reject stale callbacks across invoice/dialog changes and preserve drafts. Independent QA/Security follow implementation. Protected CI, exact API/worker deployment and browser/read-only production acceptance precede completion.

## Runtime and release baseline

Local runtime controller aligned root checkout to current branch/base on 2026-09-16; frontend5173 and API8000 healthy, source roots agree, existing populated database and migration142 preserved, provider sandbox configuration unchanged. Local browser session expired; user sign-in requested while implementation continues. No rendered native acceptance claim yet.

Production baseline verified via Railway: API/UI deployment8091863f-6a04-4d9f-969a-f36e9a03a52e and worker3169a6c7-c9fe-49a7-92a5-f5e4560e6397 both SUCCESS at49c891239e5fb146f4bc1a756a697dcd905a25e6. No open PR at intake. Older native branch and uncommitted board notes preserved. Prior receipt/PDF and reporting releases already included in main.

Rollback: redeploy matching prior API/worker49c89123 if new errors, persistent contention, stalled outbox or incorrect state transitions appear. Retain migration147 for application rollback; downgrade refuses while valid cross-invoice links exist. Migration changes validation only and does not rewrite payment records. Apply before matching app/worker release. During mixed-version rollout the new mutex cannot guarantee serialization against old writers; complete both service rollouts and retire old instances before claiming protection. Never create real charges/refunds/credits, change production invoice state or send customer notifications as verification.

## Evidence

Owner actual PostgreSQL races12/12 and credit-link identity1/1 pass on isolated scratch DB migrated142→147. Negative link cases reject wrong financial type, unrelated/issued record, wrong target, foreign attempt/tenant and realm. Independent QA reran13 PG tests and98 frontend tests: GO for scoped working diff; owner frontend147 tests, TypeScript and lint pass. Independent Security confirms migration preserves original function and changes exactly one guard, but NO-GO pending reminder stale writes, guest post-lock validation, QBP token-refresh revalidation, and Stripe customer hidden commits. Implementation owner correcting all four; release gate remains open.

Root browser acceptance used an explicitly synthetic fixture on existing5173 with all requests intercepted and unknown requests blocked. InvoiceA pending cash response → switch toB → delayed response leaves B unpaid222.00. Close/reopen A also ignores previous session callback. Refund and credit each disable both forms while pending. Compact viewport actual433px has scrollWidth433; Escape restores focus to OpenA. Temporary fixture removed; no backend request, provider or customer send. Signed-in real local journey remains pending expired session. Production acceptance/CI/merge/deploy pending.


Broadened PG checks found old blocking assertions incompatible with intentional retryable try-lock behavior; tax/fleet tests now require bounded invoice_busy followed by correct stale-version or duplicate-instrument rejection after retry. Customer-tax PG suite has four baseline failures independently reproduced from archived49c89123: three negative assertions expect a custom message but the existing FK rejects correctly; customer merge attempts to delete a customer still referenced by immutable tax audits and is rejected. These untouched baseline failures are not cleared by this payment change; customer-merge follow-up remains separate. QBP component suite requires its separate fixture variable and was skipped in the broad DB048 run.


## Implementation handoff and candidate gate

Backend source frozen after the four Security findings were corrected. Coverage: settlement/attempt/refund/credit services; cash/tax/charge changes; authenticated/guest legacy entries; invoice/repair-order lifecycle; provider configuration/retries; Stripe/QBP finalization, gross accounting, dispute/reversal; backfill and workers. Busy outbox dispatch defers without consuming retry budget. Credential/customer helper commits now require reacquisition and state/version/lifecycle revalidation. Reminder sends retain the financial mutex while notification logging uses its own session.

Owner grouped backend runs:213 core,70 legacy workers/finalization/access,45 activation/portal/reminder with1 existing skip, then11 focused provider-helper/reminder regressions passed (overlapping groups, not a unique total). Actual PostgreSQL tax/charge/fleet12 passed with updated contention expectations; native races12 + credit link negative1 passed. Security provisional source GO after corrections and independent18 tests; final frozen-SHA approval pending. Browser synthetic acceptance passed; signed-in local session remains unavailable. Local migration142→147 applied and schema preflight passed; existing financial records preserved.
