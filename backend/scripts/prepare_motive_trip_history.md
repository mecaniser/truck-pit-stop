# Prepare Motive browser history offline

This standard-library-only CLI converts captured rendered Trips table rows into
private input batches for the existing `import_motive_trips` command. It neither
logs into Motive nor writes a database. The browser collector owns source UI
navigation and the import operator separately owns dry run/apply receipts.

```sh
python3 backend/scripts/prepare_motive_trip_history.py \
  --input /private/capture.json \
  --mapping /private/reviewed-vehicles.json \
  --prior /private/previous-normalized-rows.json \
  --output-dir /private/new-preparation-run
```

Omit `--prior` for a first capture. Output directory must not already exist. It
is created mode 0700, containing `report.json` and `batch-0001.json` etc. mode
0600. Each batch has at most 1,000 rows. No accepted rows produces only a report.
Quarantined source rows are identified by window/row index with reasons; keep
the original capture alongside this report to investigate them.

## Input contracts

Capture document:

```json
{"tenant_id":"TENANT_UUID","company_label":"Example Fleet","windows":[{"start":"2026-09-28","end":"2026-09-28","source_read_at":"2026-10-03T19:00:00+00:00","status":"captured","rows":[{"cells":["","09/28/2026 09:00 AM\nExample City, NC","09/28/2026 10:00 AM\nOther City, NC","40.25\n1h 0m 0s"],"links":["/vehicles/123"]}]}]}
```

`captured` asserts the browser exhausted that exact source filter. `empty`
requires an explicit completed empty-source result and no rows. `partial` means
there was no definitive terminal result; its rows are quarantined and its
window must be recaptured. No state implies globally complete fleet history.
Only April 1, 2026 onward and nonfuture dates/read timestamps are accepted.
The current source adapter expects confirmed America/New_York display time.
Ambiguous/nonexistent DST timestamps are quarantined, never guessed.

Mapping document (reviewed from source VIN and current DieselBridge membership):

```json
{"tenant_id":"TENANT_UUID","company_label":"Example Fleet","vehicles":[{"provider_vehicle_id":"123","vin":"1M8GDM9AXKP042788","unit":"101","effective_from":"2026-07-22T20:13:45+00:00"}]}
```

The capture tenant/company must match mapping exactly. Duplicate provider IDs or
VINs reject the document. Unknown providers and premembership departures are
quarantined. The database importer rechecks live tenant, actor, VIN and membership
bounds; this offline mapping never grants access by itself.

Optional prior input is `{"rows":[...]}` containing complete previously accepted
TripImport payloads from committed receipts. Identical core observations retain
all prior frozen fields (including fuel metrics and source-read timestamp).
Changed core data is quarantined rather than overwritten. New rows have null
metrics/stops. Distinct source versions sharing provider+departure invalidate
that identity for the whole run. Do not treat a locally prepared file as proof
that a database import committed.

## Import and verification

Review `report.json`, dry-run every generated batch with the existing importer,
then use its authorized `--apply` path. Save committed receipts before advancing
collector import checkpoints. Replay must be unchanged. See
`import_motive_trips.md` and `docs/verification/DB036_HISTORY_COLLECTOR_CONTRACT.md`.

Pure offline tests (no services or database):

```sh
python3 -m unittest discover -s backend/tests -p test_motive_history_preparation.py -v
```
