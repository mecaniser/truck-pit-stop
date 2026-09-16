# DB-064 session recovery verification

Owner: Security & Identity (root). Branch: codex/session-recovery, base e02e19e7.
Contract: [session contract](DB064_SESSION_CONTRACT.md). No migration, auth-duration
change, provider setting change, or inactivity logout rule.

## Behavior

Transient renewal failures preserve the browser/server session and retry. Protected
requests still require valid server authorization. The workspace shows a polite
reconnecting notice with keyboard-accessible Retry now. Success dismisses it,
including successful renewal from another tab. Reload bootstrap stays gated while
retrying outages. Definitive expiry or revocation clears authentication and routes
to staff/driver login with distinct expired/ended copy; no unsupported inactivity
claim. Stale responses cannot replace tokens or redirect a newer session.

## Automated evidence

- Owner frontend: 48 tests / 10 files pass: keepalive, broadcast, reactive retry,
  refresh single-flight, API cancellation, bootstrap, auth store, login pages,
  recovery notice. Includes fake-clock 9m45 outage past ten minutes, retry recovery,
  terminal expiry, session changes and accessible messaging.
- Changed frontend source ESLint, TypeScript, production build and diff check pass.
- Owner backend: 67 pass, 1 existing PostgreSQL-only skip; see contract receipt.
- Independent frontend reviewer session_frontend_gate: final code QA/Security GO,
  39 tests / 8 files. Initial findings (broadcast notice and bootstrap handling,
  structured expiry code) corrected and re-reviewed.
- Independent backend reviewer session_backend_gate: code Security/QA GO,
  65 unique tests including actual Redis Lua/lease checks. Parallel owner/reviewer
  test-key collision fixed with per-run UUID; real Redis rerun passed2/2.

## Browser fixture acceptance

Playwright CLI session db064 loaded this worktree's production build via intercepted
http://db064.test requests. All API responses were synthetic; no existing API,
customer data, provider, or production service was called. External font requests
were blocked, producing expected font network errors; screenshot fallback fonts
are not proof of production typography.

- Staff expiry and driver ended messages render at1280/390/320 without horizontal
  overflow; no inactivity claim.
- Synthetic signed-in driver survives first temporary renewal at9m45 and remains
  in workspace at10m05 using Playwright's accelerated clock.
- Recovery notice renders at1280/390/320; Retry now is44px tall or larger and
  keyboard Enter recovers, dismissing notice without leaving the workspace.
- Next definitive session_expired renewal routes to driver login with visible
  expiration message and tenant context.
- Local screenshots/scripts: output/playwright/db064/. These are local evidence,
  not committed credentials or runtime/provider evidence. First harness wait used
  an incorrect heading, corrected to observed Preview Driver before passing.

## Runtime preflight and release boundary

2026-09-12 America/New_York: intended isolated checkout is
/Users/sergio_m1_promax/GitHub/truck-pit-stop-session-recovery at base e02e19e7.
Shared frontend5173 PID66880 and API8000 Docker dieselbridge_api_dev serve the
root cash-receipt task, not this checkout. Source mount is root/backend; effective
local PostgreSQL is postgres / truckpitstop_db048_local_e2e_20260912. Existing
services, populated data, settings and migrations were preserved. Dedicated ports
5197/8017 were requested per mandatory runtime skill and remain unanswered.
Status: isolated runtime blocked/unstarted, browser fixture verified. No claim
that the normal localhost app contains this change. Real authenticated local and
production renewal acceptance remain pending; no PR merge or deployment done.

A provider rotation response lost before receipt/persistence cannot be reconstructed;
subsequent confirmed invalid_grant still requires signing in. This change does not
promise sessions can survive confirmed revocation or every provider failure.

Release record: application candidate `20ec2c126dcd675b1746f33b21915f5116d4e9e7`
is pushed as draft [PR396](https://github.com/mecaniser/truck-pit-stop/pull/396).
Protected CI had no checks reported at draft creation. Merge/deployment and actual
authenticated provider/runtime acceptance remain pending. Disposable test Redis
was stopped after completed checks; existing containers were preserved.

CI follow-up: PR was reconciled with reporting-only main changes (board conflict
resolved retaining both tasks). Initial frontend CI rejected no-this-alias in a
new BroadcastChannel test fixture. Fixed in `88ca4928`; affected test and explicit
ESLint over every changed frontend source/test passed. No application change.
Protected CI rerun pending; earlier backend and migration checks passed.
