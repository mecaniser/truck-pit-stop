# DB-048 Fleet tender implementation handoff

Date: 2026-09-11. Root accountable; Architecture & Backend implemented Fleet.
Branch: `codex/db048-payment-journey`, base `d2a37545`. Shared worktree includes
root's UI/Zelle evidence and customer default144 / charge adjustment145 work.
No production action, external Fleet redemption, commit or release performed by
the Fleet owner. This is owner evidence, not an independent gate.

## Delivered contract

`docs/contracts/db048-fleet-tender-v1.md`, acknowledged by root before backend edits.
Distinct canonical `fleet_payment` rail; EFS/MoneyCode, Comchek, T-Chek and named
Other; required instrument trace, optional approval trace/note. Exact reserved
amount at confirmation, full or partial invoice principal, no card fees.
Staff and tenant permission rechecked in domain create/confirm. Evidence frozen;
one received instrument per shop/provider/normalized reference, including across
customers. Same idempotent attempt replay preserves its receipt.

Payment projection uses `FLEET_PAYMENT` and preserves brand/reference/approval.
Staff allocations retain pending sender reference plus provider/approval; nonstaff
allocations redact them. Canonical export eligibility and new-receipt authorization
include Fleet without releasing historical holds or backfilling old receipts.
Legacy-principal/gross and refund/credit-source accounting use the snapshotted
check-deposit account. QBO reference remains bounded; full provider and trace remain
in the private memo. Gross projection rejects any Fleet card fee.

## Automated evidence

- Fleet + checkout + cash-availability: **78 passed**. Fleet file alone39 cases.
  Includes all providers × full/partial, required/invalid evidence, exactamount,
  stale/foreign/customer/guest/no-permission, immutable data, same/different
  provider and tenant references, idempotency, new receipt on retained historical
  hold, fee-free read-only quote, QBO mocked legacy/gross presentation and replay.
- Adjacent settlement/cash/gross/credit/projection/new-receipt suites: **281 passed**.
- Real PostgreSQL Fleet: **3 passed**. Same-/cross-customer duplicate confirmations
  serialize; loser preserves pending reservation; DB unique index independently
  denies duplicate identity; raw SQL evidence update denied; populated downgrade
  refuses before DDL. Disposable database `db048_customer_tax_default` only.
- Migration146: actual **145→146→145→146 passed**, before Fleet fixtures were
  inserted. Existing144/145 audits retained. Final database head146.
- `git diff --check` passed. No new dependency.

An initial test invocation named nonexistent `test_db048_gross_projection.py` and
collected no tests; corrected to `test_db048_qbo_invoice_projection.py`. One new
mocked legacy-writer test initially omitted the fixture's processor_fee_amount;
fixture corrected to0 and final78 passed. No product failure hidden by those runs.
An added pending-evidence assertion initially treated the returned Pydantic DTO
as a dict; corrected to attribute access and included in the final rerun.

## Required integration / release

Root owns final frontend build/runtime and exact integrated SHA. Fresh independent
QA/Security must review all mutable payment/data boundaries and integrated UI.
Deploy migrations144→145→146, then matching guarded workers, then API/UI.
Once Fleet data exists, do not downgrade146 or roll writers back to code that
rejects Fleet; hide admission if necessary and forward-fix. Historical/test holds,
pending reservations and existing invoices are not migration cleanup targets.
