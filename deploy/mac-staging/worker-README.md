# Isolated five-worker acceptance harness

This harness exercises the real PR #611 collectors and supervisors against
synthetic rendered HTML. It is **not live Motive compatibility evidence**.
It must run on the existing `internal: true` Docker network with no published
ports, no host mounts beyond a new private state directory, no production data,
and no real provider credentials. No automatic retries or scheduling here.

## Source and image

`worker-build.sh <repository>` archives exactly
`576ce5a8a2c0bad7b8d33a236e6514bc448e8677`, builds its unchanged
`backend/Dockerfile.motive-trips`, then adds only the fixture preload and staging
launcher. The trips image contains all five unchanged collectors and Chromium.
`worker-build.sh <repository> --context-only` writes a tar context to stdout
for an SSH stream. Compress that stream with `gzip -c` before sending it to
`docker build -f Worker.Dockerfile ... -`; Docker can otherwise mistake macOS
POSIX pax tar stdin for a Dockerfile. The direct build mode handles compression
automatically. Fixture
SHA-256 values are included in `/staging-fixture/fixture-checksums.json`.
The build needs package egress; runtime must have none. Inspect its source label
before using it. No ignored files or local `.env` are copied into the image. macOS resource
metadata is disabled (`COPYFILE_DISABLE=1`) and `._*`/`.DS_Store` excluded.
The exact outgoing archive is checked for AppleDouble entries and NUL bytes in
Python source before either streaming or Docker build.

Example remote build (run in a shell with `pipefail` enabled):

```sh
set -o pipefail
./deploy/mac-staging/worker-build.sh /path/to/worker-repository --context-only |
  gzip -c |
  ssh -i ~/.ssh/dieselbridge_staging_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes sergio@192.168.4.239 \
    '/Applications/Docker.app/Contents/Resources/bin/docker build -f Worker.Dockerfile -t dieselbridge-staging-workers:576ce5a8a2c0bad7b8d33a236e6514bc448e8677 -'
```

The harness supports commands `sync`, `health`, `trips`, `fuel`, `drivers`.
Use architecture's `fixture-*` seed/config scripts for a separate
`dieselbridge_worker_fixture` PostgreSQL database. The existing staging web
DB is not the fixture DB. Run migrations from the pinned worker image on that
new database before seeding. No fixture script changes production settings.

Required environment:

- `ENVIRONMENT=staging`
- `DATABASE_URL=postgresql+asyncpg://<staging-user>:<staging-password>@postgres:5432/dieselbridge_worker_fixture`
- `STAGING_WORKER_FIXTURE=synthetic-v1`
- `MOTIVE_EMAIL=fixture@example.invalid`
- `MOTIVE_PASSWORD=synthetic-not-a-provider-password`
- `MOTIVE_COMPANY_LABEL=77 CARGO LLC`, `MOTIVE_COMPANY_ID=KT8934277`
- Fresh `SECRET_KEY`; `MOTIVE_SYNC_TENANT_ID`, `MOTIVE_SYNC_ACTOR_ID` and
  worker-specific fleet/commit/journal configuration from the private seed manifest.
- `/state` must be a dedicated persistent private writable mount. The launcher
  assigns each worker a separate state subdirectory. Restrict logs and memory.

The company text is required by the existing collector's hardcoded guards; it
is synthetic DOM content. Browser requests are intercepted before any page
exists; only synthetic auth/app HTML is fulfilled. All other requests abort.
Service workers are disabled. Internal Docker networking provides an independent
provider-egress barrier. Do not attach an internet-capable network to workers.

## Fixtures and interpretation

Six vehicles `101..106`, units `FIX-1..6`, VINs
`1M8GDM9AXKP042781..786`, drivers `201..206` named `Synthetic Driver 1..6`.
Architecture seeds two vehicles in each of three independently scoped fleets.

- Location: six fresh stationary coordinate observations.
- Health: six independently verified explicit empty fault-code cards. This
  tests empty captures, not nonzero diagnostic-code projection.
- Trips: six completed trips per requested date, 100 miles each.
- Fuel: six vehicles across normal report dates, 2 driving + 1 idle = 3 gallons.
- Drivers: score 90, 50% utilization, explicit no safety events. Full source is
  shared while normal membership gates determine each fleet's imports.

`fixture-events.jsonl` records browser launches and DOM views/actions only.
Each successful driver batch should launch one browser, not three. Two driver
**directory** reads are expected for before/after consistency. Actual receipts,
database journals and read-model parity still decide success; browser exit or
fixture events alone do not.

## Failure/recovery

A scoped run can set `STAGING_FIXTURE_KILL_MATCH` to a substring of a fixture
event and `STAGING_FIXTURE_KILL_MARKER=/state/<unique-run>.killed`.
The Node process receives SIGKILL once, after recording the marker. The real
supervisor performs its normal child-group cleanup. Examples that kill only
once at a later task:

- sync: `/102/live`
- health: `"event":"fault_card","id":"102"`
- fuel: `vehicle_ids=102`
- drivers: `/drivers/summary/202`
- trips: `start_date=<second requested date>`

Inspect persisted task 1, record its timestamp/hash and event read count, then
restart the **same worker and same state mount** within 30 minutes. Assert the
same source/task checkpoint is resumed, prior timestamps unchanged, task 1's
payload read not repeated, source complete and normal committed receipt or
journal parity verified. Fresh identity/directory reads are expected on resume.
A different private state directory is needed for independent scenarios.

`STAGING_FIXTURE_VARIANT=wrong-company` renders a company mismatch and must fail
before imports. `wrong-vin` changes summary VIN identity and must not create
forbidden captures. These variants only modify synthetic browser HTML, never
collector or import code. Database-level tenant, incomplete-source and replay
negative checks belong in the separate fixture verifier.

Not yet covered by the DOM shim: drift in live provider DOM, actual provider
rate limits/authentication, nonempty health faults, or real provider credentials. Record those limitations separately;
do not describe this harness as live-provider end-to-end testing.

## Three-fleet committed journal recovery

Use a fresh private state mount for this scenario. Retain the existing isolated
fixture DB and record its pre-probe journal/capture IDs and counts; do not
reset previously verified evidence. Run the worker with **`docker run --init`**
so Python is not PID 1. Linux PID-namespace init has special signal protection;
a self-SIGKILL request at PID 1 may return without terminating the process.
The launcher refuses the optional probe at PID 1 before importing worker code.
Set
`STAGING_DRIVER_KILL_AFTER_FIRST_VERIFIED=true` only on the `drivers` command,
with database journaling and commit enabled. The staging launcher wraps the real
`DurableRun.checkpoint` method: it awaits the unchanged method and its committed
transaction, then writes/fsyncs a private marker and SIGKILLs the Python process
only after the primary fleet reaches `verified` with `committed=true`. The
marker and log mean **kill requested**, not kill proven. Require container
exit **137**, then inspect the DB before any restart. If self-SIGKILL returns,
the launcher exits 70 and reports failure instead of projecting more fleets.

Inspect the DB: first fleet must be verified, remaining two durable sources
saved, and all three share the same source hash. Save first-fleet capture IDs
and counts. Restart exactly once with the same state mount/configuration. The
marker prevents a second injection. Require the actual `fleet_recovery_complete`
log, all three verified journal rows, unchanged first-fleet capture IDs/counts,
read-model parity and no new browser-launch event. This is a real process kill
around unchanged DB/import code, not a fabricated journal or mocked receipt.
Use `--init` for the recovery invocation too. Compare only the new batch
against the saved pre-probe DB baseline; prior fully verified batches remain
untouched. The optional launcher hook itself still needs staging runtime
acceptance. See [Linux PID namespace init signal rules](https://www.man7.org/linux/man-pages/man7/pid_namespaces.7.html).
