# DB-048: one-invoice gross receipt correction

Status: Architecture-selected correction; local implementation in progress.
Accountable owner: Backend & Integrations.
Contract reviewer: independent Architecture & API Contracts.
No production activation or historical financial rewrite is authorized here.

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
   Keep the importer's single-invoice/tenant/charge identity fences.
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

The projection foundation alone is not the production fix. Until persistence,
writer, refund/tax and importer integration are complete, the current runtime
continues unchanged and the new composition remains unactivated. No tenant
records, native Deposits/Purchases, invoice settings or Fleet UI are changed.

This model uses ordinary Invoice updates and Payment allocations. It does not
claim that changing a Payment payload makes Intuit automatically include it in
a native payout. That remaining provider behavior must be described precisely,
not confused with the already observed actual tenant payout/fee evidence.
