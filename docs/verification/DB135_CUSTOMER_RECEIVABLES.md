# DB-135 / B1 customer receivables verification

Status: Discovery; no B1 application implementation, QA/Security GO, PR, merge, deployment, or runtime acceptance yet. Accountable owner: Backend & Integrations. A1 stays queued.

## Source intake (2026-10-18 UTC)

- Official ETS guides: [A/R and aging export](https://support.easytruckshop.io/en/articles/16739469-who-owes-me-money-getting-your-a-r-and-building-an-aging-report), [customer transactions](https://support.easytruckshop.io/en/articles/16416336-where-to-view-customer-transactions-customer-transactions), and [balance differences](https://support.easytruckshop.io/en/articles/16738694-why-doesn-t-my-customer-s-balance-match-their-invoices). ETS's spreadsheet aging is the source behavior; B1's native aging is added DieselBridge behavior.
- Repository: `Invoice.billed_customer_id` is the bill-to snapshot; pre-migration-155 rows can be null. Customer merge changes RO customer but does not rewrite bill-to snapshot. `InvoiceSettlement.confirmed_principal` already incorporates applied amounts and reversals; `Payment` compatibility rows must not be counted a second time. `CustomerCreditEntry` is append-only. Existing customer `balance` and `CustomerReadModel` are blended operational projections and cannot be relabeled collectible.
- [Contract](../contracts/db135-customer-receivables.md): read-only, source-separated account and PDF statement; current, 1–30, 31–60, 61–90, 90+ buckets for verified native outstanding principal; undated/review-required outside aging; no send/provider/money writer.

## Open gates

1. Architecture review of bill-to merge resolution, native settlement coverage, credit/refund semantics, snapshot consistency and bounded API/PDF shapes. Update the contract if source facts change.
2. M1 release-record PR #573 must close its protected CI, including the separate date-sensitive test repair PR #574. Application M1 release and signed-in production acceptance have passed; this receipt PR is still open.
3. Implement against the reviewed contract, run focused financial/tenant negatives and source-separated fixed-cohort retention, then obtain independent QA and Security decisions from reviewers with no implementation participation.
4. Protected CI, focused B1 PR/merge, normal deploy health, and authenticated desktop/mobile Light/Night account and statement acceptance. No production financial mutation or statement send for QA.

Local-runtime boundary: this docs-only intake did not start local servers. On the current worktree, ports 5173 and 8000 had no listeners, the existing local development database was at migration 149, and no `.env` existed in this worktree. Before B1 implementation or local browser QA, repeat the mandatory local-runtime skill and align to the intended branch without migrating or replacing another task's runtime silently.
