# Motive daily worker recovery — November 7, 2026

Backend & Integrations accountable; Release & Reliability owns production acceptance. Codex automations remain paused. Existing dirty main checkout and shared local services are preserved. Isolated runtime dry-run reports missing approved backend/.env and Vite; no local product browser or full-stack readiness is claimed.

## Observed failure and acceptance contract

Trips 09:18 UTC, fuel 13:34 UTC and drivers 13:50 UTC failed at `login_legacy_redirect` before credential entry/source capture. Their collectors still use the legacy-only preparation path. The working health/location path already supports reviewed native lookup/password forms, exact native ownership and account checks, bounded pre-credential recovery, challenge/foreign-origin rejection and one credential submission. A successful process exit or green deployment badge is not data acceptance.

Adopt that exact existing implementation for trips, fuel and drivers through a small worker-specific adapter. Keep context timezone/locale and diagnostics static; validate the worker label before browser use. Each consumer must skip its existing legacy credential fill/submit only when preparation returns `authenticated === true`. Other failures remain terminal. No auth helper guard, timeout, company/VIN/member/assignment/report completeness rule, importer, coverage, schedule, credential or schema change is authorized by this contract. Native password flow must never be followed by a second legacy submit. Existing health and location behavior must remain unchanged.

Focused validation: direct legacy and native-success caller paths for all three actual collectors; strict boolean success; failure propagation without credential entry; origin/challenge/ambiguous-form/account/value/deadline negatives remain covered by the unchanged reviewed auth suite; correct worker diagnostics; company verification remains after authentication. Independent QA/Security and protected CI precede exact-source deployment.

Drivers currently masks collection subprocess errors as `invalid_fleet_configuration`; distinguish a static collection failure from validated configuration errors without logging arbitrary exception text. Preserve per-fleet authorization, locks, pending journal recovery and collection/import contracts.

## Recovery gates

Before any fresh provider capture, use existing exact-intent recovery under the domain's locks. Ambiguous/orphan intents block new capture. Receipt coverage is distinct from rows-per-day and scheduling markers. Preserve original accepted cohorts and immutable conflicts; no missing report becomes zero, no membership is backdated, and no verified reading is overwritten.

Fuel: inspect private scope, verified day ledger, explicit exceptions and fair bounded automatic plan; verify source/normalized hashes, saved IDs, persisted values, unique keys and subsequent unchanged recovery/read. Fuel catch-up was already deployed and accepted October 29; no duplicate deployment or replay of those completed batches is needed.

Trips: inspect scope/verified-day ledger and saved source evidence before selecting missed closed dates. Preserve populated report completeness, endpoint quarantine, membership and binding gates. Do not repeat previously accepted historical days or invent endpoints.

Drivers: audit scoped database journals and saved IDs before fresh collection. Existing pending commit recovery takes precedence and returns without collecting again. Its directory/rolling summaries/sampled recent events do not establish historical daily safety coverage; no historical backfill claim without a separate source contract.

A recovery execution must be an authorized normal collection/reconciliation, never a container started solely for SSH. No blind retry, schedule/restart/credential change or recurring Codex observer. Runtime acceptance requires exact source/image/module/config/scope parity and complete source/receipt/persisted readback with duplicate-safe evidence. Notify remaining blockers and provable collection gaps explicitly.

## Current saved-data audit and source verification

Read-only checks through the already-running API confirmed exact enabled/undeleted 77 CARGO customer identity inside the cloud. Fuel has 740 rows/740 unique source keys, latest report November2 and capture November3 13:50:32UTC; no saved rows November3–6. Trips has 4,927 rows/4,927 immutable keys, latest capture November3 09:28:28UTC and no persisted UTC departures November4–6. These are potential gaps, not provider absence or full-day coverage. Driver journals show79 verified commits,0 pending commits and one validated dry run; last three-fleet source finished November3 13:52:12UTC. Drivers do not have a historical day-range collection contract.

Full persisted-column preservation baselines were frozen with fixed capture cutoffs and include deleted rows: exact77Cargo fuel740 MD5 `b6996515991a4c612f03ab310b05e20b`; trips4927 MD5 `079b116cdc30ad3689910f64aaad161c`; all tenant driver capture fleets619 MD5 `e6f2ae8ddf321462fcef0aed8576424c`. New legitimate inserts after these fixed November3 cutoffs are excluded from later comparisons. No measurement, VIN, coordinate or raw payload was exported.

Owner validation: 465 Node/isolated Chromium auth/collector/task regressions pass after resolving both explicit relative and bare Playwright test dependency paths;22 diagnostic boundary/fault-injection tests pass, including delegated trips/fuel/drivers bootstrap and static no-secret errors;25 driver Python fleet-lock/recovery/classification tests pass. Existing health/native/login/context implementation is byte-for-byte unchanged. Actual three-consumer tests prove strict boolean success, no legacy re-submit after native authentication, error propagation and post-auth company verification. Independent final gate, protected CI and production source/receipt/data acceptance remain required.
