# DB-036 Trips independent QA / security review

Reviewer: independent `trips_review` agent, 2026-10-02.
Branch: `codex/fleet-trips`. Implementation files were not edited by this reviewer.

## Backend and security: GO

- Independently ran `backend/tests/test_db036_trips.py`: **21 passed**.
- Added and ran seven independent assertions under `output/trips-qa/test_independent_trips.py`: **7 passed**. They cover stop validation, timezone-normalized idempotency, the inclusive 31-day limit, and authorization revalidation on an existing-row replay.
- Reviewed route role guard and existing active-user/tenant dependency, tenant predicates on all joined entities, membership identity and interval checks, indistinguishable explicit-filter 404, no-store response, dry-run default, safe CLI error and atomic transaction ownership.
- Reviewed immutable digest and unique tenant/provider/departure identity. Repeated capture times preserve idempotency; changed payloads conflict. Imports validate every row before staging inserts and recheck tenant/actor/vehicle/current membership on replay.
- Source has no vehicle mileage, PM target, repair-history or telemetry mutation. Trip history has no implicit telemetry expiry.

## PostgreSQL migration: GO

Generated SQL from the **actual migration158 upgrade/downgrade functions** using Alembic Operations. Executed on PostgreSQL15 in an isolated schema inside one transaction, with minimal referenced tables. No shared schema migrations, service changes or credentials were used.

- Upgrade creates trip table, composite foreign keys and indexes; valid trip accepted.
- Seven invalid cases rejected: NaN, infinity, negative distance, excessive driving duration, equal departure/arrival, unknown vehicle, and unknown membership.
- Downgrade removes only the trip table and preserves reference data.
- Transaction rolled back; isolated schema count after completion: **0**.
- Reproducible private artifacts: `output/trips-qa/migration-smoke.py`, `.sql`, `.log`.

## Frontend / runtime: GO

Independently exercised the actual FleetApp, TruckDetail and Trips components using the synthetic API fixture at `http://127.0.0.1:5173/trips-preview.html` through CUA browser controls.

- Truck101 View trips opens the same truck selection; row expansion and View truck return to truck101. Sidebar Trips preserves the selected truck/date filters.
- Switching to truck102 clears previous truck101 results and displays zero/empty. Changing the end date to October1 produces loading followed by zero/empty, without retaining October2 rows. An invalid date range hides results and displays the range error.
- Unknown stop details and an explicit zero-stop list display distinctly. Capture detail contains date/time only; Product accepted its placement inside the already-expanded row instead of another tooltip.
- Visually inspected 768x1024, 1024x768 and 390x844 layouts with no clipping/collision in the supplied city-label fixtures. Large row controls and form controls remain usable without hover. This is viewport/browser testing, not physical iPad testing. Long full-address stress is not included in this runtime evidence.
- Captured browser error logs were empty. Temporary viewport override reset after testing.
- Screenshots: `output/trips-qa/ipad-768.png`, `output/trips-qa/ipad-1024.png`, `output/trips-qa/phone-390.png`.

Synthetic fixture acceptance is not production import or live API evidence. The current local backend is unavailable because approved runtime config is absent; no shared database migrations or copied secrets were used to work around it.

## Release limits

This report does not authorize deployment or claim production trip data was imported. CI, exact merge/deploy identity and production import receipts remain release evidence requirements. App rollback can hide Trips while retaining the additive history table; database downgrade is not a routine release rollback.

## Independent final gate

**GO for PR review/CI.** No blocking implementation finding remains in the reviewed scope. Deployment and import are still subject to the separate release evidence below.
