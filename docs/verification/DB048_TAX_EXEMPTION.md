# DB-048 explicit tax exemption

Owner: Backend & Integrations. Scope: explicit one-time staff exemption before
payment, independently of tender. Contract: `../contracts/db048-tax-exemption.md`.

## Frontend evidence

- Eight exemption component tests: required evidence, server total, cancellation,
  exact version/body, uncertain-response identity, pending guard, applied audit,
  temporary lock retry and stale-version protection (some combined assertions).
- Seven staff tender tests, including exemption editing disabling payment
  submission until cancellation/application, with Cash remaining inline.
- Existing full-cash nine and settlement UI twenty-seven tests passed.
- TypeScript, changed-source ESLint, production Vite build passed.
- CUA rendered local fixture at desktop and390px: disclosure, required labels,
  revised total, Cancel, required evidence enabling submit. At390px document
  width390px; no overflow. No submit was performed; fixture blocked API calls.
- Screenshots retained locally in `output/tax-exemption/desktop.png` and
  `mobile.png`; independent reviewer found no material visual issue.
- Preview files/server removed after verification; existing user tabs preserved.

## Gate status

Owner backend237/237 passed across exemption, cash/history/settlement, invoice
snapshot and QBO projection tests. Isolated PostgreSQL15 on55441 passed3/3
true concurrency cases, read-model tax update and immutable audit checks.
Migration143 fresh upgrade ->142 downgrade ->143 upgrade passed before test
audits were created. The race test exposed and corrected stale ORM identity
after waiting for a settlement row lock; locked reads now populate existing
state before checking the expected version. No global lock behavior changed.

Independent QA/Security is reviewing backend and migration proof. Initial
findings on temporary lock retry, deleted entities and predecessor financial
history were returned to owners; final verdict and candidate identity pending.
This document does not establish production deployment or historical receipt
closure. No real invoice exemption, payment, cash receipt, reservation release,
or QuickBooks write was performed.

## Release boundary

Migration143 adds a nullable audit column and immutable-audit trigger; no
historical backfill. Apply before API/worker code reads that column. Preserve
all existing flags, export holds, provider configuration and reservations.
Rollback application code if the new endpoint or summary fails; retain the
additive column. Never downgrade away recorded exemption audits. Signed-in
production read-only verification follows deployment; applying an exemption to
a real invoice is a distinct financial record change.
