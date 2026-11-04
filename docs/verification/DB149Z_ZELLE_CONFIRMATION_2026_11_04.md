# DB-149Z: explicit Zelle reporting

Status: preview complete; not deployed. Backend & Integrations accountable. Branch: `codex/zelle-explicit-confirmation`.

Viewing Zelle instructions now makes no payment, reservation, ledger or notification write. The customer chooses full or partial payment, views recipient and memo, then explicitly selects “I’ve sent the payment” after making the transfer in their banking app. Stable retries preserve the original report identity and payload. Staff still independently verifies receipt; reporting does not mark an invoice paid.

Refresh provides checking, unchanged, updated and failed-read feedback while preserving the last valid balance. Pending details appear once, with payment activity collapsed initially. Guest and authenticated customer routes share the behavior.

The shop receives a durable Payment review task. Eligible configured staff SMS is queued under existing consent and delivery rules; email and bank-transfer detection are not promised. Historical pending requests remain identifiable as unverified requests without rewriting them. Canonical partial reports open exact-attempt review rather than legacy full-invoice confirmation. Shop review authorization remains owner or explicitly permitted admin, with tenant and billed-customer isolation.

## Validation

- Matching backend suite: 123 passed, 2 explicit pre-existing skips; includes 9 actual PostgreSQL cases covering concurrency, rollback, pure reads, archived-source collection authority and notification consent.
- Independent Security/QA: final GO for preview/PR; clean PostgreSQL 9/9, focused backend 37/37, frontend 66/66; no unresolved findings.
- Full frontend: 2,759/2,759 passed. Final shared payment/dashboard delta: 180/180; dialog/queue delta: 42/42.
- Final production build, TypeScript and shared-control guard passed. Changed-source lint passed except two demonstrated unchanged DashboardHome baseline diagnostics. CI partition validation passed.
- Actual isolated application/API desktop and mobile journeys verified for customer, guest and staff. Instructions/copy/back preserved version, balance and all protected financial hashes, with zero attempts or ledger events. Explicit reporting exercised only on a new fictional fixture. Staff partial review displayed the exact requested amount and preserved the separate card reservation; no receipt confirmation submitted.
- Readable desktop/mobile dialog, 44px controls, no horizontal overflow at 390px, and primary button contrast 5.96:1 verified.
- Existing production financial records and prior local database fingerprints unchanged. No real payment, SMS, email or provider operation. External transport counters remained zero.

No migration or financial backfill. Current schema remains 200. Screenshots and preservation receipts are private local review artifacts. Hosted exact-head CI remains a separate PR gate. Deployment requires user approval of desktop/mobile previews.

[Contract](../contracts/zelle-explicit-transfer-confirmation.md).

## Authorized release gate follow-up

User approved previews and authorized PR772 merge/deploy plus read-only live customer/guest/shop desktop/mobile acceptance. Current-main reconciliation changes only disjoint Motive scripts and preserves both board histories; reviewed payment product source remains byte-identical. Initial hosted run41884398687: protected backend926 passed/67 explicit skips, frontend/build and browser smoke passed, disjoint full frontend2308 passed. Full backend found4 failures (4710 passed/462 skipped): existing positive receipt fixtures omitted explicit report intent and an existing quote fixture relied on a read flushing its preceding writer. Reproduced before correction; scoped test-only setup changes preserve all original authorization/export/fee assertions and add quote projection-purity assertions. The three affected files are now protected regressions. No product guard or financial record changed. Final corrected-head CI and deployed acceptance remain separate gates.

Owner122/122 and independent122/122 passed on the correction, with product hash unchanged. Partition guards and diff checks passed.
