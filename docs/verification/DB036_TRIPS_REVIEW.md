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

## Calendar refinement — owner Fast UI verification

Added Day, Week (Monday through today), Month (month to date), and Custom quick picks with shared DatePicker From/To calendars. Existing API and tenant contracts unchanged. Shared calendar scheduling detail remains default-on for existing callers and is off for Trips. CUA verified Month dates, calendar month grid, custom selection and viewport bounds at768/390; saved `output/trips-qa/calendar-ipad.png`. Synthetic preview only. Focused Trips and shared DatePicker regressions pass; TypeScript checked.

## Metrics extension independent gate — 2026-10-02

Reviewed release candidate `1e25a345` / PR455, contract v1.1.

**GO** for the metrics delta, subject to required CI and exact production release/import verification.

- Independently ran all trip backend tests after the metrics changes: **41 passed**. Coverage includes zero versus unknown, actual fuel precedence, frozen baseline, partial baseline rejection, range/nonfinite/boolean validation, future and overly old baseline, derived overflow rejection, immutable metric conflicts, and legacy omitted/null/empty metric digest compatibility.
- Reviewed persistence and projection: nullable metrics JSON is stored in each immutable trip, calculations use that stored basis, actual positive gallons produce Trip MPG, baseline-only input produces estimated gallons, and actual zero yields neither division nor fallback estimate. No current telemetry lookup can rewrite historical estimates. No cross-tenant query or authorization boundary changed.
- Regenerated actual migration158 SQL and repeated isolated PostgreSQL15 upgrade/downgrade smoke, including metrics JSON roundtrip with null actual gallons, a 6.5 MPG frozen baseline and zero idle. All checks passed; transaction rolled back and leftover schema count zero.
- Independently opened the synthetic fixture in a separate Chrome QA tab at 768px and expanded the66-mile trip. Verified visible `Est. fuel 10.2 gal`, `Based on 6.5 MPG · 30-day avg`, and `Idle time 4m`; no actual-fuel or Trip MPG claim appeared. Browser interaction initially hit control timeouts, then succeeded through the focused native Enter action. Independent screenshot: `output/trips-qa/metrics-independent-768.png`.
- Independently visually inspected parent-operated CUA screenshots `metrics-768.png` and `metrics-390.png`. Estimate and idle columns remain legible and distinct without overlap; the basis wraps on390px. Parent operated those captures; reviewer independently judged the images. The inline basis inside expanded details matches the updated contract.
- Temporary reviewer browser viewport reset; reviewer-created Chrome tab closed. Existing user tabs untouched.

No implementation files were edited by this reviewer. No blocking finding remains. These are synthetic/browser and local database test results, not evidence that production data has been imported.

## Trips release complete — 2026-10-02

- Reviewed head: `1e25a3457b9757392b0b2af41bfbb9abce0b5f8f`; all six CI jobs passed (run37068938148).
- Merge: `d8cbe69c2bdafaa61cb32f4ad3f40e2c10beb663`.
- Railway deployment: `e6b8dc5e-63e1-4290-9873-4fb62862a4ec`; public build-version matched merge SHA; readiness database and Redis healthy.
- Production schema158 verified. Dry run passed, authorized initial batch committed, exact replay unchanged.
- Initial import: three verified trips for truck609,131miles,2h43m. Estimated gallons use frozen6.5MPG average; observed idle available on two legs. No measured trip MPG or tank-capacity claim.
- Import verified vehicle, telemetry and repair-order fingerprints unchanged.
- Authenticated production browser verified Trips navigation, totals, expanded estimate/idle, View truck and return with truck609 selected.
- Responsive fixture review at768/390 and independent QA/security GO recorded in previous comment. This is browser viewport testing, not physical iPad testing.
- Motive OAuth automatic collection remains pending; this release uses imported dashboard trip history.
- Local delivery board updated to Done with release evidence. Private source data, receipts and screenshots remain excluded from Git.
