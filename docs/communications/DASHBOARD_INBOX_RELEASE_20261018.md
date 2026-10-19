# DB-COMMS-007 — Dashboard inbox UI

Owner: Frontend & UX. Lane: Fast UI (existing authenticated UI and deployed API contracts).

## Acceptance and implementation

- `/dashboard/messages` renders `DashboardInboxPage` / `ConnectedInbox` using the deployed communications API. Existing shop/role permission guard remains in place.
- Dashboard navigation replaces prototype rail and status strip. CSS rules are contained within `.communications-surface`; the inbox fits the dashboard content area on desktop and mobile.
- Existing tenant conversations, server search, delivery history, per-user unread state, assignment, resolution and durable draft/send recovery remain API-backed. Empty/error responses never fall back to sample conversations.
- Dashboard unread badge uses the same existing per-user conversation API and receives cache updates when inbox read state changes.
- Existing new-SMS, archive and delete workflows remain available through **Previous inbox**, at `/dashboard/messages/previous`, behind the same permission guard. This release does not redesign that composer or archive surface.
- Backend SMS hold reasons have visible labels and an unknown-reason fallback. Unavailable WhatsApp/Telegram remain blocked.
- No backend, migration, provider configuration, registration, infrastructure, dependency or feature-flag changes. Production routing, automation outbox and recovery must remain off.

## Focused verification

2026-10-18: 40 tests pass across communications and DashboardLayout suites, including the real Axios/auth interceptor tests, duplicate-safe send recovery, empty state, routing hold, existing dashboard permission guard on both routes, and unread cache refresh. Changed-source ESLint and TypeScript/Vite production build pass. `git diff --check` passes.

## Local runtime receipt

Intended checkout: `/Users/sergio_m1_promax/.codex/worktrees/communications-dashboard`, branch `codex/communications-dashboard`, base `b562646373e87ebb98301f47d69ace0ddcc15eaa`, with the UI diff above.

Normal controller preflight rejected absent backend/.env; existing port5173 belongs to the unrelated ETS checkout and was preserved. Used the documented isolated communications harness with its existing local-only configuration by reference (no production secrets or copied customer data).

- Frontend: http://127.0.0.1:5186/dashboard/messages, PID84826, Vite cwd this checkout/frontend, validated branch/SHA and API origin8006.
- Backend: http://127.0.0.1:8006, PID84793, uvicorn communications_local_app:app, cwd this checkout/backend.
- Dedicated existing synthetic PostgreSQL `communications_local` on loopback55460 and Redis6386; explicit additive migration reached181; seed preserved existing synthetic records.
- Direct and frontend-proxied readiness both reported database/Redis OK. Normal existing synthetic staff session authenticated successfully. ASGI harness blocks Twilio HTTP; no real SMS sent.
- Signed-in browser pass at1280×720 and390×844: actual new component rendered within dashboard; server search filtered Daniel; channel-specific draft retained switching SMS/WhatsApp and navigating through previous inbox; WhatsApp blocked; resolve/reopen persisted and restored original synthetic status; existing previous composer/archive controls present. On mobile, list/thread navigation works, header controls fit, page scrollWidth390, Send bottom720.5 stays above mobile navigation top783. No physical-device claim.

Local URL is **aligned and browser-verified** for the isolated harness. It is not a production connection.

## Release gate

Protected CI, merge, deployment identity and signed-in production route acceptance pending. UI release does not enable channels or new routing/automation.
