# DB-139 remaining ETS billing holds

Accountable owner: Backend & Integrations. Architecture contract approved 2026-11-01. Independent QA/Security gates apply before release or operational repair.

## Scope and evidence

The current cohort contains 61 repair-order rows across 17 groups. This change extends only the staff imported-billing display reader. Five narrowly evidenced cases are expected to recover 36 rows; production shadow comparison must establish the actual result and preserve every unrelated outcome. No invoice, payment, settlement, ledger, source evidence, receivable, export, accounting total, or provider record may be written or reinterpreted as native collection authority.

Evidence includes the fresh private blocker census, preserved vehicle/invoice-scoped ETS captures, importer and historical cleanup/reconciliation code, current digest/manifest-bound ETS observations, and signed-in ETS invoice inspection. Signed-in live ETS inspection confirms all 14 existing invoice routes and the 36 display-candidate rows' source paid amounts, including the three lower-source-total cases. It explicitly shows service 1040 balance -2.01 and service 1106 positive and negative 1026.98 payment entries; both remain held. Source collection and browser verification remain distinct evidence. Authenticated ETS invoice routes for services 1304, 1311 and 1381 return Page Not Found while supported invoice routes work; their 16 rows lack a current source invoice binding and remain held. A 404 alone does not prove unpaid, paid, cancelled or deleted. Subsequent signed-in ETS global search independently identifies all three source services as Archived Canceled. Their 16 rows therefore remain held as archived/canceled source jobs without a verified active invoice; unrelated invoices numbered 1304, 1311 and 1381 belong to other customers and must never be bound by service-number fallback alone.

All source observations must retain existing tenant/shop/service/invoice identity, complete singleton invoice manifest, digest/confirmation, currency, freshness, allocation uniqueness and canonical-payment conflict checks. All retired-copy exceptions retain the exact recognized cleanup reason, imported source, cancelled/deleted state, matching deletion/update time, tenant/customer/vehicle/job identity, bill-to agreement, no own source evidence, and absence of provider/revision/native financial references. Every copy must still equal the canonical invoice's locally recorded total. Unknown copies and ambiguous live invoices remain held.

## Display cases

### 1. Fully paid invoice with unapplied parent-payment excess — expected 17 rows

Services 0384, 0548, 0709 and 0979 have invoice-specific allocations that equal the invoice total and zero invoice balance. A parent payment's positive unapplied amount is not an invoice debt or an additional invoice payment.

Permit positive unapplied amount only when the source invoice has supported paid status, zero balance and exact full invoice allocation coverage. For every parent payment require completed, uncancelled, zero credit total, supported existing type/provider, USD exact nonnegative amounts, positive total and allocation, and `allocated_to_this_invoice + unapplied_amount <= payment_total`. Preserve existing uniqueness rules. Count only invoice allocation amounts. Equality to the parent total is not required: other allocations may belong to another invoice. Positive unapplied amounts on partial/unpaid invoices, overallocated payments, credits, refunds, cancellation, negative invoice balances, invalid currency or incomplete allocation evidence remain unsupported.

### 2. Verified source total differs from historical local total

Preserved source captures and current source observations agree on lower invoice totals for services 1302, 1346 and 1356; higher local totals are not established source revisions. The existing canonical source reader is authoritative for display, not a writer to local accounting columns.

A fully verified canonical source summary may supply its current total, allocated paid amount and remaining balance even when those differ from legacy columns. Remove only the additional requirement that the verified source total equal the legacy canonical total. Keep `copy.total_amount == canonical.total_amount` and every other artifact predicate. Preserve `imported_financial_rows_differ` and `review_required`; do not silently present local accounting as reconciled. Services 1346 and 1356 must also independently pass their same-owner/fallback-name cases below.

### 3. Explicitly reconciler-retired canonical payment — expected 2 rows

Service 1052 has a positive imported payment deliberately retired by `reconcile_ets_payments.py`, whose exact notes suffix is ` [retired: no matching payment in Easy Truck Shop]`. Historical source payments and the current source both contain only the remaining 1000.00 and 9.22 allocations. Native-reference inspection finds no reference to the retired payment; canonical ledger baselines reference only the retained payments.

A display-specific filter may exclude only a payment with that exact terminal suffix, imported source, method `other`, failed status, nonnull equal deletion/update timestamps, positive finite amount, and no provider, actor, refund, attempt, accounting or other native financial reference. Require the retained active imported completed-payment amount multiset to equal the fresh source's unique invoice-allocation amount multiset. Validate tenant/invoice identity throughout. No other failed, deleted or refunded canonical payment is excluded, and no native payment/settlement logic changes. The source summary and all remaining canonical-payment checks must still pass.

### 4. Retired operation copy on the later canonical owner's row — expected 6 rows

Services 1146 and 1346 contain exact-name cleanup copies on the same repair-order row as a subsequently imported canonical invoice. Recognize this case only if `copy.created_at <= copy.deleted_at < canonical.created_at`, the copy name is exactly `canonical.invoice_number + '-' + copy_order.order_number`, and every other cleanup/source/financial-reference check passes. This is not permission to ignore arbitrary prior invoice revisions, voids or same-owner deletions. Supersedes/revision/native markers continue to block.

### 5. Known importer service-number fallback in copy names — expected 8 rows

For services 1305 and 1356, preserved captures bind the service to its actual invoice number, while historical copies used the importer's documented `invoiceNumber or service_no` fallback. Accept only the exact alternative `ETSINV-<verified source service number>-<copy repair-order number>`. The verified source service must match the exact group key; the current complete singleton manifest must identify the canonical actual invoice. Retain copy/local-canonical total equality and every cleanup/reference/identity guard. Conflicting active local fallback-root invoice identity must hold rather than be silently discarded. No arbitrary suffix stripping, fuzzy matching or generic invoice-number equivalence is allowed.

## Separate source-confirmed vehicle repair candidate

Service 0733's preserved vehicle-scoped capture identifies source vehicle 117809. The older owner uses unit `05` while the existing mapped vehicle uses `5`, with the same customer. This is a separate historical FK repair candidate, expected to affect one owner link and three display rows, not an exception to shared-billing identity checks.

Before any apply, produce a finite private plan proving exact source/customer/job/vehicle mapping and unique active target, expected old/new IDs and entire group membership. Reuse the previously reviewed read-only plan, SERIALIZABLE locked compare-and-set, rolled-back rehearsal, financial/source/dependency/neighbor fingerprints, projection checks, durable audit, idempotence and guarded rollback. Change only the proven owner `vehicle_id` plus timestamp/audit. Preserve invoices and all unrelated rows. Independent operational QA/Security must approve the exact plan and dry run. The exact observed `05` versus `5` unit-label difference is permitted only for this source-ID-proven pair; do not generalize a numeric/leading-zero unit normalization rule. Signed-in live ETS additionally confirms customer 82487, source vehicle 117809, label `05Owner`, and paid invoice total 456.01. Unit normalization alone is not proof.

## Holds preserved

Service 0535 has a customer plus vehicle conflict and is outside vehicle-only repair scope. Service 1106's negative retired payment and service 1040's negative source invoice balance remain unsupported. Services 1304, 1311 and 1381 lack current source invoice binding. Unknown refund/cancellation/provider evidence, ambiguous copies, malformed identifiers, source changes, missing/stale observations, duplicate allocations, overallocations and cross-tenant relationships remain held. No automatic source refresh, retry, importer execution or financial reconciliation is part of this work.

## Acceptance and release evidence

- Focused positive fixtures for all five display cases, preserving exact cents and source amounts; existing paid/partial/unpaid behavior remains correct.
- Negative fixtures for each predicate boundary, especially allocation plus unapplied overflow, partial-with-excess, source/local copy mismatch, unmarked deleted canonical payment, provider/native reference, retained-payment multiset mismatch, same-owner chronology, fallback-name identity conflict, refund and stale source.
- Existing list/detail batching and authorization remain unchanged; no customer pricing exposure and no per-row query explosion.
- Whole-tenant old/new shadow comparison reports exactly which statuses/totals/reasons change, with complete invoice/payment/settlement/ledger/repair-order fingerprints unchanged. Counts are evidence to verify, not reasons to weaken predicates.
- Independent QA/Security reviews final source and tests. Runtime UI confirms correct source status/remaining and review indication on representative groups. Merge, deployment identity and post-deploy read-only acceptance are recorded separately.
- Roll back application code if the display overstates payment, leaks scope or duplicates money; retain all financial and source rows. The optional vehicle repair has its own guarded operational rollback.
