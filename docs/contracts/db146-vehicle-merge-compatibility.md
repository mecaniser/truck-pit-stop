# DB-146 — Vehicle merge compatibility amendment

Architecture verdict: **GO for the minimal reject-on-history contract below**, not implementation or release GO. Source inspected read-only. No application changes or database actions performed. Product & Delivery Lead adopted this amendment after DB145 controls production acceptance on2026-10-30.

## Current source evidence

- `backend/app/services/vehicle_merge.py:167` — `load_merge_pair(..., lock=True)` selects both active same-tenant vehicles, orders UUIDs and acquires `FOR UPDATE` locks. `merge_vehicles` calls it at329.
- `backend/app/services/vehicle_merge.py:341` — existing maintenance guard runs after identity confirmation and before source aliases, history moves, read-model updates and duplicate archival. This is the correct additional C3 guard seam.
- `backend/app/services/maintenance.py:744` — precedent explicitly says existing sorted vehicle locks are held and not to acquire a tenant lock inside the guard. Maintenance retains identity/history by rejecting unsafe merges.
- `backend/app/services/vehicle_merge.py:359–398` — existing merge moves multiple records and archives the duplicate. It knows nothing about standalone issues; silently leaving them behind is not safe.
- `backend/app/api/v1/endpoints/vehicles.py:85` preview presently checks identity but not maintenance history; `:121` POST calls merge service and rolls back VehicleMergeError as409 with a plain-text `detail`.
- `backend/tests/test_vehicle_merge.py` covers history preservation, VIN conflict, and guarded unit-number matches. Its existing successful cases must remain unchanged when no C3 history exists.

## Exact contract replacement for the outstanding merge paragraph

C3 does not rehome, copy, deduplicate or retire issue identity during vehicle merge. While either the kept or archived vehicle has any standalone issue record, merging that pair is unavailable. This applies to open, resolved and dismissed issues, including retained soft-deleted/history rows if any are introduced. Closing an issue is not an escape hatch for merging. No override flag is accepted. A future reviewed issue-migration contract may remove the restriction; C3 does not include that work.

Issue existence is checked for **both** vehicle UUIDs under their current tenant after ordinary role, vehicle and identity validation. Issue descriptions, counts, owners, follow-up dates and linked-order identities are not returned in the merge failure. The response is409 with existing merge-compatible plain-text detail:

`Truck issue history is attached to one of these records. Merge is unavailable until issue-history migration is supported. Keep both records for now.`

Do not suggest resolving/dismissing issues to bypass the guard. No extra issue information is added to duplicate candidates or merge summaries. For pairs without C3 history, existing preview/result schemas and merge behavior remain unchanged. Financial/source migrations are not performed by this guard.

## Implementation seams and lock order

1. Proposed new C3 service `backend/app/services/vehicle_issues.py` owns `guard_vehicle_merge(db, canonical, duplicate)`. Its only operation is an existence query on issue tenant/vehicle identities. No status/resolution/deleted filter, no writes, no tenant financial lock, no callbacks or nested commit. Raise existing `VehicleMergeError` on a match; use a lazy import to avoid module cycles. All link/audit/request records remain attached to a retained issue with noncascading FKs; none can outlive a deleted issue row. C3 has no hard deletion endpoint.
2. In `backend/app/services/vehicle_merge.py::merge_vehicles`, call the new guard adjacent to the existing maintenance guard, before `now`, before snapshots/aliases and before any update/insert/delete. Existing sorted vehicle locks cover the guard and remain held until caller commit/rollback. Do not move the existing maintenance guard or relax its failure behavior.
3. In `backend/app/api/v1/endpoints/vehicles.py::preview_vehicle_merge`, run the same issue guard after `validate_merge_pair` within the existing VehicleMergeError handling. Preview uses ordinary reads, no locks/writes; it is advisory. POST must always recheck under locks even after a clean preview. This addition avoids presenting an actionable merge confirmation that C3 already knows it must reject. Existing UI already renders merge409 text; verify both customer/fleet merge surfaces retain that behavior.
4. **Required amendment to C3 mutation locking:** every new issue create/edit/state/link/end operation first loads its same-tenant, undeleted Vehicle with `FOR UPDATE OF vehicles` and `populate_existing=True`. Recheck availability after obtaining the lock. Then acquire issue row lock (when one exists), followed by link/request-specific locks. Single-vehicle C3 operations never acquire another vehicle. This common vehicle-first order serializes issue creation with both sides of vehicle merge; issue-only locking from the earlier draft is insufficient for first-create races.
5. Do not add tenant financial locks to C3 or to the merge guard. Idempotency/request rows that require locking are acquired after the vehicle lock, not before it. A prior nonlocking receipt lookup is permitted, but recheck it under the vehicle boundary before a new mutation. Existing exact-replay no-write semantics remain unchanged; a deleted vehicle path must not be silently redirected to a canonical identity.
6. Validate all issue/link identities against the locked vehicle's tenant and UUID. Include tenant-consistent foreign-key integrity in the C3 migration where supported; a request cannot create a foreign-tenant issue pointing to this vehicle. Existing stored corruption must never cause data exposure or automatic repair. Metadata target RO reads remain scoped; linking is a reference, not an authorization to alter the target. No financial/source lock expansion is needed for this amendment.

## Race outcomes (PostgreSQL acceptance, not SQLite-only assertions)

- Create wins vehicle lock: commits issue; merge waits, then sees it and returns409; no merge/source changes.
- Merge wins with no issues and issue creation targets losing vehicle: merge completes; waiting create reloads and sees archived vehicle, returns ordinary404 context unavailable; creates no issue, receipt or event.
- Merge wins and creation targets kept vehicle: waiting create may succeed against that same surviving UUID after validation. This is safe; no issue existed during merge and no existing issue identity was moved.
- Two merges on overlapping vehicles retain UUID-ordered lock acquisition. C3 single-vehicle mutation never holds an issue/request lock and then waits for the vehicle, preventing an introduced reverse-order cycle.
- Clean preview followed by new issue creation: POST rejects409. Preview is not a reservation or permission to skip the guard.

## Focused tests and exact proposed paths

- Extend `backend/tests/test_vehicle_merge.py`: issue on canonical only, duplicate only and both; every issue state; history/link retained; both VIN and unit match paths. Assert409 before any aliases/merge record/archive/moved source rows, with all existing row hashes unchanged. Existing no-issue merge tests pass unchanged.
- New focused `backend/tests/test_vehicle_issue_merge_compatibility.py`: actual PostgreSQL independent-session races above, deterministic barriers, bounded waits, no sleep-based winner assumptions; rollback releases locks; idempotent create remains one issue/event when raced with blocked merge.
- Add C3 endpoint auth tests (new issue test module): foreign tenant vehicle/issue/assignee/link IDs; absent tenant; forbidden role; malformed context never exposes issue content. Foreign-tenant pair cannot be probed via preview/POST and no C3 history information leaks. New schema rejects inconsistent tenant/vehicle references.
- Endpoint preview/POST tests: identical blocking message, no issue detail/count; POST independently rechecks after clean preview; receptionist cannot inherit owner/admin vehicle-merge permission from C3 staff access.
- Existing customer/fleet merge component tests: blocked preview or submit shows server explanation, preserves dialog/selection, no success message or automatic retry, no suggestion to dismiss/resolve issues. No new merge UI controls.
- Migration rehearsal and immutable financial/source cohort retention remain required by C3; no production merge or real issue creation for QA.

## Remaining boundary

This closes the design gap with a deliberately narrow guard. Implementation must still prove real PostgreSQL first-create/merge serialization and tenant-consistent FKs. If those tests cannot be provided, C3 is NO-GO for release. Rehoming issues across vehicle identities remains explicitly out of scope; no new product decision is required for this guard.
