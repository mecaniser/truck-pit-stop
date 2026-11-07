# DB-074 duplicate reload prompt follow-up

Owner: Frontend & UX. Lane: Fast UI (existing recovery UI coordination only).
Branch: `codex/deduplicate-update-reload`, base `3ad3a5d0896eecb64a58145ed6f34c4bfc637f40`.

## Behavior and acceptance

The route boundary previously inferred staleness only from the thrown message.
A separately confirmed update could therefore show the floating update banner
beside a generic render-failure card. The fallback now subscribes to the existing
stale-deploy store and claims the existing full-page update presentation when
either signal establishes staleness. The redundant banner disappears.

- Update confirmed before or after a generic crash: one update message and one
  working Reload now button; no generic error message.
- Generic crash without a confirmed update: existing error/reload recovery remains.
- Healthy route with an update: route remains visible with its existing banner.
- Unsaved-work warning, native reload, chunk detection, and diagnostics preserved.
- No auth, tenant, API, migration, financial, or automatic-reload policy changes.

## Verification

Two new regression cases failed before implementation, reproducing both timing
orders. After implementation, five focused suites pass: 39 tests covering route
recovery, banner behavior, chunk recognition, build polling and dirty-work guards.
Changed-source ESLint passes with zero warnings. Production build (shared-controls check, TypeScript and Vite) passes.

Playwright CLI actual-source synthetic preview, Chromium:
- 390x844: one full-page update card, warning and reload button; screenshot inspected.
- Clicking Reload now performs real navigation and renders the recovered fixture.
- 1440x900: generic crash first, then Confirm update switches to one update card;
  measured one reload button, one alert, zero floating statuses, no generic error,
  and no horizontal overflow.
- Healthy fixture: app remains with exactly the update banner.
- Expected synthetic render errors remain logged, proving diagnostics are preserved.

Local screenshots: `output/playwright/update-mobile.png` and
`output/playwright/update-desktop.png` (not committed).

## Local runtime receipt — November 7, 2026, 11:26 AM America/New_York

Intended checkout `/private/tmp/dieselbridge-update-reload`, base SHA above,
application/test/board edits uncommitted during acceptance. Preview Vite PID51532
served port5195 from that checkout's frontend; process cwd and served source HTTP200
verified. Branch and exact base SHA were supplied to the local Vite identity guard.
Temporary preview entrypoints were removed and preview server stopped after browser checks.

Full-stack runtime is **blocked/mismatched**: controller dry-run rejected missing
approved backend/.env; existing API8000 mounts another task's privacy-safety
checkout and was preserved. Preview deliberately points its unused API proxy to
closed localhost port1; no database, authentication, or payment rails used.
`http://127.0.0.1:5195` was an actual-component synthetic preview, not a signed-in
application runtime. No signed-in full-stack or production acceptance claimed.
[Draft PR829](https://github.com/mecaniser/truck-pit-stop/pull/829), implementation `1793166c`.
Protected CI, merge, deployment, and production smoke remain pending. Not Done.


## Authorized release — November 7, 2026

The user explicitly authorized finishing verification, merging PR829, deployment,
and production one-prompt checks. Final diff reviewed: only the existing recovery
presentation, focused regressions and delivery documentation; no auth, API, tenant,
financial, migration, infrastructure or automatic-reload policy changes.

- All seven checks passed on `dfeba9e3e354175575d774a2249491b1652042d8`,
  [Quality gates run42391364396](https://github.com/mecaniser/truck-pit-stop/actions/runs/42391364396).
- PR829 made ready and squash-merged at2026-11-07T17:09:13Z as
  `12396b77cca1f215c645254f3242309bfbd41f35`. Strict required checks satisfied.
- Railway API/frontend service auto-deployment
  `f265952a-9ed5-4322-ae4b-b1792d417dcc` reached SUCCESS on that exact SHA.
- Public `https://www.dieselbridge.com/build-version` matches the merge SHA,
  build timestamp2026-11-07T17:10:59.583Z. `/health/ready` reports production ready,
  database and Redis healthy.

## Actual production recovery checks

Isolated Chrome production `/login` tab, using the deployed bundle rather than
injected replacement UI. Browser-only fault simulation set the real route
boundary's error state to a generic verification Error, and dispatched the
existing `vite:preloadError` event to confirm update availability. No requests,
server records or shared production settings were modified by fault injection.
This tests the actual fallback and store subscription; it is not a claim that a
new real missing asset was deleted from production or that staff authentication
was available.

Before deployment, the same simulation on the previous live build reproduced
the reported defect: generic error card and floating update banner each had a
Reload now action.

After loading the deployed build:

1. A healthy login route plus update event keeps the route and shows one banner.
2. Update event before generic failure produces one full-page update card.
   Browser measurement: reloadButtons1, updateMessages1, genericError false,
   floating status banners0. Mobile390x844 screenshot confirms readable content,
   unsaved-work warning, one button and no second card.
3. Activating the actual reload button's click handler caused a new
   `Page.frameNavigated` navigation to the same login URL and restored the working
   login form with no recovery UI. High-level pointer APIs timed out; the actual
   rendered button's `.click()` was invoked through documented CDP, not replaced
   with a custom reload function. Unit tests also verify the handler once.
4. Generic failure before update at1440x900 first shows the ordinary recovery
   message; after the update event it becomes one new-version card with one
   Reload now action. Desktop screenshot inspected.
5. Final recovery clears the simulated client state; working login DOM verified
   and temporary viewport override reset.

Private screenshots remain local/excluded in the implementation checkout:
`output/playwright/production-update-mobile.jpg` and
`output/playwright/production-update-desktop.jpg`.

**Remaining external acceptance:** signed-in staff coverage is blocked by expired
production staff sessions and no available prefilled password. The user was asked
to sign in in the preserved verification login tab. No account password was
changed, authentication bypassed or production token minted. Public-route global
recovery checks are complete; signed-in acceptance is not claimed. The delivery
item remains released with that explicit acceptance blocker, not Done.

Local services were not started for this release-only/documentation work. The
historical local backend alignment blocker remains separate from successful
production deployment and public global-boundary acceptance.
