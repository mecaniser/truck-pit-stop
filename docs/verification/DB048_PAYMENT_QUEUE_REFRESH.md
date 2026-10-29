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
