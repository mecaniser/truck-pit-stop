# DB-139 shared ETS invoice context

2026-11-01. Accountable owner: Backend & Integrations. Branch: codex/ets-shared-billing. Base: 9d72b777. Status: local implementation/acceptance passed; protected CI and release pending.

## Outcome and contract

All related imported operations resolve one canonical invoice across the full tenant-scoped job group. Paid/partial/unpaid and remaining balances are invoice context, explicitly labeled Shared ETS invoice, including the invoice-owning row. A suffixed/off-page owner works. Exact job/customer/vehicle identity, unique supported invoice and existing fresh source evidence remain mandatory. Missing, ambiguous, stale, mixed, deleted or refunded evidence holds unverified. No migrations, invoice/payment writes, reassignment, importer change, financial export or aggregate change. Contract: ../contracts/db139-shared-ets-billing.md.

## Verification

125 focused backend tests pass (23 new real SQLite/API cases); 152 frontend tests pass across ledger46, billing23, page5 and panel78. TypeScript/Vite production build passes. Changed-source ESLint has zero errors and two preexisting RepairOrdersPage hook warnings. Diff integrity passes. Independent source/security and automated QA review independently reproduced125 backend and74 frontend tests, GO with no blocking findings.

Signed-in actual local browser: six fictional related rows show paid $0.00 remaining, partial $434.41 and unpaid $534.41 consistently in list and detail. Partial example's invoice belongs to -2 while the unsuffixed operation correctly displays it. Popover explains ownership/count-once context and supports Escape. Native rows have no imported status. Day/Night desktop1280 and mobile390 checked; mobile list/detail document width390 and scroll width390. Initial Night new ledger text used a day-scoped secondary color; corrected to existing --db-ledger-text, verified computed rgb(246,248,251) on rgb(17,31,51). Existing unrelated Night detail content surface inconsistencies are outside this change. Fictional invoice/payment counts after acceptance remain3/2 and totals1603.23/634.41. No production records touched. Browser captures inspected in task output; no public/customer data used.

## Runtime receipt

2026-11-01 local runtime: frontend http://127.0.0.1:5202 PID31770 cwd this checkout/frontend; backend http://127.0.0.1:18021 container dieselbridge_api_ets-shared-billing mounts this checkout/backend. Direct/proxied /health/ready200 database/Redis healthy. Branch/base badge and rendered changed source corroborate alignment. Backend uses isolated local postgres DB truckpitstop_db139_shared (cloned fictional DB042 QA database), schema196_historical_owner_self_review matching source; no migration. Added only fictional ETS fixtures and local test-account settings. Approved canonical local env referenced directly, not copied; synthetic shop binding only in this container, Redis11, no worker started. Existing shared5173/8000 and other task servers preserved. User approved isolated ports; newly occupied5201/8021 required5202/18021, communicated. Local URL aligned and browser-verified. Chrome extension timed out; IAB completed acceptance. Temporary viewport override reset.

## Release boundaries

No merge/deploy or production financial change performed. Protected CI/PR state recorded in board. Rollback is application code only; no data migration/backfill. Production acceptance must verify actual sibling rows after authorized release. Importer consolidation remains separate and held; this display correction does not mark parent B4 complete.
