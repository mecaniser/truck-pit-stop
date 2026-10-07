# DB-036 Motive server worker contract

Backend & Integrations owns this high-risk slice. Additive migration161 is required for minute observation support. No provider activation, scheduler, or live import is implied by the implementation. Independent Security
and QA and deployment acceptance are required before release.

## Input and identity

A private JSON document carries company_label, company_id,
company_verified_before/after=true, complete=true and vehicles. Each row supplies
provider_vehicle_id, unit (display only), exact VIN, status located/unavailable,
sourceReadTime, paired lat/lng, address, sourceAge, rawTimestamp, timezone
America/New_York, precision second/minute. Second precision supplies observed_at;
minute precision supplies observed_minute_start/end (exclusive end), observed_at
null. Credentials never appear in documents or receipts. Unknown source timestamps
must remain unavailable rather than fabricate an observation time.

Explicit MOTIVE_SYNC_TENANT_ID, MOTIVE_SYNC_ACTOR_ID, MOTIVE_COMPANY_LABEL and
MOTIVE_COMPANY_ID are required. Company is verified by the collector before and
after collection. Database checks require active tenant and owner/admin actor,
unique exact VIN and one current tenant fleet membership covering source capture
and observation. Members may belong to different fleet customers; unit numbers
never determine identity. Unmatched source VINs are reported. A matched tenant vehicle with no eligible current fleet membership is reported as outside_current_fleet and never written; multiple current memberships remain a hard ambiguity error. Duplicate source or
ambiguous database identities abort. Unavailable rows retain saved positions.

## Import and ordering

`python -m scripts.motive_sync.runner --input PRIVATE.json --receipt RECEIPT.json`
is a dry-run: invokes the existing capture service, verifies fleet projection,
then rolls back. `--commit` performs that dry-run first, then repeats current
identity and ordering checks in a fresh transaction before committing atomically.
A local exclusive lock prevents overlapping importer processes. A tenant-scoped PostgreSQL advisory lock on a dedicated connection spans dry-run, commit and readback across replicas; the capture
service locks the tenant to serialize database writers. Collector orchestration
must hold its own exclusive process lock during collection and import.

Known older or unchanged observations are skipped. Same-time changed coordinates
are quarantined. Unknown prior timestamps stop replacement unless the current verified observation begins strictly after the prior capture time. Capture files older than 30 minutes are rejected. Unavailable source rows may lack VIN and are reported as vin_unavailable; they never map by unit. Minute intervals are preserved as first-class observed_precision="minute" and
observed_at equal to the interval's UTC minute start. This means [start,start+60s),
not an invented exact second. The raw timestamp, timezone and interval remain in
evidence_note. Minute starts must be aligned and the entire interval must belong
to the membership. A new observation is admitted only when its possible-time
interval is wholly newer than the previous one. Overlapping intervals retain
prior data; identical bounds and coordinates are unchanged.

TelemetryCapture, snapshot storage, capture receipts and ReadingProvenance expose
optional observed_precision="second"|"minute"|null. Omitted/null preserves legacy
semantics and request digests; existing rows are not backfilled. Minute precision
requires observed_at; null observed_at cannot carry a precision. Worker exact
captures continue omitting precision to preserve their previous request IDs.
Capture itself rejects overlapping location intervals when either observation
has minute precision, including later exact timestamps inside a prior minute.
Existing exact-only captures retain their old behavior. Projection carries the
precision and calculates conservative age from minute start (up to59seconds older
than the unknown exact observation). Frontend must identify minute accuracy.

Migration161 adds the nullable observed_precision column and checks supported
values/time presence/minute alignment. Backend and worker must not run against a
pre161 schema. Downgrade refuses to erase precision while minute rows exist,
because doing so would misrepresent interval starts as exact observations.


Request IDs derive from tenant and full immutable payload. Current authorization and membership are rechecked before existing request lookup; immutable capture digests verify equality. Matching committed receipts can be recovered after the 30-minute input freshness window, while unmatched expired input is never written. Replay the SAME private
input after an uncertain outcome. Do not regenerate timestamps or evidence for a
retry. Capture retains its existing immutable request digest check. Receipt files
are mode0600; logs contain only aggregate counts. Source and receipts stay out of
Git. The service source remains motive_dashboard_manual for compatibility, with
motive_server_ui_v1 recorded in evidence_note.

## Acceptance boundaries

A dry-run receipt is not a committed receipt. Board projection is checked before
commit so a superseded or hidden observation aborts the transaction. Committed receipts are reread in a fresh database session and projected again. A concurrent projection change is explicitly reported; a previously superseded replay still recovers its saved receipt. Production release must additionally verify the authenticated fleet map.
Missing provider rows, missing coordinates, unknown timestamps and unmatched VINs
are coverage gaps, never evidence of a complete import. Commit failure preserves
all earlier saved data. No trips, fuel, identity, canonical vehicle, financial or
provider configuration is modified.

## Isolated Railway runtime

Build the repository with `backend/Dockerfile.motive-sync`; start with
`python -m scripts.motive_sync.run_worker`. Configure the dedicated service using
Railway service settings/API, not the legacy railway.json mechanism. Use one
replica, restart policy Never, no cron until runtime acceptance, and a persistent
volume mounted at `/data`. The worker stores private source and receipt files
under `/data/motive-sync/<UTC run time>-<UUID>/` and never serves a public port.

Required secrets are MOTIVE_EMAIL, MOTIVE_PASSWORD and DATABASE_URL (a Railway
reference to the existing application's database variable). App settings also
require SECRET_KEY. Configure tenant/actor/company explicitly as above. Set
MOTIVE_SYNC_STATE_DIR=/data/motive-sync. MOTIVE_SYNC_COMMIT defaults to false;
only the exact string true permits the one-shot worker to save validated data.

The process lock spans collection and import. Failures leave original source
files for recovery; retry an uncertain import with the same file and request IDs.
Do not enable automatic deployment retries to generate replacement evidence.
Rollback is stopping the dedicated service or restoring its prior image; no
schema, web-service deployment, provider activation, or historical deletion is
part of this worker release.

## Runtime acceptance, 2026-10-07

Two full visible directory traversals covered 22 Motive vehicles. The current
DieselBridge fleet contained 21 vehicles: 12 received verified locations across
the two runs, five had no successful capture, and four had no source VIN match.
The runs committed 11 and 10 snapshots respectively (21 observations for 12
unique vehicles). Replaying each original file created zero additional snapshots
and recovered the same request and snapshot IDs. Both saved receipts and board
projection were checked after commit on fresh database sessions.

The live fleet map displayed the imported cities, observation ages and routes.
Unit 8 showed Stallings with an approximately 80-minute-old source observation;
it correctly remained last-known. Unavailable rows retained their prior positions.
The collection has remaining source/reader gaps: missing gateways, unverified
VINs, a legacy timestamp layout, and transient address/UI reads. These are not a
claim of complete or uniformly fresh fleet coverage.

The dedicated service's one-shot acceptance deployment was stopped after receipt
verification. Default commit remains false, restart policy Never, no cron. Source
and receipts are retained privately on the attached volume and in local evidence;
they are intentionally not included in this repository. Hourly activation and PR
merge are separate from this successful one-shot acceptance.
