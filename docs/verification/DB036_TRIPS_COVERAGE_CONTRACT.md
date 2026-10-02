# DB-036 Trips coverage and source precision contract

Status: Approved by Product & Delivery Lead, 2026-10-02.
Accountable owner: Backend & Integrations. Architecture owns this contract.
Outcome: Fleet totals include all verified imported journeys in the selected period, preserve measured source precision, and clearly identify incomplete history.

## Scope and compatibility

Add a new migration after deployed migration 158; do not rewrite migration 158.
Existing API authorization, tenant isolation, VIN mapping, current fleet membership, date filtering, and transaction ownership remain in force. No change to vehicle records, repair records, service mileage, PM, or telemetry snapshots.

## Timestamp precision

Add `timestamp_precision: Literal["second", "minute"] = "second"` to TripImport, FleetTrip, and TripItem. Persist non-null with server default `second` and a database value check.

- Second precision retains existing validation: completed end strictly after start; driving and idle each cannot exceed elapsed time.
- Minute precision requires start/end seconds and microseconds to be zero. End must be greater than or equal to start. Same-minute journeys require positive measured driving seconds.
- Minute precision permits measured driving and idle, independently, up to displayed elapsed seconds plus 59. Keep existing absolute numeric bounds, finite checks, strict integers, and explicit timezone requirements.
- Import Motive's measured duration; never invent endpoint seconds or infer duration from rounded endpoints.
- Existing stop validation stays strict. Unavailable stops stay null.

A minute timestamp denotes its full minute window. Import and read visibility conservatively require membership to cover the start-minute lower bound through the end-minute exclusive upper bound (`ended_at + 60 seconds`). The upper bound must be at or before source_read_at and current time. For membership effective_to, require the upper bound at or before effective_to. Second precision retains the existing boundary behavior.

The trip identity remains `(tenant_id, provider_vehicle_id, started_at)`. Two distinct source journeys departing in the same minute are ambiguous under this identity: reject and report, never combine them or invent distinct departure seconds.

## Digest and normal imports

Include minute precision in the canonical digest. Omit default second precision from canonical digest construction to preserve existing hashes. Preserve existing metrics normalization.

Normal imports remain insert-or-identical-retry only. A different payload for an existing identity fails atomically. Source read time alone does not change the digest. Exact retries must not mutate capture metadata.

## Explicit correction of initial truck609 observations

Provide an operator CLI correction mode separate from normal import, with explicit expected existing trip UUID and expected digest for each correction. No generic upsert. Use the existing active tenant owner/admin authorization and tenant lock, plus row locks and compare-and-swap validation.

This path corrects the three initial rounded truck609 observations using newly verified report values:

| Original distance | Verified distance |
| --- | --- |
| 40 miles | 39.89 miles |
| 25 miles | 25.08 miles |
| 66 miles | 66.26 miles |

Require unchanged tenant, VIN, vehicle, provider vehicle, captured fleet membership, departure timestamp, arrival timestamp, origin label, destination label, and stops. Allow timestamp precision, measured driving duration, and measured distance to change. Each distance correction must differ by strictly less than one mile from the expected existing snapshot. Frozen MPG basis and existing idle readings remain unchanged unless an explicit independently verified metric correction is supplied; do not silently replace metrics with null values from the report. Other unrelated fields cannot change.

Before modifying the current snapshot, append a revision containing the complete old snapshot, old digest, old source/capture provenance, replacement digest, correction reason, operator, and correction timestamp. Use a tenant-scoped revision table with composite trip/tenant FK, or a strictly append-only revision array on the existing record. The preserved original snapshot must be complete enough to reconstruct all source values and identity. The current snapshot gets new verified values and new source/capture provenance. Keep the same trip UUID and trip identity so only one trip counts.

An exact replacement retry returns unchanged and creates no duplicate revision, provided its existing UUID and preserved expected predecessor digest identify the already-applied correction. Wrong predecessor digest, different trip identity, deleted trip, inaccessible membership, stale source, or unauthorized actor aborts the entire batch. Dry-run returns planned corrections without persisting either revisions or current values.

No deleting/reinserting source records, broad upserts, or erasing old provenance. Runtime release evidence must show original revision preservation and unchanged vehicle, repair-order, and telemetry fingerprints.

## Summary and UI contract

Extend TripSummary with:

```json
{
  "truck_count": 3,
  "coverage": "partial"
}
```

`truck_count` is COUNT(DISTINCT vehicle_id) over the full authorized, date- and truck-filtered query before pagination. Existing trip_count, distance_miles, and driving_seconds use the same full query. Use zero for an empty result. Maintain all existing response fields and filtering behavior.

`coverage` is the literal `partial` for imported history. It does not become complete merely because multiple trucks have rows. Completeness requires a future separately verified capture manifest covering the selected vehicles and dates, including confirmed zero-trip days.

All trucks displays cumulative imported totals. A selected truck displays only its imported totals. Concise coverage wording: `Imported trips · X trucks · Partial history`. Zero imports must not claim zero driving. Do not call truck_count the total fleet size or a count of all tracked devices.

## Required acceptance evidence

- Legacy second-precision validation and digest replay unchanged.
- Valid same-minute journey; minute elapsed+59 accepted and +60 rejected; nonzero endpoint seconds rejected.
- Unknown seconds cannot cross membership, source-read, or current-time boundaries; equivalent read and import guards.
- Duplicate source departure identities fail atomically.
- Multiple trucks and more than 50 rows produce full-query totals and distinct truck count; selected-truck and empty results are correct.
- Foreign tenant and inaccessible membership remain hidden, including summary counts and correction requests.
- Correction CAS mismatch, unauthorized actor, unexpected identity, distance delta >=1, and deleted record fail without writes.
- Successful correction preserves original snapshot and provenance, counts one trip, retains frozen metrics, and supports exact idempotent retry.
- Dry-run creates no data; failed correction batch rolls back every row and revision.
- Frontend communicates partial history without suggesting unimported days or trucks had no driving.

Independent QA/security review and migration smoke are required before release because this change modifies sensitive data and database constraints.
