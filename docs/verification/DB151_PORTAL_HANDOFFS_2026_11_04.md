# DB-151 customer portal handoffs

Owner: Frontend & UX. Lane: Fast UI. Branch: `codex/portal-review-next-steps`.

## Outcome

- Visit requests combine optional date and notes on one screen, then retain the explicit review/send boundary.
- Success explains shop review, checking the accepted arrival date before coming in, and that no start time is reserved.
- View request opens its exact authorized `request_id`. Reload retains it; unrelated reservation filters, empty-reservation messaging and new-booking action are omitted from this record view. Missing IDs show unavailable with All visits recovery.
- Pending customer invoices retain guidance to check this invoice and not send the pending amount again. Zelle allocations identify shop verification; other pending rails retain neutral confirmation wording.
- Legacy Zelle reports stay on the reported invoice instead of automatically advancing the invoice queue. Card-success navigation and all submission/payment contracts are unchanged.

## Verification

- 234 tests across 20 booking, appointments, customer-portal, Zelle and review projection files pass. Covers preserved reserve-time journey, request retry key/payload/date/notes, exact/missing request selection, failed reads, withdrawal, explicit transfer confirmation, uncertain retry, and legacy queue retention.
- Production frontend build, shared controls check, changed-source ESLint and diff whitespace check pass.
- Real isolated browser customer request `3b087b68-10f7-4aec-a621-7d9c2a36b4df`, reference `VR-B948DD870AB8`: one submitted record with notes, direct portal destination/reload, matching Shop Work review reference/notes, staff Start review reflected on customer record, customer withdrawal reflected as withdrawn.
- Real isolated manual report of $100 created attempt `1e211883-403a-4038-b209-bdb329d7b026` on invoice `abf8cc92-1a16-4aa0-80ff-36f9eb28593e` / BOARD-INV-1. Existing $168.44 pending plus new $100 = $268.44 pending, available $0. Invoice stayed open and retained guidance after reload. Shop Work link selected that attempt's canonical invoice and showed its $100 pending review and sender. No receipt confirmation, bank transfer, card charge, accounting write or production mutation performed.
- Shop Work had zero active jobs throughout. After withdrawal, zero pending visits: review task disappears after refresh and Service visits shows no pending requests; payment reviews remain.
- Desktop 1864 and phone 390 request/payment layouts inspected. Phone request has scroll width 390. Temporary emulation restored. Local evidence: `output/playwright/portal-next-request-mobile.png`, `portal-next-payment-mobile.png`.
- Initial test launch used repository root instead of frontend configuration; corrected. Existing request-title/step assertions updated and selected-record JSX syntax corrected before passing checks.

## Runtime receipt

2026-11-04: Vite5298 PID97016, this worktree/frontend, startup037f7a67 on `codex/portal-review-next-steps`; changed rendered text verified. API8198 container `db151reviewboard-api-1` has this worktree/backend read-only bind, PostgreSQL `dashboard_lifecycle_disposable`, isolated Redis, readiness passes. Existing5173/8000 untouched. Synthetic payment fixture explicitly enabled settlement gates with fake account/realm and unusable provider tokens to exercise the manual report; no real rails or provider credentials. Container re-created only for this fixture, source mounts/readiness rechecked, browser verified after restart. After reconciling main0b9dfec5, applied its additive201_customer_payment_profiles migration only to this disposable database and restarted the same API/Vite sources; no reseed. Focused tests rerun with main pass234; customer request/payment rendering rechecked.

Status: locally verified; [PR781](https://github.com/mecaniser/truck-pit-stop/pull/781) open; protected CI is the remaining integration gate. No release authorized for this task.
