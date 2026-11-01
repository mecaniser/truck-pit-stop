# DB-139 retired duplicate invoice evidence

Owner Backend & Integrations; branch codex/ets-deleted-evidence base5213d328. User requests source-confirmed payment status/remaining balance for1076deleted-invoice-held rows without duplicate invoices or balances. Discovery/read-model correction only; no invoice restoration, deletion or financial writes. Architecture contract approved; independent final Security/QA is pending.

## Local runtime
2026-11-01: frontend5202 PID16344 serves this checkout/frontend; dedicated API18021 container mounts this checkout/backend. Approved root .env preserved, fictional postgres/truckpitstop_db139_shared and Redis11 retained; no migrations/workers started. Proxy readiness200. Fictional account session renewed through local login; actual browser verifies C3 Fictional Shop1 and codex/ets-deleted-evidence@5213d32. Aligned and browser-verified before implementation; changed-feature acceptance pending.

## Source and contract review

Fresh1076held rows span330jobs, each one live invoice plus723cancelled/deleted imported copies retired by the documented Aug23 cleanup;802copy payments are failed/deleted at the cleanup instant. No retired provider/refund/attempt/settlement/ledger references found. Exact cleanup, suffix naming, tenant/customer/vehicle, bill-to, local/source total equality and canonical full source-backed payment summary qualify313groups/1015rows:1013paid+2unpaid.17groups/61rows remain held for naming/identity/missing or unsupported source/total/canonical-payment conflicts. Architecture and independent discovery agree.

Correction is strictly a billing-display reader exception. Generic deleted-invoice guard, completed-outcome service, invoices, payments, source evidence, aggregates and exports remain untouched. Unknown or financially conflicting deleted records remain holds. No production data mutation is planned or needed.

## Implementation and pre-release verification

The complete reader shadow corrected the preliminary estimate: negative retired payment evidence and a copy attached to the canonical owner exclude two additional groups. Final scope is 313 jobs / 1,015 rows (1,013 paid, two unpaid); 61 rows in 17 jobs remain held. All other 3,739-row census results are unchanged. Invoice, payment, settlement, ledger and repair-order fingerprints match discovery and shadow before/after. Private receipts: `reader-shadow-final.json` and `reader-shadow-final-summary.json` (outside Git).

177 focused backend tests pass, including real-database native references, reverse revision links, tenant isolation and list/detail parity. Independent review identified the reverse-reference case; implementation and regression now cover it. No migration or frontend change.

Signed-in local browser acceptance: seeded one fictional retired duplicate invoice/payment with the exact cleanup signature. Generic invoice selection still holds; staff list and selected sibling both show $534.41 paid, remaining $0.00, shared invoice. Billing details explicitly state the canonical owner and amounts counted once. Existing unpaid and identity-conflicted examples remain unchanged. Production release and final independent gate pending.

Independent final source/security GO: source SHA-256 `ebb044a060060e918192347c22438ad91cd415a75c897e838eff1983cee07411`. Reviewer independently reran 149 billing tests and recomputed the full shadow cohort; reverse-reference and real database financial-reference coverage passed. CI/deploy remain release gates.
