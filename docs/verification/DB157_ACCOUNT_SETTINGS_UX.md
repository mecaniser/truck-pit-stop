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
| Navigation | Group headings visually distinct from actions. Focus targets are labeled regions, avoiding duplicate hidden headings. Sign out is a separate action below the settings groups, outside Security. Settings-section departure and page reload warn before discarding profile edits. |
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

Final reconciliation gates: production bundle passes. Changed-source lint passes against both the pre-reconciliation branch head (4 files) and current PR base21684af1 (whole PR). TypeScript reports only the previously confirmed baseline LoginPage.tsx:118 error. The first lint comparison used the older82c95576 base and also examined an unrelated appointment change already on main; the corrected comparisons exclude that upstream change. No unrelated appointment edits made.

## In-app modal correction, 2026-11-05

The user correctly identified native confirm dialogs in the previously added unsaved-edit protection. Replaced every confirm call in ProfileSettingsPage and PaymentMethodsCard with a shared AccountConfirmationDialog, using the already-installed Headless UI Dialog. No dependency added.

- Centered themed modal, dimmed/inert background, linked title/description, alertdialog semantics and safe cancel initial focus.
- Explicit Keep editing / Discard changes, Keep editing / Discard and sign out, and Keep card / Remove card actions.
- One parent-controlled pending action covers section navigation, payment-management navigation and dirty sign-out. Destination focus moves only after confirmed navigation.
- Cancel, Escape and backdrop dismissal preserve edits and restore trigger focus.
- Pending account actions bind to the authenticated session; session change dismisses them. Pending card removal binds to provider context and is dismissed on context/session change. Existing backend/provider requests and their expected-context arguments are preserved.
- Browser-owned beforeunload warning for closing/reloading an edited page remains necessary and cannot be replaced with a webpage modal. Internal settings actions no longer call native confirm.

Validation: focused suites50/50 pass (15 profile behavior,18 saved-card safeguards plus the existing navigation/summary/preferences/vehicle cases). Tests cover no action before confirmation, cancellation, confirmed navigation/sign-out, context/session changes and zero native confirm calls. Headless UI asynchronous act warnings remain in jsdom; no corresponding app errors in browser.

Actual browser checks at1366,390,320 pass for focus trap (Tab and Shift+Tab), Escape, backdrop cancellation, focus return, edit preservation, confirmed navigation and cancelled sign-out. Native dialog count0 in these internal flows. Modal panels fit the viewport. Screenshots visually inspected on desktop and phone: /tmp/account-discard-modal-1366.png and /tmp/account-discard-modal-320.png; card equivalents /tmp/account-remove-modal-1366.png and /tmp/account-remove-modal-320.png. Also verified Escape and trigger-focus restoration in the user's visible in-app browser. Layout detector and diff check pass. Only the previously confirmed baseline LoginPage.tsx:118 TypeScript mismatch remains.

Synthetic preview only; real payment writes blocked. Authenticated full-stack acceptance, merge/deploy remain pending.

## Production release and signed-in acceptance — November 5, 2026

User explicitly authorized deployment. Main was reconciled into PR798 with both account-settings and overview delivery records preserved. There was no application conflict. The reconciled head c9a93b486dff1e9cd649bf927b201d0243d73073 passed all seven exact-head checks in Quality gates run42104117940: Migration graph, Backend tests, Backend full suite (informational), Prepare frontend dependencies, Frontend checks, Frontend full suite (informational), Playwright smoke. Backend suites were classified as unaffected by this frontend/Markdown change; their successful job state is not fresh backend execution evidence. Frontend CI used the pinned installation and passed its production build; the earlier shared-local-install LoginPage resolver mismatch did not block CI.

GitHub reports PR798 merged at20:38:46UTC as88d9c98ddece697dd30356dedc9b3d8fbfc75123. The merge request returned already merged; merge state was independently re-read rather than attributing an additional merge action. Checked and merged frontend trees are identical. No branch protection bypass or direct push to main.

Automatic production deployment0a5f2583-0471-40e7-b19c-97b652860eea succeeded on that exact merge SHA. Both Railway metadata and https://www.dieselbridge.com/build-version match. API readiness reports ready with database/Redis OK; the portal route returns200. The deployed CustomerPortalPage bundle contains all six inspected account/modal/capability markers. No forced or duplicate deployment, provider configuration change or worker command issued. Rollback reference: prior successful deploymentd5b0299c-f7f7-4b19-9696-ce7b2cbf7982, source230381952d3ca5519dada3fbc4efca6b168e9886.

The production browser initially required sign-in; the user restored a customer session. Actual signed-in acceptance then verified:
- Account settings heading, grouped section navigation and separate Sign out action.
- All seven section regions render in the live customer portal.
- An unsaved local contact edit opens the themed discard alertdialog with Keep editing initial focus. Escape preserves the local edit and returns focus; confirmed discard opens Security. Returning Profile restores the original saved value and a disabled Save changes action.
- Security contains the password action and no embedded Sign out action.
- An existing saved card opens the removal alertdialog with Keep card initial focus. Cancellation leaves it intact; no removal/default/save/payment request submitted.
- At390px and320px, the document and section have no horizontal overflow. The mobile settings list includes Sign out, the discard modal fits the viewport, and cancellation followed by form Cancel restores the original saved field.
- Browser error count0. Viewport override cleared; actual default1597x1313 restored. Page left on Profile, no open modal, saved field restored and Save changes disabled.

No contact save, credential change, sign-out, shop switch, notification preference, provider, invoice, payment or saved-card mutation was submitted. Unsaved form edits were confined to browser state and cancelled. Production account identifiers, contact values and card details are omitted from this public-safe record.

**DB-157 is Done:** implementation, focused tests, protected exact-head CI, merge, successful production deployment and real signed-in desktop/mobile acceptance exist. Notification delivery controls remain explicitly unavailable in the UI; implementing delivery preferences is a separate capability outside this release. The earlier full-stack verification blocker is resolved.
