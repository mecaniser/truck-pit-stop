# DB-145 solid count badges

Owner: Frontend & UX. Lane: Fast UI. Status: local GO; protected release pending.

User selected the Solid badges preview. Closeout and Activity counts use solid teal with white digits in Day; bright teal with dark digits in Night/High Contrast. Count data and interaction code are unchanged. One/two-digit badges are 23px circles; wider counts expand to pills. Forced colors use system Highlight/HighlightText with an explicit edge.

## Verification — 2026-10-30

- Approved runtime aligned to `codex/shop-work-solid-badges`, base `c0eef04a`: frontend127.0.0.1:5173 PID47342 and backend8000 PID47305, both source roots in a2-closeout-count. Canonical approved environment symlinks; explicit localhost `truckpitstop_db145_a2`, schema191, zero invoices, no migrations/reseed. Direct and proxied readiness OK.
- Local sign-in expired; no authenticated local acceptance claimed. Temporary actual-component fixture imported real source/CSS, used fictional data only, and was removed before commit.
- CUA desktop1280 and mobile390 Day/Night: solid circles, larger1000/capped1+ values, selected Activity/Closeout, keyboard Enter, unchanged icon-only mobile actions and no horizontal overflow. Badge color pairs read from actual computed CSS. No real record mutation.
- Existing focused component tests:26/26 pass. CSS-only implementation: no JavaScript lint target changed; TypeScript and production build pass; protected CI remains the release gate. Impeccable reported only existing unrelated gray-on-color warnings elsewhere in index.css; changed badge rules clear. `git diff --check` clean.
- Existing payment-only closeout, missing timing Unknown, tenant/API/permission contracts and held ETS importer unchanged. No invoices, payments, financial records, providers or collectors touched.

## Release

Pending exact-head protected CI, normal merge, automatic Web deployment and signed-in production desktop/mobile badge smoke. Prior A2 completion and C3 draft contract are recorded separately in PR688.
