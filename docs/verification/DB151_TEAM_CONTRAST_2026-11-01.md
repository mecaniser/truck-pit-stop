# DB-151 — Team and technician board contrast

Frontend & UX accountable; Fast UI lane; `codex/team-contrast`, base `9d72b777`.
Status: local verification passed; [draft PR732](https://github.com/mecaniser/truck-pit-stop/pull/732) open. Protected CI, merge and production release pending.

## Findings and corrections

The Team overrides covered neutral text but left bright status colors on light surfaces. Technician Board/detail still used fixed night colors for counts, suggestions, tabs and summaries. Clocked Out faded the entire informational badge. List actions faded on hover; the calendar icon turned yellow on hover. High contrast made the progress track white without giving its fill sufficient contrast.

Scoped `db-team-colors` styling now owns neutral/status text, opaque surfaces, form fields/placeholders, readable action fills, list links, focus indicators, status dots and progress tracks. Status text remains full opacity. Existing API contracts, roles, tenant boundaries, staff/timer/request actions and stored settings are unchanged. Appearance switching during QA used the application's token generator without saving preferences.

Compact QA also reproduced the bottom navigation and scrolling content intercepting the editor footer. Add/edit Team dialogs now portal into the existing staff shell, retaining theme inheritance while escaping the scroller. Mobile navigation is hidden only while a Team dialog is open. Normal pointer Cancel succeeds; no forced click was used. Staff editing now has an explicit named dialog.

## Acceptance evidence

WCAG AA thresholds: normal text 4.5:1; large text 3:1; meaningful non-text controls/graphics 3:1. Sources: [W3C text contrast](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum), [W3C non-text contrast](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast).

[Measured matrix](db151-team-contrast/contrast-results.json): 111 settled view/theme/accent checks, 7,224 text samples, zero failures; minimum text **4.94:1**. The matrix also contains 603 icon/input-border/status/progress samples, zero failures; minimum **3.31:1**. Earlier failed probes led to the fixes above and were superseded by the final measurements. Counts represent samples across repeated states, not distinct elements or automated test cases.

| Surface | Covered states |
| --- | --- |
| Team | Cards/list, management roles, active/inactive technician, points/streak, PTO/cash requests, work status variants, empty search |
| Forms | Add technician/other role, validation errors, portaled role options, technician edit, admin edit/permission switches, Cancel without saving |
| Work | Expanded work rows and repair-order drawer with service/cost details |
| Time board | Active Job, On Break, Clocked In/Out, red/yellow/green attention, suggestions, hold notice, timer, stop dialog, empty and error states |
| Technician detail | Daily summary, seven-day trend, date calendar including selectable past days, tooltips, expanded completed sessions, edit/delete dialogs |
| Admin controls | Active timer, idle Misc/Repair Order selections and fields, disabled/enabled commands; mutations blocked during fixtures |
| Appearance | Light, dark, authored High contrast; all five accent choices on Team; desktop 1440px, compact 390px, detail 320px |

Keyboard input focus is visible with a solid 2px outline. Windows forced-colors emulation on the open form passes 88 text samples with minimum 14.02:1. Filled input values also pass the final reusable probe. Disabled controls are excluded from minimum-contrast assertions; decorative emoji are not used as the sole status signal. This is scoped Team QA, not a whole-application WCAG conformance claim.

Browser probes use computed colors, alpha compositing against ancestor surfaces, sRGB luminance, font-size/weight thresholds and visible opacity. Entry animations settle before measurement. Portaled role menus are explicitly included. [Reusable browser probes](../../e2e/tools/team-contrast-audit.mjs) can be passed to Playwright `page.evaluate`; visual review supplements them for layering and controls. Fixture API reads supplied conditional states; non-GET fixture requests were blocked. Normal local staff sign-in and live local Team/Time Board reads were checked separately. No staff, permissions, requests or timers were saved.

### Screenshots

[Light board](db151-team-contrast/board-light.png) · [Dark board](db151-team-contrast/board-dark.png) · [High contrast board](db151-team-contrast/board-high_contrast.png) · [Team](db151-team-contrast/team-light.png) · [Mobile editor](db151-team-contrast/editor-mobile.png). All data is fictional local QA data.

## Automated checks

- 21/21 focused component tests: MechanicsPage (including portal cancellation and restricted-role regression), DashboardLayout and MyGaragePage.
- TypeScript and Vite production build pass; existing Browserslist staleness and React Router future warnings remain.
- Changed-source baseline lint passes across four changed TypeScript files; full-file ESLint identifies 12 pre-existing `no-explicit-any` errors, not introduced by this work.
- `git diff --check` and browser-probe syntax check pass.

## Runtime receipt — 2026-11-01, America/New_York

Intended checkout `/Users/sergio_m1_promax/.codex/worktrees/team-contrast/truck-pit-stop`, branch above, scoped uncommitted changes during browser acceptance. Vite5201 PID32031 serves this checkout/frontend with an isolated `/tmp/db151-vite-cache`; API8031 `dieselbridge_api_team-contrast` mounts this checkout/backend. Direct/proxied readiness confirms database and Redis healthy. Approved canonical backend environment is symlinked; existing fixture database `truckpitstop_db042_qa`, Redis12, sandbox provider settings preserved. Database/source both at `196_historical_owner_self_review`; no migration, reseed, worker or payment execution. Other previews, including5173, were preserved.

Initial candidate port8021 became occupied before startup; that failed candidate container was removed and this task uses8031. Shared dependency-cache interference was resolved with this task's separate Vite cache. The local WebSocket endpoint returned403 during an earlier legacy-login pass; HTTP reads and all rendered acceptance checks worked. Live push delivery is not claimed by this color-only change.

http://127.0.0.1:5201/dashboard/garage/mechanics is **aligned and browser-verified**. Mock routes were removed after QA. Local acceptance is separate from protected CI, merge and deployment; no production release is claimed.
