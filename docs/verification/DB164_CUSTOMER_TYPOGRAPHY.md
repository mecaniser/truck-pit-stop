# DB-164: Working customer portal typography

Owner: Frontend & UX. Fast UI lane; no API, staff ThemeContext, auth, schema, payment, dependency or provider changes. Release not yet authorized.

## Problem and behavior

The old customer Appearance page edited the shared staff theme, but that theme only applies tokens to `.db-staff-shell`. The customer shell and task pages hardcoded Helvetica and pixel sizes. The named webfont options also had no loaded font assets. Accent choices mainly changed a decorative preview.

Remove color customization and the fake button/badge theme preview. Offer three available font stacks (system sans serif, Georgia/serif, platform monospace) and three distinct text scales (14/16/18px body bases). Apply the family and proportional type scale to customer navigation, headings, content, fields and portalled dialogs, while preserving spacing, semantic colors and control targets. Do not resize the document rem unit or use page zoom. Task-page pixel sizes now resolve against the customer type scale; Tailwind text utilities use the same scale. Small labels have an11px floor; mobile editable controls retain a16px minimum and grow with Large.

Preferences save immediately in browser storage under a versioned user/shop key. Portal subscribers update together and cross-tab storage changes are supported. Invalid/unsupported preferences use defaults. Failed writes leave the previous selection applied and show an error. Reset text changes only customer typography; old staff theme/accent keys remain untouched. Customer-only variables and the active-portal scope are removed when leaving the portal. Existing monospaced codes and externally hosted payment fields retain their own typography.

## Automated checks

- 38 focused typography/settings/saved-card tests pass: subscriber updates, reload/remount persistence, separate customers/shops, invalid preferences, cross-tab updates, denied staff writes, storage failure, reset preserving staff preferences, removed accent UI and unchanged draft safeguards.
- 45 existing settings-navigation, overview authorization and vehicle-route tests pass.
- Full TypeScript and production build pass; shared control check passes.
- New-source ESLint and diff checks pass. Baseline-aware changed-source lint records existing legacy violations separately; no new violations required for PR.

## Local runtime alignment — 2026-11-06

Isolated checkout `/tmp/customer-portal-typography`, branch `codex/customer-portal-typography`, initialHEAD36980c15. Frontend `http://127.0.0.1:5190`, PID48565, cwd `/private/tmp/customer-portal-typography/frontend`, proxy8126. Port5189 belongs to the previous sign-out preview and remains untouched.

Intentional unchanged-backend split: existing Docker `customer-notification-api` bind `/private/tmp/customer-notification-preferences/backend`, port8126. Backend app/alembic trees are identical to this branch. Existing isolated PostgreSQL `customer-notification-pg/customer_notification_preferences`, migration204, provider keys disabled. API and proxied readiness pass for DB/Redis. No migration/reseed/production credentials or service restart. This local frontend is aligned and browser-verified with the explicit unchanged-backend split.

## Actual browser acceptance

Signed in through the real isolated API with the fictional Notification Tester fixture. Appearance shows only typography choices and a text sample. Selecting Serif/Large changes the account heading to Georgia27px; reload and a new login retain it. Account heading sizes are21/24/27px for Small/Default/Large. Reset restores system sans and24px heading. Root body bases are14/16/18px. Profile fields inherit the chosen family and control type scale; the portalled discard dialog inherits Georgia and22.5px title at Large. Keep editing preserves the fictional unsaved name; Cancel restores it without a write.

Home's initial hardcoded task CSS was discovered during runtime checks and corrected too: desktop Large Monospace Today heading33.75px, mobile29.25px. Maximal Monospace/Large fits at390×844 and320×844 with no document/main/region horizontal overflow.44px control contract remains; keyboard Tab advances among font options with visible outline. On synthetic logout the portal class and customer font variables are removed; Login returns to its normal16px sans typography. Local account restored, preferences reset, viewport restored; Appearance left open for review.

Screenshots: `output/typography-desktop-default.png`, `output/typography-mobile-large.png` (fictional local data). No production customer/preferences/financial/provider writes or messages. Source review/protected CI, merge and deployment remain separate pending steps.
