# DB-164: Working customer portal typography

Owner: Frontend & UX. Fast UI lane; no API, staff ThemeContext, auth, schema, payment, dependency or provider changes. User approved deploying PR817; the final font choices are Geist, Jakarta and Monospace.

## Problem and behavior

The old customer Appearance page edited the shared staff theme, but that theme only applies tokens to `.db-staff-shell`. The customer shell and task pages hardcoded Helvetica and pixel sizes. The named webfont options also had no loaded font assets. Accent choices mainly changed a decorative preview.

Remove color customization and the fake button/badge theme preview. Offer Geist, Jakarta and platform Monospace and three distinct text scales (14/16/18px body bases). Apply the family and proportional type scale to customer navigation, headings, content, fields and portalled dialogs, while preserving spacing, semantic colors and control targets. Do not resize the document rem unit or use page zoom. Task-page pixel sizes now resolve against the customer type scale; Tailwind text utilities use the same scale. Small labels have an11px floor; mobile editable controls retain a16px minimum and grow with Large.

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

Signed in through the real isolated API with the fictional Notification Tester fixture. Appearance shows only typography choices and a text sample. Selecting Jakarta/Large changes the account heading to the bundled Plus Jakarta Sans27px; reload and a new login retain it. Account heading sizes are21/24/27px for Small/Default/Large. Reset restores Geist and24px heading. Root body bases are14/16/18px. Profile fields inherit the chosen family and control type scale; the portalled discard dialog inherits the selected font and22.5px title at Large. Keep editing preserves the fictional unsaved name; Cancel restores it without a write.

Home's initial hardcoded task CSS was discovered during runtime checks and corrected too: desktop Large Monospace Today heading33.75px, mobile29.25px. Maximal Monospace/Large fits at390×844 and320×844 with no document/main/region horizontal overflow.44px control contract remains; keyboard Tab advances among font options with visible outline. On synthetic logout the portal class and customer font variables are removed; Login returns to its normal16px sans typography. Local account restored, preferences reset, viewport restored; Appearance left open for review.

Screenshots: `output/typography-desktop-default.png`, `output/typography-mobile-large.png` (fictional local data). No production customer/preferences/financial/provider writes or messages. These pre-release checks are superseded by the completed release evidence below.

## Final font-set qualification

The user specifies Geist and Jakarta plus Monospace; Inter and DM Sans are removed. Small/Default/Large have no pixel labels. Geist and Plus Jakarta Sans variable WOFF2 files are self-hosted from pinned `@fontsource-variable`5.3.0 packages, unmodified, with OFL licenses and SHA256 source manifest under `frontend/src/assets/fonts/customer-portal/`. Latin/Latin Extended and normal/italic are included; browser requests only applicable glyph/style faces. Portal-specific family aliases avoid altering staff font names. No npm dependency/lockfile change or third-party font requests.

Actual Chromium rendered-font inspection confirms Geist/Geist-ExtraBold and Plus Jakarta Sans/PlusJakartaSans-Regular_ExtraBold with `isCustomFont:true` and16 heading glyphs. Jakarta/Large remains27px after reload. Final corrected desktop/mobile screenshot and type-scale acceptance passed before merge; the earlier generic-family screenshots are superseded.

## Production release and acceptance — 2026-11-06

User approved PR817 production and refined the final font set to Geist/Jakarta/Monospace. Concurrent portal presentation PR816 landed during CI. Reconciled its colors/motion by combining shell imports and preserving its task CSS before applying only the font-family/type-scale changes.90 focused regressions including motion, final TypeScript/build/controls and baseline-aware lint pass. Rechecked Jakarta/Large on the combined local UI at320px without overflow.

All seven protected checks passed on `52b92ed2968baf4310b38be325d9d188f464334e`, run [42176700697](https://github.com/mecaniser/truck-pit-stop/actions/runs/42176700697). Normal protected squash merged [PR817](https://github.com/mecaniser/truck-pit-stop/pull/817) as `62713c902de4b41b7772a1b73199fb9073d66a6c`. Complete checked/merged tree `ee3a3d06150a69e6484182a9834bedd406bae607` is identical. No direct main push, protection override or force push.

Automatic Railway Web deployment `a4d2f074-1dce-42b3-9e6b-976a5e257f8f` succeeded on the merge SHA. Public `/build-version` matches62713c90, built2026-11-06T06:57:57.301Z. `/health/ready` passes with database and Redis healthy. No database migration, worker-policy or financial/provider operation.

After the coordinated customer-browser handoff from the PR816 owner, the signed-in production Appearance page passes:

- Exactly Geist/Jakarta/Monospace and Small/Default/Large; no color customization, Inter, DM Sans or pixel labels.
- Actual custom-rendered Geist and Plus Jakarta Sans heading glyphs confirmed through Chromium rendered-font inspection (`isCustomFont:true`).
- Jakarta/Large changes the heading to27px and survives a real reload. Small/Default/Large produce21/24/27px account headings.
- Jakarta/Large at390×844 and Monospace/Large at320×844 have no document/main/region horizontal overflow.
- Observed original Geist/Default restored through the UI; original tab confirms the restored pressed states. Requested1307×1313 viewport restored. Only explicitly approved reversible browser typography choices were exercised; no account/contact/notification/invoice/payment/provider data was changed and the customer was not signed out.

This thread's IAB5 namespace exposes customer tab10 at `/portal/settings?tab=appearance`; the handed-off tab5 was not visible here. Used dedicated verification tab12 and closed it afterward. Original customer tab10 stays signed in, with Geist/Default at1307×1313, and was released to the coordinator for the PR818 staff-browser handoff. No further browser actions after release. Safe panel screenshot: `/tmp/customer-typography-release-evidence/output/typography-production-panel.png`; excludes real account name/email.

DB-164 product release is Done. This isolated documentation receipt intentionally remains draft with its merge held until PR818 has landed, per the coordinated release instruction; it is not an outstanding application deployment or browser gate.
