# DB132 / P1 parts pricing matrix

Accountable: Backend & Integrations. State: **contract intake; application implementation not started**. Selected second in the [parity tracker](../ETS_PARITY_TRACKER.md), after R1 production closure.

## Scope and acceptance
[Architecture contract](../contracts/db132-parts-pricing-matrix.md) defines acceptance, writer coverage, privacy, tenant/concurrency boundaries and production verification limits. Reuse existing inventory settings and price controls; preserve compact desktop and complete mobile journeys. No existing prices, inventory valuation, financial records or shop defaults change merely from deployment.

## Source and preparation
Branch `codex/ets-parts-pricing-matrix` begins at R1 merge7b3dc4b3. Preparation reviewed21546789; full application tree is identical. Backend/frontend integration handoffs and later C1/M1/B1/A1 drafts are preserved in `/Users/sergio_m1_promax/Documents/Codex/ets-priority-preparation-20261015/`; those are preparation, not completion receipts. Canonical tracker retains all29 discoveries and selected order.

## Remaining gates
Runtime alignment before any application implementation or local QA; focused implementation and automated checks; independent Architecture/QA/Security as applicable; actual Light/Night desktop/mobile workflows; focused PR and protected CI; exact release; authorized production acceptance with no invented real-shop pricing activation. No P1 code, tests, PR, deployment or pricing-policy mutation claimed.
