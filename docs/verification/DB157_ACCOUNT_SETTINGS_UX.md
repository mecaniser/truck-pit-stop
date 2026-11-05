# DB-157 customer account settings

Owner: Frontend & UX. Fast UI lane. 2026-11-05.

## Acceptance and implementation

- Account / Preferences / Business group all seven sections on desktop.
- Mobile settings list opens individual sections; All settings restores selection focus.
- Existing tab identifiers and unrelated URL parameters survive; content follows URL changes.
- Payment methods has one heading/container, named current shop with fallback, prominent Add Card, readable Remove, and Make default on nondefault cards.
- Provider routing, session/context keys, unavailable/error/unconfirmed states, confirmation, idempotency and mutation contracts preserved. No backend, auth, provider or data edits.

## Verification

- Focused suites: 25/25 pass (saved cards16, profile summary5, navigation4), including provider/session changes, unavailable/unconfirmed states and expected context on mutations.
- Playwright CLI, real source components in synthetic fixture: desktop1366/mobile390/320; seven navigation choices, named shop/default card, mobile list/detail round trip, keyboard activation and section-focus restoration. No horizontal overflow; visible mobile controls >=44px high.
- Screenshots: /tmp/customer-account-settings-desktop.png, /tmp/customer-account-settings-mobile-list.png, /tmp/customer-account-settings-mobile-detail.png.
- Layout detector: no findings. Git diff check passes.
- Direct ESLint: two pre-existing no-explicit-any violations on unchanged profile error handlers. Changed-source lint regression check recorded below.
- TypeScript: LoginPage.tsx:118 resolver mismatch, remember_me optional versus required. Baseline comparison below.
- Fixture checks do not establish signed-in full-stack acceptance. No real customer/card/shop/provider mutations.

## Runtime receipt

2026-11-05, branch codex/customer-account-settings-ux, base82c95576640cd5027d0d2a30ef232ca86d808216, dirty UI changes.
Port8000: Docker db761-sandbox-api-1, source privacy-safety worktree. Port5173 subsequently owned by truck-portal-overview checkout, PID43837. Both preserved.
Isolated Vite fixture http://127.0.0.1:5187, PID44087, source /private/tmp/customer-account-settings-ux/frontend, matching branch/HEAD stamps and rendered changed components.
Fixture uses in-memory API adapter; no backend/database connection. Database/payment readiness not asserted.
Application runtime blocked/mismatched; synthetic fixture browser-verified only. Temporary server and fixture files removed after checks.
Authenticated acceptance, protected CI, merge/deploy pending. Not Done.

Baseline TypeScript comparison: clean detached base82c95576 with the same installed dependencies reproduces the identical LoginPage.tsx:118 resolver error. No TypeScript errors in changed files.

Final validation: Vite production bundle passes; repository changed-source lint passes across all5 changed frontend files using ESLINT_USE_FLAT_CONFIG=true (installed ESLint8 requires flat-config mode). The plain legacy-mode invocation could not load the flat config; rerun in the correct mode passed.
