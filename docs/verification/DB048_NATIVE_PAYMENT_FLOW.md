# DB-048 native DBN payment flow

Owner: Backend & Integrations, native payment task. High-risk lane.
Branch: `codex/native-dbn-payment-flow`, base `648dfbb05e0f6a25ca198f07f12176988c605ace`.

## Source handoff

Product explicitly transferred selective native source ownership from
`truck-pit-stop-invoice-details` (`fafee4819b3d0488da2ac96d43cbc18cbd117203`).
Original checkout is untouched. Adopted saved labor/parts DTO/service/tests,
native disclosure within summary, payment-state labels, duplicate-credit guard,
and refund/credit mutual pending locks. Legacy preparation endpoint, service,
action flag, API helper, and PrepareLegacyResolution remain excluded/ETS-owned.

## Staged acceptance matrix

| Stage | Required acceptance | Current evidence / remaining work |
|---|---|---|
| 1. Native issuance | NEW native RO, labor/parts/discounts, complete and approve work, atomic invoice with saved totals | Snapshot/supplies unit tests5 pass. Native finalization/issuance-to-cash regression37 pass. Real endpoint/browser fixture not created. |
| 2. Fees | ON applies/OFF zero; supplies use labor after labor discount, never parts; immediate save; stable rows; preserve explicit partial draft/tender | UI layout7/drafts22 pass, discounted-labor test passes. Signed-in native runtime acceptance pending. |
| 3. Payments | 0.01 through available; supported full/partial tenders; QBO/Zelle/Cash primary, More/ACH/EFS accessible; correct history/balance | UI76 total pass. Cash contract is full-only and disallows any prior attempt, including failed. Separate cash/noncash fixture invoices required. |
| 4. Recovery | Pending/paid/review labels; stale/version/idempotency safeguards; no duplicate collection/credit; tenant isolation | State UI and new duplicate-credit regression included. Settlement55 pass (including same-key replay/new-key duplicate credit regression); independent code-level QA/Security GO after pending-lock correction. PostgreSQL concurrency and real recovery E2E pending. |

## Contract findings

Architecture read-only audit: native path is POST `/api/v1/repair-orders`, add
labor/parts, override-start-work as authorized, admin-complete-work, then
approve-completion (atomic finalization/issuance). Existing fixtures are
`test_repair_order_finalization.py::_seed_review_order` and
`test_db048_cash_payment_timing.py::test_actual_invoice_issuance_and_email_then_cash`.

Noncash attempts use amount, rail, expected settlement version and Idempotency-Key;
confirmation/failure use attempt versions. Cash uses a separate cash-confirmation
contract with no amount. All noncash rails currently require configured card-provider
readiness. Sandbox environment values alone do not prove tenant/provider readiness.
Existing DB048 Playwright tests intercept APIs; they are presentation evidence only.

## Runtime receipt — 2026-09-12, approximately 17:10 America/New_York

Status: **blocked/mismatched** for native candidate at http://127.0.0.1:5173.
Controller identifies `truck-pit-stop`, `codex/db063-status-pipeline`, base648dfbb,
healthy=false because the target has intentional dirty work. Runtime owner explicitly
retains these ports for user review; no alternate is configured. Frontend PID23573
cwd is root checkout/frontend. API `dieselbridge_api_dev` bind mounts root backend
at /app. `/health/ready` returns200. Database identity is postgres /
`truckpitstop_db048_local_e2e_20260912`; controller head142_qbo_shop_activation.
This migration follows146_fleet_payment_rail; numeric order is not schema evidence.
Effective ENVIRONMENT=development; QBO Accounting and Payments both sandbox;
split payments enabled. No credentials copied or printed. No service restart,
migration, configuration/gate change, invoice creation, charge/refund/credit, or
provider call performed. Candidate rendering is unverified.

Runtime handoff must reconcile the retained status UI, exact candidate sources,
worker/outbox ownership and tenant/provider readiness before NEW native fixtures.
Issuance can queue notification/accounting work, so do not create fixtures against
an unowned worker runtime. Preserve existing database/volumes and sandbox settings.

## Delivery status

Local selected implementation committed in this branch; not pushed, merged or deployed.
No signed-in native browser acceptance and no PostgreSQL concurrency acceptance.
Runtime blocker owner: status-pipeline task, coordinated through Product & Delivery.
Next action: coordinate runtime handoff for stage1. Independent code-level QA/Security GO; this does not clear runtime or release gates.

Owner verification: backend97 total (snapshot/supplies5, settlement55, native
finalization/cash timing37); frontend76 (details3, staff16, settlement28, layout7,
drafts22); TypeScript and changed-source ESLint pass. Initial regression attempt
used wrong working directory and failed module resolution; rerun with the project
Vitest3 configuration. New pending test first exposed an inherited mock call,
corrected with per-test mock isolation; full settlement28 subsequently passes.
Independent review found asymmetric refund retry availability during consent;
owner added the symmetric pending disable and deferred-mutation regression.

Remaining acceptance: broader StaffSettlementDialog stale-response ordering is
unverified (late callbacks may replace local state). ETS DB-064 task
01a09773-db8c-7ba1-befd-385eb6ed9061 reserves transfer contracts separately;
canonical invoice/settlement writer lock ordering must be established by
Architecture before integrating transfer/legacy writers. No concurrency GO.
Runtime owner has no agreed window while the status-pipeline design review awaits
user response; its four-file passive UI patch is not approved for integration.
