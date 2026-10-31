# DB-094 historical correspondence identity proof (local candidate)

Owner: Backend & Integrations. Architecture conditional GO for this narrow
sent-notification design; independent Security/QA gate remains required.

This extends historical evidence verification only. It never uploads evidence,
creates mappings, grants keys, changes invoices, rewrites source identities,
posts costs/payments or changes financial v2 keys/revisions/hash vocabulary.
Production use, evidence uploads, owner approvals, publication and deployment
are outside this local task's authorization.

## Additive verification request

The existing verify request may include strict `identity_proof`:

```json
{
  "kind": "sent_notification",
  "notification_id": "uuid",
  "observed_invoice_id": "uuid",
  "observed_repair_order_id": "uuid",
  "observed_recipient_email": "account@example.com",
  "original_correspondence_attested": true
}
```

Existing source hash, observed bill-to name, invoice number, exact target and
verification note remain required. A different same-tenant owner/admin must
verify; the uploader cannot. A typed email or UUID alone proves nothing.
`original_customer_id`, if present, must equal this exact target; other/deleted
identities need a separate lineage review and are not handled here.

The evidence must be billing correspondence or a preserved source record with
application/json content. Its bytes must equal the canonical JSON capture from
`historical_invoice_proof.snapshot` and `canonical` of an existing same-tenant,
undeleted EMAIL Notification. Capture includes id/tenant/type/status/recipient,
subject/body/template/created_at/sent_at/external_id. Original sent status must
be SENT or DELIVERED, template invoice_created, and
invoice.created_at <= notification.created_at <= notification.sent_at <=
invoice.created_at+24h; sent_at must also precede evidence capture. No resend,
current-RO/customer association, current PDF or subject-only inference qualifies.
All captures and tests are per invoice; nothing bulk-authorizes eight cases.

Recipient uniqueness is a point-in-time verification/approval property. PostgreSQL
uses a shared tenant transaction advisory lock for the proof check and customer
INSERT/email/archive/tenant/deletion writes, followed by a fresh scoped read.
A later new namesake/shared contact never inherits or transfers the frozen target
UUID grant; a fresh verification/approval will reject that ambiguity. No permanent
cross-account email restriction is introduced. Multirow contention may abort a
transaction for retry; it must fail closed, never bypass identity review.

The reviewer-observed recipient must exactly match normalized source recipient
and the target primary email. Normalization is trim+casefold only; no Gmail dot,
plus, display-name, phone or alias rewriting. It must identify exactly one active
same-tenant customer. Legal name matching remains mandatory even with proof.

Ordinary invoices require the exact current invoice number bounded in BOTH
original subject and body, unique across all same-tenant historical invoices.
Those without structured proof retain the previous unique-name-only rules.

## Native replacement on imported RO

Invoice.source must be NULL (native) with a direct nonself supersedes_invoice_id
pointing to an undeleted imported predecessor in the same tenant and same RO.
The predecessor must be cancelled, explicitly voided, noninternal, without a
native bill-to snapshot and not created after the replacement. No multi-hop,
missing, cross-tenant, other-RO or nonvoided predecessor is inferred. Imported
invoices themselves remain read-only. Sources and numbers are never changed.
This exception ALWAYS requires the structured proof, even when names/current
invoice numbers appear to match.

If the original observed native number differs from the current historic alias,
it must have the native INV-<tenant prefix>-<six digits> shape and occur in both
original subject/body. The original body's actual anchor must contain the exact
replacement UUID in `/portal/invoices/{uuid}` under the configured app origin or
canonical DieselBridge HTTPS origins. Imported predecessor number alone, a UUID
written into a request or an unrelated/opaque expired token URL is insufficient.
The same UUID link is required for any imported-RO replacement proof.

## Approval, audit and removal

Verification freezes canonical proof JSON/hash, original source bytes/hash,
recipient identity, target UUID, observed invoice/RO UUIDs and native alias,
reviewer and replacement-context digest. Approval reconstructs/rechecks the
proof against source, current target name/email uniqueness and exact invoice
context. Name/email/context/source drift requires fresh evidence and independent
review; old verification is never edited. The decision copies the proof hash.
Changes of the mapped target's proof-bearing email require revocation first.

Migration195 adds nullable proof fields without seeding evidence or mappings.
PostgreSQL guards freeze original evidence, verified metadata and decision
updates/deletes. Downgrade is fenced once proof/audit data exists; silently
removing proof fields would destroy the grant's basis. Legacy proofless rows
remain unchanged. Schema rehearsal uses an isolated synthetic schema which is dropped in finally;
public/application tables are never touched.

Revocation checks only scoped invoice identity and existing mapping; new grant
proof checks must not prevent removing access after source/identity drift or
cancellation. Existing version/idempotency rules and access_removed events are
retained. Financial v2 exports expose no proof document or contact fields.

## Current operational holds

No original evidence has been uploaded and no invoice has been verified or
approved by this implementation task. The eight records still need exact source
captures, evidence review by distinct staff, owner decisions and release approval.
The ETSINV-0718 replacement requires original UUID-linked invoice-created mail;
a former/current number match without that original source does not suffice.
Notification template/timing/uniqueness are deliberately not assumed from a
conversation summary. Actual eligibility remains unproven until safely reviewed.

Sent-to-delivered status or other durable Notification snapshot drift also requires
fresh evidence review; the original frozen verification is never rewritten.


## Owner attestation pending independent review

The owner confirmed the eight repairs were originally billed for Elis Logistics
LLC and that the DBN and ETS profiles represent the same company for those
invoices. This is owner-provided attestation, pending independent verification;
it is not a source correspondence substitute or permission to approve/grant.
For invoice 000006 the owner requests the DBN date July 19, retaining the ETS
date in notes. No invoice date, export date or production notes are changed here.
A future separately reviewed date/provenance decision must preserve both source
facts. This identity-only change does not select financial dates.

## Operator sequence after separate release authorization

1. Capture each original durable sent Notification using the exact canonical
   snapshot contract; preserve source bytes and SHA256, original invoice/RO UUIDs
   and owner attestation as distinct evidence. Do not regenerate a current PDF.
2. An authorized staff uploader records that per-invoice evidence through the
   existing evidence endpoint. No uploader may verify their own capture.
3. A different same-tenant owner/admin examines the original source, exact
   invoice/RO UUIDs, original recipient and bill-to name, alias/lineage when
   applicable, then submits the structured proof to the existing verify endpoint.
   Failure remains a review hold; do not edit the frozen capture to pass.
4. Verification alone creates no mapping. A separately authorized owner decision
   revalidates source and unique recipient identity before a mapping can exist.
   Existing version/idempotency rules and audit events still apply.
5. Any identity/source drift requires new evidence and review. Remove an existing
   grant before changing its proof-bearing target identity. A concurrent edit can
   reject while a mapping remains visible; retry after committed revocation.
