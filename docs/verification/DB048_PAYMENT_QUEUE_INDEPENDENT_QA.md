# DB-048 payment queue refresh: independent QA

Date: 2026-10-29 (America/New_York)
Reviewer: fresh `payment_refresh_qa` agent; no implementation participation or edits.
Owner: Frontend & UX (root implementation session).
Branch: `codex/payment-queue-refresh`, base `81fac6dc`.

## Gate result

**GO for reviewed source and focused automated behavior. Runtime/release acceptance remains pending.** No source-level blocker was found in the final frontend diff. This is not a production release or a completed end-to-end QA gate.

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

No authenticated local browser journey was run: approved backend configuration is absent in this isolated checkout. The parent session records runtime preflight separately. No payment, receipt, provider reconciliation, accounting or production record was mutated by this reviewer.

Required before Done: authenticated desktop/compact affected-journey acceptance in a safely configured sandbox, protected PR checks, approved merge/deployment and runtime release evidence. The predecessor-payment warning for order51 is a separate reconciliation investigation; this cache fix does not clear it or establish that its prior payment is safe to disregard.
