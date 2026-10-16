# DB-036 current speed: independent QA and Security gate

Reviewed 2026-10-16 UTC (2026-10-15 EDT) by `independent_speed_gate`, a fresh
reviewer with no implementation participation. Backend & Integrations remains
accountable. This review changed only this evidence document.

**Implementation QA: GO. Security: GO.** The initial history-bound finding was
returned to the backend owner, corrected, and independently retested. No open
implementation finding remains. Protected CI, deployment, fresh production
worker receipts and production browser acceptance remain release gates; this
document does not claim those gates have passed.

Reviewed branch: `codex/motive-current-speed-coverage`.
Base: `70530bda5705b30e27c3f222421b77e9e7ce6341`.
SHA-256 of `git diff --binary -- .github/workflows/quality.yml backend frontend`
at review:
`8b82edd8c0bcee6c7e63d0ed7ea3573293b79b81cb9efe1c54d378e37748be44`.
The contract is [DB-036 current speed](../contracts/db036-current-speed.md).

## Independent verification

| Command or scope | Result |
| --- | --- |
| `node --test backend/scripts/motive_sync/collector.test.cjs backend/scripts/motive_drivers/collect.test.cjs` | 48 tests passed, plus the collector's 12 legacy assertions |
| `pytest -q tests/test_motive_sync_import.py tests/test_db036_telemetry_precision.py tests/test_db036_fleet_telemetry.py` | 80 passed after the history-bound correction |
| `pytest -q tests/test_db036_fleet_telemetry_postgres.py` | 4 passed against disposable local PostgreSQL, no skips |
| `vitest run` for `FleetTelemetry`, `TruckTelemetry`, `MotiveIntegration`, and `TruckDetailHarden` | 76 passed |
| Full changed-source review and `git diff --check` | Passed |

Backend tests used `/tmp/db128-backend-venv`. PostgreSQL was the existing
loopback-only `db036-health-test-pg` test database; each test created and removed
its own schema. The test credential was passed in process environment without
printing it. No production reads or writes, browser control, commits, or
deployment were performed by this reviewer. Existing dependency deprecation and
React test warnings did not fail the focused suites.

## Boundaries checked

- Speed is read only from the unique visible Live vehicle location panel. The
  collector requires an explicit bounded mph value and a verified source time;
  missing or changing speed does not become zero or inherit capture time.
  Provider route, VIN, coordinate and observation stability checks remain.
- Driver VIN recovery retries only null reads, at most three fresh documents.
  Any non-null mismatch fails immediately. Persistent null verification fails
  the whole collection with a distinct bounded reason. Complete-directory and
  before/after account/assignment verification still gate import.
- Exact tenant VIN and current fleet membership validation remain before
  writes. The actor is reloaded and authorized; source capture and full minute
  observation must belong to the membership. No fleet remapping is introduced.
- Speed and location are planned independently. Same-minute speed-only
  supplements preserve the original location, legacy request IDs, immutable
  replay, and complete request-digest checking. Both written fields are checked
  after capture and again on a fresh connection after commit.
- Tenant serialization protects concurrent replay and minute-speed conflicts.
  Field-specific interval checks preserve location-only coexistence and legacy
  exact-time manual capture semantics. The PostgreSQL race tests exercise actual
  locking, rather than relying on SQLite.
- Cards and details share the current-speed selector with motion classification.
  Twelve-day-old, capture-only, invalid, wrong-source and out-of-range speed is
  unavailable. Fresh zero remains zero. Five-minute boundaries and open-view
  expiry are covered, including closing a stale speed tooltip.

## Closed finding

The initial speed-history query counted every lifetime snapshot toward its
1,000-row limit. Old disjoint readings could eventually stop otherwise valid
updates. The corrected query counts only history that can hold the incoming
observation: overlapping/later known intervals and unknown-time captures not
provably earlier. It does not rely on scheduled purge. Six 1,001-row regressions
prove that old exact/minute/unknown history permits advancement while relevant
exact/minute/unknown history still fails closed. Review confirmed the half-open
minute boundary and preservation of missing capture-time holds.

## Release handoff

Parent-owned browser and source-coverage evidence is separate. Require a fresh
timestamped speed observation captured, imported and replayed by the deployed
worker; a successful job with no trustworthy speed is insufficient. Confirm
desktop and compact production views suppress old speed, preserve independent
location age and expire open current readings. Retain the contract's rollback
signals for identity, replay, interval or projection failure. Do not mark the
delivery board Done until those release receipts and protected CI exist.
