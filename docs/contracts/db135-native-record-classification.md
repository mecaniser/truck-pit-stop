# DB-135 native record classification — read-only revision

Status: Independent Architecture contract-proposal GO; owner selections received, loader contract GO; independent implementation and release gates pending. This is not implementation or release approval. Accountable: Backend & Integrations. Source: explicit product-owner instruction on 2026-10-19 to distinguish real activity from legacy/test records, keep tests out of balances and finish B1 without financial-record changes.

## Intake and release boundary

Private repeatable-read, read-only inventory found 47 invoice-column native candidates; the original 32 without any settlement are unchanged. Review all 47 because an existing settlement does not prove that activity is real. Exact customer names, row IDs and amounts remain private. One candidate has an ETS-numbered invoice and repair order; classification must not override imported-source lineage.

No inference from company name, number of transactions, status, payment presence or lack of payment. The owner submitted exact snapshot-bound selections: 34 `test`, 13 `real`. Unlisted/new identities remain `unknown`. The owner reviews each exact invoice as `real`, `test` (including legacy non-business activity), or leaves it unknown. Legacy real business activity is `real`, not automatically test.

This revises the proposed financial-attestation dependency: no production attestation, settlement backfill, status repair or financial apply is authorized. Existing financial facts remain unchanged. Real invoices still require existing source/identity/settlement trust before contributing money; an unsupported real balance remains explicitly incomplete. A review decision establishes business classification, never tender or collection authority.

## Proposed deployment read-filter policy

Use a private, reviewed deployment policy scoped to exact tenant and invoice identity. Each entry binds tenant UUID, invoice UUID/number, repair-order UUID and resolved bill-to customer UUID, classification, policy version and reviewer reference. Bind the approved map to the private review snapshot digest and retain an integrity digest. Do not commit customer identifiers or per-invoice decisions to the public repository. Architecture approved deployment configuration `DB135_NATIVE_RECORD_POLICY_JSON`; implementation and negative gates remain required before use.

- `unknown`: default for unlisted, new or conflicting identity. Hold outside money/aging, expose an authorized staff review count and make account completeness false; never imply a zero balance or paid state.
- `test`: exclude the invoice and attributable payment/refund/credit history from customer balances, aging and customer statements. Retain a staff review exclusion count; never delete or rewrite source rows.
- `real`: proceed through existing tenant, bill-to, source, internal-fleet and settlement trust rules unchanged. Real classification does not bypass missing or untrusted settlement evidence.
- ETS-owned or mixed source lineage remains historical/review-only even when classified real. Never count imported debt as native collectible or claim QuickBooks reconciliation without observed proof.

Only the requested actor's tenant policy may affect its response. Missing, malformed, stale-identity or cross-tenant policy cannot silently include rows. No customer-wide/company-name wildcard, broad default-real or amount/status override. Recheck source identity on every read in the same read-only snapshot.

## Child lineage and credits

Invoice-only filtering is insufficient. Trace Payments and refunds to invoice identity. For credit, trace PaymentOverpayment.invoice_id, issued CustomerCreditEntry.origin_overpayment_id, source_entry_id descendants and target_invoice_id. Exclude test-origin credit families; unknown or mixed lineage stays quarantined. A real settlement supported by test/unknown credit cannot silently remain fully trusted; quarantine the whole affected invoice and mark completeness false, without inventing a partially collectible amount. Preserve the existing no-double-counting and source bounds.

## Acceptance

Approved exact owner selections; contract-approved loader and tenant/identity isolation; real/test/unknown and new-row cases; test payment/credit/refund exclusion; mixed-credit quarantine; unchanged real settlement trust; imported lineage exclusion; account/PDF consistency. No financial, provider or statement-send writer. Independent QA/Security, focused checks and protected CI, normal release readiness, fixed-cohort financial retention and actual signed-in Light/Night desktop/mobile account/PDF acceptance remain required. B1 is not Done while classification or required release evidence is missing.

## Approved policy loader contract (2026-10-19)

Strict version-1 JSON, at most 64 KiB and 256 entries. Reject duplicate keys/identities, unknown fields, noncanonical UUIDs and classifications outside real/test/unknown. Top-level keys are version, review_reference, review_snapshot_sha256, entries and policy_sha256. Entries bind tenant_id, invoice_id, invoice_number, repair_order_id, nullable stored billed_customer_id, resolved_customer_id and classification; canonical sorting is by tenant_id/invoice_id. SHA-256 covers UTF-8 compact sorted-key JSON excluding policy_sha256. Authorized deployment configuration supplies authority; the digest only proves integrity. Keep the approved map private.

A missing or invalid policy fails closed as a whole: all native candidates unknown, no native invoice or credit money included, completeness false and an explicit policy-unavailable indication. Each read rechecks exact identities in the same snapshot; unlisted/new/stale rows become unknown. No shop-name or tenant-wide default is authorized. Owner selections include one test in the real shop; shop identity is context, not a replacement for exact selections. Financial status/amount changes retain classification but must pass current trust checks. Both invoice and repair-order ETS lineage veto native eligibility, including a nominally native invoice attached to an imported order.

Native account metadata adds classification_policy_available, excluded_test_invoice_count, unclassified_invoice_count and quarantined_credit_count. Account and unsent PDF disclose exclusions/holds without exposing test monetary activity. Whole-invoice quarantine applies to contaminated credit lineage. No financial writer, backfill, status mutation or provider operation exists in this revision.
