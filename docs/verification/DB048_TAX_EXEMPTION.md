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
- Preview was removed after initial verification, causing the reported file-not-found.
  It was restored at `http://127.0.0.1:5194/exemption-preview.html`, verified in
  the Codex in-app browser and left running. It is clearly labeled example data
  and uses a local mock adapter, not the real API.

## Gate status

Owner backend237/237 passed across exemption, cash/history/settlement, invoice
snapshot and QBO projection tests. Isolated PostgreSQL15 on55441 passed3/3
true concurrency cases, read-model tax update and immutable audit checks.
Migration143 fresh upgrade ->142 downgrade ->143 upgrade passed before test
audits were created. The race test exposed and corrected stale ORM identity
after waiting for a settlement row lock; locked reads now populate existing
state before checking the expected version. No global lock behavior changed.

Independent QA/Security GO at `beeed6bf02016fde50632ff3ec80238f10abae6c`:
backend237/237, PostgreSQL3/3, UI15/15 independently rerun; desktop/mobile
screenshots reviewed. Initial findings on temporary lock retry, deleted entities
and predecessor financial history were corrected and independently rechecked.
All six PR377 CI checks passed. PR377 merged as
`777bdcc78c74cfe56cbc5b7617b105da1871bba0` (identical reviewed source tree).
No real invoice exemption, payment, cash receipt, reservation release, or
QuickBooks write was performed. Historical receipt closure is separate.

## Ordered production migration

Migration143 installed before API/worker builds, using exact reviewed migration
blob `04cb06b249928cd436113d5c2866850bcc0f9668`. The independently reviewed
one-transaction runner SHA256 is
`7fcc138b9862482db6f4f27edab7dc096a2eb5297d93825a0f6517160d9c854d`;
it passed an isolated PostgreSQL rehearsal first. Expected head142, bounded
lock/statement timeouts, exact source identity and before/after fingerprints
were enforced. All new exemption values were null.

| Table | Rows | Unchanged fingerprint |
|---|---:|---|
| invoices | 2167 | `30abf80efec23368da3cc87b757aa8dc` |
| invoice_settlements | 1381 | `501c23481d56cde59685b4d46a35f918` |
| invoice_payment_attempts | 3 | `e597fb7a1f0b991f7a2af34e39ef11ad` |
| payments | 2283 | `49db975ad19af763ae9f6a4e2a8298ff` |
| provider_outbox | 587 | `f6417ebab414de3c29ae5e362b8a4510` |

API deployment `c4ddfb40-cb4a-47fd-bed3-b41fbecd95b4` and worker deployment
`0248a624-5760-4b0b-8815-ee186197b0f1` successfully deployed merge777bdcc7;
database/Redis readiness passed. Signed-in runtime acceptance then FAILED:
INV000020 lost its preserved ancestor-proof match because the new nullable
audit field was included in the generic all-column invoice history digest.
Read-only production comparison proved its parent had a null audit, its
current digest differed, and the pre143 digest still exactly matched the stored
proof. No record changes caused this failure.

## Historical-proof compatibility correction

Branch `codex/db048-tax-audit-history-compat` adds a NULL-only compatibility
rule for the Invoice audit field. Non-null audits and every other history field
remain bound. No proof is regenerated or changed. Five regression cases cover
a persisted pre143 proof through actual Cash and exemption eligibility, audit
tampering, financial drift and an unrelated formerly-null field. Owner focused
suite62/62 passed; independent review, protected CI and signed-in successor
verification remain required. PR377 alone is not accepted as the final release.

## Release boundary

Migration143 adds a nullable audit column and immutable-audit trigger; no
historical backfill. Apply before API/worker code reads that column. Preserve
all existing flags, export holds, provider configuration and reservations.
Rollback application code if the new endpoint or summary fails; retain the
additive column. Never downgrade away recorded exemption audits. Signed-in
production read-only verification follows deployment; applying an exemption to
a real invoice is a distinct financial record change.
