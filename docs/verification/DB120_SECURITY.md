# DB120 independent security and privacy gate

Reviewer: Security & Identity, independent of DB120 implementation and contract
design. Date: 2026-10-14. Branch: `codex/vehicle-history-export`.

## Decision

**GO for the reviewed DB120 security and privacy scope.** Both boundedness
findings are corrected and independently verified. The stable working tree has
no unresolved security blocker. This document does not approve workflow QA,
merge, deployment or production behavior.

## Findings and remediation

`export_csv` initially fetched full `RepairOrder.description` and
`Labor.description` Text fields, accumulated them, and joined operation bodies
before checking the 2 MiB output cap. Those existing fields have no schema length
limit. A small number of oversized stored/imported descriptions, or many large
operations within the count cap, could consume far more memory than the final
CSV limit before returning 413. Row count limits alone do not satisfy the
contract's boundedness requirement. Reported to Backend & Integrations and
Product. The owner added metadata-only candidate lookup, raw-size SQL preflight,
bounded SQL text projections and one-row streaming with a cumulative guard.
Oversized order, labor and outside text now rejects before body fetch; growth
after preflight also rejects. These cases passed independently.

The related operation preflight initially used an unbounded COUNT/SUM(length)
before rejecting too many operations. The owner now fetches only operation IDs
with MAX_OPERATIONS+1, rejects overflow before any text-length inspection, and
limits later aggregates and body fetches to those candidate IDs. The dedicated
regression proves over-cap IDs fail without calling text-length inspection.
No successful export silently truncates a source field or returns a partial
file. The reviewer did not modify application or test code.

## Reviewed boundaries

- The service positively allows owner/admin/receptionist before data queries;
  other roles are denied. Allowed actors need a tenant. The vehicle query
  requires exact ID, actor tenant and active status with one generic 404.
- Eligible repair orders independently require tenant, vehicle, nondeleted
  status and completed/invoiced/paid state. Outside records require tenant,
  vehicle and nondeleted/nonvoided status. Operations require the same tenant,
  one of the eligible order IDs and nondeleted state. Customer/bill-to identity
  is not used to alter physical truck history.
- Only explicit export fields are selected. Customer/contact data, internal
  notes, operation-note envelopes, audit payloads, actors, amounts and payment
  data are absent from projections and columns. No mutation or external event
  path is present. Native merge provenance is not invented; outside original
  vehicle identity remains explicit.
- CSV uses the standard writer, BOM and CRLF. All emitted text passes control
  cleanup and apostrophe neutralization when its first nonwhitespace character
  is `=`, `+`, `-` or `@`; CSV quoting alone is not relied upon. Filenames use
  the parsed UUID, never user-provided display text.
- Native completion dates use the shop timezone; imported completion dates keep
  their UTC calendar date. Unknown completion uses separately labeled record
  creation. Outside service dates are reported dates. Historical odometer fields
  preserve known zero and explicit basis; current mileage is not queried.
- The route rejects unsupported/repeated query parameters. Failure responses
  are JSON without attachment headers. A dedicated route wrapper supplies
  no-store/nosniff for domain, validation and unexpected errors; authenticated
  success adds exact vehicle/count headers. Exposing the download metadata
  headers does not change CORS origins, credentials or authorization.
- Record and operation candidate lists use cap+1 checks. Raw text length is
  checked before fetching bodies; selected unbounded Text fields use a SQL
  cap+1 sentinel, streamed one row at a time and counted cumulatively, covering
  edits after preflight. Exact encoded CSV bytes are checked before success is
  returned. A final active-tenant-vehicle read rejects a committed archive or
  merge of the target; no locks, mutation or snapshot guarantee are added.
- Frontend download controls require an allowed authenticated actor and stop
  during logout. Scope includes tenant, actor, role and session epoch; vehicle
  changes remount and abort. Each completion checks live auth identity, request
  identity and abort state. Failed/malformed blobs do not produce object URLs.
  Downloads use a local authenticated blob, a fixed UUID filename and revoke
  the object URL. Cancel/Escape abort pending work. No query/blob cache is added.

## Evidence

- Independently ran `VehicleHistoryExport.test.tsx`: **28 passed in 1.98 seconds**.
  This includes denied roles, retry/date retention, JSON error blobs, malformed
  vehicle/type/count/size responses, pending Escape cancellation, late vehicle/
  tenant/actor/role/epoch/logout responses and navigation unmount.
- Independently ran the focused role/tenant/oversized-source/concurrent-growth
  backend cases: **13 passed in 5.73 seconds**.
- After the final operation candidate correction, independently ran the complete
  `test_vehicle_history_export.py`: **31 passed in 11.45 seconds**. This covers
  every role, wrong/archived/foreign target, inconsistent foreign order/labor/
  outside links, physical history after customer transfer/deletion and vehicle
  merge, eligibility/void/deletion filters, all-page output, source/date/mileage
  truthfulness, formula/control cleanup, round-trip quoting, no writes, count/
  byte/source-memory caps, and actual HTTP failure privacy.
- Reviewed the three PostgreSQL tests and final
  `/tmp/db120-postgres-tests.log`: **3 passed in 2.90 seconds**. They use the
  existing opt-in isolated localhost test fixture and prove actual-dialect DST/
  imported-calendar filtering, a committed text enlargement from a separate
  transaction after preflight returning 413, and a committed vehicle archive
  before the final read returning 404. This reviewer did not run or alter that
  database. The implementation owner reports no product edits after these runs.
- `git diff --check` passed. Existing SQLAlchemy/Pydantic and Browserslist-data
  warnings are not failed assertions.
- This is a read-only review/document task. No server restart, runtime config,
  migration, browser operation, production data or application/test edit was
  performed by this reviewer.

## Remaining gates

No security follow-up remains for this reviewed scope. Independent runtime QA
and protected CI/release/production download evidence remain parent-owned,
separate gates. Rollback removes the additive API/UI; there is no migration,
stored export or business-data repair required by this implementation.
