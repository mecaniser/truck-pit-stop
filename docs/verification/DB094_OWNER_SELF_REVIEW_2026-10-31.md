# DB-094 owner self-review — development verification

Accountable: Backend & Integrations. Branch `codex/historical-owner-self-review`,
base `16f72a35`. User explicitly authorized owner self-review and a tested draft PR.
No merge, deployment, production settings, real evidence/grants or financial writes.

## Behavior

Existing verify requests retain independent review. An explicit
`owner_self_review: true` permits only the current active, undeleted same-shop
GARAGE_OWNER who uploaded that evidence to inspect and verify it. Current owner
identity is reloaded under a shared row lock. Admin self-review, default uploader
review, nonowner roles, another tenant and labeling another person's upload as
self-review remain denied. The authenticated owner is the actual verifier.

Server-derived `verification_mode` is frozen on evidence and copied as
`evidence_verification_mode` into decision audit and idempotent responses.
Verification alone grants nothing; the owner must still send a separate existing
approval request with legal-continuity attestation, source/target and version.
Missing/inconsistent actor/mode audits fail closed; valid legacy null-mode reviews
remain accepted. Revocation remains possible after reviewer/source drift.

All source bytes/hash, legal-name, recipient uniqueness, invoice/tenant/RO and
native replacement UUID/alias checks remain. Identity proof service and EDGv2
are unchanged. No frontend or new credentials are required for this API workflow.
[Contract](../contracts/db094-owner-self-review.md).

## Verification

- Seven focused/adjacent suites: **94PASS**, including18 owner/audit cases,
  historical proof/review, export holds/readiness and fleet/financial export
  regressions. `/tmp/db094-owner-final-tests.log`.
- Authenticated ASGI owner flow: original upload fixture→opt-in verify→separate
  approve, same-actor immutable audit snapshot and idempotent replay. Standard
  and imported-order native replacement cases covered; verification creates no
  mapping/decision, and revocation after reviewer demotion preserves mode.
- Negative tests: default denial, admin/mechanic/customer/super-admin, missing
  authentication/inactive identity, client audit/actor injection, another uploader,
  tenant/hash/invoice/alias/UUID/recipient/proof errors, source drift, malformed
  missing-actor audit and legacy independent compatibility.
- Independent Security/QA:47 focused tests and8 additional adversarial probes
  passed (stale role/tenant/deletion/deactivation snapshots, API-key-only attempt,
  proofless unique-name owner path, legacy compatibility and missing-verifier denial). Source-only findings
  resolved; missing-actor guard regression added. Architecture GO with16 owner
  cases and2 final legacy cases independently passed.
- Actual local asyncpg/PostgreSQL private schema: populated195→196→195→196,
  legacy source preservation, owner/admin/tenant/inactive/preverified-insert
  rejection, immutable evidence/decision mode, both concurrent role-edit/review
  orders and audit-erasing downgrade fencePASS. Assertions require trigger
  SQLSTATE P0001; timeouts/invalid SQL cannot count as denials. Log:
  `/tmp/db094-owner-postgres.log`. Own schema removed in finally. Rehearsal:
  `backend/scripts/rehearse_historical_owner_self_review.py`.
- Single Alembic196 head, changed Python compilation and diff integrityPASS.

## Risks and remaining gates

Owner self-review deliberately removes independent human corroboration for that
explicit owner path; it never represents it as independent review. Owners keep
responsibility for reviewing original source and attestations. New audit fields
are nullable with no backfill or seeded evidence. Downgrade refuses to erase any
recorded review-mode audit; revocation does not erase history and does not make
such a downgrade safe. Review the normal rollout/rollback plan before release.

Draft PR and protected CI are integration/review evidence, not release approval.
Actual invoice evidence review/access and production financial entries remain
outside this development task. Browser acceptance does not apply: no UI changed;
real authenticated ASGI and PostgreSQL journeys cover the changed API boundary.
