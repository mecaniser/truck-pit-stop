# DB-036 truck 9 prospective membership — October 30, 2026

Backend & Integrations accountable. The human authorized enrolling the exact Motive truck 9 in 77 CARGO prospectively from the time of the operation. This approval does not authorize historical membership, a new VIN, owner/default-payer changes, or promotion of old telemetry.

## Worker interval contract

Current fleet membership and coverage of an older source reading are different facts. After a prospective enrollment, a current member may legitimately retain an older Motive reading. The location importer must classify only these two known ineligible intervals per row, continue the batch and preserve other eligible truck updates:

- `outside_membership_interval` / `source_capture_outside_membership` when the membership does not cover the source capture timestamp.
- `outside_membership_interval` / `observation_outside_membership` when it does not cover the full known source observation interval (including the existing half-open minute-end policy).

Both classifications include the resolved vehicle and current membership IDs, create no snapshot and do not weaken genuine VIN/binding, unique membership, tenant/admin, source completion, source timestamp, or binding-interval validation. These guards remain fatal when they were fatal before. A future fully covered genuine observation may append one immutable snapshot; exact-source replay and same-observation/later-read must not duplicate it. The prior query-bound fix is unchanged.

## Guarded operation contract (root owns execution)

Deploy and independently verify the worker interval handling before enrollment. Resolve the exact source VIN to one active tenant vehicle 9, verify the exact source company/provider and fresh complete source/receipt (age 0–30 minutes), the fleet-enabled 77 CARGO customer and authorized same-tenant owner/admin. Vehicle customer ownership compatibility alone is not operating authority; the new human approval supplies prospective authority.

Under one transaction, lock tenant, actor, exact vehicle and customer; serialize against the collector's tenant advisory lock. Recheck zero memberships including deleted/history and zero operator records for this vehicle; abort on any unreviewed discrepancy. Freeze the exact vehicle/canonical fields, all existing memberships/relationships and immutable snapshot cohort before writing. Do not call `ensure_fleet_membership`, which can alter operators/default payers.

Create exactly one `FleetMembership` and exactly one `operator` relationship for the approved customer, using direct membership construction and `ensure_vehicle_relationship(..., relationship_type='operator', is_primary=False)` only. Assign both newly created `effective_from` values the same server clock timestamp obtained after locks and checks. Do not change existing rows, VIN, Vehicle.customer_id, canonical coordinates, owner or default-payer roles, billing/default payer, feature flags or credentials. Flush and commit atomically, then fresh-session readback verifies exact saved IDs, interval, scope and unchanged frozen projections.

Use one immutable, private, hash-pinned operation intent with exact IDs/source hashes and approval note. Put a deterministic intent token in only the two new notes. If outcome is ambiguous, read back those exact IDs/token and verify both rows from the same committed interval; do not issue another enrollment. Recovery of this exact committed intent may inspect old evidence without pretending it is fresh. A missing/partial/mismatched outcome remains blocked rather than retried blindly.

Future collections may import only source/observation intervals fully covered by this prospective interval. Historical truck-9 readings stay excluded. Codex automations stay off; no start solely for SSH, schedule or restart-policy changes.

## Local verification boundary

The mandatory local controller dry-run reports missing approved backend `.env` and Vite; no listeners, services or secrets were changed. Synthetic database/import fixtures verify source behavior. Independent QA/Security, protected CI, deployment-byte/configuration parity and exact production receipts are required before release acceptance. This document is a contract, not evidence that enrollment has happened.

## Owner source verification

**112 focused Python tests passed**, zero skipped, covering the new interval batch cases plus all prior importer, history-bound, reviewed-binding and precision regressions. Actual SQLite/import fixtures verify that old source capture, old observation, a minute straddling enrollment and a minute ending outside membership produce no truck-9 snapshot while another fleet truck commits. The first fully covered known reading appends exactly one snapshot; exact-source replay and identical observation with a later source-read time do not duplicate it. The old reading remains held after the new reading is accepted. VIN/customer/canonical fields, membership start and earlier snapshots remain unchanged.

```sh
uv run --no-project --python 3.11 --with-requirements backend/requirements.txt --with pytest --with pytest-asyncio python -m pytest -q backend/tests/test_motive_sync_membership_intervals.py backend/tests/test_motive_sync_import.py backend/tests/test_motive_sync_location_history.py backend/tests/test_dashboard_vehicle_bindings.py backend/tests/test_db036_telemetry_precision.py
```

Only the two interval error branches and their receipt provenance change in production code. Fatal tenant, identity, ambiguous membership, source timestamp and reviewed-binding guards remain unchanged. Ruff `F,E9`, formatting, compilation and diff checks pass. Independent QA/Security, protected CI, exact deployed bytes and the root-owned authorized enrollment/runtime acceptance are pending. No production enrollment, capture or automation was performed by the implementation owner.
