# DB-036 daily Motive trip worker

Owner: Backend & Integrations. High-risk worker lane. Implementation branch:
`codex/motive-trip-worker`. Diagnostics are a separate delivery outcome.

## Acceptance contract

The server opens Motive's rendered dashboard with its configured credentials.
It verifies 77 CARGO LLC / KT8934277 before and after reading, verifies New York
source timezone, and captures the previous two New York calendar days plus today.
Only complete report windows with visible count evidence, or explicit empty
reports, may reach the importer. No private Motive endpoint or extracted browser
session is used.

Provider vehicle IDs map through exact verified VINs to unique current fleet
memberships in the configured tenant. Units are labels, never identity. Unknown
VINs, pre-membership trips, unfinished trips and changed historical records have
explicit exclusion reasons. Neither missing data nor an incomplete report means
zero activity. Arrival times have minute precision; DST ambiguity is rejected.
Existing frozen metrics are retained when the same trip is seen again.

The existing trip service owns all writes. Validate first, apply accepted rows
atomically, require an unchanged replay, commit, and save a receipt with readback.
Persist the normalized input before commit so an uncertain result can be retried
without manufacturing a new source observation. No fuel, coordinates, membership,
financial data or provider activation is changed by this worker.

## Deployment configuration

Separate Railway service: `diesel-bridge-motive-trips`
(`5c9706b7-560c-452b-a2dd-cb6c68f49307`), volume
`6f28bc94-d592-4cbb-a763-2ecf7242ca12`.
Build with `backend/Dockerfile.motive-trips`; start with
`python -m scripts.motive_sync.run_trip_worker`. Mount a private persistent volume
at `/data`. Use one replica and restart policy NEVER. Initial deployment is a
one-shot dry run; schedule only after source and import acceptance.

Required variables use Railway references to the existing authorized Motive
worker, not copied credentials: `MOTIVE_EMAIL`, `MOTIVE_PASSWORD`,
`MOTIVE_SYNC_TENANT_ID`, `MOTIVE_SYNC_ACTOR_ID`, `MOTIVE_COMPANY_LABEL`,
`MOTIVE_COMPANY_ID`, plus the existing approved application/database configuration.
`MOTIVE_TRIPS_COMMIT=false` is the default; `true` enables saving after gates.
`MOTIVE_TRIPS_STATE_DIR=/data/motive-trips` isolates receipts and process lock.
Daily target: 09:00 UTC (04:00 EST / 05:00 EDT); the data window itself always uses
America/New_York, independent of server timezone. The overlap repairs late arrivals
without claiming complete historical coverage.

## Operations and rollback

Each run saves private source checkpoints, normalized input and a receipt under a
unique run directory. Logs contain stage/count summaries, not credentials. A
failed collection must not run the importer. A failed import must not claim a
committed receipt. If commit outcome is uncertain, reconcile the saved input
through the existing idempotent importer before another capture.

Rollback: disable the trip schedule and set `MOTIVE_TRIPS_COMMIT=false`; keep the
volume and receipts. Do not delete already committed trips or alter the separate
hourly location worker. Investigate company/tenant mismatch, source layout drift,
replay conflicts, unexpected coverage loss or repeated authentication failures.

## Evidence

Independent QA/security GO for isolated dry run at `b29f8377`: 18 worker/process,
13 collector and 82 existing trip/history/coverage/batch tests pass. Initial dry-run
deployment `3a188eeb-3eb1-4aa9-9351-ed84cfd4e42c` is building; commit remains false
and no schedule is enabled. [PR480](https://github.com/mecaniser/truck-pit-stop/pull/480).
Pending: live source validation, committed receipt, unchanged repeat, fleet activity
readback, protected CI and final release.

Railway rejected setting a new legacy config-file path. This service uses explicit
service build/start/restart settings. CLI deploy archives exclude the repository
root web-service railway.json, preventing web migration/start commands on this
worker. No source code or dependencies are changed in that release archive.
Local fullstack is unavailable because this worktree has no approved backend
configuration. An existing frontend at 5173 belongs to the location checkout and
is preserved. Isolated tests do not establish production behavior.
