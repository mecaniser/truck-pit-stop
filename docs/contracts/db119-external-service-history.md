# DB119 — outside-shop service history contract

2026-10-14. Architecture & API Contracts approved for implementation. Backend &
Integrations accountable; Frontend & UX consumes this contract. High-risk lane
because this adds durable tenant data and a migration. Independent QA and
Security gates must be assigned to agents who did not implement or direct it.

## Outcome and boundary

Staff can record, correct, void and restore work performed elsewhere, then find
it from a customer's truck or the repair-order vehicle context. Every record is
visibly **Outside-shop service**; optional cost is **Reported cost**, never an
amount owed to this shop. This creates no repair order, invoice, payment,
receivable, revenue, timer, recommendation, inventory movement or PM completion.
Historical odometer never updates current vehicle mileage or PM thresholds.

First release is owner/admin/receptionist only. No customer, driver, mechanic,
fleet-manager or platform-super-admin access. Do not add these records to
generic vehicle responses, customer portals, invoices/PDFs/exports, fleet
history, or repair-order activity. A shop staff member can see retained truck
history after customer ownership changes; customer relationships confer no
access to these private staff records. Receipt uploads are a follow-up: existing
`WorkPhoto` is repair-order-bound Cloudinary storage, not a reusable private
vehicle document primitive.

Use the shared `CustomerVehicleDetail` for both staff entry points. Add an
explicit **View vehicle history** action to the order's vehicle popover that
opens the existing customer/vehicle workspace with a reliable return path.
Show a compact Outside-shop service section alongside existing Repair history;
do not mix its totals or entries into the repair-order query. Existing fleet
TruckDetail is outside this first release.

## Data model and migration

Add migration `169_external_service_history`, descending from
`168_operation_execution`; no backfill, no edits to existing financial rows.
Register both models in `app.db.models`.

`ExternalServiceRecord` (`external_service_records`, existing BaseModel fields):

- `tenant_id` required tenant FK; `vehicle_id` current truck; composite FK
  `(tenant_id, vehicle_id)` to existing `vehicles(tenant_id,id)` with RESTRICT.
- `original_vehicle_id` immutable UUID of truck at creation. Retain as audit
  identity rather than a cascading FK; current vehicle FK prevents orphans.
- `provider_name` String(160), `service_date` Date, `description` Text required.
- `odometer` nullable integer miles, `reference` nullable String(100),
  `reported_cost` nullable Numeric(12,2), currency fixed USD for this release.
- `version` positive integer starting at 1; `voided_at` nullable timestamptz.
- `created_by_user_id`, `created_by_name`, `updated_by_user_id`,
  `updated_by_name` immutable-ID/snapshot attribution; UUID identities need not
  be FK-linked to users so retained audit/replay survives account deletion.
- Unique `(tenant_id,id)` for event FK; index
  `(tenant_id,vehicle_id,service_date,id)`; checks version >= 1, odometer NULL or
  0..99999999, cost NULL or 0..9999999999.99. App also rejects excess precision.
- Do not use BaseModel `deleted_at` for voiding; voided data remains queryable.
  No hard-delete route and no cascading ORM delete from vehicle/customer.

`ExternalServiceEvent` (`external_service_events`, BaseModel fields):

- `tenant_id`, `record_id`, composite RESTRICT FK to the record; `request_id`
  UUID, `request_hash` String(64), unique `(tenant_id,request_id)`.
- `version` positive integer, unique `(tenant_id,record_id,version)`.
- `action`: create/update/void/restore; actor user UUID and name snapshot,
  `created_at`; optional reason; full normalized after-snapshot JSON/JSONB.
- Snapshot contains every business field, record ID, original/current vehicle
  IDs, version and voided_at. Earlier snapshots retain the vehicle at the time.
- Events are append-only by application contract: no update/delete endpoint.
  Do not mutate snapshots when moving the current record during a vehicle merge.

No artificial uniqueness on provider/date/description: repeated legitimate work
can occur. Request IDs prevent accidental retries, not intentional second work.

## HTTP contract

Routes are under existing `/api/v1/vehicles/{vehicle_id}/external-services`.
Register routes in `vehicles.py` or mount an equivalent dedicated router without
changing existing vehicle API contracts. All bodies use extra=forbid.

`GET ?skip=0&limit=25&include_voided=false` returns:

```json
{"items":[{"id":"<record UUID>","vehicle_id":"<current vehicle UUID>","original_vehicle_id":"<creation vehicle UUID>","source":"external","provider_name":"QA Outside Shop","service_date":"2026-10-01","description":"Replaced air dryer cartridge","odometer":425000,"reference":"EXT-QA-1","reported_cost":"240.50","currency":"USD","version":1,"voided_at":null,"created_at":"2026-10-14T15:00:00Z","updated_at":"2026-10-14T15:00:00Z","created_by_user_id":"<actor UUID>","created_by_name":"QA Staff","updated_by_user_id":"<actor UUID>","updated_by_name":"QA Staff"}],"total":1,"has_more":false}
```

Order by service_date DESC, created_at DESC, id DESC. Skip >= 0, limit 1..100;
invalid query validation is 422. No unbounded list; total uses the same filters.

`POST` creates one record:

```json
{"request_id":"<client UUID>","provider_name":"QA Outside Shop","service_date":"2026-10-01","description":"Replaced air dryer cartridge","odometer":425000,"reference":"EXT-QA-1","reported_cost":"240.50"}
```

201 on first create, 200 on exact replay. Response for every mutation is
`{"record": <current record using item shape above>, "replayed": false}`.

`PUT /{record_id}` corrects an active record. Body contains all create business
fields, `request_id`, and `expected_version` (integer >= 1). A full replacement
avoids ambiguous absent-versus-null optional fields. No vehicle change accepted.
200 returns the current record and replay flag. A meaningful correction appends
one update event and advances version exactly once. Submitting unchanged
business values is allowed, but should not be exposed as an enabled Save button.

`POST /{record_id}/void` body:

```json
{"request_id":"<client UUID>","expected_version":2,"reason":"Recorded against this truck by mistake"}
```

`POST /{record_id}/restore` body is `request_id` and `expected_version` only.
Void sets timestamp, appends its reason and version; restore clears timestamp,
appends restore event and version. 200 responses use the same envelope. Both are
reversible; void is excluded from the default list and visible through an
explicit Show voided control. Editing a voided record requires restoring first.
No silent toggle or physical deletion.

`GET /{record_id}/history?skip=0&limit=25` returns `items,total,has_more` ordered
by version DESC. Each item: id, record_id, version, action, actor_user_id,
actor_name, created_at, reason (nullable), snapshot (full business snapshot).
The UI shows a compact recorded/edited/voided/restored history with attribution;
prior saved values remain inspectable. History remains available while voided.

Validation: trim provider/description/reference/reason; provider 1..160 chars,
description 1..4000, reference blank -> null or 1..100, void reason 1..500.
Valid ISO date from 1900-01-01 through the shop's current date (Tenant.timezone,
existing America/New_York fallback); no datetime coercion. Odometer is a strict
integer or null, not bool/fraction; cost is a finite nonnegative Decimal with
at most two decimal places within Numeric(12,2), serialized as decimal string.
Null cost means unknown and renders “Not recorded”; zero renders $0.00. Render
all text as text, never HTML. No free-form receipt URLs in this release.

## Authorization, replay and concurrency

Use an explicit role allowlist (garage_owner, garage_admin, receptionist), active
user and non-null authenticated tenant. Load active vehicle by ID **and** tenant,
then record by ID **and** tenant **and** current vehicle ID. Unknown, foreign,
archived vehicle or wrong-vehicle record -> generic 404, without names/content.
Forbidden role -> 403 before data queries; missing tenant -> 400. Do not reuse
the broader legacy vehicle get/update authorization policy.

Every write transaction locks the active vehicle row first (`FOR UPDATE`, fresh
values), then the record for existing-record actions. This matches merge's
existing sorted vehicle-lock ordering; never lock a record before its vehicle.
After acquiring the lock revalidate active vehicle and exact record ownership.
Check replay before expected-version/lifecycle checks, after authorization:

1. Find event by `(tenant_id,request_id)`.
2. Exact replay requires same actor ID, action, target record/vehicle and hash of
   canonical normalized input including expected_version when supplied.
3. Exact replay returns the **current** record with `replayed:true`, even if a
   later correction/void/restore occurred. No second event or stale overwrite.
4. Any request-ID reuse with different identity/content/action/target -> generic
   409 “This save ID has already been used. Refresh and try again.” No original
   payload or other target revealed. Different tenants may reuse UUID safely.
5. New write with mismatched expected_version -> 409 “This service record has
   changed. Refresh it before saving.” No mutation. New update/void on a voided
   record or restore on active -> 409 with readable state message.

Create record + event atomically. Unique request constraint is the final guard
for concurrent cross-vehicle collisions: use a savepoint/whole-transaction safe
rollback and resolve collision to exact replay/409, never a raw 500 or orphan.
Never automatically replay POST/PUT after uncertain transport results. Explicit
Retry retains the same normalized payload/request ID. A changed draft creates a
new attempt ID. An action must remain single-flight while pending.

404 detail “Vehicle or service record not found”; 422 standard field validation;
409 stale/reused ID/lifecycle as above; unexpected backend failure 5xx. Do not
return success while silently discarding a write.

## Vehicle merge and customer privacy

Extend `services/vehicle_merge.py` inside its existing transaction: count
`external_services` in moved summary, update each current record's vehicle_id
to canonical under both sorted vehicle locks (including voided records).
Preserve record IDs, original_vehicle_id, versions, actor attribution and all
events. Add `external_service_count` default 0 to merge-summary response and
include it in preserved-history summary/ranking where applicable. Current data
fields/version do not change on merge; existing VehicleMergeRecord captures the
identity move/count. No separate fake service-edit event.

Old archived-vehicle routes return 404; do not redirect/retry writes silently.
An old attempt retried against a different canonical route conflicts rather
than creating a duplicate. New edits require reading the canonical context.
Race outcomes: write wins -> merge moves it; merge wins -> old-vehicle write is
rejected. Events retain provenance either way. Customer merge/relink does not
move, duplicate, expose or purge external records; they follow permanent truck
identity. No record in customer-facing vehicle serialization.

## Frontend state and interaction

Scope query keys and component remount by tenant ID, actor ID, role,
authSessionEpoch, vehicle ID, pagination and void filter. Reuse the DB118
OperationNotes identity pattern; don't depend on the entire mutable user object.
Only the allowlisted staff component mounts/fetches. Abort queries on navigation;
clear incompatible cached data/drafts on logout/tenant/role/actor changes. A late
response from the previous session must not populate the current UI.

Keep active history visible, with Add outside service adjacent. Record rows show
date/provider/work first, optional mileage/reference/reported cost next; no
invoice affordance. Creation/correction uses one compact labeled form, ordinary
date/number/text entry, retained failed draft, explicit Retry save. Field errors
remain by the form. Stale save preserves the draft and offers Refresh record;
refresh is not implicit approval to overwrite newer values. After refresh,
reviewing/resubmitting is a new request with current version. Separate successful
save from failed refresh: do not report a saved record as failed merely because
list reload failed; allow explicit list Retry.

Cancel and Escape dismiss without writes and restore triggering focus; dialogs
must have a named close control. Void confirmation states retained history and
requires reason; Cancel/Escape/close produce no request. Show voided entries with
clear status and Restore. Existing workspace stays full height with one primary
scroll area, compact desktop rows and full-width mobile form/whole button labels.
Navigation preserves originating order, customer search/filter and return state.

## Acceptance and release gates

Backend: schema bounds/null versus zero; role matrix; foreign tenant/vehicle/
record indistinguishable 404; no customer/driver/fleet/mechanic data; exact replay
for each action including after subsequent mutations; changed-payload/actor/
action collision; stale correction/void/restore; lifecycle guards; pagination,
date ordering, void inclusion; original audit snapshots retained. Assert no
changes to native order/invoice/payment totals, vehicle mileage or PM fields.
Test vehicle/customer merge/relink preservation and archived vehicle rejection.

Real PostgreSQL two-session races: duplicate create -> one record/event; same
request on two vehicles -> one winner + generic409, no orphan; two corrections
from one version -> one winner; correction versus void -> one winner; creation
and correction versus vehicle merge -> safe serialized outcomes. Test migration
upgrade/head and all FK/check/unique constraints (including cross-tenant vehicle
and record FK rejection), not only SQLite model creation.

Frontend: create/reload/correct/history/void/restore; empty/loading/failure/retry;
lost response explicit retry produces one record; stale draft retained;
cancel/Escape/named close; role/session/vehicle switch isolation and late response;
unknown cost versus zero; current-version retry; malformed response not trusted.
Independent QA checks actual desktop1280, mobile390/320 and landscape740x400
workflows through both customer and repair-order entry points. Check viewport
overflow, scroll ownership, labels/actions visible, back navigation and reload.

Production QA uses only the labeled synthetic QA customer/vehicle, nominal
reported cost (no payment), a dated QA service, correction, void and restore,
then returns it to voided state. Record exact CI head, merge/deploy SHA, migration
head, readiness, signed-in browser source and screenshots. Browser emulation is
not physical-device/native-keyboard proof.

Rollback: feature is additive. Revert application code if routing/privacy/data
or layout gates fail; leave both new tables/data intact. Do not downgrade/drop
tables after user writes. No native financial backfill to reverse. Rollback
trigger includes tenant exposure, duplicate writes, lost history, mutation of
billing/odometer/PM or unusable primary workspaces. Inspect post-deploy readiness
and changed workflow over a proportional observation window before Done.

## Source anchors and handoff

- `frontend/src/features/customers/CustomerVehicleDetail.tsx`: shared staff truck
  details and separately paginated native repair history, embedded by both pages.
- `frontend/src/features/operation-execution/OperationNotes.tsx`: identity-scoped
  query/draft and explicit uncertain-write retry precedent.
- `backend/app/services/vehicle_merge.py`: sorted vehicle locks, archive and
  canonical move; current merge has no external-service handling.
- `backend/app/db/models/vehicle.py`: existing `(tenant_id,id)` unique key.
- `backend/app/db/models/work_photo.py`: uploads require repair-order linkage.
- `backend/app/core/date_ranges.py`, `db/models/tenant.py`: shop timezone pattern.

Board ID: DB119. From Architecture to Backend & Integrations / Frontend & UX.
Contract/migration impact: new private vehicle record/events and additive routes;
no financial or public-portal schema changes. Implementation and runtime are not
yet verified. Branch `codex/external-service-history`. Return to Architecture if
roles, visible customer surfaces, attachment scope or replay semantics change.
