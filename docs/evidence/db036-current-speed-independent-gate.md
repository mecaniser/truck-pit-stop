# DB-036 current speed: independent QA and Security gate

Reviewed 2026-10-16 UTC (2026-10-15 EDT) by `independent_speed_gate`, a fresh
reviewer with no implementation participation. Backend & Integrations remains
accountable. This review changed only this evidence document.

**Implementation QA: GO. Security: GO.** The initial history-bound finding was
returned to the backend owner, corrected, and independently retested. No open
implementation finding remains. The subsequent backend/worker release review
below closes CI, deployment and production data gates. The final authenticated
production browser review below also closes the desktop and compact UI gate.

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
printing it. During the implementation review, no production reads or writes,
browser control, commits, or deployment were performed by this reviewer.
Existing dependency deprecation and
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

## Backend and worker release review — 2026-10-16 UTC

**Backend/worker release gate: GO. Authenticated production UI gate: pending.**
This follow-up independently inspected the saved source, receipt, runtime-hash,
cron-log, journal, coverage and preservation evidence. Read-only GitHub and
Railway queries confirmed six successful CI jobs in run `38844297984` at
`5b1070c5`, and SUCCESS for Web `c7eaef64`, app worker `6f0be5e5`, driver
`8bfb34f4` and location `0d3efd78`. Merged `e3ff99e0` has identical backend,
frontend and workflow trees to the reviewed head. All 14 runtime file-hash
checks match the merged source. Public readiness returned HTTP 200 with database
and Redis healthy at 04:36:20 UTC.

- Controlled deployed import: ten created observations and ten identical
  replays; source hash, request IDs, snapshot IDs and capture times match.
  Saved-receipt and projection checks passed; replay created no rows and kept
  the content fingerprint unchanged. Seven readbacks were within five minutes.
- Location execution `e90c6427` exited successfully at 04:19:12 UTC. It collected
  22 vehicles/18 locations and committed nine distinct request/snapshot rows,
  including eight numeric speeds aged 70–250 seconds at commit. No projection
  failure appeared in the committed outcomes.
- Driver execution `12659a0e` exited at 04:27:25 UTC with `fleets_complete` for
  all three configured fleets. All three durable journals are complete,
  committed and verified. Saved/readback/replay/projection counts are 18, 1
  and 1, with zero unverified assignments. Each source directory contains all
  22 rows. Final readback at 04:33:53 UTC has 20 available, non-stale records
  checked on October 16, including truck 532, and 15 numeric scores. Trucks
  26 and 70 retain the explicit `no_capture` reason.
- Preservation at 04:33:50 UTC, after the third fleet commit, matches all four
  pre-canary fingerprints: vehicle identity/contact data, memberships,
  outside-scope driver captures and outside-scope directory captures.

No unresolved backend release defect remains in the reviewed evidence. This is
successful current canary evidence, not a claim that earlier failed daily runs
succeeded or that future scheduled runs have already occurred. The production
browser session expired, so desktop/compact fleet acceptance remains open.
Keep DB-036 out of Done until that separate gate passes. See the
[release receipt](../verification/DB036_CURRENT_SPEED_RELEASE.md) for deployment
identities, preserved schedules/storage and remaining source-data gaps.

## Authenticated production UI release review — 2026-10-16 UTC

**Authenticated production UI gate: GO.** This reviewer independently inspected
the parent-operated browser's saved screenshots, full DOM snapshots and timing
receipts in the private `production-ui-2026-10-16` evidence directory. No browser
control, production mutation or application edit was performed by this reviewer.
The earlier sign-in blocker is resolved. This covers desktop 1280×900 and compact
390×844 browser viewports, not a physical-device claim.

Read-only deployment and GitHub comparison confirmed current Web deployment
`582d69ad-3fec-4103-8297-46c9ae245763` at `d5cb6628`, a descendant of the reviewed
merge `e3ff99e0`. The intervening PR549 does not change frontend, telemetry or
Motive collector files. The reviewed worker deployment remains `0d3efd78`.

- Fleet cards, truck details and the selected map truck retain driver scores
  on both viewport sizes. The saved board has 22 trucks, 21 score buttons,
  15 numeric scores and six explicit unavailable scores. The latter includes
  the local alias for truck 26; truck 70 has no assigned driver button.
  W900 displays score 88 without its historical 10 mph reading. The inspected
  surfaces contain no internal “Local contact” or “Assigned contact” label.
- Driver popovers are readable on all six card/detail/map and desktop/compact
  combinations. The saved interaction evidence covers internal scrolling,
  close and Escape. The corrected full snapshots and screenshots confirm truck
  532 was checked October 16 and explicitly reports an unavailable provider
  score, while truck 609 remains in Elis Logistics with score 81.
- Fresh source evidence is visible in production: truck 860 shows 51 mph on
  desktop and compact cards/details, observed around 13:25 UTC and captured
  13:25:50 UTC. Its detail reports moving. The full fresh board also contains
  five explicit 0 mph readings; missing speed has not been substituted with zero.
- Open-view expiry passed without a reload or intervening UI interaction:
  `expiry-before` at 13:28:52.312 UTC shows 51 mph and moving;
  `expiry-after` at 13:30:39.847 UTC shows Unavailable and motion unknown.
  The subsequent compact card likewise suppresses the expired speed.
- Main FleetMap pins and labels represent the operational truck status and
  location age, not speed-based motion. Source review confirms its independent
  recent-position boundary is 15 minutes. Fresh and last-known map screenshots
  are consistent with that rule. Five-minute speed motion applies to card dots
  and truck-detail dots/footer; no map movement class is expected.

The authorized off-schedule refresh `e223df0d` independently reached EXITED at
13:25:56.214 UTC. Structured logs show one execution instance, a complete
22-vehicle collection with 17 source locations, 12 committed update outcomes,
and `worker_complete`, without an error or projection-failure outcome. The two
preceding scheduled location executions also exited successfully. These are
timestamped successful runs, not a guarantee of future runs or continuous live
telemetry; the existing hourly schedule remains the refresh cadence.

No unresolved implementation, security, backend release or reviewed UI defect
remains. Provider gaps for trucks 26/70 and the five records without numeric
scores remain explicit in the release receipt and are not masked by invented
values. The delivery owner may close DB-036 with this UI evidence and the prior
backend release receipts.
