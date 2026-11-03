# DB-149 customer portal implementation review — 2026-11-03

Owner: Frontend & UX. Branch: `codex/portal-task-first-implementation`, based on `8582077ba3069e1e1ddbf1dd2d934d7ff80ca58a`.
Status: implementation and local acceptance review; [PR767](https://github.com/mecaniser/truck-pit-stop/pull/767), source commit `461cee28`. No merge/deploy authorization for this change.

## Acceptance and contract

- Today-first home for one truck and fleets; exact authorized vehicle IDs preserved across booking/history/back navigation; no inferred VIN or source-record joins.
- Common-needs discovery plus search and complete active service catalog. Stable Home/Repairs/Invoices/Vehicles/Account navigation on desktop/mobile.
- One account balance, one action per invoice; multi-invoice selection only for multiple eligible invoices, with pending reservations subtracted from selection totals. Unknown/failed financial reads never become zero or verified amounts.
- Complete pagination, identity-scoped query keys, cancellation signals; foreign/missing/ambiguous vehicle choices fail explicitly. Account-level invoices and visits without a known vehicle remain labeled.
- Architecture approved additive slots `starts_at`/`timezone`: shop-local hours map to exact UTC instants; booking submits the returned instant. Existing confirmed/in-progress overlap semantics retained, including overnight spans. Slot service lookup requires current tenant, active, nondeleted service; foreign/inactive/deleted returns 404.
- Booking/payment/approval write handlers remain explicit user actions. No submissions during browser QA, no financial migrations/backfills/record edits.

## Checks

- Full frontend: 233 files / 2,554 tests pass with two workers. Initial full run had three staff-screen timeouts; those 15 tests passed independently and the full rerun passed without test-source changes.
- Additional history failed-read regressions: 2/2, against actual portal shell; failed initial/refetch invoice reads hide stale totals/PDFs, preserve repair rows, show unavailable/retry, recover correctly; no repair-total fallback or paid-YTD inference.
- Backend slot regressions: 11/11 (real SQLite admission negatives plus aware/naive/offset UTC overlap, boundary adjacency, overnight, DST, invalid zone).
- Matching declared dependency installation resolves the stale login typecheck error. Upstream login schema input/output generics already correct; default/checked/unchecked remember-me behavior verified without an unnecessary auth implementation change.
- Final focused frontend: 15 files / 114 tests pass. Production build, TypeScript and shared controls pass; changed-file lint passes with no new violations. Independent QA/Security source GO retained after final review.

## Actual application runtime and browser acceptance

Isolated implementation frontend `http://127.0.0.1:5173`, exact worktree `/tmp/portal-task-first-implementation/frontend`, API proxy `http://127.0.0.1:8014`. Dedicated compose project `portal-task-first-local`, disposable database `portal_task_first_disposable`, migration head 197. API backend is read-only bound to implementation source. Environment test, live provider credentials absent; unrelated port 8000 and main dirty worktree preserved.

Normal customer login, actual API reads, single/fleet home, selected vehicle filtering, common-needs and search, booking Date & time → Details → Review, Back, quote-review navigation, invoices, appointments, history, vehicles, and Account inspected at 1440px desktop and 390px mobile. Foreign-account vehicle URL displays Vehicle unavailable. No horizontal overflow on mobile; changed home actions 44px high. Temporary viewport override restored. No final booking, approval, cancellation or payment submitted. Payment providers remain disabled in this isolated API; provider checkout was not exercised.

Occupied-day slot GET initially exposed naive/aware datetime comparison 500. Fixed endpoint reverified against real PostgreSQL: Nov 4 returns 18 slots, 14 available, correct America/New_York starts_at values and actual occupied intervals excluded. Human-facing time labels use Eastern Standard Time.

Screenshots are actual application captures, not the prior prototype. Local review artifacts: `/Users/sergio_m1_promax/.codex/visualizations/2026/10/31/01a1903f-abe6-7d20-bd1a-7bf7df5f4a4a/portal-implementation/` (single/fleet desktop/mobile homes, desktop/mobile booking review).

Final read-only database fingerprint comparison after browser QA: all nine protected table hashes unchanged against before-journey baseline. Two appointments, invoices, quotes and settlements retained; payments, attempts, ledger entries, accounting links and provider outbox remain zero. Receipts local/private under `/tmp/portal-task-first-runtime/`: `runtime-receipt.json`, `slots-fixed-verification.json`, `final-browser-financial-receipt.json`. No production data was accessed or changed for this implementation.

## Release boundary

Preview approval is required before merge/deployment. Protected exact-head CI and production acceptance remain separate release gates. This item is not Done or deployed.

Lint scope: changed-line baseline gate passes. Explicit whole-file ESLint across all edited/new TypeScript files additionally reports three unchanged pre-existing violations: ProfileSettingsPage catch-any lines111/291 and types/index.ts empty interface455. No new violations were introduced; those unrelated lines were preserved.
