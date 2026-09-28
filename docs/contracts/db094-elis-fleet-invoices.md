# DB-094: ELIS fleet invoice import contract (architecture draft)

Owner: Backend & Integrations. Lane: high risk (invoice data, API credentials,
tenant isolation). Architecture & API Contracts owns this contract; independent
Security and QA gates are required before release.

## Scope and eligibility

An ELIS connection is bound to one DieselBridge shop tenant and one explicit
bill-to customer ID. The export includes finalized invoices whose immutable
`Invoice.billed_customer_id` equals that bill-to ID. Current repair-order
customer, `Invoice.is_internal`, vehicle owner, operator, and fleet membership
do not grant access. Historical invoices without this verified snapshot stay
excluded until separate bill-to review; current RO customer cannot safely
backfill the snapshot after a merge. Invoice, repair order, customer, vehicle, and credential
must all belong to the same shop tenant.
Merging a bill-to account that has an active export credential returns 409 until
the connection is revoked and reconciled. After a merge, the deleted bill-to
identity cannot be used to authorize old invoices; access requires a separate
verified mapping review, never an automatic reassignment.

DieselBridge returns vehicle identity. ELIS imports only when a normalized,
nonempty VIN uniquely matches a truck (not trailer or SUV) in the connected
ELIS tenant. Two trucks is not a configured limit; later trucks qualify when
added to ELIS. Missing or duplicate VINs, or a vehicle-type mismatch, require
review, with no repair expense or journal entry. A later VIN or assignment
change must not silently remap an imported invoice to another ELIS truck.

One credential per bill-to account. Additional legal bill-to customers require
separate, explicitly provisioned connections. Credentials are read-only,
random, hashed at rest, shown once, revocable, and independent of the
conversion export key. Only the shop owner creates or
revokes them. JSON omits raw customer contacts, notes, attribution, and payment
method data. PDF content needs separate privacy review: the current staff PDF
renderer includes customer contact fields and invoice notes. The integration
PDF must omit unnecessary contact/notes and payment details, or the document
must be approved as a customer-visible bill before provisioning.

## v1 API

`GET /api/v1/fleet-invoice-exports/invoices?updated_since=<UTC>&updated_before=<UTC>&limit=100&cursor=<opaque>`
with `X-API-Key`. The first page fixes an exclusive `updated_before` sync
watermark. Subsequent pages use an opaque, authenticated cursor bound to that
watermark, the credential, filters, and last
`(effective_updated_at, invoice.id)` tuple. Return
`{items, next_cursor, watermark}` in ascending tuple order. ELIS advances its
stored watermark only after every page has been durably applied.
`effective_updated_at` is the greatest invoice, repair-order, and vehicle
`updated_at`, so VIN, unit, and mileage corrections reappear in the feed as
well as invoice status, amount, void, and replacement changes. An overlap
window is required because commit order can differ
from timestamp order. The keyset cursor must not miss equal-timestamp rows.

Items carry `invoice_id`, `invoice_number`, `repair_order_id`, `vehicle_id`,
`vin`, `unit_number`, `mileage_in`, `mileage_in_carried`, `invoice_date`,
`effective_updated_at`, `status`, `voided_at`,
`supersedes_invoice_id`, `subtotal`, `shop_supplies_amount`,
`service_fee_amount`, `tax_amount`, `discount_amount`, `total_amount`,
`currency`, and finalized labor/parts snapshot. For native invoices,
`invoice_date` derives from `created_at`; for Easy Truck Shop imports it
derives from `ets_invoiced_at` when present, with fallback provenance
explicit. Drafts are excluded; cancelled/voided invoices remain in the feed
so ELIS can reconcile a prior import. Supersession links distinct invoice IDs,
not revisions of one ID. The source invoice ID is durable identity; an
effective revision timestamp or monotonic version identifies changes. Money
is a decimal string in USD.

`GET /api/v1/fleet-invoice-exports/invoices/{invoice_id}/pdf` uses the same
credential and eligibility predicate. It returns 404 for inaccessible or
absent invoices. It never redirects to the existing staff/customer PDF route
or exposes a signed URL without equivalent scope enforcement.

`POST /api/v1/fleet-invoice-exports/api-keys` binds the credential to a
same-tenant bill-to customer. Listing and revocation are staff-only and use
the normal user session, never an integration key. Invalid or revoked
credentials return 401. Invalid cursors or time bounds return 422; cursor
reuse with another key, scope, or filter fails. Data outside the credential's
tenant/customer returns 404. Limit is capped at 100. Revocation takes effect
on every later list and PDF request. Logs redact keys and invoice payloads.

## ELIS import contract

ELIS needs a tenant-scoped import record with unique `(ELIS tenant ID,
source_system, DieselBridge shop ID, invoice ID)`, last applied revision,
matched truck ID, review state, and document reference. The current `Repair`
model has only `invoice_number`, without a durable external invoice key or
revision, so direct import into `repairs` cannot guarantee idempotency.
Apply each revision atomically with its cursor progress; replay is a no-op.
Stage unmatched and revised invoices for operator review.

An accepted invoice may produce one repair expense only after the ELIS
repair/accounting workflow confirms its cost treatment. Source `paid` status
is not proof of payment by ELIS and does not automatically post cash, reserve
usage, or a journal entry. Voids and replacements flag accepted expenses for
explicit correction; they never silently overwrite posted ledger entries.
Neither system creates a DieselBridge payment or changes invoice financial
state during import.

## Verification and rollout

Use fixtures for two bill-to customers in one shop, another shop, an internal
invoice, a cancelled and superseded invoice, a mutable bill-to attempt, a VIN
absent from ELIS, and two ELIS trucks with the same VIN. Prove negative
auth/tenant cases, key revocation, PDF parity, changed invoice revision,
cursor continuation, interrupted-page replay, and duplicate-safe ELIS import.
Release the read-only API before provisioning the ELIS connection; import dry
run and reconciliation precede automatic expense posting. No production key
or customer mapping is assumed by this document.

Historical invoices without a verified immutable bill-to are not automatically
eligible. A separate reviewed mapping/backfill is required if historical import
is requested. The source API can ship without making that authorization guess.
