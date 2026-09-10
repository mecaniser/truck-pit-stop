# DB-048 inactive shop activation guards: verification

Status: implementation in progress; **not released or activated**.
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

This early gate does not approve unfinished service code. Exact-candidate
automated checks, independent caller/security review, CI, merge, and deployed
runtime verification remain required.

## Explicit activation prerequisite

Managed CDC and payout import must not reuse an unscoped historical importer.
Until an activation-scoped payout reader/importer is implemented and verified,
the managed path stays denied. Thus this guard release is not a claim of complete
payment-to-bank matching readiness. QuickBooks deposit/payment reconciliation
also does not by itself prove a bank-feed match.

