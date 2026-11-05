# DB-157: tractor and trailer fleet assets

Backend & Integrations is accountable for the canonical asset and attachment
contract; Frontend & UX implements the existing fleet surfaces. This is a high
risk change because it adds a relational table and a tenant scoped mutation.
Independent Security and QA review plus migration and runtime acceptance are
required before release.

## Acceptance and identity boundaries

- Existing equipment records retain their Vehicle UUIDs. Classification uses
  the existing `equipment_type` enum: `unknown`, `tractor`, `trailer`, `other`.
- The two user identified Elis trailers already have canonical trailer
  classification in the reviewed production read. No unit number backfill,
  ownership transfer, new equipment identity, or production classification
  write is needed. Unknown equipment stays unclassified until explicitly edited.
- Tractors and trailers can be filtered independently; All preserves unknown
  and other assets. Classification is not inferred from unit numbers.
- Each asset retains its own repair orders, inspections, maintenance programs,
  readings, service history and account relationships. Attachment never moves,
  copies or inherits these records or its counterpart's telemetry.
- A current tractor/trailer pairing has navigable links in both directions.
  Changing or releasing it closes a dated row; prior pairing rows remain.
- Missing trailer engine hours are not presented as a missing tractor reading.
  Existing real readings remain available; no measurement or observation time
  is invented.
- Foreign tenant, archived, off-board, future-membership and nonexistent
  attachment targets are rejected without exposing their identity.
- A tractor and trailer each have at most one active pairing. Concurrent
  attachment, swap, detach, classification and lifecycle edits cannot steal a
  counterpart, silently overwrite a newer pairing, or leave a hidden live pair.

## Additive API contract

Existing `GET /fleet/board`, `GET /fleet/trucks/{id}` and fleet update responses
add these `BoardTruck` fields:

```json
{
  "equipment_type": "trailer",
  "attached_asset": {
    "id": "00000000-0000-4000-8000-000000000001",
    "unit_number": "Example tractor",
    "equipment_type": "tractor",
    "attached_at": "2026-11-04T23:00:00Z"
  }
}
```

`attached_asset` is null without a visible, valid current pairing. Its `id` is
the original Vehicle UUID used by existing fleet detail navigation. The compact
board's materialized JSON is enriched from fresh canonical Vehicle rows, so old
cached classification or absent cached fields never override a current record.
Detail uses the same enrichment before PM mileage projection. A restored orphan
projection row stays unknown and never exposes an attachment.

`PATCH /fleet/trucks/{id}` additionally accepts `equipment_type` with the existing
four enum values. An omitted field leaves classification unchanged; null and
invalid enum values fail validation. An attached asset must be detached before
changing its classification. The same guard applies to existing company
equipment and staff Vehicle update routes.

`PUT /fleet/trucks/{id}/attachment` is usable from either asset's perspective:

```json
{
  "attached_vehicle_id": "00000000-0000-4000-8000-000000000002",
  "expected_attached_vehicle_id": null
}
```

Both keys are required, including a null expected value when previously
unattached. A null requested value detaches. A successful response is the
updated `BoardTruck`; clients invalidate fleet board and detail caches for
both assets. Repeating the already achieved pairing or detached state is
idempotent. No existing partner of the chosen counterpart is displaced.

Authorization uses existing `require_fleet_access`: garage owner, garage admin,
fleet manager with an authenticated tenant. Both endpoints of a new pairing
must be current, unarchived board members in that tenant. Owners and operators
may be different companies; customer-name or owner equality is not an access
rule. Unknown or other equipment must be classified before pairing.

Errors: 404 for unavailable assets/tenant, 409 for stale expected state, self
attachment, incompatible equipment roles, an occupied counterpart or an active
pair that blocks a lifecycle/type edit; 422 for malformed/missing fields. The
existing role dependency retains its existing 403 behavior.

## Migration and concurrency

Migration `202_fleet_asset_attachments` follows
`201_customer_payment_profiles`. It adds only `fleet_asset_attachments` with
tenant-composite Vehicle foreign keys, distinct-asset/date checks, actors and
dated attach/detach fields, plus one partial unique active index for each role.
It creates no pairings and changes no existing business records. The existing
separate driver-custody `FleetTrailer` identities are not cloned or treated as
the permanent serviceable Vehicle identities, and shared driver custody does
not establish a physical tractor/trailer attachment.

Mutation takes the tenant row lock before asset locks. Classification, fleet
membership removal, customer fleet disabling, relationship synchronization,
archiving and merging share that serialization point. Existing customer
update/delete paths that lock Customer first now acquire the attachment tenant
lock first for the guarded operation, retaining tenant -> customer ordering.
Active pairings block removal/merge/archive until explicitly detached; closed
pairing rows retain their original asset identity and do not move service history.

Rollback before any pairings can drop the additive table. Once real pairing
history exists, prefer reverting the application and retaining the additive
table; a downgrade would erase pairing history and requires explicit review.
Existing equipment classification and service records are unchanged by either
application rollback. Stop rollout for tenant leaks, duplicate current pairing,
lost attachment history or changed repair/maintenance identity.

## Local runtime receipt

2026-11-04: intended checkout `truck-fleet-assets`, branch
`codex/fleet-tractor-trailer-assets`, base `f8ffd880`. Mandatory local runtime
controller status and switch dry run were inspected. Port 5173 had no listener;
8000 belongs to the existing privacy-safety Docker source mount, not this
checkout. Controller refuses the dirty target. Existing services, configuration
and volumes were preserved. Local product serving is blocked/mismatched and no
local authenticated product rendering is claimed by backend implementation.
Synthetic pytest fixtures and the isolated DB157 PostgreSQL container are
separate test infrastructure, not a replacement product runtime.

## Verification and release status

Backend owner checks: 55/55 focused and adjacent cases passed in 35.45 seconds,
including 6 genuine PostgreSQL tests in disposable schemas: actual migration
upgrade/downgrade, tenant-composite
foreign key rejection, simultaneous competition for each role, and attachment
serialization against membership removal, merging and classification changes.
SQLite cases cover both endpoint perspectives, idempotent retries, swaps,
detach history, occupied/stale states, unknown/same-kind/self pairing rejection,
tenant/off-board/archive/future-membership denials, cached board and detail
classification, all existing classification editors, lifecycle guards and
unchanged separate repair/maintenance/readings histories.

The combined SQLite-first/PostgreSQL run exposed an existing test fixture
delegation bug: its UUID result processor did not forward the required
`coltype` argument to PostgreSQL. The one-line forwarding fix is included;
the final combined run passes in that formerly failing order. No application
assertion or database constraint was weakened. `git diff --check` passes.

Independent gates, runtime evidence, migration identity, PR and deployment are
recorded as they become available. Owner tests do not establish release
completion or independent approval.

Independent Security GO: no unresolved findings. Reviewer reproduced and closed
lifecycle orphan and tenant/customer lock inversion findings; 12 focused asset
cases, 6 PostgreSQL migration/concurrency cases, 2 independent PostgreSQL
customer lock-order probes and detach/remove/reattach probe passed. Source
service SHA256 `008649b5ae17be93b014987b7b3b21e02d9af594350f9284b8426872e7ff6f21`;
migration SHA256 `0d208e02f65881e38463eb5345cdf28413ae71e92daf76b9c9b39951440ddafd`.

Independent QA source GO is recorded in [DB157_QA](DB157_QA.md). Root's final
TypeScript production build and baseline-aware changed-source lint passed
(10 TypeScript files, no new violations). No pairing is inferred or written to
production for acceptance; actual current assignments must be selected by an
operator. PR checks, migration/deployment and authenticated production read-only
acceptance remain pending at source handoff.

## Production release complete

PR [788](https://github.com/mecaniser/truck-pit-stop/pull/788) merged as
`29a47bf2bc2512fe1278dbb8fcf93d5c9892e179` after all seven checks on combined
head `5b60eda2149d3f9d5fac735c5e6c4ac5c8100b0d` passed in run
`41963626631`. Checked and merged trees are identical. The earlier clean
candidate also passed all seven checks; a subsequently merged payment PR caused
only a project-board conflict. Both delivery records were preserved and the
combined head was checked again. The reviewed fleet service and migration hashes
remained unchanged throughout integration.

Production deployment `40aeb0b3-85c7-4ae3-93a7-c0d050ea232d` is SUCCESS.
The public build stamp reports the merged SHA, built at
`2026-11-05T03:57:16.432Z`; production readiness reports database and Redis OK.
Read-only production acceptance confirms migration
`202_fleet_asset_attachments`, all 25 board records, the two preexisting trailer
classifications and the two preexisting Elis tractor classifications. All 21
assets with available Motive vitals still project both mileage and engine hours.
Deployed service and migration SHA256 values match the independent approvals.

After deployment, the user explicitly supplied the physical assignments:
tractor609 pulls trailer24 and tractor603 pulls trailer42. Exactly these two
pairings were saved via the existing authenticated staff session, using the new
attachment controls. The database contains two current dated rows with valid
actor tenant scope, and board/detail projections agree on all four reciprocal
links. No prior pairing or vehicle classification was overwritten.

Actual production browser acceptance verified the trailer filter contains only
Elis24/42, both trailer health panels show engine hours Not applicable, and both
tractor panels retain their own actual mileage and engine hours. Reciprocal
links navigate the appropriate assets. Trailer42's picker excluded the already
occupied tractor609. The trailer filter survives returning from detail. A375px
production viewport has375px document width and retains the trailer health
behavior; the viewport override was reset afterwards. Screenshots remain private
local artifacts, not repository attachments.

Before/after read-only fingerprints match for all six identity/membership/account
relationship scopes, including all25 current fleet vehicles. The six separate
Elis service-history scopes also match:57 repair orders,8 inspections,9 incidents,
1 saved PM package,2 maintenance programs and0 maintenance readings. Attachment
writes did not alter any of those rows, service odometers, VINs or ownership.
The21 other assets without a saved canonical equipment type intentionally remain
Unclassified and can be edited independently through Change type.

Independent runtime QA GO is recorded in [DB157_QA](DB157_QA.md). Required source,
security, automated, migration, deployed-source and authenticated runtime evidence
is complete. The isolated synthetic PostgreSQL container and browser harness
were stopped; existing product services and user data remain preserved.
