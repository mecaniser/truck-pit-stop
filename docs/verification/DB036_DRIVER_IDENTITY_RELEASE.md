# DB-036 driver identity release evidence

Backend & Integrations accountable. High-risk lane; existing PostgreSQL storage.

## Source and review

- PR496: https://github.com/mecaniser/truck-pit-stop/pull/496
- Reviewed head: `e28f0dabaa0ee6cab6f355c6e3f53840ddc338c5`.
- Squash merge: `a771a562cbb3b3980b9a91879cf19372bfaaeb2e`, 2026-10-10 01:51:44 UTC.
- All six PR CI checks passed. Merged backend/frontend match reviewed source.
- Independent offline QA/Security: 113 backend/worker and 86 frontend tests; TypeScript/build; synthetic desktop/mobile; production read-only candidate validation.

## Dry run and deployment

- Fresh source: 22 complete directory entries, verified company before/after.
- Three exact customer-scoped dry runs: 18 primary, 1 Elis Logistics (609), 1 DONTRANS (532). Each validated with committed=false, disjoint eligibility, and unchanged capture/journal fingerprints.
- Independent dry-run gate GO; source hash `dd3464ffb1382f773901f9cae4f425437d37a422dcaee4429dc647cbc0e48d06`.
- Web deployment `ba4fc4f8-bf01-4af3-b9e3-28cc96fc72fa` and app worker `e16ce980-27fa-450c-86ac-349d59dc6bf4` succeeded at merge SHA.
- Production `/health/ready`: database and Redis healthy.
- Dedicated driver canary deployment `567c328d-7b99-452d-9325-4c801f7d719e`, image `sha256:3006d794eddea145a1128e27a4803e02786c12e14d159006ff990bb04679bc94`. Five running source file hashes match the immutable merged backend archive.
- Entrypoint `python -m scripts.motive_drivers.run_fleets`; same tenant/actor/company; existing primary journal plus two exact additional fleet identities; no new volume or plan.
- Deployed backend after the fresh canary exposes 20 driver records across 22 trucks, with 14 numeric scores and six available records without a source score; two source gaps remain unknown.

## Preservation and source gaps

Read-only before/after hashes are exactly equal for 1,431 vehicle identity/contact rows, 45 fleet memberships, and zero managed driver profiles. All unconfigured-fleet and other-tenant capture/directory fingerprints remain unchanged.

Fresh source has 20 captured records and 14 numeric scores. Six captured drivers have no provider score; unknown is not zero. Truck 70 has no assigned Motive driver. Truck 26 lacks a VIN in both systems and cannot safely link. Truck 609 remains in Elis Logistics; truck 532 remains in DONTRANS. No fuzzy alias binding, contact reassignment, membership move or billing mutation.

## Verified worker and schedule

All three child journals have five expected stages ending verified/committed. Primary 18, Elis 1, DONTRANS 1 records created; unchanged replay, committed readback and available projection each match 18/1/1, with zero unverified assignments. Wrapper logged fleets_complete for all three. Independent server/data/schedule gate GO includes source/attempt hashes, exact tenant/customer bindings, deterministic request IDs, disjoint scope, and preservation comparisons.

Daily deployment `9750fedb-f94a-47b3-87eb-fa75b1f99c2b` is SUCCESS and active with the exact tested driver image. The scheduled instance is CREATED awaiting the next run, not a failed worker. Entrypoint remains run_fleets; daily `45 13 * * *` UTC; next run 2026-10-10 13:45 UTC; one replica, NEVER restart, no volume or web healthcheck. The four other Motive collector configurations are unchanged. Primary journal identity and the two explicit additional fleet IDs match the approved configuration.

A direct Railway redeploy attempted Railpack and failed before execution. Re-uploading the immutable backend archive with an explicit Dockerfile/daily deployment manifest corrected it; final image digest matches the successful canary. Future release operations should use the explicit deployment archive configuration rather than relying on the service redeploy default.

Application readiness remained healthy after more than 12 minutes; Celery ready and beat startup were confirmed for the merged app worker.

## Signed-in acceptance and correction (2026-10-10)

After unlock, production Fleet Board showed verified provider names beside numeric scores, including Brandon 82 and Elis truck 609 at 82. Native Chrome opened Brandon's popover with the provider period, safety behaviors, 41.4% utilization, active/idle time, four coaching items and recent events. Escape returned focus to its trigger. At 390 by 844, truck 728 displayed Bohdan Goshovskyy without a saved local contact name, with score 98 and a readable scrolling popover. Temporary viewport override was reset. Private screenshots and accessibility evidence are retained under output/driver-matching.

The signed-in gate found two hidden scores on trucks 77 and 02. A fresh read-only server check still returned 18 primary records and 13 primary scores, with only the known two no-capture gaps. DriverRecordDetail inherited provider-source whitespace stripping, changing the exact local_driver_name snapshot while BoardTruck retained the original value. The frontend's exact snapshot guard therefore rejected those two valid records.

Focused correction on codex/driver-alias-snapshot preserves whitespace only on local_driver_name. Provider normalization and client/current-assignment guards remain unchanged. Regression first failed for all three whitespace-bearing aliases, then passed after the correction; 102 backend/worker tests and 33 frontend tests pass, with changed-source lint. Tests cover detail JSON and summary serialization, exact provider-score display, and genuine whitespace-only assignment changes remaining invalid. No migration, capture rewrite, collector change, or contact/fleet mutation is needed.

Independent review, protected CI, corrected deployment and signed-in confirmation of the two affected scores remain required. Backend & Integrations accountable; item is not Done.

## Rollback

Restore prior driver image `sha256:12c497f41914a786794b9bf4de9a8f73754a43f68f599c58e38e493a91e3c616` and command `python -m scripts.motive_drivers.run_worker`, remove additional-fleet configuration, retain immutable journal/capture evidence and primary key. Prior Web/app worker revision `0fa8336be06235a1b56996197fb628b46a29628c`. Roll back on wrong-person/tenant projection, identity drift, failed replay/readback, or unhealthy application.

Private raw source, customer identities, receipts and hash evidence remain under `output/driver-matching/` and are not committed.
