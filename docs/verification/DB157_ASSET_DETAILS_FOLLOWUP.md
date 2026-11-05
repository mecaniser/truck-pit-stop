# DB-157: asset details and required tractor assignments

Backend & Integrations owns this high risk follow-up contract and service
implementation. Root owns frontend presentation and the separately authorized
reviewed classification operation. Existing Vehicle identities, repairs,
maintenance and telemetry stay independent; no production write is performed
by backend implementation.

## Approved acceptance

- Type and attachment settings belong inside the existing Truck details modal.
- Customer-account equipment can exist off fleet, retaining its own service
  history. A current fleet trailer must have a classified, current fleet tractor.
- No standalone detach may strand a trailer on the fleet. Reassigning a trailer
  to a free tractor is atomic and preserves the prior dated pairing row.
- Removing a trailer from fleet closes its pair and last membership together.
  Removing its tractor is blocked until the trailer is reassigned or removed.
- No implicit two-pair swap or occupied-tractor displacement occurs. Both
  existing reviewed Elis pairings are preserved unless explicitly changed.
- A trailer classification cannot be committed onto an unpaired active fleet
  asset through an older editor. Atomic type-plus-tractor selection is required.
- Unknown equipment is not guessed from a unit number. The user's fleet-wide
  tractor classification authorization is a separate frozen-allowlist operation.
- Preserve tenant isolation, stale-state rejection, actor/timeline evidence,
  distinct repair/PM/reading ownership and all existing financial records.

## UI/API contract

`PUT /fleet/trucks/{id}/asset-settings` accepts exactly four required fields:

```json
{
  "equipment_type": "trailer",
  "attached_vehicle_id": "00000000-0000-4000-8000-000000000001",
  "expected_equipment_type": "unknown",
  "expected_attached_vehicle_id": null
}
```

Equipment kinds are the existing `unknown`, `tractor`, `trailer`, `other` enum.
The desired attachment is the counterpart Vehicle UUID, usable from either
perspective. The response is the updated existing `BoardTruck`, including its
fresh `equipment_type` and `attached_asset`; clients refresh board and both
details. A repeated achieved state is idempotent. A different request against
stale expected type or counterpart returns 409 without changing either field.

An active trailer requires a non-null free current tractor in the same save.
A tractor with a current trailer cannot become another type, detach, or replace
that trailer in a way that would strand it. Reassign the trailer to a free
tractor, or remove the trailer from fleet first. A selected occupied target
returns 409; no second partner is silently moved. Other/unknown equipment cannot
be attached. Existing `PUT .../attachment` is retained with the same invariant;
existing PATCH/company/Vehicle type editors reject unpaired fleet-trailer
classification and direct users to the atomic settings operation.

`POST /fleet/trucks` adds `equipment_type` (default `tractor`) and optional
`tractor_id`. Creating a fleet trailer requires `equipment_type: trailer` and
a free current `tractor_id`; missing/incompatible/occupied choices fail and the
entire request rolls back. Non-trailer equipment cannot provide `tractor_id`.
The response remains `VehicleResponse`.

`POST /fleet/memberships` adds optional `tractor_id` to its existing vehicle and
fleet-customer fields. Off-fleet trailers require a tractor selection and are
paired and enrolled atomically. Already valid paired trailers can be re-enrolled
without inventing or moving their pairing. The response remains the existing
membership/vehicle/company identifier object. Fleet vehicle candidates now
project actual `equipment_type` so the picker can require tractor selection.

Generic customer-account and Vehicle creation keeps newly registered trailers
off fleet even when the customer participates in fleet operations. Bulk enabling
a company enrolls other eligible equipment but skips unpaired trailers. Those
trailers remain available in company equipment and the explicit fleet picker.

The existing DELETE membership route still requires its removal reason. The
last trailer membership closes its current pairing in the same transaction;
history and registration remain. A current paired tractor returns 409. Bulk
company removal processes trailers before tractors and rolls back entirely if
it would strand a trailer belonging to another remaining fleet membership.
Scheduled future memberships are not treated as current attachment authority;
an attached trailer's future assignments must be resolved before its last
current membership can be removed.

Existing staff fleet authorization applies: owner, admin or fleet manager with
an authenticated tenant. Foreign/deleted/off-board/future-only counterparts
return 404; invalid roles, stale expectations, occupied targets or invariant
violations return 409; malformed/missing fields return 422. Owner/operator
company equality is not required within authorized tenant fleet scope.

## Writers, locking and compatibility

No new migration is needed. The released attachment table's tenant-composite
foreign keys and active unique indexes remain. A tenant lock serializes all
canonical attachment, type, admission and removal writers. Searches confirm
`vehicle_identity.ensure_fleet_membership` is the sole application membership
constructor; admission validation is now centralized there. Existing driver
custody and provider observation services do not create these memberships.
Historical migration backfills are not runtime fleet-entry APIs.

Covered entry points: explicit fleet create/link, generic customer/Vehicle
create, operator-relationship linking and company fleet-enable synchronization.
Covered exits: membership deletion, company fleet disabling, existing guarded
relationship synchronization, archival and merge. Attached archive/merge remains
blocked until fleet removal; no audit or service history is reassigned.

Generic create and relationship entry points acquire the tenant lock before
their first Vehicle/relationship flush. This avoids PostgreSQL FK KEY SHARE
locks being upgraded to Tenant FOR UPDATE by concurrent same-tenant creations.
Customer fleet toggles retain tenant-before-customer row-lock ordering.

The rule is an application transaction invariant across these canonical writers,
not a new database constraint on arbitrary administrative SQL. No raw database
writer or scheduled membership-admission path was found. A database deferred
constraint would require a migration, commit-time cross-table trigger/locking
semantics and restore/backfill handling; those are unnecessary for the covered
application writers. Direct operational writes must retain their separately
reviewed scope/invariant checks; they must not bypass assignment validation.

## Runtime receipt and verification

Intended checkout `truck-fleet-assets`, branch `codex/fleet-asset-details`, base
`9ad6809e`. Mandatory runtime status/dry-run repeated after the branch switch.
5173 has no product listener; 8000 remains owned by the preserved privacy-safety
Docker checkout. Controller refuses the dirty target, and no approved local
environment was copied or invented. Product runtime remains blocked/mismatched;
isolated synthetic tests are not a claim of local signed-in product serving.

Source acceptance, independent gates and the separately reviewed classification
are recorded below. Merge, deployment and exact-source runtime acceptance are
still pending.

Backend owner candidate: **70/70 passed in 57.45 seconds**, including ten real
PostgreSQL cases in fresh disposable schemas. These verify the released
attachment migration and tenant foreign key, competing admissions for either
role, serialization against tractor removal/merge/classification, plus four
parallel actual create/link endpoint paths. The latter also assert actual
tenant lock acquisition before FK-bearing Vehicle/relationship/membership
flushes, preventing the reviewed KEY SHARE lock-upgrade deadlock.

An additional **89/89 Fleet Workflows and Workspace Typeaheads cases passed in
15.17 seconds**. Focused negative cases cover future memberships for both roles,
foreign/occupied targets, every legacy classification editor, no orphaning
detach, atomic type-plus-pair saves, idempotent replay and stale expectations,
off-fleet customer trailer registration, explicit trailer admission/create,
bulk company enable/disable and unchanged independent service histories.

The first combined run returned one test-fixture failure after a deliberately
rolled-back nested request expired the modified Customer object. Explicit
fixture refresh fixed the asynchronous fixture read; no product assertion or
constraint was weakened. All ten real PostgreSQL cases already passed in that
first run and passed again in the final candidate.

Frozen service SHA256:
`2b861dc598486a954180968cf00a0f7398825381fd7a2b7f03dfb0fa0d2b9709`.
Owner evidence is not independent gate or runtime-release approval.


## Classification and source gates

The frozen reviewed production operation changed exactly20 remaining unknown
records to tractors. Unit533 was already classified and was preserved. Independent
fresh readback and the real staff browser show23 tractors,2 trailers,0 unknown;
confirmed609→24 and603→42 remain unchanged. All protected Vehicle fields and
eight service/history/membership/relationship domains match their baselines.
Private allowlist, transaction receipt and readback stay local.

Independent Security GO covers33 focused tests plus five adversarial probes;
independent QA GO covers21 backend/PostgreSQL cases and desktop/375px synthetic
browser journeys. See [QA evidence](DB157_ASSET_DETAILS_QA.md). The map-pin popup
keeps address and speed off the closed card/header, preserves real zero and each
field's own observation time, and supports keyboard/outside dismissal.

November5 New York startup preflight repeated: intended dirty branch remains
codex/fleet-asset-details at9ad6809e;5173 absent;8000 is Docker PID3415 with the
preserved privacy-safety backend mounted read-only. Controller dry-run refuses
the dirty target and approved backend/.env remains absent. Local product serving
is blocked/mismatched. The isolated synthetic browser harness is separate.

Frontend production build and shared-control checks pass. Direct whole-file
ESLint reports four existing FleetApp no-explicit-any errors and one existing
hook warning; changed-source regression lint passes with no new violations across nine files. No unrelated
lint cleanup is included.

Final focused frontend acceptance passes59/59 across seven suites. A deterministic
jsdom fake-clock/RAF cleanup failure was reproduced and corrected in the test
harness without changing product behavior, assertions or deadlines; the isolated
open-popover expiry case still verifies automatic stale-speed removal.

## PR791 CI return — PM retirement fixture

November5 New York: full backend CI returned only
`test_pm_day_load::test_ignores_deleted_trucks`. The fixture attempted to enroll
an already archived Vehicle; the new admission guard correctly rejects that
with404. The correction first enrolls both live fixture assets, then retires
GONE before querying PM day load. The original count1 and units[LIVE]
assertions remain unchanged, so the case still proves that an archived asset
with historical fleet membership does not contribute to current PM load.

The full PM module passes **14/14 in 2.08 seconds**. No product change or guard
weakening; the frozen service hash remains `2b861dc5…`. Independent fixture
review and fresh exact-head protected CI remain required before release.

Nov5 preflight repeated at branch `codex/fleet-asset-details`, HEAD `6dbcb38c`:
5173 absent;8000 remains Docker PID3415 with the privacy-safety backend mounted
read-only. Runtime controller refuses the dirty target. Existing services,
configuration and volumes remain untouched; local product serving remains
blocked/mismatched. PM tests use isolated in-memory fixtures, not product data.


## PR791 CI return — trailer admission test setup

Run [41973025675](https://github.com/mecaniser/truck-pit-stop/actions/runs/41973025675)
returned one full-frontend failure: the newly added requires-tractor admission
case exceeded its existing5000ms deadline;2348/2349 cases passed. Product source
was unchanged from the preceding passing frontend gate. QA optimized only this
new test: make/model are direct fixture change events, named controls are scoped
to the identified panel, and portaled option text is scoped to option elements.
The actual dropdown-selection clicks and disabled/no-POST→selected-tractor
request assertions remain unchanged. No timeout increase, assertion removal,
product edit or broader suite reduction.

Focused case passes under the unchanged deadline. The final exact seven-suite
acceptance set passes **59/59 in9.71 seconds** with the same two isolated workers
used by the full frontend CI runner. A draft selector initially matched both the
named group and its combobox; restricting the label query to the actual button
resolved that test-only ambiguity before freezing the candidate. No application
semantics changed. Fresh independent Security review and all seven exact-head
CI checks are required before release.


## Released November 5, 2026

PR [791](https://github.com/mecaniser/truck-pit-stop/pull/791) merged as
`beae00f8a76054ee0111acff46228181ec5ba8b9` after all seven checks in
[run 41974304304](https://github.com/mecaniser/truck-pit-stop/actions/runs/41974304304)
passed on `3fd8706d`. The checked and merged trees are identical. The two CI
returns were test-fixture issues, corrected and independently reviewed with
assertions and deadlines preserved; no product weakening was introduced.

API deployment `69f9f8e2-66b9-4b21-95cc-0b7c56223dcb` succeeded. The public build
stamp matches the merge, built 05:40:12.971 UTC; database and Redis readiness
pass. Read-only production checks verify the seven reviewed backend/migration
module hashes, existing migration 203, 25 active assets, 23 tractors, two trailers,
zero unknown types, 21 assets with both available Motive readings, and all four
reciprocal Elis attachment projections. Six protected identity/membership groups
and six Elis service-history groups remain byte-identical to pre-deploy.

Independent signed-in runtime QA is GO. Actual desktop and 375px Chrome checks
verify settings only inside Truck details, required tractor/no standalone Detach,
609→24 and 603→42 navigation, current own health readings, and trailer engine
hours Not applicable. Browser acceptance read 609 at 673,150.66 mi / 8,305 h and 603
at 693,831.25 mi / 23,560 h after the next hourly health collection; these exceed the
prior readback and confirm continuing automatic updates.

Cards and headers show only a 44px map-pin until opened. The actual 320px popover
contains the long address within 375px, preserves real-zero/stale semantics and
its own speed observation time, consumes outside dismissal, and supports Enter,
Escape and focus return. The settled phone details dialog occupies exactly
x0..375 with document width 375; equipment controls remain 44px and in bounds.
Settled trailer 42 selectors visibly show Trailer and assigned tractor 603. Two
initial screenshots were captured before paint/entry completion; settled visual
and geometry evidence closed both capture issues without a product change.
Default viewport was restored. No production Save/create/remove action was used
for acceptance. Private DOM, images, IDs and fingerprints remain outside Git.

The follow-up is Done. The independent location/speed worker authentication
repair is recorded under DB-036 and is not included in this runtime approval.
