# DB-151 customer portal handoffs

Owner: Frontend & UX. Lane: Fast UI. Branch: `codex/portal-review-next-steps`.

## Outcome

- Visit requests combine optional date and notes on one screen, then retain the explicit review/send boundary. Preferred-date input stays left-aligned with its label (desktop x335, width320) instead of inheriting centered shared-control alignment.
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


## 2026-11-05 current-main reconciliation

- Reconciled current main `82c95576640cd5027d0d2a30ef232ca86d808216` into PR781 in the isolated review clone. The only textual conflict was `docs/PROJECT_BOARD.md`; retained both histories. Original owner checkout and untracked evidence remain untouched.
- Compared every added/removed frontend line with the prior head64e0b6f3 delta against its basef8ffd880: the125 changed lines are identical. Current customer/guest payment design, EFS submission/resolution controls, and all main payment contracts are preserved. No production fix was needed during reconciliation.
- Backend, migrations, dependencies, GitHub workflow and critical test manifest are byte-identical to current main. The proposed PR remains the original13-file frontend/documentation scope. No backend suite execution is claimed for this frontend-only reconciliation.
- Changed-source ESLint passes for10 TypeScript/TSX files, shared controls check passes, production TypeScript/Vite build and diff whitespace checks pass. Build retains the existing bundle-size advisory; no build failure.
- Full current-main frontend result: 2,907 tests across255 files pass (155.69seconds). Logs retained locally under `output/frontend-main82-reconciliation.log`, `output/build-main82-reconciliation.log`, and `output/lint-main82-reconciliation.log`.
- Source review checked exact request selection, failed-read behavior, preserved uncertain-submit key/date/notes, request review/send boundary, pending summary guidance, legacy invoice-queue retention, and integration with main's quieter full/partial/Card/Zelle/EFS controls. Comprehensive frontend tests cover these current components together.
- No new desktop/mobile browser acceptance was attempted in this reconciliation turn. Earlier disposable runtime evidence is historical, not fresh acceptance of the82c95576 integration. Updated protected CI and any required final preview remain separate gates.
- No PR approval, merge, deployment, production mutation, feature activation or provider action. The earlier automatic-approval denial of merging781 remains in force; this reconciliation does not retry or bypass it.
