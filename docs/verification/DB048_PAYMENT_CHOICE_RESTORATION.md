# DB-048 payment-choice restoration

Status: implementation frozen for independent gate and protected CI; not released.

Backend owns implementation; Architecture owns the receipt-scoped contract;
independent QA/Security reviews the frozen candidate; Release owns deployment.

## Required user outcome

Cash is an optional full-invoice, local-only settlement. It must not turn an
otherwise eligible invoice into a cash-only invoice. Configured card, Zelle,
check and ACH choices retain their existing audience and partial-payment rules.
Historical export holds remain on old records and jobs. Only newly authorized,
confirmed receipts may enter their own canonical accounting flow.

## Read-only production baseline

Verified against deployed `043b5745a63ded26286a57363f17789f571907b3` on
2026-09-10. Both inspected settlements use `legacy_principal_v1`, have no QBO
invoice ID, no current confirmed/pending principal, and no projection snapshot.

- INV-…000020: principal $469.52, legacy reconciliation status `reconciled`.
  This clean existing invoice must offer noncash choices and eligible full cash.
- TPS-…000001: principal $224.62, status `native`. Its replaced invoice has an
  existing $232.48 pending card attempt. Preserve that reservation and report
  the actual conflict; do not permit a duplicate collection or clear it silently.

Signed-in baseline reproduces the incorrect blanket noncash pause. The selected
replacement invoice also reports unavailable cash. No payment button that starts
collection, cash confirmation, vehicle release or provider write was executed.

Tenant baseline fingerprints, excluding the new nullable authorization column:

| Records | Count | Fingerprint |
| --- | ---: | --- |
| Settlements | 1381 | `501c23481d56cde59685b4d46a35f918` |
| Attempts | 3 | `a8a5fd0f90a14631fa94ee12e91b8746` |
| Payments | 2252 | `0815eb35a809f8e95bfd3f2a3add0efd` |
| Outbox | 536 | `2ef3fdd792f36e490cb62e1f42cdc367` |

## Release acceptance (pending)

Backend owner evidence: new-receipt suite **20/20**, preceding combined
new-receipt/cash-panel/historical-hold/gross suite **110/110**, and clean diff.
Provider calls are mocked. Frozen source hashes: receipt authorization
`a959409b284332bafb3949588cf5301311d3ac17`, policy
`3da4e3c87fd9202ce69dfe3e8d58eadd9fb9e0a1`, settlement service
`25d85395a3e0afce0493d76cc064615709f466b8`.

Independent review of `cb4335d0` reproduced two initial legacy-admission defects:
unknown existing QBO provenance and invoice/settlement amount drift. Backend
corrected both before release, adding eight regressions; successor combined
authorization/gross/cash-panel suite **106/106** passes. Corrected receipt helper
blob `45e30d876205f9babbd6271bb28891b648390c61`, test blob
`f4c7a50ec9814974712cc535f3f0049c8b27941e`. Independent successor re-gate pending.
Live read-only invoice-money snapshots match the two target settlement amounts.
PR and release evidence: https://github.com/mecaniser/truck-pit-stop/pull/374.

Local presentation verification: existing full-cash and settlement tests **36/36**;
new actual staff-dialog choice/cancel regressions **2/2**; changed-test ESLint and
TypeScript pass. These prove presentation, not backend admission or settlement.
Alembic graph is linear at `142_new_receipt_authorization`.

Independent migration rehearsal: **12 PostgreSQL assertions passed** on migration
final blob `4c8a9dd2b3d77fcbfc4ed952b535b2feca4cb0e7`, using a new isolated database and
focused prior-schema fixture. No historical authorization backfill; normal state
updates permitted; authorization assignment/change/removal rejected; populated
downgrade refused. Final candidate must retain this migration identity.

The exact release runner also passed independent isolated rehearsal: SHA256
`fdf64915dd30e64ffa431113f77054c8977ad26995f493065dd9b8f81b491f15`.
It upgraded the prior-schema fixture, preserved fingerprints of all five checked
tables and NULL authorizations, and rejected replay or a different source blob.

- Actual staff/customer/guest admission and confirmed-receipt worker tests.
- Clean legacy and successive partial receipt accounting; production request
  routing despite the shared worker's sandbox default.
- Old jobs/callbacks remain held, tenant/realm/identity checks, context cleanup,
  and existing reservation/history preservation.
- Nullable migration and independent QA/Security on the exact candidate.
- Protected PR checks, migration → approved-PR-head worker (all older consumers
  retired) → identical-tree merge/API/UI deployment. This avoids changing shared
  automatic deployment triggers or exposing new admission before workers guard it.
- Signed-in payment-choice verification without recording real money.

Rollback: retain the additive nullable schema and roll back application images
if no new authorization has been created. Once new receipts exist, preserve their
authorizations and accounting obligations; do not downgrade the schema or replay
held history. No global worker environment change or PR372 activation is included.
