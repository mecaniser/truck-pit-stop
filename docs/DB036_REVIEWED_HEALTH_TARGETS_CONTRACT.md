# DB-036 reviewed health collection targets

Architecture & API Contracts reviewed this extension independently on 2026-11-04.
Backend & Integrations owns implementation. No schema, public API, owner, operator,
payer, fleet-membership, canonical mileage or financial mutation is required.

The source company/account and default fleet pin remain mandatory for exception
configuration. `MOTIVE_HEALTH_REVIEWED_TARGETS` is an optional JSON object keyed by
provider vehicle ID; each value contains exactly `vehicle_id` and
`fleet_customer_id` UUID strings. The configured tenant is unchanged. Unit labels
and ownership alone are never mapping authority. Only the reviewed provider row
can bypass the default customer pin; its exact unique source VIN must resolve to
the pinned vehicle and its one current membership must match the pinned customer.
Missing, deleted, foreign-tenant, contradictory or ambiguous identities fail closed.
Source read time must fall within current membership. Diagnostic capture performs
its own second locked resolution against the resolved customer.

Apply the same resolution to vitals, diagnostics and unavailable-source matching.
Source-missing reporting adds only explicitly targeted vehicles, never an entire
additional fleet. Keep zero and unavailable values distinct and vitals independent
of fault availability. Never copy old captures into a different membership.

Canonical reviewed targets become part of immutable attempt identity only when
nonempty, preserving legacy no-target receipts. Recover any pending legacy attempt
before enabling exceptions. Scope drift, conflicting saved identities or membership
drift during recovery fails; never retry an uncertain commit with a new source.
Existing deterministic request IDs, rollback-only dry run, atomic commit and exact
replay/readback remain unchanged.

Production verification established unique VIN matches for the603/609 vehicles
owned by Elis Logistics LLC (DBN) in the Truck Pit Stop tenant, including matching
saved diagnostic VINs.603's dated operating fleet is77Cargo; its current vitals
already reach that same Elis-owned vehicle.609 has an Elis fleet membership and
matching older diagnostic capture but no vitals. Preserve all relationships and
add a reviewed609 exception. A separate603 in another tenant has a different VIN
and is not an authorized target. Full VINs and private source artifacts stay out
of committed evidence.

Required gates: default fleet regression; reviewed target success; unreviewed
fleet exclusion; wrong provider/VIN/vehicle/customer/tenant, duplicate memberships,
deleted targets and source-time negatives; independent availability and zero;
dry-run/commit/replay/recovery and mapping drift; immutable canonical mileage;
independent QA/Security; fresh source/readback for both actual vehicles and deployed
health-panel acceptance.
