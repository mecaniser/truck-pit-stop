# DB-139 remaining ETS legacy vehicle-link audit

Accountable owner: Backend & Integrations. Source/transaction scope reviewed by Architecture; independent Security/QA gates the finite manifest and operational script. No application release or importer change is needed.

## Read-only discovery and finite scope

The November 1 census used the deployed billing resolver in pages of 50 inside one repeatable-read, read-only transaction: 3,739 active imported repair orders; 1,574 unavailable totals. Reasons: 460 shared-job identity conflicts, 1,076 deleted-invoice evidence, 10 shared-job source conflicts, 16 missing/ambiguous invoices and 12 unavailable source identities. Payment status is separate: 1,882 paid, 1,825 unverified, four partial and 28 unpaid.

Structural inspection finds 259 groups with unavailable totals and differing vehicle links, including 12 groups whose financial-evidence hold masks the link mismatch. The preserved source capture SHA-256 `f72882d175406468af2ba22d80c734b11b0ce818062c6a00dfdab86cfc4a404a` proves **243 specific legacy repair-order vehicle corrections**, across 243 groups/698 operation rows and 193 disjoint connected vehicle components (maximum five groups per component). There are 238 invoice-owner corrections and five nonowner operation corrections; invoice ownership never changes.

Each accepted group has exactly the captured operation count; every occurrence of its service in the entire capture binds exclusively to the same source customer and vehicle. Current imported customer/source identity, unique active source vehicle, legacy null external vehicle identity, same customer/unit and no conflicting VIN, active invoice/source-service identity and trusted shop binding must agree. The finite private manifest is independently reviewed by digest; the script never adds newly discovered candidates during execution. Sixteen structural groups remain held (12 customer conflicts and five unit conflicts, one overlaps). The prior service0662 repair is explicitly excluded and fingerprinted separately.

233 selected groups cover 429 currently unavailable operation rows. Ten additional selected groups contain 36 unavailable rows with deleted-invoice evidence; their historical links may be repaired, but those independent financial holds remain. Other missing/deleted/source-unverified balances are not repaired by this work. No invoice reconstruction, payment reconciliation, source refresh or guessed paid/unpaid status is authorized.

## Transaction contract

`backend/scripts/repair_ets_legacy_vehicle_links.py` reuses only small immutable utility helpers from the earlier0662 tool; that earlier tool is unchanged.

- `build-manifest`: offline validates the exact preserved source hash and candidate proofs; writes a private0600 manifest. Reviewed scope is exactly243 changes/193 components; customer source and global source exclusivity are mandatory. Manifest pins original/target IDs, all group members, source row digests, invoice set and actual invoice owner separately.
- `plan`: SERIALIZABLE READ ONLY per component. Metadata is loaded once and reused; one union query captures each dependent table once per component. Scope includes both vehicles, every group member, all unplanned neighboring orders, invoices and every direct order/invoice/vehicle-dependent row. Current sole active invoice set must exactly match the reviewed active ID; existing cancelled/deleted copies remain immutable. Full invoice/source evidence is fingerprinted per component.
- `rehearse`: apply, audited no-op, guarded rollback and rollback no-op inside one transaction that always rolls back. Real PostgreSQL locks, projection triggers and exact invariants must pass; a separate read-only baseline check follows.
- `apply`: SERIALIZABLE component transaction with deterministic vehicle/order/invoice/dependency locks and exact plan/manifest digests. Update only explicitly listed repair_order.vehicle_id and updated_at. All financial, source, neighbor and nonprojection fleet records remain unchanged. Verify planned RO projection fields from independently computed target vehicle/customer/order identity: vehicle FK, vehicle display/search fields and update/refresh times only. Every other projection remains exact. The reviewed cohort initially has no fleet-board projection rows; require that invariant before and after normal triggers. If a projection appears or any other guard fails, roll back and hold that component for review.
- `rollback`: expected repaired state plus matching durable audit required; restore only the listed old links, preserve all financial/dependent invariants, append rollback audit. No forced rollback after intervening drift.

One durable component audit, anchored to its first corrected RO, lists every changed row and source/manifest/plan/before/after digests. Attribution is system repair with null actor_user_id and “Owner-authorized ETS repair”; no arbitrary staff identity is impersonated. Apply/no-op and rollback/no-op require exact audited state. Any exception rolls back. There is no automatic retry or discovery expansion.

Components are disjoint by old/target vehicle neighborhoods. Apply first a small independently accepted smoke component, then remaining accepted components sequentially. Stop on unexpected drift/invariant; replan only after reviewing the cause. Do not reuse overlapping precomputed group plans.

## Financial and prior-repair invariants

Whole-tenant baseline: 2,528 invoices, 2,666 payments, 1,398 settlements and 1,456 payment ledger events. Private full-row digests are recorded for payments/settlements/ledger; invoice financial fingerprint omits only source_evidence and updated_at to distinguish unrelated source confirmations from financial changes. **Inside each mutation transaction, full invoices including source evidence remain exact.** Prior0662 has a separate four-order/one-invoice/four-payment/one-settlement/three-ledger fingerprint and must remain unchanged. Never sum repeated shared UI balances as separate receivables.

Proofs, manifest, per-component plans, IDs and production receipts stay in private0700/0600 artifacts outside Git. Report link repair, UI availability, payment verification, financial invariants and unresolved holds separately.
