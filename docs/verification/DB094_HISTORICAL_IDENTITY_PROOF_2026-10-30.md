# DB-094 historical identity proof — local verification

Accountable owner: Backend & Integrations. Branch:
`codex/historical-billing-identity-proof`, base `17608d10`.
Status: LOCAL VERIFIED; publication/release and actual per-invoice review pending.

## Existing behavior and change

The legacy verifier required a unique legal name, blocking otherwise separately
reviewable namesakes. All invoices on an imported RO were rejected, including
native replacements. The candidate adds an optional exact preserved original
sent-correspondence proof while retaining the proofless unique-name path.
Original recipient must identify exactly one active same-tenant target, with
mandatory bill-to name matching. Source bytes, timestamps, template, invoice
number and UUID lineage are checked, not inferred from current RO ownership.

The imported-RO exception requires a native invoice directly replacing a voided,
cancelled imported predecessor on the exact same RO/tenant. A historical alias
requires the native original number in subject and body and an actual trusted
portal anchor containing the exact native invoice UUID. Imported invoices,
unsupported lineage, opaque expired links, ambiguous recipients and drift reject.

Verification freezes source/proof/context hashes and reviewer; it creates no
mapping. Approval independently revalidates. Uploader cannot verify. Nullable
migration195 introduces no evidence/mapping data and makes evidence and decisions
immutable in PostgreSQL. Proof-bearing target identity edits require revocation;
revocation remains possible after invoice/source drift. Auth customer-email
assignment paths now use the same clear409 guard before writing.

EDG financial v2 shape, revision/hash vocabulary, invoice/RO IDs, sources, numbers,
amounts, payments and dates are unchanged. There is no historical reassignment,
source upload, approval or access-key creation against actual records.

## Verification

- Final six-file adjacent regression: **79 passed**, including25 new proof cases
  and committed ASGI authentication/role/strict-schema checks. Log:
  `/tmp/db094-attribution-final.log`.
- Independent Security/QA:30 focused tests,4 extra adversarial probes and HTTP
  authorization/schema probe passed. Local-candidate GO with no access-bypass
  finding. Logs `/tmp/db094-security-extra-probe.log` and
  `/tmp/db094-security-http-probe.log`.
- Actual PostgreSQL/asyncpg rehearsal runs migration195 upgrade/downgrade/upgrade
  on legacy synthetic rows in a uniquely named private schema; verifies immutable
  source/verified evidence, separate verifier, append-only decisions and downgrade
  audit fence. Two concurrent sessions prove customer edit first causes a fresh
  ambiguity denial, and approval first pins the target UUID while later contact
  sharing cannot transfer the grant. Own target email/archive/move/delete reject.
  Script: `backend/scripts/rehearse_historical_identity_proof.py`; log:
  `/tmp/db094-proof-postgres.log`. Both initial and final schemas were removed.
- The first rehearsal caught customer guard executing before the advisory lock.
  Trigger ordering was fixed and the complete rehearsal passed. Old/new tenant
  moves acquire locks in stable order. Point-in-time uniqueness introduces no
  permanent global shared-email restriction or payment enrichment changes.
- Synthetic removal/edit test explicitly acquires the advisory lock; it verifies
  trigger ordering, not concurrent HTTP revoke acceptance. Actual edit may reject
  while a mapping is visible and succeed on retry after committed revocation.
- `git diff --check`, Python compilation and linear migration graph pass.

## Workflow and remaining holds

The exact capture/verify/owner-decision workflow is in
[the contract](../contracts/db094-reviewed-identity-proof.md). Original canonical
sent captures and independent staff review are required per invoice. The eight
actual invoices have not been proved eligible by synthetic tests. In particular,
ETSINV-0718 needs its original UUID-linked native invoice-created correspondence.
Source template/timing and target uniqueness cannot be assumed from discussion.

Owner attestation says the eight repairs were billed to Elis Logistics LLC and
DBN/ETS profiles represent the same company for those invoices. This remains
pending independent verification. The requested July19 DBN date for000006, with
ETS date retained in notes, is recorded as separate provenance preference; no
dates or notes are mutated here and this identity patch does not choose dates.

No operational blocker remains for the local candidate. Separate authorization
and normal release review are needed before publication, production migration,
real evidence upload, independent verification, owner decisions or access grants.
No push, PR, merge, deployment or production mutation was performed.
