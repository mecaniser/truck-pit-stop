# DB-048 inactive shop activation guards: verification

Status: independent QA/Security GO; **not released or activated**.
Accountable implementation owner: Backend & Integrations.
Contract: [Shop activation](../contracts/db048-shop-activation.md).

## Deployment boundary

This release creates no activation rows or invoice enrollments. Existing payment
admission, flags, credentials, process-wide environments, historical export holds,
and financial records remain unchanged. Production activation is a separate action.

## Independent migration evidence

The independent reviewer ran 35 assertions in a separate local PostgreSQL database.
Existing local databases and production were not modified.

Covered:
- Empty upgrade/downgrade preserves invoice data and seeds no management records.
- Server-generated first activation cutoff and immutable identity/cutoff.
- Disable and re-enable preserve original cutoff; deletion is not a disable path.
- Creation-only enrollment with composite tenant binding.
- Historical, held, imported, cash, replacement, and null/invalid inputs rejected.
- Enrollment removal/reassignment and downgrade with management rejected.
- Concurrent disabling and enrollment serialize in both directions.

Reviewed migration blob: `87fc3a39525b2ecb0f481c7b914e2156a57e02e2`.

Independent QA/Security approved exact implementation commit
`1b6eebe3ef5d487da7ee85683146528968d28fc5` after independently running 69 tests.
All three reproduced findings were fixed and tested at the actual entrypoints:
issuance admission before lease changes, capture admission after lock-releasing
commits, and refund environment binding to the original provider. Owner also
reported 61 issuance/cash and 240 adjacent accounting/hold tests passing.
Protected CI, merge, and deployed runtime verification remain required.

## Explicit activation prerequisite

Managed CDC and payout import must not reuse an unscoped historical importer.
Until an activation-scoped payout reader/importer is implemented and verified,
the managed path stays denied. Thus this guard release is not a claim of complete
payment-to-bank matching readiness. QuickBooks deposit/payment reconciliation
also does not by itself prove a bank-feed match. The required follow-up is tracked
in [the managed payout import contract](../contracts/db048-managed-payout-import.md)
and the project board; it is not implicitly deferred or marked complete.
