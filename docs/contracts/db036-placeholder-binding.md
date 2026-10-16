# DB-036 reviewed dashboard vehicle binding

Accountable owner: Backend & Integrations. High-risk lane. Architecture handoff approved by the parent; implementation is limited to a local candidate pending independent QA/Security and release handoff.

## Acceptance and identity contract

Truck26 keeps its existing DBN vehicle UUID and `PENDING-26` local reference until a real VIN is available. The placeholder is never sent to Motive or represented as a verified VIN. No matching by unit, name, driver, or approximate VIN is permitted.

A new reviewed binding stores tenant, exact source company ID/label, provider vehicle ID, DBN vehicle UUID, current fleet membership/customer, exact placeholder snapshot, reviewer, review time, effective interval (no automatic expiry unless explicitly supplied), and revocation. An unrevoked binding is unique both per DBN vehicle and per tenant/company/provider vehicle. Expired, revoked or conflicting bindings require separate reconciliation; this CLI cannot replace historical bindings. Creation requires an active owner/admin and an explicit exact manifest; no migration inserts a binding. Capture time must follow review and remain within the active interval. The current membership and unchanged placeholder must still match. Real VIN appearing on either side closes this path pending reconciliation; vehicle UUID/history remain.

Only the explicit MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST path can retain source VIN as null after positive loaded-summary proof before and after capture. source_vin_state is honestly `not_displayed` when a complete overview omits the VIN field, or `explicitly_empty` for a displayed empty field; neither claims a verified real VIN or absence in Motive storage. Stable source company/provider routes and driver directory assignments remain mandatory. Ambiguity, route changes, and timeouts never become missing-VIN proof. Raw absent-VIN observations are not trusted mappings: the importer must resolve the exact active binding before creating any immutable record.

Driver and telemetry captures reference either a genuine verified VIN or a binding ID, exclusively. Public manual telemetry schema remains genuine-VIN-only. Worker imports require the active tenant/admin, current unique membership, source scope, verified source VIN display state, capture/observation times, assignment revision and replay digest. Replays recheck the live binding before returning unchanged. Read projections also recheck binding validity; revoked, expired, changed-placeholder, changed-membership or real-VIN captures cannot project. Driver response identity_basis remains `motive_current_assignment`; new vehicle_identity_basis is `reviewed_provider_binding` with vehicle_identity_binding_id, alongside all existing assignment and freshness context.

## Compatibility and verification

Existing VIN captures and request digests remain compatible; nullable additive binding fields do not rewrite records. Migration creates no mapping and deletes no history. Downgrade is deliberately blocked when any reviewed binding or bound capture exists; rollback should revoke the mapping and restore application/collector code, retaining the additive schema.

Focused negative tests cover wrong tenant/company/provider/membership, duplicates, revoked/expired binding, inactive actor/vehicle, source outside interval, replay after revocation, changed route, ambiguous VIN, timeout versus absence, newly supplied/conflicting real VIN and old-capture projection invalidation. Independent reviewer owns Security/QA approval. Protected CI, migration retention proof, driver/location canary and UI acceptance remain parent release gates. Keep five-minute location and daily driver schedules and existing database storage.

## Exact activation plan (not executed)

Use the dry-run binding CLI with an explicitly supplied reviewed JSON manifest and approved database runtime. Review exact tenant/company/provider vehicle, current membership/customer, vehicle UUID and placeholder snapshot against current source evidence; then use the same manifest with `--apply` only in the parent-authorized release slot. The known candidate is DBN vehicle `f946f5da-f9f4-4960-8670-5ca87467d879`, provider vehicle `5981300`, local reference `PENDING-26`; resolve fresh tenant/customer/membership/reviewer IDs rather than guessing or embedding credentials. New collector captures after activation must show source VIN null, honest display state and the exact binding, preserve driver/provider source IDs, and render fresh score/speed only when actually supplied. Stop collection/import and reconcile on any identity mismatch; revoke the binding when review establishes it is no longer valid. No binding is created by this candidate preparation.

## Source and activation refinements

Keep existing driver `identity_basis=motive_current_assignment` semantics. Add vehicle-specific basis and binding ID; genuine VIN remains the default for old clients. Only an explicit collector allowlist enables structural not-displayed collection: `MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST='[{"company_id":"KT8934277","provider_vehicle_id":"5981300"}]'`. It grants permission to read a fully verified source page, never mapping authority. Imports/projections revalidate the actual reviewed database binding. All other source vehicles keep existing VIN readers.

Positive source readiness requires fresh exact company/provider summary route, one expected visible unit header, unique matching Live link, a complete loaded overview with Fuel type, Regulated, Availability, Groups and Data source values plus Odometer value/unit or explicit empty. Loading, incomplete fields, wrong/duplicate headers/routes/links, malformed nonempty VIN and generic timeout fail closed. Check before and after capture. Root's authenticated source evidence establishes truck26 omits the VIN label in its completed overview; do not depend on an invented VIN dash.

A fully validated complete source document observing a genuine VIN for the exact binding revokes it with source VIN, read time, digest, actor and reason, without changing local VIN or mapping any vehicle. Only source evidence at/after the reviewed effective start can revoke; stale replay, malformed or unverified source cannot. Local real-VIN replacement invalidates projection immediately. Identical approved creation manifests return unchanged without refreshing review/effective time; conflicting or revoked requests fail for reconciliation. No default expiry is imposed on truck26.


## Reviewed source evidence and operator commands

Run these only in the release owner's approved existing worker/backend environment after independent approval. Keep source/manifest files private (directory 0700, files 0600), and retain the exact release SHA alongside their hashes. No credentials are embedded in the commands. Direct collector execution reads Motive and writes only the specified private source file; it does not import, create a database journal or change a schedule. Do not substitute `run_worker.py` for this read-only step.

```sh
MOTIVE_DASHBOARD_VEHICLE_ALLOWLIST='[{"company_id":"KT8934277","provider_vehicle_id":"5981300"}]' node backend/scripts/motive_drivers/collect.cjs /private/review/source.json
```

The approved runtime must already provide the exact existing company ID/label and provider login configuration. Confirm the deployed reader/collector SHA before collecting. The collector must finish successfully with a complete, company-verified directory; provider 5981300 must have one captured row, source VIN null, `source_vin_state=not_displayed` or `explicitly_empty`, and verified before/after assignment. The source itself supplies those flags. No manual claim or failed browser-control command substitutes for source proof.

Construct an explicit manifest from independently reviewed current DBN IDs and that untouched source file:

```json
{
  "vehicle_id": "f946f5da-f9f4-4960-8670-5ca87467d879",
  "fleet_customer_id": "<fresh confirmed current customer UUID>",
  "fleet_membership_id": "<fresh confirmed unique current membership UUID>",
  "source_company_id": "KT8934277",
  "source_company_label": "77 CARGO LLC",
  "provider_vehicle_id": "5981300",
  "placeholder_vin": "PENDING-26",
  "effective_to": null,
  "review_note": "Explicitly reviewed truck26 mapping with current membership and final collector evidence",
  "source_evidence_sha256": "<SHA256 of untouched source.json bytes>",
  "source_evidence_read_at": "<exact matching source row source_read_at>",
  "source_vin_state": "<exact matching source row display state>"
}
```

The manifest intentionally contains no guessed tenant/reviewer/customer/membership ID. CLI verification validates the entire source document, exact company/provider row, null VIN, source state, assignment flags and timestamp, and compares the file hash. New creation requires source no older than two hours and not future-dated. Existing identical manifests remain idempotent without extending their review/effective time. A manually reviewed summary proof is also supported, but requires actual before/after company/summary observations, exact summary and reader hashes, and matching timestamps; do not manufacture those fields.

From `backend/`, preview and then apply the **same** reviewed files only in the parent's release slot:

```sh
python -m scripts.motive_sync.review_binding --tenant '<confirmed tenant UUID>' --reviewer '<active tenant admin UUID>' --manifest /private/review/manifest.json --evidence /private/review/source.json
python -m scripts.motive_sync.review_binding --tenant '<confirmed tenant UUID>' --reviewer '<active tenant admin UUID>' --manifest /private/review/manifest.json --evidence /private/review/source.json --apply
```

The source document used for approval predates `effective_from`; do not import it after activation. Run a fresh normal collector after mapping creation. Source location observation intervals must also begin after the binding starts; an older parked location is not newly attributed merely because it is read again. Unknown provider timestamp retains unknown provenance and never invents current speed.

For rollback, disable only the new allowlist entry and revoke the exact returned binding ID, leaving additive schema and history intact:

```sh
python -m scripts.motive_sync.review_binding --tenant '<confirmed tenant UUID>' --reviewer '<active tenant admin UUID>' --revoke '<confirmed binding UUID>' --apply
```

Deploy migration before application/worker code and preserve existing scopes, five-minute location cadence, daily driver cadence, database storage and all journal/runtime settings. Do not schedule overlapping collectors. Real source VIN observation durably revokes the binding; replacing the local placeholder with a real VIN invalidates old projections immediately. Reconciliation preserves the DBN UUID and immutable history.

## Source-reader runtime evidence

On 2026-10-16 the parent tested the exact extraction function against authenticated Motive truck26. Initial global title extraction incorrectly included Fuel trend, Fuel performance, Inspections and Recent activity, so it correctly failed instead of inventing identity. The corrected reader scopes `vehicle-profile-v2-summary > phx-card.vehicle-profile-card`, checks the breadcrumb and Live route, and detects complete overview fields. The hidden responsive blank VIN field is not a displayed VIN field; a nonempty hidden VIN remains a contradiction.

The parent verified the full corrected snapshot/parser with VIN null and state `not_displayed` (`output/truck26-reader-live-fixed.json`, private), and observed the final function pass once before CUA transport interruptions. Final `summarySnapshot.toString()` SHA256 is `e74410c9d13349f38f14eaa86b2b0110f931fa62e112fc0974069c647e47583d`. Source reader unit tests cover transient startup before overview, bounded timeout, duplicate profile rejection, unrelated titles and hidden VIN values. This is source-reader acceptance, not final collector/deployment/import proof. Fresh final collector evidence and post-activation canaries remain release gates.


## Shared-directory eligibility correction

Independent review of995c19d8 found a commit/readback ordering defect: a bound truck belonging to the primary fleet was correctly excluded in another approved fleet's dry run, but its binding was resolved again before checking that fleet's saved eligible request IDs. The commit then failed instead of retaining the exclusion. Stable request identity is now calculated without resolving the vehicle; saved excluded IDs skip binding/capture work, while eligible requests still require the current binding and all tenant/membership/assignment checks. This changes no request ID or digest formula. Validated genuine-source-VIN observations retain the separate durable revocation path even when no genuine local VIN match exists, so eligibility cannot keep a known-invalid placeholder binding alive.

The regression exercises a single complete source directory across primary bound-vehicle, secondary genuine-VIN and empty local scopes using the actual runner's dry-run, commit, replay and fresh readback. Separate cases revoke the already-eligible binding or replace its local VIN before commit/readback and require rejection. The independent original reproduction is retained under private output/ and passes after correction. Independent re-review is required; owner tests are not gate approval.
