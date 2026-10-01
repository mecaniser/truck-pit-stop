# DB-094: ELIS fleet invoice import contract (architecture draft)

Owner: Backend & Integrations. Lane: high risk (invoice data, API credentials,
tenant isolation). Architecture & API Contracts owns this contract; independent
Security and QA gates are required before release.

## Scope and eligibility

An ELIS connection is bound to one DieselBridge shop tenant and one explicit
bill-to customer ID. The export includes finalized invoices whose immutable
`Invoice.billed_customer_id` equals that bill-to ID, or whose separately
reviewed historical mapping grants that exact bill-to scope. Current
repair-order customer, `Invoice.is_internal`, vehicle owner, operator, and
fleet membership do not grant access. Historical invoices without a verified
snapshot or approved mapping stay excluded; current RO customer cannot safely
backfill the snapshot after a merge. Invoice, repair order, customer, vehicle,
mapping, and credential must all belong to the same shop tenant.
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
For reviewed historical mappings, approval/update time also participates in
the revision. A revoked or changed mapping requires a durable scoped removal
event for the formerly authorized bill-to even though the invoice is no longer
eligible for the normal query; see below.

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

## Historical bill-to review and mapping follow-up

Migration 151 leaves preexisting `Invoice.billed_customer_id` values null.
The customer merge endpoint moves the loser's repair orders to the winner and
deletes the loser, while invoices remain attached to those orders. Therefore
`RepairOrder.customer_id` after a merge, current customer/vehicle ownership,
VIN, an account name, and a newly regenerated PDF are insufficient evidence
of the original bill-to. Review is per invoice; no bulk assignment from those
fields or from a shared repair order is permitted. A reviewer may group cases
for display but must inspect and record evidence for every invoice.

### Evidence and owner action

Create a tenant-owned evidence record per historical invoice, with immutable
source fields and a restricted copy of the source artifact. Staff upload the
actual PDF, source JSON, or original email; the server computes its hash. It
records invoice and repair-order IDs, source type and stable source reference,
source bytes and content hash, capture time, the original bill-to identity shown by
the source (customer ID where genuinely preserved, otherwise an explicit
unknown ID plus verified legal name/reference), and any merge lineage used.
Acceptable sources are an immutable original invoice/receipt, preserved source
system record, or contemporaneous billing correspondence with an attributable
recipient. A regenerated DieselBridge PDF, current RO/customer/vehicle fields,
VIN match, or owner assertion alone cannot establish the original bill-to.
Only same-tenant staff can download source documents; the feed exposes none of
their contents or customer contacts. A different staff member must inspect
the stored artifact and record the observed invoice number, bill-to name,
target customer ID, matching server-computed hash, and verification note.
The uploader cannot verify their own evidence. The owner can approve only
evidence verified for that exact target. Preserve source bytes, hash, and
reference after an approval is undone.

The shop owner sees the invoice identity, original-evidence summary, proposed
active bill-to customer, and any merge lineage before deciding. Approval
requires a reason, verified evidence ID, target active customer ID, and an explicit
attestation that the target is the same legal bill-to (or a documented lawful
successor) shown by the original evidence. The original identity and evidence
remain immutable; the approved export target is a separate, versioned mapping.
The initial implementation requires the target's active legal name to match
the observed bill-to name and holds cases where multiple active customers in
the shop share that name. A target name change after verification invalidates
the approval, and an approved target's legal-name change or deletion is blocked
until its mapping is revoked. Different-name successors and duplicate-name
accounts remain pending until separate stable-identity or lineage evidence and
verification are implemented; a typed customer ID or merge-reference string
alone never authorizes them. If legal continuity
is not supported, leave the case pending. The owner
may reject or revoke a mapping with a reason. Only the shop owner may approve,
change, or revoke; API keys cannot perform review. Edits use a version
precondition and idempotency key so stale or repeated submissions cannot
silently overwrite another decision. A change of target is revoke-old then
approve-new in one transaction, producing both scope events.

### Tenant boundary, revisions, and undo

Enforce the same tenant on invoice, RO, evidence, mapping, reviewer, target
customer, and export key at read and write time. The target must be active
and cannot be inferred from a deleted merge loser. A conflicting native
`billed_customer_id` cannot be overridden by historical mapping; correction
of a native snapshot is a separate audited financial-data process. Review
does not mutate invoice, RO, payment, or ledger facts.

Approval adds the invoice to only the approved target's feed and enables PDF
access there. Revocation or target change immediately removes list/PDF access
under the old scope and emits a durable `access_removed` event to that
bill-to's feed, carrying only shop ID, invoice ID, event ID/revision, and
effective time. It is not represented as a financial cancellation or void.
Approval emits an `invoice` representation with a new revision. These events
survive key rotation. Customer merge/deletion is blocked while a reviewed
mapping or scoped removal event exists, since deleting the old bill-to would
make its key unusable before ELIS can reconcile. A future reconciliation
acknowledgment is needed before that merge path can reopen. Page ordering and cursor/watermark
semantics cover mapping events as well as normal invoice changes; repeated
windows and interrupted pages are idempotent. ELIS marks an imported invoice
as access/review required on removal and flags any accepted expense for owner
correction; it never silently deletes or reverses posted entries. A revoked
mapping may be reapproved only with a new versioned decision and source event.

Every decision appends a tenant-scoped audit event with actor, invoice,
evidence ID/hash, original identity, old/new target, action, reason, version,
and timestamp, omitting document contents and contacts. The audit and scope
events are committed atomically with the mapping state. Review endpoints
return 404 for cross-tenant IDs, 409 for stale versions or conflicting
native bill-to, and 422 for missing or inadequate evidence. No production
historical mapping is made by the migration.

### Migration and acceptance

Add separate historical evidence, versioned mapping/decision, and scoped
export-change storage with tenant-aware keys and uniqueness for one active
mapping per invoice. Migrate schema only; leave all old invoices pending and
keep migration 151's null snapshots unchanged. Backfill candidates may be
listed for review without granting access. Rollout requires a dry run count by
tenant and proposed target, sampled source-document verification, and explicit
owner decisions before any key can retrieve newly mapped history.

Test an unmerged original bill, loser/winner merge before review, unrelated
same-name customer, cross-tenant evidence/target, deleted target, internal or
draft invoice, forged evidence, concurrent owner decisions, idempotent retry,
approval visibility and PDF, revocation/retarget removal to old scope, replay
after key rotation, cursor continuation across mixed invoice and scope events,
and ELIS handling of an already accepted expense on access removal.
