# Shop Work review tasks

Owner: Frontend & UX. Board item: DB-151. Fast UI lane, existing authenticated APIs and mutation contracts.

## Acceptance

- Shop Work is the first heading. No Service visits banner or Review payments banner appears above the view switch.
- Overview combines existing authorized visit requests and payment review records with operational tasks, even with zero active jobs.
- Requests display customer, vehicle, service and requested date. An accepted date is an arrival date, never a fabricated start time. Accepted arrivals and confirmed reservations appear in Coming up.
- A request action opens exactly that request, including after reload. Missing or foreign records never substitute another record. The existing Shop Work breadcrumb and browser Back preserve the originating task.
- Canonical payment actions resolve through the current authorized queue and open the exact invoice settlement. Legacy-only submissions retain their existing repair-order path. Merely opening a record submits no review or financial mutation.
- Empty visit queues contribute no attention item; Service visits remains discoverable beside Coming up. Closeout owns its detailed payment queue below the view switch. Active work and Activity contain no duplicate review banner.
- Loading and failures cannot claim all clear. Each source retains independent availability and permission checks. Existing user/tenant session query scopes remain intact.

## Implementation

Existing read-only visit-request and confirmed-appointment APIs are composed with the existing Zelle review queue and server overview. Existing repair priority order is retained, followed by oldest customer reviews and routine work. No schema, API, payment writer, provider, authentication policy or dependency changes.

## Runtime receipt

2026-11-04. Worktree `/Users/sergio_m1_promax/.codex/worktrees/shop-work-review-board/truck-pit-stop`, branch `codex/shop-work-review-board`, base `e3936844`. Frontend PID57003 serves this checkout at `http://127.0.0.1:5298`, proxy8198. Docker `db151reviewboard-api-1` mounts this checkout's backend read-only. Fresh disposable PostgreSQL `dashboard_lifecycle_disposable` and Redis are isolated under project `db151reviewboard`. Approved prior synthetic runtime configuration reused; existing ports5173/8000/8197 and their databases preserved. Schema preflight and direct/proxied readiness pass. Signed-in rendered Shop Work verifies source alignment. Native local logins; no injected authentication or production backend.

## Verification in progress

- Dashboard/appointments component and navigation suite: 229 tests pass across17 files. Follow-up source and final checks recorded below.
- Production frontend build and shared-control validation pass. Direct ESLint exposes only the pre-existing `false && isManager` legacy panel rule; the repository's changed-source baseline gate is the required lint check.
- Real customer portal request sent from synthetic local customer, visible on owner Overview with Active work0. Exact request opens with original note/reference; Start review retains task; Accept visit removes attention item and places accepted arrival in Coming up. Returning to Service visits shows no pending requests.
- Exact canonical invoice `BOARD-INV-1` and partial pending amount168.44 opened from Overview and Closeout without payment submission. Reload, close, browser Back and originating board position checked.
- Desktop1440 and phone390 Day/Night renders inspected. No document horizontal overflow. Empty visits remain accessible. All four board views exercised.
- Early runtime logs include existing stale-session fixture messaging403 and Appearance409 responses after initial fixture setup changed synthetic tenant settings. No changed-source exception was observed. Clean-session repeat remains to be recorded.

Screenshots are local under `output/playwright/` in this checkout. Unit-test scenarios use mocks; the journeys above use genuine isolated PostgreSQL/API data. No external WorkOS, banking or payment-provider submission is part of this UI change. Merge and deployment are not authorized by this implementation request.
