# DB-149 customer portal implementation review — 2026-11-03

## Current fulfillment handoff (supersedes the historical stages below)

Accountable owner: Frontend & UX. Branch `codex/portal-task-first-implementation`; [draft PR767](https://github.com/mecaniser/truck-pit-stop/pull/767). Current main8e1c264e is integrated. Preview only: no merge, deployment, production payment flag, real charge/refund, customer outreach or production financial-record change.

Frozen architecture: [two booking paths](../contracts/portal-verified-booking-prepayment-v1.md) and [operational fulfillment/application](../contracts/portal-booking-fulfillment-followup.md). Migrations198/199/200 are additive; destructive downgrade is refused. Original preview databases197/198 and unrelated8000 runtime remain preserved.

The service choice appears once: reserve a time with verified full payment, or request a visit without payment or a guaranteed start. Fifteen-minute server checkout holds expire only when proven unpaid. Unknown provider outcomes cannot start a duplicate charge. Staff can accept an arrival date, decline, withdraw or record actual check-in without turning an unpaid request into reserved capacity. Verified prepayment links to the exact tenant/customer/vehicle work order and applies immutably during genuine invoice issuance; the application, settlement, accounting tasks and publishing outboxes share the transaction.

Applications do not create another Payment, sale or cash receipt. Provider/account/configuration/realm/charge evidence and fresh locked balances are checked. Current itemized invoice economics must match the reviewed server hash. Applied amounts appear consistently in customer/guest/PDF/email projections. Invalid evidence exposes unavailable balances and suppresses payment controls. Definitive external refunds/disputes remain retained even when they require review; pending/unknown evidence is not treated as settled.

External bookkeeping is deliberately manual: exact receipt/application review tasks require explicit evidence and remain export-held even after acknowledgment. Fleet accounting snapshots fail closed rather than sending incomplete financial replacement data. Ordinary provider financial facts and unrelated invoices continue through the existing worker; held accounting prefixes are excluded before batch limits. The QBO existing-refund check uses provider GETs only; no refund initiation is included. An unreadable/unknown refund reference remains fail-closed and has no discard override in this change. This operational limitation must be reviewed before production activation.

### Final source checks

Full frontend245 files/2713 tests pass, TypeScript and production build/control check pass. Full disjoint backend partitions5557 pass/513 explicit skips (critical801/51, remaining4756/462), no failures, matching isolated Python3.11/Node22 image with network disabled. Skipped external DB/Redis/provider opt-ins are not live certification. Actual independent PostgreSQL: full/partial issuance and post-queue-flush atomic rollback3/3; strict missing/empty/mismatched charge binding5/5; prior application race, retained refund and dispute cases pass. Independent final source QA/Security GO:112 backend/52 frontend delta,18 ordinary-issuance/application regressions and54 booking result-display checks. Counts overlap. Exact-head hosted CI remains a separate gate; no local result is claimed as deployment evidence.

Runtime acceptance caught a real MissingGreenlet while email publishing accessed an expired relationship. The failed transaction left zero invoices/applications/settlements/notifications/outboxes; existing receipt and link were intact. Fixed by awaited relationship loading at each actual publication boundary. Real ASGI tests retain actual checklist, financial wakeup, QBO-hold and email queue helpers; only final external delivery is absent. Independent source review and actual browser retry passed.

### Actual application preview

Frontend5173 is owned source `/tmp/portal-task-first-implementation/frontend`, proxy8016. API uses frozen source and new fictional `portal_booking_fulfillment_final_qa` database at schema200, outbound provider access unavailable. Fresh canonical schema catalog matches migration200; all203 table fingerprints survived guarded schema alignment/restarts. No old fixture or production financial record was edited. Only explicit fictional fixtures and their normal workflow records were created; no card data entered/tokenized and no Pay button submitted. No mail worker/delivery or real provider call occurred.

At1440×1000 and390×1100: actual single/fleet customer login, Today-first tasks, selected fleet vehicle persistence, common-needs/search, one-time booking choice, optional-date no-payment request review, accepted arrival date, server reservation slot/review/held card form, saved confirmed state, and partial invoice payment choice checked. Mobile invoice has390px document width and44px amount/full/partial/continue controls. Reservation result includes saved service, exact authorized vehicle and shop-local schedule; missing details are unavailable.

Real staff UI linked and issued all three fictional prepaid scenarios:180 receipt applied180 to180 invoice leaves0;180 receipt applied180 to240 invoice leaves60;180 receipt applied100 to100 invoice leaves80 unapplied and0 due. No new charge. Customer Today shows only60 outstanding; partial invoice shows180 applied,60 due, and permits30 preview leaving30 after confirmation. Continue/payment was not clicked. Manual external bookkeeping remained pending; no fabricated acknowledgment/export success.

Actual screenshots live under `/Users/sergio_m1_promax/.codex/visualizations/2026/10/31/01a1903f-abe6-7d20-bd1a-7bf7df5f4a4a/portal-implementation/fulfillment/`: `customer-choice-desktop/mobile.png`, `customer-request-review-desktop/mobile.png`, `customer-reservation-checkout-desktop/mobile.png`, `customer-fleet-accepted-desktop/mobile.png`, `customer-partial-invoice-desktop/mobile.png`, staff application/result captures. Private runtime receipts are under `/tmp/portal-booking-fulfillment-qa-runtime/final/`, including publication rollback and source-aligned restart evidence. Screenshots use intentionally fictional shop/account/service text, not production copy or financial data.

| Before | After | Why |
|---|---|---|
| Unclear booking/payment authority | One familiar reserve/request choice after service | One meaningful decision, followed by the selected path |
| Payment success without useful visit identity | Saved service, exact vehicle and shop-local schedule | Customers can verify what they reserved |
| Prepayment could be charged again on the service invoice | One immutable applied credit and the true remainder | Preserve money and clarify what remains to pay |
| Mobile field/action crowding | Shared44px controls, bounded desktop checkout, no overflow | Predictable keyboard and touch interaction |

Guest print acceptance: the actual Print link opened the authorized inline application/pdf route, not the guest HTML. All three one-page Letter PDFs were downloaded and visually rendered; full/partial/excess applied totals and0/60/0 due match the portal. Guest full invoice has no Pay action; guest partial supports full60 or part30 with30 remaining after confirmation. No payment Continue action clicked. Runtime/PDF comparison also exposed an existing date-only due-date display shiftingNov3 toNov2 in America/New_York; the correction preserves the calendar day across Today, guest invoice and invoice history without changing stored dates. Initial pure-date fixtures did not cover the actual UTC-midnight datetime wire and GO was revoked. Final helper normalizes only legacy exact UTC-midnight Z/+00:00 with all-zero fractions; other timestamp semantics and paid_at are unchanged. Independent61/61 tests pass in each of New York, Los Angeles and Kiritimati. Real guest reload and Today now both showNov3 matching the PDF, with180 applied and60 remaining unchanged.

Final natural expiry: the real browser-created unpaid hold reached its unchanged server deadline2026-11-04T00:03:40Z. Actual desktop/mobile screens show Checkout expired and no card fields/Pay action. The registered expiry task then persisted expired_unpaid with exactly one expiry event and released the slot. Full203-table comparison changed only appointments and booking_payment_events; all existing invoices/applications/receipts/accounting rows remain identical and provider create/retrieve counters0/0. Receipt `final/actual-expiry-acceptance-private.json`. No clock adjustment or artificial early expiry. Final frontend protected manifest29 files/406 tests passes, full245/2713 passes, production build passes.

The historical stages below are retained as an audit trail. Their counts, runtime addresses and earlier activation blockers do not override this current handoff.

---


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

Integration: main advanced to `8e1c264e` (PR764). Merged into this branch preserving both board histories and the upstream logout/session changes. Only the delivery board conflicted; ProfileSettingsPage automatically retained both its scope-preserving navigation and upstream logout handling. Recheck integrated runtime, focused suites, build and exact-head CI before release.


## Superseding booking/payment handoff — November 3, 2026

The initial read-only UI acceptance above is historical. Deeper checkout review found a pre-existing simulated-payment handler. Its earlier GO was revoked and PR767 returned to draft. No simulation was submitted during review. The following implementation supersedes preservation of that unsafe contract.

### Acceptance fixed before implementation

- One choice after service selection: **Reserve a time** or **Request a visit**, retained on Back. A single known truck is not an extra decision; fleet scope stays explicit and authorized.
- Requests have an optional preferred date and no payment or reserved start time. They appear separately as awaiting shop confirmation.
- Reservations hold a server-priced available start time for15 minutes. Only verified full payment and a fresh authorized confirmed/paid/receipt snapshot permit “Time reserved.”
- Unknown payment outcomes prevent another charge. Refresh resumes the same reservation. Expiry releases only proven-unpaid capacity; late or uncertain money never silently reclaims a released slot.
- Exact tenant/customer/configuration/account/environment/amount/currency binding; inactive catalog entries cannot hide an existing receipt. Existing invoice settlement callbacks remain functional.
- Prepayments remain booking liabilities, separate from invoice sales. A linked repair order cannot issue or collect another full invoice while unapplied funds or unknown money remain. Credit-application and refund writers are outside this change; staff API exposes unapplied money for review.
- No real payments, real booking submissions, production financial edits, production configuration changes, merge or deployment during preview work.

### Current source and safety evidence

Architecture: [frozen contract](../contracts/portal-verified-booking-prepayment-v1.md). Additive migration198; no backfill. Booking payment capability defaults off, requires explicit tenant admission and eligible selected tenant payment configuration. QuickBooks Payments and Stripe Connect use bound provider evidence. No global Stripe fallback or unconditional confirmation endpoint remains.

Independent reviewer source QA/Security GO:117 backend focused tests,6 actual disposable PostgreSQL migration/race cases,55 frontend. Owner backend suite112 plus one additional actual PostgreSQL cancellation race pass. Provider adapter23 cases and invoice guard/cash/credit/pricing82 combined pass. Counts overlap and must not be summed.

Full frontend240 files/2613 tests pass with two workers. Focused booking/visits/QBO/login73 pass. Production build, TypeScript, controls and changed-line lint pass. Whole-file ESLint has three unchanged main-baseline violations in ProfileSettingsPage and shared types; no new violation. New booking safety suites promoted into the protected critical test manifest.

Database constraints enforce tenant-composite relationships, frozen snapshots/attempts/receipts/events and v1 paid-confirmation evidence. Application assertions additionally bind cross-row customer, amount, currency and exact configuration/environment. The latter are not claimed as a complete database cross-row constraint system.

### Current actual application acceptance

Aligned implementation frontend: `http://127.0.0.1:5173`, PID56652, `/private/tmp/portal-task-first-implementation/frontend`, proxy8015. API8015 uses read-only current backend source bind, test database `portal_booking_qa`, final migration198, isolated Docker network with outbound provider access unavailable. Original8014 database/schema197 and unrelated8000 remain preserved. Private runtime receipt: `/tmp/portal-booking-qa-runtime/final-launch-receipt.json`.

Normal customer login and actual API/browser journeys checked at1440×1000 desktop and390×1100 mobile: single-truck Today, fleet Today and selector, scoped search and service choice; one-time booking choice; request optional-date/details/review/send/visits; reservation slot/details/review/hold creation/card form; keyboard Next/Back focus; refresh recovers the same hold; a different customer sees Reservation unavailable. Mobile choice and checkout have no horizontal overflow; checkout actions measure44px. Final desktop recovered checkout is capped at640px rather than stretching card fields across the full page. Removed duplicate vehicle identity in service discovery.

Only fictional request/hold records were created in the explicitly disposable `portal_booking_qa` database. No card data was entered or tokenized, and no Pay button was submitted. Payment success/unknown/refund races were tested with mocked providers and disposable test schemas, not live provider certification.

Current captures in the existing local `portal-implementation` artifact directory:
- `two-path-choice-desktop.png`, `two-path-choice-mobile.png`
- `visit-request-review-desktop.png`, `visit-request-review-mobile.png`
- `reservation-review-desktop.png`, `reservation-review-mobile.png`
- `reservation-checkout-desktop.png`, `reservation-checkout-mobile.png`
- `final-single-home-desktop.png`, `final-fleet-home-desktop.png`, `final-fleet-home-mobile.png`

### Impeccable and Emil review

The original bounded Impeccable baseline was16/20; it is not a comprehensive payment-safety score. P0 simulated payment path replaced and independently re-reviewed. P2 keyboard focus corrected and actual Enter/Back transitions land on the next heading. P3 prototype CSS debt removed:16 unused class families and superseded mobile declarations; raw stylesheet reduced from21,177 bytes to roughly17KB. Existing tenant palette preserved; measured reviewed color pairs exceed AA normal-text contrast, without claiming formal accessibility certification.

| Before | After | Why |
|---|---|---|
| Booking choice repeated or unclear payment authority | One post-service choice; verified reservation and unpaid request | Familiar scheduling pattern with one meaningful decision |
| Keyboard step transition loses focus | Focus moves to the new heading on deliberate progression | Preserve position without stealing focus on refetch |
| Recovered card form spans the desktop |640px centered checkout; mobile full available width | Readable field lengths and a stable action area |
| Prototype selectors, touch-hover and duplicate vehicle text | Removed unused CSS, pointer-gated hover, one vehicle label | Reduce visual and maintenance noise |

No decorative entrance or repeated-action motion added. Press feedback is immediate; reduced-motion preference remains respected. This remains a preview and source-review result, not a merge/deployment or live payment-readiness claim.


Final runtime expiry acceptance: one additional near-expiry synthetic hold was created through the real reservation service with a test-process clock. The real expiry service persisted `expired_unpaid`, wrote its expiry event, and released the exact09:00 slot. Actual desktop/mobile screens show Checkout expired with no card form or Pay action; expired amounts are labeled Reservation total. Original browser-created hold remained byte-for-byte unchanged. QA final counts:2 appointments,1 visit request,3 booking events;0 payment attempts/receipts/invoices/settlements/payments/ledger/accounting/outbox. Provider create/retrieve counters0/0. Original8014 nine protected projected-column hashes match the pre-QA baseline. Private receipts: `expiry-final-receipt.json` and `final-browser-counts-receipt.json` under the QA runtime directory. Additional captures: `reservation-expired-desktop.png`, `reservation-expired-mobile.png`.

Independent final consolidated Impeccable/Emil delta review retained GO with no P1: desktop/mobile choice and checkout captures,640px checkout cap, vehicle duplicate removal and critical-manifest promotion. Review is source/isolated-runtime bounded; no live provider certification or release assertion.


Production activation limit: this repository currently has no appointment-to-repair-order linking writer and no booking-receipt application writer. The exact-linked-RO guard is independently tested, but it does not infer relationships for separately created repair orders. Therefore this preview is not evidence of a complete prepaid-booking-to-final-invoice accounting workflow. Production booking payment gates must remain off until explicit liability ownership and the reviewed link/application workflow are ready. No production flag was enabled. This is an activation blocker, not a hidden completed follow-up.


Final source handoffdc657801: protected backend715 pass/14 explicit skips; PostgreSQL7 pass; repeated task entry unit/real PostgreSQL2 pass and independent worker/runtime7 pass. Worker wrapper now uses existing process-local `run_async` so pooled connections survive repeated Celery entries. Critical manifest38 backend files; disjoint327 remaining. Exact CI41728886935 passed backend remaining4755/462 skipped, backend critical, frontend checks, migration graph, dependencies and Playwright smoke. Full frontend repeated the known Fleet account-switch test5000ms timeout; no new booking test failed. Narrow test-only correction replaces repeated global role walks with named account-panel queries and explicitly controls/awaits the deferred profile save. Exact save payload, session-epoch advance and no cross-account password POST assertions are strengthened, not skipped. Owner6/6 and fresh independent6/6 pass; no product-source or timeout change. Final commit CI must pass before release consideration.


Baseline57a6c41e exact CI41730483454: all7 checks pass, including full frontend after the deterministic account-switch regression correction and full backend. This clears that committed customer-preview baseline; it does not clear the newly identified operational fulfillment gaps. Follow-up Architecture contract freezes staff date-only request acknowledgment and immutable prepaid invoice application before implementation. No unpaid request becomes a reserved/paid appointment. Production remains off while staff operational fulfillment and accounting application are implemented and independently accepted.
