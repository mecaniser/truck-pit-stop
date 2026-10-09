# DB-036 Motive driver records


> Subsequent deployment authorization and database-journal release evidence are tracked in [DB036_DRIVER_RECORD_RELEASE.md](DB036_DRIVER_RECORD_RELEASE.md). The notes below preserve the original implementation-stage evidence.
Accountable owner: Backend & Integrations. High-risk worker lane.
Branch: `codex/motive-driver-records`, base `5fcff895`. Implementation `8004ca30`; [draft PR492](https://github.com/mecaniser/truck-pit-stop/pull/492).
State: implementation and isolated verification; live collection and release gates outstanding.

## User outcome and contract

Current-driver names on the fleet tile, truck header/contact, focused map, and current-driver comparison share a compact three-dash safety indicator. Clicking opens a keyboard-accessible popover with available safety, fuel, coaching, and recent safety-event observations. Historical trip identities are not relabeled. The frontend does not calculate a risk rating from arbitrary thresholds.

See [the contract](DB036_DRIVER_RECORDS_CONTRACT.md). Migration163 adds immutable record/directory captures and a driver assignment revision guard. Reads require the active tenant and fleet membership. The provider driver ID comes from the same directory row as the provider vehicle ID, with exact VIN verification. Local driver names must exactly match the source name before a captured record is shown; shortened/misspelled local names remain unverified. Editing a name/phone, including away and back, invalidates prior observations. A newer complete provider directory suppresses removed or changed assignments, even when its directory is empty.

## Source evidence, 2026-10-09

Read-only signed-in Motive accessibility inspection confirmed:

- Fleet View > Drivers exposes driver summary and vehicle summary links in the same row and an explicit `Showing 22 of 22` footer. One driver was unassigned.
- A driver summary exposes a score with a displayed weekly label, top behavior impacts, last-30-days fuel utilization, active/idle durations, coaching count/status, and ten recent safety events.
- The source's graph `Coaching` label is an annotation, not its risk band.
- Safety > Settings > Performance ranges exposes Fair50–84, Good85–95, Excellent96–100 for this account. These are observations, not defaults: the worker reads and validates the provider's current ranges before and after every collection.
- [Motive's documentation](https://helpcenter.gomotive.com/hc/en-us/articles/6162164321693-Motive-Safety-Score) confirms performance ranges are configurable. A weekly score label does not imply that the scoring lookback is one week; the collector preserves the exact displayed source label.

No live driver records were imported. Chrome DOM scripting repeatedly timed out before dispatch, although accessibility reads/navigation worked. Therefore the new collector's browser extraction selectors have NOT passed an end-to-end live run. The recent-event list is explicitly a summary sample. Historical chart points, deeper reports, videos, license/contact information, and other summary tabs are not claimed collected. Additional metric/history slots in the API are for verified future source extraction.

## Worker operation

Build with `backend/Dockerfile.motive-drivers` from the repository root. It reuses the existing pinned Motive Playwright installation and runs `python -m scripts.motive_drivers.run_worker`. It is a separate worker; existing location/trip/fuel/health schedules are untouched. No scheduler is enabled by this change.

Required configuration, supplied through the approved worker secret mechanism:

- `MOTIVE_EMAIL`, `MOTIVE_PASSWORD` for the normal Motive login.
- `MOTIVE_COMPANY_LABEL`, `MOTIVE_COMPANY_ID`, matched against visible company fields.
- `MOTIVE_SYNC_TENANT_ID`, `MOTIVE_SYNC_ACTOR_ID` (active tenant admin).
- `MOTIVE_DRIVER_FLEET_CUSTOMER_ID` (explicit tenant fleet customer).
- Existing backend database/application configuration.
- `MOTIVE_DRIVER_STATE_DIR`, default `/data/motive-driver`, on a persistent private volume.
- `MOTIVE_DRIVER_COMMIT=false` by default. Set true only for an approved controlled import after source acceptance.

From `backend/`, source collection and rollback-only validation:

```sh
node scripts/motive_drivers/collect.cjs /private/run/source.json
python -m scripts.motive_drivers.runner --input /private/run/source.json --receipt /private/run/receipt.json
```

Use a new private run directory each time. Captured provider data stays in0600 source/attempt/receipt files; never commit it. The importer validates the entire directory and all nested values before writing, rejects changed identities/company/source ranges, and leaves unknowns unknown. It locks the active actor/tenant and VIN/member boundary, stores the directory and eligible captures atomically, checks unchanged replay, then verifies receipt IDs after commit. Pending commit receipts must recover against the exact immutable source before another collection runs. Saved-row counts and visible-current-driver projection counts are separate.

## Verification

- Collector parser/directory tests:9/9, including provider range boundaries/change, zero/missing data, duplicate/incomplete/empty directory, malformed source, and sanitized failures.
- Frontend:73 focused tests, TypeScript and production build pass. New component files pass lint; pre-existing FleetApp lint findings remain unchanged.
- Backend:71 focused schema/service/importer/process tests pass. Independent QA/Security reran71 backend,9 collector and12 UI checks. Independent PostgreSQL full migration chain through163, raw-SQL reassignment trigger, composite tenant FK, empty downgrade/re-upgrade, populated downgrade refusal, atomic importer/replay/readback and empty-directory suppression all pass. A two-session stale-ORM reassignment reproduction correctly rejects the old capture.
- Independent offline QA/Security GO. Release NO-GO until live collector source acceptance and authenticated full-stack evidence. Review found and implementation corrected exact company ID matching, empty-directory collection, sanitized CLI failures, and contradictory terminal-footer acceptance. Gatekeeper did not implement or direct code.
- Synthetic real-component browser: fleet tile and truck detail popovers opened in IAB; Escape restores focus, card navigation stays separate,390px viewport has no horizontal overflow; the compact panel is366px wide and640px tall with12px margins, including a trigger near the bottom. Unknown/stale/zero/error states verified. Screenshots remain private under `output/driver-records/`.

Runtime receipt:2026-10-09, worktree branch at5fcff895 plus uncommitted edits; Vite5173/PID76897 owns this worktree's `frontend/`. HTTP200 and rendered new component verified. No8000 listener or worktree `backend/.env`; old managed-runtime metadata refers to migration147, while this branch requires163. This is an aligned, browser-verified synthetic frontend preview, not authenticated full-stack acceptance. Preview: `http://127.0.0.1:5173/tests/driver-record-preview.html`.

## Required release gates and rollback

1. Complete independent Security/QA, protected CI and review.
2. Run the collector twice with approved credentials, saving disabled. Verify exact company/directory/VIN/provider driver identities, ranges, extracted metrics and explicit source gaps. Resolve local-name identity mismatches through an explicit reviewed mapping or correct current assignment; never fuzzy-match.
3. Apply migration163 through the normal approved release procedure. Deploy web and the separate worker with saving and scheduling disabled.
4. Approve a controlled import; verify receipt/replay IDs, current-driver card/detail in an authenticated browser, reassignment/unavailable behavior, and related service health.
5. Only then approve a daily schedule (daily is sufficient for the displayed summary; Motive scores themselves update weekly). Observe the first scheduled run and retain its receipt.

Rollback signals: wrong identity/company, changed layouts/ranges, incomplete directory, non-idempotent replay, tenant boundary failure, or incorrect visible driver. Stop the new schedule and disable saving first. Preserve immutable evidence. Revert application code if required; migration downgrade refuses to destroy populated observations. No production merge/deploy/schedule activation is included in this implementation request.
