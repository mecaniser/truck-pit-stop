# Synthetic worker database fixtures

Owner: Backend & Integrations. These scripts never connect to the existing
`dieselbridge_staging` database. They require `ENVIRONMENT=staging`, host
`postgres`, and database **`dieselbridge_worker_fixture`** through PostgreSQL.
External WorkOS/Motive API flags must remain disabled. Provider login values,
if present, must exactly match `fixture@example.invalid` and
`synthetic-not-a-provider-password`. No Railway credential belongs here.

The deployment owner creates the separate database on the isolated PostgreSQL
service, sets only that database URL in a worker-only environment, then migrates
it with the pinned worker source's `alembic upgrade head`. Seed does not create,
migrate, drop or reset a database. Do not attach this URL to the normal staging
web service. Run only after the reboot owner clears remote work.

Run inside the pinned PR611 worker image, with these scripts mounted read-only
and `PYTHONPATH=/app`:

```sh
python /fixtures/fixture-seed.py --manifest /data/fixture-manifest.json
```

Seed refuses populated tenant/user/customer/vehicle/membership tables. It creates
a synthetic operating tenant/owner, three fleets with two exact-VIN vehicles each,
and a second tenant/owner/customer as an isolation sentinel. The manifest has
fixed deterministic synthetic IDs and an `environment` object containing only
worker identity/commit settings and dummy browser credentials, not a database URL
or private provider secret. The private output directory must be mode 0700.

Final shared DOM/database identities:

| Provider | Unit | VIN | Driver |
|---|---|---|---|
| 101 | FIX-1 | 1M8GDM9AXKP042781 | 201 / Synthetic Driver 1 |
| 102 | FIX-2 | 1M8GDM9AXKP042782 | 202 / Synthetic Driver 2 |
| 103 | FIX-3 | 1M8GDM9AXKP042783 | 203 / Synthetic Driver 3 |
| 104 | FIX-4 | 1M8GDM9AXKP042784 | 204 / Synthetic Driver 4 |
| 105 | FIX-5 | 1M8GDM9AXKP042785 | 205 / Synthetic Driver 5 |
| 106 | FIX-6 | 1M8GDM9AXKP042786 | 206 / Synthetic Driver 6 |

The rendered company `77 CARGO LLC` / `KT8934277` is the existing collector's
constant used in a fabricated page; no customer account/session is accessed.
Current memberships and initial assignments begin seven days before seeding.
No reviewed no-VIN binding is needed or created: genuine synthetic VINs take the
normal exact-VIN path. No binding allowlist, auth guard or membership guard changes.

Use actual worker commands, injecting the manifest environment and persistent
private state directories. Driver entry point is `scripts.motive_drivers.run_fleets`
so all three configured fleet journals participate. Other entry points:
`scripts.motive_sync.run_worker`, `scripts.motive_sync.run_fuel_worker`,
`scripts.motive_sync.run_trip_worker`, `scripts.motive_health.run_worker`.
The worker owner supplies the staging-only DOM interceptor and orchestration;
these DB scripts do not fabricate collector output.

After a worker succeeds, verify its exact private source and receipt:

```sh
python /fixtures/fixture-verify.py --kind location \
  --manifest /data/fixture-manifest.json \
  --source /data/location/RUN/source.json \
  --receipt /data/location/RUN/receipt.json
```

Kinds are `location`, `health`, `fuel`, `trips`, `drivers`. Drivers omit `--receipt`:
three independent verified DB journal rows must match the exact source hash.
Trip verification also reads the immutable `receipt.json.normalized.json` file.
Verification runs a read-only DB transaction; it compares source identities and
values with real stored captures and available current read-model projections.
It requires committed/verified receipts, each expected current membership,
unchanged canonical VIN/mileage, and zero captures belonging to other tenants.
For fuel/trips, the immutable DB models are checked with their normal digest
validators. It prints only a bounded parity result and source hash.

This verifies synthetic collection/import persistence. Browser fixture request
counts, interruption/restart recovery, a single driver collection, retry limits,
negative auth/identity cases and reboot/schedule monitoring need separate harness
evidence. Neither these scripts nor successful synthetic receipts establish live
Motive or Railway production acceptance.
