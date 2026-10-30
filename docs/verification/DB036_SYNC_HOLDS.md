# DB-036 sync held readings — October 30, 2026

Architecture & Backend contract; Backend & Integrations accountable. Live affected-truck evidence and release acceptance are owned separately by the release lead. Codex automations remain off.

## Scope and equivalence contract

The location importer currently loads the newest 1,001 location snapshots from the admissible capture window and holds a reading when more than 1,000 exist. Strictly earlier known observation intervals cannot affect `disposition`: they only take its `continue` branch. Counting such rows toward the bound can therefore prevent an admissible new reading.

For a timestamped incoming location only, filter out known old intervals before applying the existing 1,001-row bound:

- An exact/second observation at or after incoming interval start remains relevant.
- A minute observation remains relevant while its half-open interval overlaps incoming start: strictly later than start minus one minute. A minute ending exactly at incoming start is safely earlier.
- Every row whose `observed_at` is unknown stays relevant. Location disposition may recover a legacy interval from its evidence note; captured time alone must not discard this evidence. Unknown incoming source time retains the original full-history query and guard.
- Canonical fallback must continue to use original-scope history emptiness. If the filtered query is empty for timestamped source with canonical coordinates, an original-scope EXISTS check distinguishes genuinely absent history from safely omitted known old history.
- Keep all later observations, genuine overlaps/conflicts, the original 30-day capture-window rule, canonical unknown-position fallback, source freshness, 1,001 bound and overflow behavior, tenant/vehicle/membership filters, locks, saved request identity, subset replay and immutable append-only capture semantics.

No timestamp, location, VIN, membership or historical row will be invented, backdated, deleted or overwritten. This change does not repair genuinely ambiguous source time or missing current membership. No schema/API/migration change.

## Acceptance cases

Actual database queries must prove: more than 1,000 strictly earlier exact/minute locations no longer block a safe timestamped update; more than 1,000 overlapping/later/unknown intervals still hold; minute boundary is half-open; all unknown observed times remain eligible even with old capture times and legacy future evidence; unknown incoming precision remains guarded; single overlapping/conflicting/later/unknown observation retains its disposition; tenant/member scopes remain unchanged; saved rows and request keys replay without duplicates and canonical vehicle fields stay unchanged.

Local controller dry-run reports missing approved `backend/.env` and Vite, with no local listeners/services/secrets changed. Synthetic SQLite fixtures apply; local product runtime/browser verification is unavailable. Independent QA/Security, protected CI and natural production source/receipt/persisted-value acceptance remain required before release completion.

## Owner implementation and synthetic verification

The original location query scope is factored without changing any tenant, vehicle, membership, deleted-row, coordinate or 30-day condition. Only timestamped input adds `relevant_location_history(start)` before the original limit. When filtering leaves no history and canonical coordinates exist, an EXISTS query over the unchanged original scope preserves canonical-fallback semantics. Unknown incoming timestamps still use the original full bounded query.

**107 focused Python tests passed**, zero skipped, across location-history regressions, existing importer, timestamp precision and reviewed bindings. New actual SQLite/import regressions cover 1,001 old exact/second/minute rows, relevant overflow, retained unknown/legacy future notes, half-open minute edges, conflicts/later observations, original-empty canonical fallback, outside-window canonical fallback, tenant/member isolation, preserved immutable historical columns, exact-source replay, later-read same-observation no-op, and a pre-existing speed-only snapshot receiving one immutable location-only supplement followed by replay.

Command:

```sh
uv run --no-project --python 3.11 --with-requirements backend/requirements.txt --with pytest --with pytest-asyncio python -m pytest -q backend/tests/test_motive_sync_location_history.py backend/tests/test_motive_sync_import.py backend/tests/test_db036_telemetry_precision.py backend/tests/test_dashboard_vehicle_bindings.py
```

Changed Python passes Ruff `F,E9`, Ruff formatting and compilation; `git diff --check` passes. Initial dependency resolution on the host's default Python 3.14 could not build pinned production-era dependencies; verification used the available production-matching Python 3.11 without changing dependency pins or production settings. Independent QA/Security, CI, deployment and concrete natural receipt acceptance are still pending. No production write, capture, membership change or automation was performed by the implementation owner.
