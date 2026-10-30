# DB-094: Elis repair-order history v1

Architecture & API Contracts handoff, 2026-10-30. Accountable implementation
owner: Backend & Integrations. High-risk lane because a tenant boundary and new
persistent consumer history are involved. Independent Security and QA gates are
required; this contract is not a release or import receipt.

## User outcome and authorization

The user explicitly requested the 15 completed repair orders visible in **Truck
Pit Stop → Elis Logistics LLC (DBN)** under their correctly matched Elis trucks.
The read-only audit found 15 nondeleted paid ROs: 6 for unit 603 and 9 for unit
609, all uniquely VIN-matched in Elis tenant 1. There is one additional cancelled
RO and 20 soft-deleted ROs; neither belongs to this 15-record target.

This is an operational service-history representation. The existing invoice
feed represents only seven of those ROs, through twelve invoice versions. Eight
other finalized invoices have no immutable bill-to or approved historical
mapping. Those invoice/PDF restrictions stay intact. An RO's current customer
assignment must never backfill `Invoice.billed_customer_id` or grant invoice,
PDF, payment, or ledger access.

The existing read-only connection remains bound to one shop and explicit
customer. The new endpoint returns only the same customer's nonfinancial RO
metadata expressly requested by the user. No new credential, role, persistent
permission flag, other customer, other shop, or historical invoice grant is
needed for this narrowly defined metadata import. Any proposal to add monetary
amounts, invoice references outside existing invoice scope, documents, contacts,
private notes, or another customer returns to Security/Architecture and requires
its own authorization before exposure.

## Source API

`GET /api/v1/fleet-invoice-exports/repair-orders` with the existing `X-API-Key`.
There are no customer/shop selectors, incremental filters, or pagination. It is
a complete, bounded snapshot. The implementation hard-caps eligible results at
1,000, reading at most 1,001 rows. More than 1,000 is HTTP 409
`repair_history_snapshot_too_large`; it must never return a successful partial
snapshot or truncate silently. A later paginated contract can replace this cap
only with equivalent complete-snapshot and removal guarantees.

Use the existing active-key guard on every request. Credential, active shop,
active/nondeleted customer, RO, and vehicle must have the same shop tenant.
Eligible ROs have all of:

- `RepairOrder.customer_id == key.customer_id`;
- `RepairOrder.tenant_id == key.tenant_id` and vehicle in that same tenant;
- nondeleted RO, `is_internal == false`;
- status in `completed`, `invoiced`, or `paid`.

Current vehicle ownership or fleet membership does not independently grant RO
access. Trailers/SUVs are not guessed from source labels: the consumer's unique
truck/VIN matching decides whether a row can be attached. Keep unmatched source
rows in review rather than dropping them from counts. Do not join invoice data
into eligibility or infer invoice authorization from these operational rules.

One joined SELECT materializes the eligible RO/vehicle snapshot, ordered by RO
ID. Serialize that materialized result; do not issue per-row later reads that
could mix revisions. Response is `Cache-Control: private, no-store`:

```json
{
  "version": "db094-repair-history-v1",
  "shop_id": "shop-uuid",
  "customer_id": "customer-uuid",
  "snapshot_id": "sha256-of-canonical-scope-and-items",
  "complete": true,
  "count": 1,
  "items": [{
    "repair_order_id": "ro-uuid",
    "order_number": "TPS-828ACD84-000058",
    "vehicle_id": "vehicle-uuid",
    "vin": "1M8GDM9AXKP042788",
    "unit_number": "603",
    "status": "paid",
    "description": "Customer-visible repair description",
    "created_at": "2026-10-19T10:00:00+00:00",
    "work_completed_at": "2026-10-19T15:00:00+00:00",
    "service_date": "2026-10-19",
    "service_date_source": "work_completed_at",
    "revision": "sha256-of-canonical-item-without-revision"
  }]
}
```

Dates preserve source timestamps normalized to UTC (naive source timestamps are
explicitly treated as UTC). `service_date` uses the UTC date of
`work_completed_at`; if absent, the UTC date of `created_at` is an explicit
`service_date_source: created_at_fallback`. Preserve both timestamps. Never
substitute invoice creation/regeneration time for service completion.

`description` is only `RepairOrder.description`, which is customer-facing. Do
not expose `internal_notes`, `shop_notes`, `customer_notes`, customer contacts,
attribution, mechanic identity, monetary totals, pricing, invoice IDs/numbers,
invoice snapshots, payment status/details, PDF URLs, or document bytes. `status`
is an RO workflow status, not proof of payment by Elis. Odometer/PM writes and
labor/parts detail expansion are outside this minimal metadata version.

Canonical hash bytes are UTF-8 of Python-equivalent
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`
with no trailing newline; hashes are lowercase SHA-256 hex. UUIDs are lowercase
strings, timestamps use UTC `datetime.isoformat()` (`+00:00`, with actual source
microseconds if present), and dates use ISO calendar dates. Item revision covers
only the allowed source representation.
Snapshot digest covers version, shop/customer scope, and the ordered full item
list. Hashes are revision/consistency identifiers, not authorization grants;
TLS and the active scoped credential provide authorization. Rotation of a key
within the same scope need not create new history identities.

Invalid/revoked key: 401. Inaccessible scope cannot be selected. Oversize source
snapshot: 409 with no partial response. The existing invoice list, invoice PDF,
key provisioning, merge guards, and historical evidence/mapping APIs retain
all prior semantics. Tests must prove RO export does not make an otherwise
inaccessible historical invoice/PDF readable.

## Elis persistence and application

Add separate nonfinancial source-history storage; do not create `Repair`,
`FinanceEvent`, `FinancePosting`, reserve, journal, payment, or bill rows during
history import. Identity is unique `(Elis tenant, source_system, shop_id,
repair_order_id)`; customer scope is retained and cannot silently change.
Store source payload/revision, last complete snapshot, matched truck ID, state,
review reason, date provenance, and optional existing-history candidate IDs.
One RO remains one history entry across invoice replacements.

Only an authorized tenant-1 operator can sync this connection or view its rows.
Reuse the established accounting authorization; a header selects a tenant and
never grants it. List history optionally by a tenant-checked truck ID. Expose no
credential values or configurable arbitrary source URL to the browser.

A history-sync operation runs entirely in a worker thread, with the tenant
write lock held before source fetch through atomic validation/application and
commit. This serializes concurrent full snapshots without blocking the ASGI
event loop. A dry run rolls back and reports counts, matches, existing-history
candidates, and changes. Source/client errors roll back all changes.

Before writing, validate version, exact shop/customer scope, `complete == true`,
count equality, at most 1,000 items, unique RO IDs, required allowed fields,
revision/snapshot consistency, valid timestamp/date provenance, and allowed RO
statuses. No successful partial response can authorize absence handling.

Match only nonempty normalized VIN (remove whitespace, uppercase) to exactly one
`truck` in the authorized Elis tenant. Missing/duplicate VIN, no match,
trailer/SUV-only match: retain a review row, no financial effect. Once linked, a
changed VIN or source/local assignment never silently moves the row to another
truck; preserve the original truck link and mark review required. Replays do
not duplicate rows. A changed allowed source revision updates the history row
and its visible provenance without modifying existing expenses.

After a fully validated complete snapshot, previously imported scope rows not
present are marked `source_unavailable`/review-required, never deleted or treated
as a financial void. Keep durable identity/original assignment; withhold cached
work description from normal source-history output for unavailable access.
Reappearance can restore visible history only under the same scope and unique
original-truck identity. Do not infer which absence reason occurred.

Existing Elis repairs are reconciliation candidates, not automatic matches.
Find candidates by tenant truck and service date (and available descriptive
signals); retain their IDs as a review annotation. An exact invoice-number scan
found no matches in the earlier audit, but renumbered/reissued documents make
that insufficient proof of no historical overlap. Never auto-merge, delete,
reassign, duplicate a cost, or change payment confirmation based on a candidate.
The separate RO-history section may show all 15 operational entries while
keeping legacy cost records intact.

## Consumer UI and fixtures

Maintenance & Repairs shows the imported RO history separately from invoice
cost review and legacy expenses, with source order number, matched truck,
service date/provenance, customer-visible description, source status and review
badges. The vehicle detail repair/history surface filters to that truck. It
must not label a source `paid` RO as an Elis-confirmed payment or add expense
accept/edit/delete controls to the source-history records.

Shared acceptance fixture: 15 completed ROs, distinct source IDs; 6 unique VIN
matches to unit 603 and 9 to unit 609. Include seven current invoice-backed ROs
and eight with missing bill-to snapshots; all 15 operational rows are returned,
while the eight invoice/PDF reads remain excluded. Six current invoices are
replacements, one is an original; cancelled invoice versions never add extra
RO-history records. Include RO 000055/000054 with service date 2026-10-08 and
regenerated invoice date 2026-10-19, and RO 000053/000050 with service date
2026-10-01 versus invoice date 2026-10-19.

Negative cases: another tenant/customer on the same VIN; inactive/revoked key;
deleted/incomplete/internal/cancelled RO; vehicle tenant mismatch; missing or
duplicate VIN; wrong vehicle type; malformed/incomplete/oversize snapshot;
duplicate source RO ID; repeat import; changed revision; changed assignment;
complete-snapshot removal; failed fetch/apply rollback; replay with legacy
candidates; no accounting or invoice authorization changes. Source implementation
must follow RED-GREEN-REFACTOR per repository rules.

## Release and runtime acceptance

Backend & Integrations owns implementation and board evidence. Architecture
approves this metadata-only contract before parallel consumer work. Fresh
independent Security and QA reviewers must inspect final source/consumer code,
negative tests and production receipts. Use focused PRs and protected CI; no
direct main push. Release source API before consumer activation/import. No new
secret or persistent grant is part of this contract. Any such need is a blocker
requiring an exact action/scope proposal before mutation.

Runtime acceptance is a validated 15-row dry-run manifest, unique six/nine truck
counts, correct service dates, explicit existing-record candidates, followed by
the already-authorized 15-row history import. Repeating it must leave exactly
15 source RO rows. Confirm unchanged legacy repair, payment, reserve, finance
and journal counts and unchanged historical invoice/PDF authorization. Record
merge/deploy IDs, source/consumer health, UI evidence and any review-only rows.
Rollback disables the history surface/sync without dropping the new history
rows or altering existing invoices, costs, credentials, or accounting.
