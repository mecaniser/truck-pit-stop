# DB-094 explicit owner self-review

Owner: Backend & Integrations. User expressly authorized this owner-only exception
to the separate-uploader/reviewer rule in the historical identity-proof contract.
Draft publication only; merge, deployment, production settings, actual evidence
review/grants and financial entries are not authorized by this implementation.

## Existing verification endpoint

Add optional `owner_self_review: false` to VerifyRequest. Existing callers retain
independent verification. An uploader still receives403 unless they explicitly
set true and are the authenticated, active, undeleted same-tenant GARAGE_OWNER.
An admin, mechanic, customer or platform super-admin cannot self-review. Owner
opt-in for someone else's upload returns422. The server refreshes/locks the
current owner identity; an earlier role/tenant/active snapshot is insufficient.

All original source bytes, SHA256, note, legal-name, invoice/tenant/RO, target,
recipient-uniqueness and original correspondence/replacement UUID-link checks
remain required. No new alias or imported-invoice exception exists. VerifyRequest
rejects unknown fields; clients cannot submit reviewer identity or audit mode.
The authenticated actor is always the recorded verifier, without impersonation.

The server stores verification_mode as owner_self_review or independent on the
evidence. The response includes that mode. Verification alone creates no mapping,
key, decision, cost or payment. Existing owner-only approve/revoke/reject and
attestation/version/idempotency rules remain. Approval revalidates identity/proof
and rejects missing/inconsistent reviewer/mode audits. Null-mode legacy reviews
are valid only with a recorded verifier distinct from uploader.

Every decision carrying evidence copies evidence_verification_mode; first and
idempotent replay responses expose the same snapshot. Revocation remains possible
after reviewer role or source drift and retains the frozen mode, without a new
review check that could block access removal. EDG financial v2 is unchanged.

## Migration196 and immutable audit

Two nullable String32 fields preserve existing rows without backfill. New evidence
is inserted unreviewed. PostgreSQL permits one review transition, validating mode
and reviewer identity/active/tenant/role under SELECT FOR SHARE. Independent mode
requires distinct current owner/admin; self mode requires same uploader and owner.
Role/tenant/deactivation edits serialize with verification. An already completed
owner review remains a historical fact after a later role change.

Original source columns, verified metadata including mode, and decision snapshots
remain immutable. Downgrade is fenced once either new audit field is populated;
without new audit, downgrade restores revision195's exact trigger and schema.
The existing source proof/hash and target identity safeguards are unchanged.

## Acceptance and operational sequence

Synthetic HTTP acceptance covers owner upload→explicit verify→separate approve
request, same-actor audit, no grant on verification, idempotent decision/revoke,
admin/default/unauthenticated/inactive/cross-tenant/client-audit denial, source
hash/UUID/alias/recipient drift and legacy compatibility. PostgreSQL rehearsal
uses only a disposable localhost schema, checks real trigger denials and both
role-edit/verification orders, and drops its schema in finally.

After a separately authorized release, a shop owner may inspect their preserved
original evidence and submit the existing verify request with owner_self_review
true and a substantive note. They may then issue a separate owner approval with
the existing evidence/target/legal-continuity attestation. Neither step is run
against actual invoices by this development task.
