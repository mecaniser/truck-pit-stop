# DB-036 health vitals contract

Architecture & API Contracts: additive existing-contract use; no migration or external API change. Backend & Integrations accountable.

Health source rows gain optional vitals containing odometer_miles and engine_hours (finite nonnegative bounded numbers or null) plus source_read_at. Read visible vehicle-summary labels under the same exact provider route and verified VIN; no location/fault timestamp substitution. Unknown provider observation time remains null. Values in mi/h; convert explicitly labeled km to miles. Ambiguous/malformed/missing fields remain unavailable independently.

Import vitals as separate deterministic eligible requests through fleet_telemetry.capture with existing tenant/admin, exact unique VIN and active membership enforcement. Require membership effective at source read time. Preserve original source read in evidence; capture timestamp denotes import, not engine observation. Keep receipt dry-run/commit/replay/readback atomic with diagnostics. Old source documents without vitals retain existing recovery behavior. No canonical vehicle mileage update.

Truck health receives existing truck telemetry from parent detail response. Render odometer and engine hours separately from fault query/loading/error/empty states, preserving zero, provenance and unavailable states. Telemetry retention policy remains unchanged. No new permission or endpoint.

Negative gates: foreign company/tenant/fleet, duplicate/wrong VIN, source outside membership, invalid numeric types/ranges/time, unavailable faults with valid vitals, missing vitals with valid faults, recovery identity drift, duplicate request replay. Independent QA and Security review required before release.
