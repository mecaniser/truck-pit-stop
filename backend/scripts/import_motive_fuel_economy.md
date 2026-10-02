# Motive summary MPG import

Requires deployed migration `157_fleet_fuel_economy` and application code. Run from
`backend` using the intended environment's approved connection configuration.
Do not copy database secrets or source data into Git.

Input JSON has `period: "last_30_days"` and a nonempty `rows` array. Each row requires
`unit`, `provider_vehicle_id`, full `vin`, `fuel_economy_mpg`, and timezone-aware
`source_read_at`. Capture the **Average MPG / This vehicle / Last 30 days** summary;
do not use the chart's latest point. Missing MPG means omit that truck, not zero.

```sh
python -m scripts.import_motive_fuel_economy --input /private/path/readings.json --tenant-id TENANT_UUID --actor-id ACTOR_UUID
```

Review the dry-run JSON plan, then repeat with `--apply` only for the authorized
target environment. The actor must be the authorized active owner/admin in that
tenant. Every VIN must uniquely match an active truck and fleet membership.
Ambiguity aborts the entire batch. No canonical mileage, PM target, or prior
snapshot is changed. Snapshot observation time stays unset: the browser read time
is evidence, not a device observation time.

The importer verifies persisted snapshot fields, board projection, and unchanged
existing vehicle and snapshot rows before a single commit. Any failure rolls back
the batch. Re-running the same source reads is idempotent; changed MPG under the
same request conflicts. Receipts distinguish stored from currently visible MPG.
After successful apply, verify live truck details' MPG and reporting period.
Keep the JSON receipt with the private source file. Dry runs create no snapshots.
