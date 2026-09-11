# DB-048 customer tax-exemption default

Backend accountable; root owns profile UI/release. Baseline d2a37545. No reason
field, mandatory certificate, automatic Cash exemption, or retroactive invoice edits.

## Profile API and persistence

Owner/admin with payments permission only: GET and PUT
`/api/v1/customers/{customer_id}/tax-exemption`.
GET/PUT response: `{tax_exempt:boolean,support_reference:string|null,version:int,updated_at:ISO|null}`.
PUT requires Idempotency-Key and body `{tax_exempt:boolean,support_reference?:string|null,expected_version:int>=0}`.
Reference omitted/blank normalizes null; nonblank max255. Extra fields forbidden.
Baseline false/null/version0/updated_atnull. Tenant-scoped active tenant/customer;
unauthorized/inaccessible404, invalid422, staleversion409, conflictingkey409.
Exact replay returns current state without another mutation. Profile command
locks customer row; records immutable actor/time/before/after/version/request audit.
No tax fields are added to generic self-service CustomerUpdate or creation payload.

Migration144 adds customer boolean/reference/version/changed-at fields and one
append-only tax-default audit table with tenant/customer coherence checked by an
INSERT trigger and key uniqueness. Customer ID is an archived identity reference,
not a delete-blocking FK: existing merge/delete flows retain immutable loser audit
and its customer identity snapshot; winner setting never inherits loser exemption.
Audit UPDATE/DELETE prohibited; downgrade refuses recorded changes. A savepoint
contains cross-customer idempotency collisions and returns409 without state change.
No Invoice column addition or historical proof regeneration.

## Issuance and previews

Both native constructors in invoices.py (automatic completion and manual
issuance/reissue) read/lock the final same-tenant bill-to customer after recipient
selection. Current true setting zeros sales tax including card-fee tax; supplies,
repair net and service fee remain unchanged. Record immutable invoice.tax_exemption
snapshot with source=customer_profile, customer/version, setting audit ID,
issuer and original/revised amounts. Snapshot only upon new invoice creation.
Toggle and issuance serialize on customer row. A later toggle cannot change the
issued snapshot; all existing explicit invoice-exemption/payment guards stay intact.
New successor invoices use current profile; resend/reprint preserves old values.
ETS source imports remain unchanged; merge keeps winner profile, loser audit retained.

Pricing helper takes explicit keyword tax_exempt=False. New-order previews resolve
current final bill-to; issued-invoice displays and receipts use stored invoice
amounts/audit, never a current customer flag. Dedicated read-only profile preview
data is permission-scoped; reference must not leak into guest/customer output.
Frontend may pass explicit tax_exempt into its unissued price-builder arithmetic;
server issuance remains authoritative. Cash selection alone never changes tax.

## Gate

Test role/tenant/deleted targets, optional reference normalization, length/extra
validation, exact replay/conflict/stale version, immutable audit and migration
upgrade/downgrade, concurrent toggles/issuance, both native constructors, final
bill-to switch, future successor/current-default behavior, old issued immutability,
all tenders' zero fee tax, supplied fees retained, and no tax-default importer side
effects. Independent QA/Security before release; production migration separate.
