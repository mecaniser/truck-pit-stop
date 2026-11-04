# DB-036 Elis health collection correction

Backend & Integrations accountable. Branch `codex/elis-health-vitals`, base
`d25c7743`. User authorized verifying603/609 VIN mappings and fixing collection
on the existing correct Elis records.

## Verified diagnosis

Read-only production transactions establish both physical vehicles are owned by
Elis Logistics LLC (DBN) in the same Truck Pit Stop tenant. Each has exactly one
nondeleted matching VIN in that tenant; saved Motive diagnostics contain that exact
VIN. Provider identities are distinct.603 has a dated77Cargo operating membership
and fresh mileage/engine hours on the same Elis-owned vehicle.609's current fleet
membership is Elis; it has matching fault capture but zero telemetry rows with
mileage or engine hours. Current health worker environment pins77Cargo. Earlier
fault captures for609 therefore do not prove current vitals import eligibility.
A separate603 in another tenant has a different VIN and is unrelated. No ownership,
operator, payer, membership or canonical mileage correction is needed for this fix.

## Contract and verification

Independent Architecture approved [reviewed target exceptions](../DB036_REVIEWED_HEALTH_TARGETS_CONTRACT.md).
Keep the default fleet pin and add only the verified609 provider/vehicle/customer
target. No schema, public API, frontend or provider-account change.

-80 focused/adjacent backend tests pass: health targets, diagnostics, worker and
telemetry.17 new target cases cover successful scoped exception, default-fleet
regression, unavailable faults, zero hours, unreviewed exclusion, source-missing
scope, wrong vehicle/customer/VIN/tenant, deleted target, duplicate membership,
source before membership, mapping drift/removal and legacy receipt recovery.
-37 collector/login tests pass after installing the existing locked Playwright
dependencies and supplying its module path. Initial local invocation lacked that
module path; no source correction was necessary.
-Changed-source Ruff and diff integrity pass.
-Fresh independent QA GO:80 tests plus3 independent probes for diagnostic-only
target, unavailable-fault VIN drift and membership-replacement recovery.
-Fresh independent Security GO:59 tests, noP0/P1/P2 findings.

Both independent reviewers attested identical SHA256 source:

```text
targets.py       39883ff2c2c14a8fa3685ad7c61f6e2eccf7e9e2a4c510958525c37a69b7b2ca
import_health.py bc92d801831b9d341ce79d540c199e4a7d18f5169b2df6bc478e2b7a3b501de0
runner.py        350af10d19359dbd556bd64948bce7f7d0a3824c6450b06e7f324a531d9cb58f
```

## Runtime and rollout gates

Local runtime preflight ran on2026-11-04: shared5173 belongs to the portal-task-first
checkout and8000 mounts privacy-safety backend. This checkout lacks approved
`backend/.env`; controller dry-run refuses startup. Shared services were preserved.
No claim of aligned local full-stack browser acceptance. A dedicated signed-in
production tab reproduces609's unavailable fields on the correct Elis header.

Before enabling target configuration, inspect/reconcile pending old-scope receipts.
The stopped cron container cannot be SSH-inspected between runs; retain old scope
for the first new-code run, inspect while running and require verified completion
before enabling609 and taking one fresh canary. Preserve cron, volume, default pin
and all other worker services. Do not recover an old attempt under expanded scope.

PR/CI, deploy source attestation, fresh source/VIN/readback, exact service-odometer
preservation and signed-in production health-panel acceptance remain release gates.
Rollback: stop new captures or remove only the reviewed target config after all
pending attempts are reconciled with their exact mapping; preserve imported
append-only captures and all source/receipt evidence. Never rewrite existing
attempts to force recovery under a different scope.
