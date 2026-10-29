# DB-048 payment queue refresh: independent QA

Date: 2026-10-29 (America/New_York)
Reviewer: fresh `payment_refresh_qa` agent; no implementation participation or edits.
Owner: Frontend & UX (root implementation session).
Branch: `codex/payment-queue-refresh`, base `81fac6dc`.

## Gate result

**GO for the frontend cache-refresh implementation, focused automated behavior and independent fixture runtime acceptance.** No blocker was found for this frontend-only change. Production release/provider acceptance remains separate.

The review covers `StaffSettlementDialog`, `refreshPaymentViews`, the two existing manual-payment handlers in `RepairOrdersPage`, and the existing `payment_received` WebSocket handler. It includes the new workspace-refresh tests and expanded WebSocket regression. No API, provider, permission, payment-state transition, migration or tenant contract changes are present.

## Evidence

- Independently ran five focused suites: **59/59 passed** (`payment-workspace-refresh`, `staff-payment-choice`, `settlement-response-order`, `full-cash`, `useWebSocket`).
- New active-query integration regression observes queue, daily workset, daily value, overdue list, status-count, order-value and invoice projections refreshing after a later settlement query confirms payment.
- Partial and pending settlement reads retain server-provided open membership; a failed status read does not remove the row. No optimistic paid/queue update was added.
- Existing full-cash tests cover confirmation and failure/idempotency behavior; existing staff-choice/response-order tests cover delayed older summaries and wrong-invoice safety. The dialog retains its mounted/invoice/version guards before accepting state.
- The helper's prefixes match the actual page query keys, including nested value-summary/status-count queries. Inactive queries become stale for navigation; active queries refetch under existing React Query behavior.
- Both accepted mutation responses and later query/WebSocket settlement results flow through the dialog's accepted `current` state. Parent callbacks also refresh the workspace projection when the detail query is disabled.
- With the payment dialog closed, the expanded WebSocket regression confirms action queue, daily workset, list/count/value projections and the affected order workspace/detail/invoice refresh. Another order's workspace is not invalidated by the targeted order-ID path.
- Backend source confirms existing Stripe, QuickBooks and manual finalization use `broadcast_payment_received` with invoice/order identifiers. The frontend extension uses that existing event contract.
- Legacy manual recording and pending-Zelle clearing use the shared helper; existing success/failure semantics are retained.
- `git diff --check` passed. Changed-source ESLint has no errors; two pre-existing `RepairOrdersPage` hook warnings remain.

## Limits and next gate

Initial source review did not include a browser journey. The independent fixture runtime acceptance below supersedes that initial limit. Approved backend configuration remains absent, so no real full-stack or provider acceptance is claimed. No payment, receipt, provider reconciliation, accounting or production record was mutated by this reviewer.

Required before Done: protected PR checks, approved merge/deployment and production runtime release evidence. The desktop/compact frontend affected journey is accepted by the fixture runtime checks below. The predecessor-payment warning for order51 is a separate reconciliation investigation; this cache fix does not clear it or establish that its prior payment is safe to disregard.


## Independent fixture runtime acceptance — 2026-10-29 16:22–16:25 EDT

**Runtime QA GO for the changed frontend interaction on exact candidate `03353c58fc793dd666f9a3fc47537c37b6e7fce2`.** The implementation checkout was clean before temporary QA harness/artifacts were created. This acceptance uses current application source and existing API contract fixtures; it does not require or imply a real provider charge or a production payment mutation.

### Runtime alignment and boundaries

- Read and applied the mandatory `dieselbridge-local-runtime` skill before browser QA. Intended branch/root: `codex/payment-queue-refresh`, `/Users/sergio_m1_promax/.codex/worktrees/payment-queue-refresh/truck-pit-stop`.
- Shared frontend5173 PID56097 and backend8000 PID58770 were corroborated by commands and cwd as belonging to the unrelated `a2-shop-work-aging` worktree; neither was changed or stopped.
- Explicitly approved isolated split: Vite frontend `http://127.0.0.1:5181` from this candidate; every `/api/v1/**` request fulfilled by Playwright route fixtures and `/api/v1/ws` fulfilled by the fixture WebSocket. External font assets were stubbed. The frontend proxy origin was explicitly set to `http://127.0.0.1:9`, so an interception miss could not reach the shared API or production.
- Vite PID69199 and later PID70197 command/cwd were verified against the candidate frontend directory. HTTP200 and served `refreshPaymentViews.ts` were checked, including all four changed query prefixes. Final run4's runner-owned Vite PID70773 launched the same config/source and exact unchanged candidate. Each runner stopped its isolated Vite process automatically when finished;5181 is no longer serving after completion.
- Database identity/readiness and migration execution: **not applicable to this intentionally fixture-only runtime**. No backend was started, credentials copied, database seeded/migrated, tenant flag changed or external provider called.
- Runtime classification during the accepted run: **aligned and browser-verified fixture runtime**. The ordinary real full-stack checkout remains unavailable without approved backend configuration; that is not a blocker for the accepted frontend-only cache change.

### Executed acceptance

Final private harness run4: **4/4 Chromium browser tests passed**, zero retries.

1. Staff Zelle confirmation/overpayment desktop1440×900: actual confirmation flow, current excess-payment notice and accounting-pending display, focus trap and focus return pass.
2. Same staff confirmation at390×844: focus and containment checks pass.
3. Daily Ready-to-Close cash confirmation desktop: initially one RO at `$780.00` work value; one fixture cash receipt returns confirmed paid settlement; active daily-workset and value-summary endpoints are re-read; the RO disappears from the queue and work value becomes `$0.00` without reload; paid invoice detail remains visible.
4. Same daily confirmation at390×844: paid dialog is shown, then returning from detail to Ready-to-Close shows0 orders and `$0.00` work value, with Closed Today1. Queue and total re-read counters each exceed their initial read; only one fixture cash confirmation is submitted.

All four final tests assert no page errors, failed requests, unhandled fixture routes or browser-console errors. Desktop/mobile horizontal-overflow checks pass. Existing focused component/WebSocket suites separately prove partial/pending/failed responses retain server membership and later provider/status refresh propagates to queue caches; source review confirms no financial state-transition or authorization contract changes.

### Fixture maintenance discovered during QA

The repository's existing two staff E2E cases initially failed because they expected old `$50.00 is unapplied` copy. Current source rendered the successful confirmed-payment state and the newer `$50.00 exceeds the invoice balance…` notice. The old fixture also omitted newer read-only communications, recommended-work, checklist and operation routes. A private copy updates only that assertion/fixture coverage and adds the exact queue regression; the production implementation and committed test files were not edited by this reviewer. Intermediate harness attempts also corrected mobile navigation to reflect the existing detail-only compact layout. None of these intermediate failures established a product regression.

### Artifacts and repeatability

Private harness retained (untracked, do not include in production commit):

- `e2e/.qa-db048.config.ts`
- `e2e/tests/.qa-db048-queue.spec.ts`
- Existing root e2e dependencies are linked via local `e2e/node_modules` for this run.

Run from `e2e/`:

```sh
DIESELBRIDGE_API_ORIGIN=http://127.0.0.1:9 ./node_modules/.bin/playwright test --config .qa-db048.config.ts --grep 'DB-048 staff|QA queue' --output ../output/playwright/db048-independent-2026-10-29/run4
```

Reviewed screenshots (local synthetic data only):

- `output/playwright/db048-independent-2026-10-29/queue-paid-desktop.png`: empty Ready-to-Close queue,0 total,$0.00; paid invoice retained.
- `output/playwright/db048-independent-2026-10-29/queue-paid-mobile.png`: Ready-to-Close0,Closed Today1,$0.00 work value.

The predecessor-payment reconciliation warning for order51 remains deliberately unchanged. This runtime acceptance does not attest that its earlier pending provider attempt is safe to clear.
