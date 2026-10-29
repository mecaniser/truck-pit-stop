# DB-048 payment workspace refresh

Owner: Frontend & UX (root). Branch: `codex/payment-queue-refresh`, base `81fac6dc`.

Acceptance: accepted settlement updates refresh active Ready to Close/action/daily queues, overdue/all repair-order lists, counts and value summaries, plus the affected invoice and order workspace. Partial/pending payments use server membership. Failed, older and wrong-invoice responses cannot falsely close the row. Inactive caches become stale for navigation. Provider confirmation works through the existing payment_received event with the dialog closed.

No API, authorization, tenant, financial state-machine, migration, provider dispatch or invoice lifecycle contract changes. The helper invalidates projections; it never submits or retries payment and never guesses paid status.

## Verification

- Owner: 75 tests across payment workspace refresh (3), staff payment choice (15), full cash (9), settlement response ordering (1), repair-order request/lifecycle regressions (16) and websocket (31). All passed; the workspace suite also explicitly rejects older and wrong-invoice status data after confirmation.
- TypeScript, production build and changed-source ESLint pass. Two existing RepairOrdersPage hook warnings remain.
- Independent source/test gate: 59 tests passed; see DB048_PAYMENT_QUEUE_INDEPENDENT_QA.md. Authenticated sandbox acceptance is still required.
- Production page was inspected read-only. Scoped database investigation used SET TRANSACTION READ ONLY, tenant-constrained invoice ancestry and rollback. A predecessor card reservation remains pending with unknown provider outcome; no receipt, invoice, attempt, ledger, outbox or provider state was changed. Private row details are excluded from this committed record. The current refresh fix does not resolve that separate reservation.

## Runtime receipt — 2026-10-29 America/New_York

Intended checkout: `/Users/sergio_m1_promax/.codex/worktrees/payment-queue-refresh/truck-pit-stop`; branch `codex/payment-queue-refresh`, base HEAD `81fac6dc`, only task-scoped edits. Initial frontend5173/backend8000 listeners absent. Controller dry-run before implementation refused missing approved `backend/.env` and frontend dependencies. Existing frontend dependencies were subsequently linked for automated checks; no credentials copied. No application service, database, provider setting or migration changed. Later controller invocation correctly refused the dirty target.

`http://127.0.0.1:5173` and `http://127.0.0.1:8000`: **blocked/mismatched**; backend database identity and authenticated sandbox browser acceptance cannot be established without approved worktree backend configuration. Build/component evidence is not a locally served or deployed feature claim.

Next: configure approved sandbox, execute desktop/compact payment acceptance with fixtures, protected PR CI, then authorized merge/deployment and changed-journey verification. Keep the predecessor provider reconciliation as an explicit separate gate; do not clear an unknown card outcome because its deadline passed.

## Authorized release — 2026-10-29

PR675 merged20:24:32UTC as4457525009a53bfc7a569418c632f5f47706cc6b. Seven checks passed on03353c58 in40942244389; merge tree equals checked tree. Independent final frontend runtime4/4 passed desktop/390px payment and daily queue/value refresh in isolated5181 fixture with proxy127.0.0.1:9. Evidence is in updated independent QA receipt and private screenshots. Railway Web71f42066-2925-41a6-92e5-3c8bcf2cdc05 reached SUCCESS; both www and api/build-version serve exact44575250, readiness database/Redis OK. Signed-in existing Chrome Alexandru/Truck Pit Stop session loads deployed selected Ready-to-Close workspace and payment dialog. Original in-app session returned to login; existing Chrome was used without copying credentials. Chrome CDP input timed out; native supported controls completed live inspection. No real payment submitted.

Original old reservation was separately retired through an explicitly authorized, independently reviewed owner-attested test transition; it did not contact a provider or record payment. Final live dialog shows noncash choices admitted. Cash still rejects preserved test history under its stricter ancestry rules; that newly discovered cash-only outcome is tracked separately in DB048_REVIEWED_TEST_CASH.md and is not hidden by this refresh completion. Local runtime5173/8000 remain owned by a2 and untouched; full local backend remains unavailable, fixture/runtime/production evidence are distinct.
