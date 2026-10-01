# DB-036 compact telemetry presentation

2026-10-01; Frontend & UX owner; Fast UI lane.
Branch: `codex/fleet-telemetry-compact`; base `ab0724c3`.

## Acceptance and scope

- Truck card: last reported location, blue labeled speed, one shared source/age
  when provenance agrees. Reported odometer appears only in truck detail.
- Detail: compact metric grid; blue speed, purple fuel, neutral mileage/hours.
  Complete field-level source, observed/captured time and mileage basis remain
  under the keyboard-operable Lucide **Reading details** disclosure.
- Mixed sources/timestamps retain independent concise age labels. Manual capture
  time is explicitly a save time; missing observation time never claims live or
  fresh telemetry. Zero remains visible; retention behavior is unchanged.
- Manual input has a compact **Add reading** trigger, no bordered empty form in
  the default view, and collapses after successful save with a visible receipt.
- No API, authorization, tenant, mapping, canonical mileage, migration or worker
  change. Existing VIN/membership validation and idempotent retries are retained.

## Verification

- Focused Vitest: 38/38 across FleetTelemetry, FleetBoard.pmSort,
  FleetBoard.order-views and TruckDetailHarden.
- Changed-source ESLint (including preview): zero warnings/errors.
- TypeScript and production build passed; git diff check passed.
- Playwright CLI, real FleetBoard/TelemetrySummary/TelemetryCapture components,
  synthetic staff identity/data and an in-memory HTTP adapter that rejects
  unknown requests. This is presentation acceptance, not authenticated full-stack
  or live provider acceptance.
- Desktop 1440x950: compact card, no reported odometer on card, detail metric
  grid, provenance open/close and keyboard Enter verified.
- Mobile 390x844: two-column detail metrics, compact card, manual form opens,
  accepts a synthetic zero speed and verified fixture VIN, closes after save,
  and leaves a visible receipt. Page width 390; no horizontal overflow. Card
  width 335, telemetry block height 97.5 CSS px in this fixture.
- Screenshots inspected locally in `output/playwright/db036-compact/`:
  desktop-board.png, desktop-detail.png, mobile-board.png, mobile-detail.png.
- Console: no application errors; initial missing fixture favicon corrected.
  Two existing React Router future-flag warnings remain.

## Runtime receipt and limitation

Controller switch dry-run blocks on missing approved `backend/.env`. At preflight
ports 5173/8000 were unbound. The isolated frontend fixture was served from this
worktree on 127.0.0.1:5173 by Vite PID6645; cwd and command confirmed. HTTP fixture
returned 200 and browser rendered the changed source. The task-owned fixture server
was stopped after acceptance; the screenshots remain available. Proxy remains the default
127.0.0.1:8000, but the fixture handles requests in memory and uses no backend or
provider. No database, shared service, credentials or production records changed.
Authenticated local full-stack acceptance remains blocked on runtime configuration.
Preview entry: `/tests/telemetry-preview.html`; excluded from production entrypoints.

## Automatic collection status

The current code schedules `reconcile_motive` every five minutes and gates
provider calls on `MOTIVE_ENABLED` plus approved tenant/connection state. Manual
captures do not schedule automatic browser scraping. OAuth approval/client
credentials, company consent and mappings, provider webhook subscriptions, and
verified API/worker/Beat deployment remain prerequisites for live collection.
See `docs/DB-036_MOTIVE_SETUP.md`. This UI change does not activate collection.

## Release state

PR448, implementation `5eaa33e4`, ready for review; not merged or deployed. Authenticated production smoke check
must follow an approved release. The earlier manual integration PR443 was merged
at `73675fd0`; that does not deploy this follow-up.
