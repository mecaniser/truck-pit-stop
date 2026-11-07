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
