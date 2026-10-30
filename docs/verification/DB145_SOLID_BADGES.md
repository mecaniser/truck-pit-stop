# DB-145 solid count badges

Owner: Frontend & UX. Lane: Fast UI. Status: Done — merged, deployed and production verified, 2026-10-30.

User selected the Solid badges preview. Closeout and Activity counts use solid teal with white digits in Day; bright teal with dark digits in Night/High Contrast. Count data and interaction code are unchanged. One/two-digit badges are 23px circles; wider counts expand to pills. Forced colors use system Highlight/HighlightText with an explicit edge.

## Verification — 2026-10-30

- Approved runtime aligned to `codex/shop-work-solid-badges`, base `c0eef04a`: frontend127.0.0.1:5173 PID47342 and backend8000 PID47305, both source roots in a2-closeout-count. Canonical approved environment symlinks; explicit localhost `truckpitstop_db145_a2`, schema191, zero invoices, no migrations/reseed. Direct and proxied readiness OK.
- Local sign-in expired; no authenticated local acceptance claimed. Temporary actual-component fixture imported real source/CSS, used fictional data only, and was removed before commit.
- CUA desktop1280 and mobile390 Day/Night: solid circles, larger1000/capped1+ values, selected Activity/Closeout, keyboard Enter, unchanged icon-only mobile actions and no horizontal overflow. Badge color pairs read from actual computed CSS. No real record mutation.
- Existing focused component tests:26/26 pass. CSS-only implementation: no JavaScript lint target changed; TypeScript and production build pass; protected CI remains the release gate. Impeccable reported only existing unrelated gray-on-color warnings elsewhere in index.css; changed badge rules clear. `git diff --check` clean.
- Existing payment-only closeout, missing timing Unknown, tenant/API/permission contracts and held ETS importer unchanged. No invoices, payments, financial records, providers or collectors touched.

## Release

- PR690 final head `c21ad14981866f32a27e630c433db76bbeaa12e8`; all seven checks PASS in41102684505. Normal protected squash merge `2472e45ae23ff8d0bb847aea6fbf82f77ea599bc`.
- Checked and merged trees both `231c1f554aab430281c0162bd743884cacc371a3`. Intervening docs-only main was integrated with both board histories preserved; reviewed CSS unchanged.
- Automatic Web `2f67b378-1889-4097-9953-5be769c59bcd` SUCCESS. Public build exact2472e45a, built2026-10-30T18:14:49.652Z. Readiness DB/Redis OK.
- Actual signed-in NC owner production desktop1280/mobile390 Day/Night: Closeout1 and Activity20 solid badges, computed Day `#006782/#ffffff` and Night `#7edbf0/#102534`; contrast6.44:1 and9.94:1. No horizontal overflow; compact mobile icon actions retained. Activity is loaded through the existing read-only tab. Original Day appearance and default viewport restored.
- Private screenshots `/tmp/db145-solid-badges-release/{day-mobile,night-desktop,night-mobile}.png`; not committed or published. No financial/source/provider/importer action. Owner local services stopped after exact PID/cwd confirmation; no live local preview claimed.
- Prior A2 completion and C3 draft contract remain separately recorded in PR688. This release does not implement the deferred redesign or dropdown follow-up.
