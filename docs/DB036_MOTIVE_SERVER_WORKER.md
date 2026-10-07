# DB-036 Motive server worker contract

Backend & Integrations owns this high-risk slice. No migration, provider activation,
scheduler, or live import is implied by the implementation. Independent Security
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
never determine identity. Unmatched source VINs are reported, duplicate source or
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
are quarantined. Unknown prior timestamps stop replacement unless the current verified observation begins strictly after the prior capture time. Capture files older than 30 minutes are rejected. Unavailable source rows may lack VIN and are reported as vin_unavailable; they never map by unit. Minute intervals are
preserved in evidence_note without manufacturing seconds. Because existing board
projection prefers exact observed_at over null, a minute-only candidate with an
existing known observation is quarantined as precision_insufficient_for_projection.
No shared projection contract is changed here.

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
