# DB-036 Fleet telemetry independent QA and security

2026-10-01. Independent reviewer did not implement the candidate. Review and
reproductions only; this verification document is the reviewer's sole edit.

## Candidate and verdict

**Offline implementation QA: GO. Application security: GO for the reviewed
offline scope.** No unresolved blocking finding remains from this review.

Candidate: dirty `codex/db036-motive-sandbox` on
`e009acb400e85612009ff3320e9f8dc1435c2f8e`, draft PR443.
Digest of 27 changed/new source, test and configuration files under `backend/`,
`frontend/`, `.github/` (sorted pathname, NUL, contents, NUL; SHA256):
`57b85efd0b85eb62ab74bd900f7ada37a95ad21d418a322aad98a0c9f382199e`.
Material subsequent changes require renewed review.

## Independently executed checks

Backend, using `uv run --python 3.11 --with-requirements requirements-dev.txt
python -m pytest -q --tb=short`, with the dedicated disposable PostgreSQL DSN
configured through `DB036_TEST_DATABASE_URL`:

- `tests/test_db036_fleet_telemetry.py` and
  `tests/test_db036_fleet_telemetry_postgres.py`: final **22 passed**, zero skips.
- Existing `tests/test_db036_motive*.py`: **140 passed**, zero skips, including
  the real PostgreSQL suites. Run together with the first 18 telemetry tests:
  158 passed; the final 22-test telemetry candidate was then rerun separately.
- `tests/test_fleet_board.py` and `tests/test_fleet_board_projection.py`:
  **14 passed**. Run together with the two new PostgreSQL tests: 16 passed.
- Total distinct backend cases checked: **176 passed**. Synthetic fixtures and
  isolated schemas only; no application or production database used.

Frontend, using `npx vitest run`:

- `FleetTelemetry.test.tsx`: 17 passed.
- `FleetBoard.pmSort.test.tsx`: 13 passed.
- `FleetBoard.order-views.test.tsx`: 1 passed.
- `TruckDetailHarden.test.tsx`: 3 passed.
- `FleetApp.return-context.test.tsx`: 3 passed.
- Total: **37 passed**. `git diff --check` also passed.

An additional independent synthetic reproduction created an older known-time
speed of 12, a newer unknown-time speed of 50, and a newer known-time speed of 70
for another simultaneously active company membership. Reading the original
company retained **12**, confirming company filtering before field selection
and known-time precedence. A remote mapped ten days earlier, with fault coverage
nine days earlier and a receipt just now, produced **stale** fault-count provenance
whose observation time equaled coverage, not receipt time.

## Findings returned and verified corrected

1. The map freshness clock recreated its Mapbox instance every 30 seconds,
   discarding pan/zoom/popups. Persistent map lifetime and the focused lifecycle
   regression now pass; board/detail motion also reevaluates as time advances.
2. Capture reloaded the same ORM user object without first preserving the
   authenticated tenant. A tenant reassignment could alter both sides of its
   comparison. The corrected snapshot is verified by a two-session PostgreSQL
   test returning 403 after the user's tenant changes.
3. API board candidates initially omitted the connector's active tenant and
   eligible fleet-company checks. The corrected projection excludes disabled
   companies while preserving independently authorized manual snapshots.
4. Partial historical fault catch-up initially used the current receipt clock
   as a fresh count timestamp. It now uses authoritative coverage; the independent
   historical catch-up reproduction above passes.
5. Database-invalid NUL/surrogate strings and mismatched form length limits were
   corrected. Invalid request values produce safe, no-store validation errors.

## Reviewed boundaries

Reviewed staff roles, authenticated tenant preservation, exact VIN, current
membership and membership replacement, foreign tenant/company denial, original
actor replay authorization, concurrent idempotency, trusted cookie Origin,
response privacy, and exclusion from generic idempotency caching. Captures do not
write canonical mileage, repair status, PM inputs or provider bindings.

The shared projection is attached after company context on board projection,
legacy builder and detail paths. SQL ranks fields independently within selected
memberships and materializes at most six snapshot rows per truck. Source inspection
confirms fixed batch queries without provider requests or a per-truck SQL loop;
the query-count test compares one card to 100 cards. Per-field time/source ranking,
retention, disconnect, virtual/calibrated distinction, real zeros, unknown times,
and timestamped legacy fallback were reviewed.

The UI consumes validated telemetry coordinates, provides an unlocated-truck
list, preserves exact coincident positions, separates reported from service
mileage, uses safe text DOM for map captions and does not send VINs or driver
names in map URLs. The selected truck fixes the displayed board-membership
company; full VIN confirmation and Save are the explicit user confirmation,
as clarified by the accountable owner in the contract.

## Limits and remaining acceptance

Migration154 roundtrip/schema checks, builds/lint and desktop/mobile synthetic
browser interactions are owner evidence recorded in the main verification file;
they were not independently executed here. Mapbox is mocked in automated tests.
No configured-provider basemap/WebGL/network journey was verified, because the
approved map token is absent. Accessible no-token fallback is verified.

Normal authenticated application runtime remains blocked by the missing approved
backend environment. No real dashboard values, VIN worksheets, authenticated
snapshot write, provider call, production database mutation, merge or deployment
is claimed. This offline gate does not approve live activation or production
release. Actual capture identity and consenting-fleet evidence remain separate
from synthetic verification.
