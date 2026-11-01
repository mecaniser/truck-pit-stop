# DB-135 customer balance correction — 2026-11-01

Backend & Integrations owns this financial read-path fix. Contract: [customer balance correction](../contracts/db135-customer-balance-correction.md).

## Evidence

- Original production discrepancy reproduced read-only: $2,674.97 combined paid-cash fee residue and historical ETS remainder.
- Final compiled PostgreSQL expressions executed inside a READ ONLY production transaction: native customer balance0, historical2058.12; equipment native0 each, historical1089.21/968.91. No application deployment, financial mutation or provider request.
- Backend balance, customer HTTP endpoints and existing Account regression:28 passed. Covers paid cash, unpaid/partial, completed vs pending/failed/refunded, optional fee tax, cancellations, drafts/internal, deleted records, immutable bill-to, tenant/customer isolation, stale projections, HTTP fields and sorting.
- Frontend panel22 and workstation28 tests pass; TypeScript, changed-source ESLint, production Vite build and diff check pass.
- Independent reviewer issued source/security and automated QA GO after original bill-to/historical hold/deleted-record findings were fixed. Final internal-order/house-account guard re-review GO; independent balance14 passed.
- Signed-in actual API/browser with fictional customer and two tractors: desktop1440, mobile390 list and cards. Current native0.00 and separately labeled ETS unverified amounts render. Card toggle works. Customer record has no horizontal overflow or children beyond right edge in each view; no captured page errors. Local screenshots in output/db135-balance (not committed).

## Local runtime receipt

2026-11-01 America/New_York. Worktree customer-settled-balances, branch codex/customer-settled-balances, source base9d72b777 plus reviewed working changes. Frontend5208 PID45054 serves this worktree/frontend; configured API origin8027. Docker dieselbridge_api_customer-settled-balances binds this worktree/backend. Database postgres/truckpitstop_customer_settled_balances is an isolated clone of fictional local QA database; schema196_historical_owner_self_review matches sole application head. No migration required. Direct/proxied health/ready200, database/Redis healthy. Provider credentials disabled in local compose overrides; no worker started. Synthetic fixtures only changed in the clone. Shared5173/8000 and other task5207 preserved. Backend configuration uses approved canonical env symlink, no secret copy. Aligned and browser-verified at http://127.0.0.1:5208 before commit; badge identifies startup base and served changes verified by rendered feature.

## Release and limits

No financial records are repaired, reconciled or marked paid by this change. Historical remainder is evidence only, not collectible debt. Operational native balance does not certify Account classification completeness. Existing Account warnings and credit ledger remain separate. No migration, provider calls or production write. Protected CI, approved merge/deployment and production browser acceptance remain required. Rollback is application code revert; no data rollback needed. Verify post-release customer/equipment zero, separate historical amount and unchanged financial records.
