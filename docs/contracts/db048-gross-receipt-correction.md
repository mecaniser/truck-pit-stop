# DB-048: one-invoice gross receipt correction

Status: Runtime correction implemented locally; independent local QA/Security GO.
Accountable owner: Backend & Integrations.
Contract reviewer: independent Architecture & API Contracts.
No production activation or historical financial rewrite is authorized here.

## Sandbox acceptance correction contract (2026-09-10)

- US fee-tax invoices use line `TAX`/`NON` indicators and the verified transaction
  `TxnTaxCodeRef`; mapped TaxRate identity, signed tax base, and total must still
  match provider readback. Mixed transaction tax codes fail closed. Preserve
  existing no-tax snapshots and never rewrite historical posted compositions.
- Invoice adjustments may cause QBO to clip a receipt's allocation and advance
  its version; reread and validate only the exact expected cap-derived state.
  The provider's omitted deposit account is allowed only on a verified zero
  receipt with explicit empty lines and zero unapplied money. Positive recovery
  must restore and verify the original snapshotted clearing account. Genuine
  numeric5010 responses use bounded retries, including successful final-attempt
  readback; no foreign identity, account, or money change is adopted.
- Actual sandbox refund `MT7353020517` returned `ISSUED`; its charge
  `MT0359488296` subsequently read `CANCELLED`. Treat issuance as provider
  acceptance, not proof of bank settlement. Do not misclassify it as rejection.
- Intuit's [official SDK refund tests](https://github.com/intuit/PHP-Payments-SDK/blob/master/tests/ChargeTest.php)
  assert `ISSUED` as the successful submission response. Its
  [official Java sample refund model](https://github.com/IntuitDeveloper/SampleApp-Payments-Java/blob/master/src/main/java/com/intuit/sample/payment/model/Refund.java)
  defines `ISSUED`, `DECLINED`, and `SETTLED`. Normalize verified `ISSUED` as
  accepted/pending, `SETTLED` as succeeded, and `DECLINED` as failed, retaining
  the exact refund identity in all cases. Never infer settled from issuance
  alone. Known-ID polling must cover settlement timescales, not exhaust an
  error retry budget within minutes for an ordinary pending refund. Unknown
  outcomes and genuine errors remain bounded/actionable. Payout/expense
  evidence remains separate from refund state.
- Ordinary known-ID `ISSUED` polling uses a six-hour interval with a fourteen-day
  deadline from refund creation; beyond that, retain the pending refund and ID
  with an actionable dead outbox item. This does not submit money again.
- Persist a returned refund identity before any retry. A known identity is
  reconciled through GET on its original charge, never another POST. Verify
  tenant, original provider account/realm, charge, refund identity and amount.
- If submission outcome is unknown without an identity, keep an actionable
  unresolved state rather than automatically submitting another refund. A
  replay HTTP400 is not proof that an earlier accepted refund failed.
- Retry/worker transaction handling must retain accepted identities across
  commits and lease checks; bounded retries must end in an actionable state.
  Stripe behavior remains unchanged. No new migration is intended.
- Acceptance requires focused negative/tenant-isolation and worker persistence
  tests, independent non-implementing review, and GET-only verification of the
  already-created sandbox refund. No additional refund or charge is authorized
  merely to test a correction to retry handling.

## Evidence and defect boundary

Real tenant evidence is already recorded in PROJECT_BOARD.md: QBO Deposit
5728 totals 1,259.08 from Payments 5713 and 5724; native fee Purchase 5729 is
35.77 and the observed net payout is 1,223.31. These are existing tenant
records, not DB-048-created payments. This proves an available gross-payment,
deposit, and actual-fee structure. It is not missing payout evidence.

Our existing writer instead emits principal-only Payments and separate fee
journals. Its successful surcharge fixture constructs Deposit-to-journal links
that the real sample does not establish. There is no missing reference-label
fix: the importer already understands the writer's exact `QBP <charge>` label.
The correction must align the accounting representation, not guess fees or
weaken native identity checks.

## Selected representation

Preserve one canonical repair Invoice in QBO, the original invoice number,
and immutable local repair principal. Do not introduce companion fee invoices.

For original principal B and confirmed earned components P, F, T:

- QBO invoice total is B plus the sum of earned customer fees F and fee tax T.
- A card Payment records captured gross G and applies P+F+T to this invoice.
- A Zelle Payment applies principal only and adds no card fee.
- Local principal paid is the sum of P, never the sum of gross Payments.
- Actual excess G-(P+F+T) remains explicit refundable unapplied customer money.
- Fee income is recognized on the new invoice composition, never again by the
  legacy fee journal for that same component.
- Actual processor expense still comes from the provider settlement evidence.

Example: a 1,000 invoice paid by card principal 200, 300, 100 and Zelle 400,
with card fees 6, 9, 3, produces one 1,018 QBO invoice and four Payments of
206, 309, 103, 400. Both QBO balance and local principal balance become zero.

## Implementation sequence and acceptance

1. Pure, versioned deterministic projection: scoped immutable attempt inputs,
   earned principal/fee/tax, gross allocation and real unapplied excess. Reject
   foreign identities, duplicate attempts, invalid monetary precision, unknown
   composition, and over-allocation. Reordering equal inputs preserves the
   projection revision. This foundation performs no IO or accounting writes.
2. Persist composition version, projection revision and returned fee-line
   identities. Preserve all historical principal/journal records. Mixed legacy
   invoices need an explicit compatibility path; do not silently migrate them.
3. Replace BOTH existing-ID and DocNumber adoption paths in
   `_ensure_db048_qbo_invoice`. They currently reset the QBO invoice to principal
   only and would erase appended fee lines. Validate expected line semantics;
   preserve unexpected provider edits as a visible conflict, not an overwrite.
4. Serialize changes per invoice, GET current SyncToken, and boundedly reread
   and retry on stale-token conflicts. Invoice update request identity includes
   projection revision; never reuse a fixed key for different invoice bodies.
5. Update and read-verify the invoice before issuing its gross accounting
   Payment. Retrying an interrupted operation neither duplicates a fee line
   nor creates a second Payment. Never set ProcessPayment to charge again.
6. Verify customer, realm, currency, same invoice ID, exact line allocation,
   gross and unapplied amounts before acknowledging accounting completion.
   Keep tenant/customer/realm/charge identity fences. Additional invoice
   allocations require exact persisted customer-credit application evidence;
   unrelated or amount-only matches remain rejected.
7. Implement version-aware partial refunds, reversals, disputes and recovered
   funds so posted fee obligations are adjusted auditably without deleting
   financial history or re-recognizing fee income.
8. Fee item mapping and actual QBO tax-code mapping must return the exact frozen
   earned tax. A sales-tax-liability account is not a sales item or tax code.
   Do not silently turn unknown tax mapping into zero tax.
9. Independent QA and Security must cover all changed paths and historical
   compatibility before activation. Integration acceptance remains distinct
   from deterministic local fixtures. No new synthetic/live charge is required
   merely to implement or test this local correction.

## Scope fences

### Versioned runtime correction

Migration `139_qbo_gross_composition` persists the immutable composition and
projection snapshots. Existing settlements and invoices with payment/accounting
history remain `legacy_principal_v1`. New eligible invoices select
`gross_invoice_v1` only with `DB048_GROSS_QBO_ACCOUNTING_ENABLED`; this flag
defaults off. Turning it off does not reinterpret already-selected invoices.

Fee items and tax codes are frozen configuration-version mappings. Earned fee
tax must match the actual mapped QBO tax rate and returned invoice tax exactly.
Unsupported or compound mappings fail closed rather than estimate tax.

Reversal/dispute/recovery history retains the original positive fee line and
appends signed compensating lines identified by immutable accounting events.
This changes the original invoice's accounting period; it is not a separate
current-period credit memo. Closed-period invoices are rejected before update.
Signed tax-line behavior still requires provider acceptance before activation.

Refund integration covers the existing domain's actual unapplied-overpayment
refunds. It does not add an earned-service partial-refund product workflow.
Customer-credit applications update allocations on the original gross receipt,
never create a second receipt or convert an earned fee into customer credit.

Persistence, writer, refund/tax, customer-credit and importer integration now
exist in the isolated candidate. The running preview and production runtime
remain unchanged and the new composition remains unactivated. No tenant
records, native Deposits/Purchases, invoice settings or Fleet UI are changed.

This model uses ordinary Invoice updates and Payment allocations. It does not
claim that changing a Payment payload makes Intuit automatically include it in
a native payout. That remaining provider behavior must be described precisely,
not confused with the already observed actual tenant payout/fee evidence.

### Acceptance boundary

Local integration tests use real settlement/domain transitions and mocked
provider responses. Migration rehearsal uses a separate schema-only PostgreSQL
database. Neither is evidence of a new Intuit-produced payout. Before production
activation, verify the candidate's signed fee/tax invoice updates and native
payment-to-deposit linkage in the provider environment; then complete the
protected CI, merge, migration and deployment checks for the exact candidate.
Do not manufacture deposits, backfill fee estimates, or rewrite historical
principal-only invoices to clear that acceptance boundary.
