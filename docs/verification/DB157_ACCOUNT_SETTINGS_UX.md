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

Draft PR: https://github.com/mecaniser/truck-pit-stop/pull/798. Application implementation commit07b73e0a. Not merged/deployed; protected CI and signed-in acceptance pending.

## Full-surface reconciliation, 2026-11-05

User requested a complete reassessment after identifying issues the initial pass missed. Frontend & UX owns the work under the same Fast UI outcome.

| Surface | Finding and correction |
| --- | --- |
| Navigation | Group headings visually distinct from actions. Focus targets are labeled regions, avoiding duplicate hidden headings. Sign out is a separate action below the settings groups, outside Security. Dirty-profile departure and reload warn before discarding edits. |
| Profile | Explicit Save changes and Cancel with dirty-state feedback; fields locked during save; failures retain input; successful saves clear dirty state; refreshed server values preserve edited fields. Failed initial loading offers Retry. |
| Checkout preference | Renamed Preferred checkout method and explicitly limited to this browser/invoice opening. Contextual explanation follows Zelle/Card selection. Saved shop card remains a separately labeled fact with a direct management action. Failed browser storage does not falsely update selection. Removed unsupported blanket fee claim. |
| Security | Existing password API and logout/session behavior preserved. Password labels associated with fields, proper autocomplete, requirements visible before submission, Cancel disabled during submission. Sign out moved to navigation footer. |
| Appearance | Selected choices expose aria-pressed, color/font choices reflow on narrow screens, preview examples are noninteractive, supporting text improved, browser persistence scope explicit. |
| Payment methods | Existing provider/session/tenant safeguards, default-card behavior, pending/unconfirmed and recovery states retained. No real payment/provider write. |
| Vehicles | Removed duplicate title/container; copy accurately describes license-plate editing. Inputs have associated labels and touch-readable sizing. Failed loading offers Retry and is not shown as an empty fleet. |
| Shops | Failed loading offers Retry; successful empty state no longer claims a linked shop. Existing switching contract unchanged. |
| Notifications | Source search found only local storage writes and no delivery consumer for the switches. Removed duplicate inert switches and replaced them with an explicit unavailable state. Stored values preserved. Actual notification-delivery controls require a separately scoped capability; this work does not implement them. |

Validation: 45/45 focused tests across six suites, including12 profile behavior tests, existing16 provider-neutral card tests, profile summary/navigation/preferences/vehicle-scope cases. Playwright exercised all seven sections at1366,390,320 (21 section/viewport cases), with no overflow or undersized visible controls, plus profile Cancel, checkout selection/help, and navigation to payment management. Screenshots visually inspected for profile, Security, Appearance and phone adaptation. No page errors; React Router future-flag warnings only. Layout detector reports no findings. Production bundling and changed-source lint recorded below. The only TypeScript failure remains the previously reproduced baseline LoginPage.tsx:118 resolver mismatch.

The preview adapter is synthetic and rejects account/payment writes. Browser evidence establishes presentation and local interaction behavior, not signed-in provider/auth acceptance. Merge/deploy remain unperformed. Notification delivery capability and aligned full-stack acceptance remain explicit limitations.
