# DB-149 payment-state reconciliation contract

2026-11-02. Architecture & API Contracts design GO for local implementation at current main `7b56fe254e02b3bf9910ff356f3d08e1f4626b90` (#756/#757), branch `codex/payment-state-current-main`. This adapts the previously approved dashboard payment-summary contract. No implementation, test execution, production access, publication or deployment was performed by this contract reviewer. Independent QA/security and real isolated acceptance remain required; this is not a release approval.

## Ownership and narrow scope

Board ID: DB-149. From: Architecture & API Contracts. To: Backend & Integrations (API/tests) and Frontend & UX (presentation/tests), coordinated by parent Product & Delivery Lead. Reconcile only the payment-state outcome from local `402fde47`: remaining dashboard principal; refund/unapplied notices on paid guest/portal pages; prior+confirmed native applied collection display; failed-read/stale-control handling. Do not port the overlapping `cf9e8e96` branding/selector/document work.

Preserve #756's existing `source_collection.display_invoice_number` (e.g. TPS-1687), leading zeros/second-tenant aliases, hash-validated `original_bill_to_name` and all customer identity/memo/share/PDF/email/download behavior. Do not introduce the old `customerInvoiceIdentity` helper or replace current tenant aliases with bare original numbers. Preserve #757's informational balance card, one Pay link per invoice, quote-only Action required, historical exclusion, and `canSelect`/`selectionActive` only for multiple known payable invoices. No selector redesign, new selection instructions or duplicate payment prompt. Invoice UUID remains the action and selection key.

## API/data contract

Add/move the existing optional `payment_summary: InvoicePaymentSummary | None = None` onto base `InvoiceResponse`; detail inherits identical semantics. Existing create/update/list/detail response envelopes, IDs/numbers, amounts, pagination, filters, source_collection fields, scopes and ordering stay unchanged. No new request, endpoint, migration, persisted read-model shape or error code. Avoid duplicate inherited-field kwargs in detail constructors.

Example: total100, confirmed40, pending20 returns the unchanged total100 plus:

```json
{"payment_summary":{"state":"partially_paid_pending","applied_amount":"40.00","balance_due":"60.00","pending_amount":"20.00","basis":"settlement","note":"Pending payment is awaiting confirmation and has not reduced the balance."}}
```

Both projected and legacy invoice-list paths populate this summary freshly from authorized current ORM Invoice rows. Projected payload status/total/summary can be stale and must not drive current payment facts. Include the current Invoice in the authorized projected query; discard any stale cached summary before validation. Preserve the existing source_collection loader and its exact viewer_customer_id, tenant-scoped alias and reviewed legal-name enrichment. Do not bypass identity review or silently drop these fields while adding the payment summary.

Reuse `project_payment_summary` without changing financial derivation, cash/settlement/legacy precedence, status-only paid semantics or conservative unknown/refund handling. Batch live settlements by selected tenant and returned IDs, then nondeleted legacy payments only for rows without a settlement. Group by bound tenant+invoice, reuse existing current cash receipt results. Empty pages add no reads; nonempty pages add at most two summary-evidence SELECTs, not N per-invoice summary calls or frontend detail requests. Existing source/cash per-item work need not be redesigned.

This addition is read-only: no flush, settlement initialization/backfill, commit, status/total change, ledger/attempt/payment row, provider request or external message. Preserve existing customer/tenant/source-history alias/access predicates and error behavior. Unknown/malformed evidence uses the established unknown summary; actual query/transport failure propagates rather than fabricating a successful fallback. Dashboard reads are snapshots; existing detail/attempt version/admission/idempotency guards remain the payment authority. EDG financial-manifest v2 schemas, consumers and canonical integration IDs must remain byte-shape compatible; do not add fields there.

## Frontend meaning

Use valid nonnegative decimal-cent `payment_summary.balance_due` for current aggregate, row, selection and queue eligibility. Sum cents with existing exact-money helpers. Never substitute original total or allocatable balance, and never subtract pending a second time. Current summary may override a stale raw paid status for current-debt classification; preserve actual cancelled/history guards and existing cash/paid reporting bases.

Missing/null/unknown/invalid summary or failed read is unavailable, not zero or original total. Keep the invoice reviewable without Pay/selection. If unresolved rows exist, qualify a known-only aggregate or withhold the aggregate; do not claim All paid up. Maintain #757's single-action hierarchy while handling unavailable data. Selection totals/destinations recompute from currently known payable rows after refetch; zero/unknown/history rows cannot remain payable merely because their ID was previously selected.

Paid pages retain independent refund_pending and unapplied_credit notices, including coexisting notices; do not render reconstructed paid amounts when saved applied_amount is intentionally null (legacy paid-without-tender). Collection applied amount is prior allocation plus confirmed native principal once; pending is excluded and unknown native applied stays unknown. Retain existing pending/history/resolution facts without a second differently scoped confirmed aggregate. When a fresh settlement read fails, cached summary data must not keep payment controls actionable; normal refresh/recovery can restore controls. No amount-choice/provider/memo/request change.

## Shared fixture and acceptance

Use existing exact100 principal fixtures: confirmed0/40/100; pending0/20; prior source0/20; refund0/20; unapplied0/15; saved applied null; normal/cancelled/unknown/status-only and stale raw paid state. Expected principal balance is100/60/0 based on confirmed amounts, unaffected by pending. Known40 plus prior20 displays60 applied against original120 without counting pending20. Tenant aliases and reviewed legal names from #756 stay identical before/after; no stale source metadata or new visibility grants.

Required owner and fresh independent evidence:

- Projected/legacy list matrix, stale/invalid cached payload, 1/50/100 page fixed added-query bounds, empty page, cash precedence, deleted/foreign evidence, customer/tenant/alias denials, failed evidence reads and no ORM writes. Retain current #756 identity/legal-name/PDF/export tests and v2 contract guards.
- Guest/portal native+collection unpaid/partial/pending/paid/refund/credit/unknown matrix; original/prior/native combinations and null-tender case; actual balances and no unintended payment submissions. Failure with cached data and successful recovery; remount/refetch; unchanged public aliases/memos/UUID destinations.
- Dashboard one-invoice and multiple-invoice hierarchy, no payment entries in Action required, authorization alerts preserved, multi-selection only when >1 known payable invoice, integer-cent totals, historical/unknown exclusion, refetch changes and stale selected IDs. No restoration of removed Pay invoices/Pay oldest duplicate CTAs.
- Relevant full regression suites in addition to focused cases, source/build/lint and independent QA/security. Record every failure separately from untested scenarios; do not call a broad suite green from overlapping focused counts.
- A newly isolated real PostgreSQL/Redis backend with synthetic normal authenticated customer/guest journeys, desktop and390px, reload and failed-read recovery. No live payments or operational financial writes. Snapshot full financial rows before/after reads and UI changes; synthetic seed creation is distinct from payment operations. Preserve evidence and clean only owned disposable services.

Return to Architecture for changed financial derivation, persisted columns/migrations, access scopes, provider execution, identity alias/legal-name policy, unbounded added reads or inability to keep unknown balances conservative. Otherwise proceed locally without another product-owner permission request. Publishing/merge/deploy remain explicitly unauthorized in this task.

## Draft publication scope update — 2026-11-03

The later explicit instruction authorizes publishing the independently reviewed payment-only draft PR. Original local-only contract language records the earlier stage; merge, deployment and GitHub PR approval remain outside this step. Enrollment remediation and unrelated test-infrastructure changes remain excluded. Current verification is recorded in `../verification/DB149_PAYMENT_STATE_DRAFT_PR.md`.
