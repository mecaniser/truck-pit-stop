# DB-036 mileage and engine-hours coverage audit — 2026-10-31

Accountable owner: Backend & Integrations. Read-only production audit, completed2026-10-31 04:09:18UTC (12:09AM America/New_York). This report does not change worker code, fleet memberships, bindings, provider configuration or telemetry. No job was triggered, retried or imported for this audit. UI refinement remains a separate change.

## What19 versus21 means

The released health worker was deliberately pinned to the existing **77 CARGO LLC** fleet. That fleet has21 active members;19 currently have both mileage and engine hours. Its missing units are **5 and26**.

The retained authorized Motive Health source also contains21 provider rows, but it is a different set:19 map into77Cargo, source26 has no displayed VIN, and source609 maps to **Elis Logistics LLC (DBN)**. Source609 has both measurements but is excluded by the released single-fleet pin. It is not one of77Cargo's two missing member rows. Counts from these different sets must not be treated as interchangeable.

## Current coverage across all active local fleets

Production has25 active fleet memberships in this tenant. Nineteen have the newly collected canary vitals. Truck609 still has older manual vitals. Five have neither projected mileage nor engine hours.

| Company | Unit | Current state | Evidence and reason |
| --- | --- | --- | --- |
|77 CARGO LLC|5|Both unavailable|No retained telemetry snapshots. Neither its exact VIN nor its unit label matches the retained authorized Health source. This source does not supply it.|
|77 CARGO LLC|26|Both unavailable|Recent location-only snapshots exist. Motive source26 has no displayed VIN; health collection records `vin_unavailable` and never reads vitals for that row. A non-revoked reviewed source binding already exists, reviewedOct16 with `source_vin_state=not_displayed`. The health path does not consume that existing binding, although the location path does.|
|Elis Logistics LLC (DBN)|609|Old readings remain visible; fresh readings held|Current exact-VIN match resolves to one active Elis membership, effective sinceJuly24. Released77Cargo fleet pin excludes it. No reassignment is appropriate.|
|Elis Logistics LLC (DBN)|24|Both unavailable|No exact-VIN match in the retained authorized Health source. Source coverage or device association has not been established in this audit.|
|Elis Logistics LLC (DBN)|42|Both unavailable|No exact-VIN match in the retained authorized Health source. Source coverage or device association has not been established in this audit.|
|DONTRANS LLC|532|Both unavailable|No exact-VIN match in the retained authorized Health source. Source coverage or device association has not been established in this audit.|

Truck609's visible values are **661,369mi /7,992h**, capturedOct2 at19:25:34UTC; provider observation time is unknown. The retained source read onOct31 at02:55:19UTC shows **671,597.62mi /8,273h**. Those newer measurements were held by fleet scope. Its old visible values are not evidence that current automatic collection includes609. It has a source-scope integration gap for an account-wide collection outcome.

## Evidence and limits

- Current production query used an explicit database read-only transaction and the same field projection used by Fleet. It found21 active77Cargo memberships,19 with both readings, plus25 active memberships across all local fleets. Missing-field checks use `None`, preserving valid zero readings.
- Current memberships confirm609 belongs uniquely to Elis; the source account label77Cargo does not override local fleet/customer identity. Current binding rows confirm26 already has a reviewed no-displayed-VIN association; it does not require fabricating a VIN or remapping the truck by unit name.
- The retained candidate Health source finalized2026-10-31 02:57:52.989UTC. Its dry-run explicitly classified609 as `unique_current_membership_required` under the77Cargo pin; source26 is `vin_unavailable`. Its current-fleet source-missing rows are5 and26. This is prior candidate source evidence, distinct from a new provider capture.
- The deployed canary finalized2026-10-31 03:52:03.517UTC. Its independently verified source identity is `cc92bc222bd77af0c452f1e6ec06942189816568e61389ba2c4bf1274fb0c913`. Current production lookup of deterministic vitals request IDs for that exact source hash confirms19 snapshots for the known provider identities and none for609 or26. The release-time receipt/readback recorded19 vitals and17 diagnostic captures; these are different collections.
- The stopped health service could not serve its persisted receipt through SFTP. That read-only file attempt failed; no service start or job retry followed. This audit therefore does not claim a new full canary source/receipt download. It combines release-time canary evidence, exact-request snapshot lookup, retained candidate source and fresh production membership/projection checks.
- Absence from the retained Health report does **not** prove5,24,42 or532 are absent from all Motive screens, lack a device, or have no reading elsewhere. Other provider directories/accounts were not inspected. No source record, VIN, company membership or approval was invented to fill a gap.

## Follow-up ownership

Backend & Integrations should extend health vitals ingestion to consume26's already reviewed binding under the existing bound-telemetry contract. Missing/contradictory source identity must remain a safe failure.

Architecture and Backend should define explicit reviewed account-to-fleet projection for609 so one authorized source account can supply permitted local fleets. Preserve the current Elis membership and all tenant, source-company and mapping guards. The released single-fleet pin must not be silently removed or replaced with an unrestricted cross-fleet projection.

For5,24,42 and532, first establish whether the authorized source directory/account supplies a verified matching vehicle and measurements. Until proven, show unavailable. This audit authorizes no provider or membership mutation and makes no implementation/release claim for these follow-ups.
