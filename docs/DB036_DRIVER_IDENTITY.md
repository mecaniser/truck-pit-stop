# DB-036: observed Motive driver identity

Backend & Integrations owns this follow-up on `codex/motive-driver-identity`.
Architecture contract agreed 2026-10-09; independent QA/Security and release
verification remain required. This changes the read projection, not stored
contacts, custody, historical captures, or provider assignments.

## Identity and display

`Vehicle.driver_name` and `driver_phone` are local contact/custody fields. They
are not provider identifiers. A first name, alias, transliteration, matching
phone, or shared truck does not prove that a local contact is the same person as
a Motive driver. No fuzzy matching or automatic alias binding is permitted.

The score is displayed beside the **Motive full name** from its verified current
vehicle assignment. Local contacts and managed profiles remain separate when
different. A missing local name does not hide a verified Motive driver. Never
replace local contact values or move their phone number to the provider person.

## Additive API contract

Board/detail `driver_record` summaries and `/fleet/trucks/{id}/driver-record`
record details retain existing score, coverage, source-time and stale fields.
`driver_name` continues to mean the provider full name. They add:

```ts
{
  identity_basis: 'motive_current_assignment';
  source_company_id: string;
  provider_vehicle_id: string;
  local_driver_name: string | null;
  local_assignment_revision: number;
  assignment_verified_at: string; // latest complete directory UTC time
}
```

These fields are inside the record, not additional BoardTruck fields. The detail
response adds nullable `unavailable_reason`: `no_capture`, `directory_missing`,
`provider_assignment_unverified`, `local_assignment_changed`, or
`vehicle_identity_changed`. Existing availability values remain unchanged.
No-score source records remain available with `safety_score: null`; absent source
evidence is never zero. A missing capture has no inferred cause beyond
`no_capture` because omitted/unavailable source rows are not persisted as driver
captures.

Clients require the same company, provider vehicle/driver, capture, local
revision/name and assignment verification context when opening details. A local
name must agree with the board alias snapshot. Without a summary, refresh the
board before attaching provider details. A managed profile is never matched to
Motive using name coincidence. Stale records retain neutral score treatment and
their observation time.

## Server guards

Projection requires the authenticated tenant, one active fleet membership, the
same fleet customer and membership as the capture, exact current VIN, and a
source read within membership. Capture-time local name, phone and revision must
still match; name/phone edits and change-away/change-back invalidate the old
observation. A fresh capture is required after a local assignment edit.

A complete directory is mandatory, scoped to the same tenant and fleet customer.
Its company ID and label must match the record. Its timestamp must cover the
record, lie within current membership and not be in the future. The directory
must contain exactly one occurrence of both the provider driver and provider
vehicle, identifying each other. Missing, unassigned, duplicate, changed or
cross-company evidence suppresses the projection. Latest capture selection never
falls back to an older person when the newest observation is invalid. A cached
board label must match the current local vehicle label before attaching summary.

No new write endpoint, database migration, alias table, provider mutation or
capture replay behavior is introduced. Existing API authorization and `no-store`
detail responses are preserved.

## Acceptance cases

- Different/absent local alias: source name and its score available; contacts
  unchanged and presented separately.
- Exact local/provider name: same provider identity contract; no special trust.
- Missing directory, directory older than record, changed provider assignment,
  duplicate driver or vehicle ID: no record and explicit unverified reason.
- Same provider IDs in another customer/tenant: no cross-scope projection.
- Local name/phone change or change-away/change-back: old capture stays invalid.
- VIN or membership change and stale cached board name: no wrong-truck score.
- No source score, explicit zero and empty events preserve distinct meanings.
- Card, detail and popover use the same provider identity; stale/different detail
  response cannot appear beside a cached person.

Local preflight: Vite5173/PID76897 belongs to this checkout; backend8000 and
approved backend configuration are absent. No local full-stack visibility claim.

## Additional fleet coverage

The user confirmed retaining truck 609 in Elis Logistics while adding collector
coverage. `python -m scripts.motive_drivers.run_fleets` runs the primary configured
fleet and an explicit `MOTIVE_DRIVER_ADDITIONAL_FLEET_CUSTOMER_IDS` JSON UUID list.
The entire bounded, canonical, distinct target/key/path plan is validated before
any child starts. Additional fleets require PostgreSQL journaling.

Each child uses the existing worker with the same tenant, actor and Motive company,
its own exact expected local fleet customer, a separate stable journal key and
UUID-named temporary directory. The primary key and state directory are unchanged
so outstanding primary recovery remains intact. Every child independently checks
authority, immutable journal binding, advisory locking, exact VIN/current fleet
membership, dry-run/commit, replay and committed readback. Sources and receipts
are not shared between fleet identities. Children execute sequentially; failure
stops the remaining targets and logs only the fleet ordinal. No fleet membership,
contact, billing relationship, provider record, plan or volume is changed.

Source-gap investigation: Motive has no assigned driver for truck 70. Truck 26
has no VIN in either system, so its provider identity cannot safely be linked by
this VIN-based importer. Neither absence produces an invented zero score.

Rollback: restore the previous worker command/image and clear the additional
fleet list; retain all immutable journal/capture evidence. Restore the prior Web
image if the identity display fails. Existing primary key remains unchanged.
