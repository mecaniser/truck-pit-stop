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


## Independent gates at frozen application commit

`e794424a636e9d43a405f58363ce314050cbcdb2`: independent Security GO (all four findings corrected;2 helper-commit races and15 PG/reminder checks passed). Independent QA GO (13 PG +25 activation/helper/reminder checks; prior98 frontend tests apply to unchanged frontend diff). Existing SQLite fixture UUID monkeypatch contaminates mixed PG execution, so these suites run in separate processes. This is scoped code/isolated acceptance, not real provider capture or customer-delivery proof. Root synthetic browser evidence above remains separate.

PR398 opened; all six protected CI checks required. Runtime controller restarted clean candidate e794424a with migration147, ports5173/8000 healthy. Production browser staff session is available for post-deploy read-only verification even though local session expired. Application source is frozen; subsequent gate documentation does not change its source tree.


## Released 2026-09-16

PR398 merged17:47:06UTC as `da8fe7ed46c6da32c8fd6cfc6cbfda4f5d2ef6c7` after all six CI checks passed. Full backend1964 passed/88 skipped, frontend85 test files passed, protected browser smoke passed. Reviewed application e794424a and final PR head1e296acc differ only in gate documentation.

Railway API/UI `7956b4a6-5b41-473d-b7dc-4cddd7e1b4f2` and worker `ab617ad9-8b5d-4305-9813-979555aa1d4c` both SUCCESS at exact merge SHA. Old worker3169a6c7 is REMOVED. Production read-only schema preflight passed on new application (migration147). App readiness remained healthy with DB/Redis OK at22s and237s uptime; six records tagged error by log transport were inspected and are ordinary Uvicorn INFO startup/WebSocket messages. New worker connected to Redis and reports ready; no application startup exception observed.

Signed-in production after reload: orderTPS-828ACD84-000046 / invoiceTPS-828ACD84-000001 retains Paid in cash207.50 confirmed and0.00 outstanding/pending/available. Unpaid invoiceINV-828ACD84-000012 opens Record or review payment, balance41.42; View details shows labor37.50/parts0 and existing accounting review restrictions stay enforced. Escape closes dialog and restores Record payment focus. No payment, fee change, refund, credit, provider or resend action submitted. This is read-only production acceptance; real money capture and native automatic email are not claimed.

Shared root main is clean at merge SHA; managed local runtime aligned main/migration147 with populated database and sandbox preserved. Local authenticated session remained expired; synthetic rendered acceptance and production signed-in read-only evidence are recorded separately. Task checkout has been reconciled to identical backend/frontend source; old release notes were committed asf9a00119 and preserved in branch history. No uncommitted source changes remain. Unrelated preexisting customer-merge audit-FK defect remains the explicitly separate follow-up above.
