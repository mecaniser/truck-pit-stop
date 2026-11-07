# Motive daily worker recovery — November 7, 2026

## Current acceptance — November 7

**Recovery fixes are released; final November 3 trip private-source proof remains open.** Backend & Integrations is accountable. PR [831](https://github.com/mecaniser/truck-pit-stop/pull/831) merged `b5d569a454ccde1d1358bd01b25324a6c8d69939`; PR [832](https://github.com/mecaniser/truck-pit-stop/pull/832) merged `0bd0b375b61a0004c60b710f8a1feabc96b71c13`. Both passed all seven CI checks. Independent QA/Security accepted the login release, 150 focused trip-planning tests and both test-partition checks. Codex automations remain off; production cron schedules, restart policies and replica counts were preserved.

The shared failure was `login_legacy_redirect_loop` in the three legacy-only collectors. They now delegate to the unchanged reviewed native-login implementation and skip legacy submission only for strict authenticated=true. Drivers collection failures now retain their correct static classification. Trip planning uses durable scope-bound first-slot fairness, prioritizes the latest three closed New York dates and leaves today provisional. No credential, schema, membership, timestamp-policy or importer-proof changes were made.

| Result | Independently verified evidence | Limit |
| --- | --- | --- |
| Drivers | Three fresh verified journals; 21 unique captures (19+1+1),21 current available projections,0 assignment-unverified/pending; exact source/attempt/receipt chains and fresh typed database readback | Directory/rolling-source recovery does not prove historical daily safety coverage |
| Fuel |78 new rows for November 3–6:20/20/19/19. Eight exact date receipts and source/normalized hashes,89 prior row observations plus20 November 3 observations, fresh stored semantics/current projection/unique keys and saved replay counters pass; 0 pending/orphan intents | Explicit source absences and identity exceptions remain unresolved |
| Trips |580 new rows overall:559 for November 3–6 and21 provisional November 7 rows. Closed-date totals136/158/144/122, including one retained old November 3 row. Two14-date runs have exact source/receipt/SELECT proofs for 445 distinct saved IDs; their721 readback observations include replays, not721 new rows | Final November 3 adds135 rows with independent SQL checks, but its final private source/normalized/receipt audit was missed before container exit and remains open |

Post-exit SELECT-only QA found879 fuel rows/879 unique keys and5,863 trips/5,863 unique keys. All 78 new fuel and 580 new trip stored-payload self-digests, current unique membership/source-window checks and visible projections passed. These SQL checks do not replace the missing final November 3 trip source/receipt proof. The worker logged verified commit and normal one-day completion without rejections; that is worker evidence, not an independent reread of the private receipt.

All original full-column cohorts, including deleted rows, remain byte-equivalent under fixed capture cutoffs: fuel 801 MD5 `ae13bbe6c2568436a41b4de49c02a85e`; trips 5283 MD5 `a09fa94dfecdbeb93fa28aba4599f5c5`; drivers 619 MD5 `e6f2ae8ddf321462fcef0aed8576424c`. Expanded pre-final cohorts 859/5728/640 also retain exact full-row MD5s after the last135 trips and20 fuel rows were appended. No verified row was overwritten; duplicate source-key counts are zero.

### Explicit fuel source holds

| Motive unit | Dates | Verified status |
| --- | --- | --- |
| 5, 532, 533 |November 3–6|Observed source report absence; no zero reading inserted|
| 77 |November 5–6|Observed source report absence; November 3–4 readings accepted|
| 24, 42 |November 3–6|Unresolved identity; no guessed mapping or membership change|

Motive units 4 and 530 and DBN W900 have accepted November 3–6 fuel readings. A fresh in-cloud identity join confirms provider unit 900 maps to DBN W900 through exact stored verified-VIN/Vehicle-VIN equality; 4→4, 530→530 and 77→77 also match. No VIN values were exported. Final November 3 trip per-truck exceptions cannot be reconstructed from aggregate SQL. Historical endpoint/membership/coverage holds remain separate from this recent-data recovery.

### Controlled executions and restoration

Each source upload and actual recovery start had a once-only host fence, exact service/environment/source selectors and an idle check. Normal runs reconcile pending durable evidence before any fresh capture. Running source attestation passed71 modules for drivers/fuel and75 for the trip login/fairness release. The final one-day trip image was built from the independently verified full832 archive; a separate live module-hash attestation was not captured before exit.

| Execution | Deployment | Outcome |
| --- | --- | --- |
|Driver recovery `93e18d7b-a7a4-4f93-b541-723003dfa57f`|`072fbff4-86e4-4401-b030-edc1ebb37aab`|EXITED17:53:03UTC; runtime acceptance GO|
|Fuel automatic catch-up `c5ebc178-474c-4b0e-ab88-95ab8ca95738`|`e0decc40-ed17-4375-9bcb-af37f76869b6`|Seven dates completed; 89 exact row observations, including 31 unchanged historical readings|
|Trip login recovery `d5c6bc15-78cc-41c9-96e8-179f5649ddbe`|`7e01bfbe-154e-48c6-a802-d6f0a4d7db9e`|Fourteen dates completed, no rejected dates|
|Trip fairness recovery|`080a2094-6698-468a-a5c5-0b70c3359812`|Exact private14-day plan places November 4–6 before today; 445 distinct saved IDs across both trip runs independently verified|
|Fuel November 3 `08e83061-a136-42e4-8cde-83a61fb36fc8`|`23f4c8dd-c626-40bf-b65f-edced95c85be`|EXITED18:37:28UTC; 20 new rows independently source/receipt/SELECT verified|
|Trips November 3 `03014805-b82d-42f4-b7a6-5e12162f7569`|`6a6a35bc-f637-4e75-829b-00efded524d4`|EXITED18:39:42UTC; 135 appended/one old retained, final private-proof hold open|

The one-day runs use process-local date selectors and reviewed fail-closed preflights before replacing themselves with the unchanged normal worker. The fuel preflight pins the exact prior run through a preverified source hash and validates all seven outcomes; the trip preflight pins the exact 14-day plan and old November 3 provisional source. Both require fresh SELECT proof and zero pending/orphan intents, close database sessions and create exclusive fsynced private once fences before normal-worker execution. Ten fuel and 22 trip offline fault tests passed. These fences are intent, never coverage, and were not reset.

Railway retained a UI command override despite the archive command. This mismatch was detected before any collection; the unused build-only deployment was not triggered. Only the service start-command field was temporarily changed, read back exactly, then deployed build-only with full manifest/mount verification. After the one-day runs, both UI commands were restored and canonical source archives uploaded build-only, without another collection:

- Fuel canonical `32fd17a4-9c86-4b89-a2ac-5509e3e55dfb`:SUCCESS, image `sha256:8e1d47452c41366e67692f3cfe44e033805869b2b7c9d16db398fece968b2567`; complete original manifest and/data mount preserved.
- Trips canonical `2f793334-ceae-4c78-9a08-0cd1d23029cc`:SUCCESS, image `sha256:652f892124a414f9b1254babab1bb4ae1bd386977e69023b776619914959a428`; complete original manifest and /data mount preserved; build-only, no extra collection.

Latest observed natural health and sync runs also exited normally at 18:36:26 and18:49:16UTC. Their worker images were not changed. This is a bounded observation, not proof of sustained five-worker recovery or complete historical coverage.

### Remaining acceptance hold

Release & Reliability returns the final November 3 trip private-proof gate to Backend & Integrations. During legitimate natural trip activity, independently validate the saved November 3 source/normalized/receipt hashes, exact scope/day and stored IDs, provider-level exclusions and replay/readback counters. Do not recapture November 3, start a container solely for inspection, invent endpoints/timestamps, clear the once fence, or create/resume a Codex automation. The next normal trip schedule is November 8 09:15UTC. This hold is not a claim that the135 saved trips failed or are duplicates.

Safe local audit bundles contain only dates, unit labels, counts, UUIDs, hashes and booleans; provider VINs, endpoints, metrics, driver PII and secrets were not exported. No local product-browser readiness is claimed; isolated local configuration remained unavailable and unrelated local services were preserved.

## Earlier intake and implementation evidence

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

## Login release and controlled recovery

PR [831](https://github.com/mecaniser/truck-pit-stop/pull/831) passed all seven protected CI checks and independent QA/Security, then merged as `b5d569a454ccde1d1358bd01b25324a6c8d69939`. Each fresh archive's 3,079 tracked files (apart from the explicit canonical railway.json) independently match that merge. Full service manifests and mounts equal their prior deployments; commands, schedules, NEVER restart and replica1 are unchanged. Each upload occurred once with no active execution, produced buildOnly=true, and was followed by one authorized actual collection/reconciliation run. No Codex automation was created or resumed.

| Worker | Exact deployment | Running module attestation | Controlled execution |
| --- | --- | --- | --- |
| Drivers | `072fbff4-86e4-4401-b030-edc1ebb37aab` |71/71 exact|`93e18d7b-a7a4-4f93-b541-723003dfa57f`, 17:48:32–17:53:03 UTC, EXITED|
| Fuel | `e0decc40-ed17-4375-9bcb-af37f76869b6` |71/71 exact|`c5ebc178-474c-4b0e-ab88-95ab8ca95738`, started17:48:35UTC|
| Trips | `7e01bfbe-154e-48c6-a802-d6f0a4d7db9e` |75/75 exact|`d5c6bc15-78cc-41c9-96e8-179f5649ddbe`, 17:48:39–17:55:37UTC, EXITED|

Fresh drivers source17:48:52–17:52:59UTC SHA `9e168e63c563d0617a3f681f9b4af50c89b7e2142dc39ed8df63fb135c942f39` was independently reconciled after exit via the naturally active API. Scope allowlist came only from prior verified November3 journals, pinned77Cargo tenant/company and three enabled customers, crosschecked against pre-recovery32/24/23 journal counts and fleet hashes. Three new verified journals have valid exact-source/attempt/receipt identity and hash chains. Fresh SELECTs prove19+1+1=21 persisted typed captures and current projections; worker readback/replay21, assignment_unverified0, unique capture IDs and pending commits0. No import or replay was performed by the independent auditor. This is current directory/rolling-source recovery, not historical daily safety coverage.

The stronger all-tenant original-column cohorts include deleted rows and fixed November3 capture cutoffs: fuel801 MD5 `ae13bbe6c2568436a41b4de49c02a85e`; trips5283 MD5 `a09fa94dfecdbeb93fa28aba4599f5c5`; drivers619 MD5 `e6f2ae8ddf321462fcef0aed8576424c`. Post-driver/fuel-start comparison preserved all three exactly. Legitimate later inserts are excluded from these fixed cohorts. Final fuel/trip missed-day receipt acceptance remains in progress.

## Trip planning follow-up contract

The old planner reserves recent slots but appends them after up to11 old days and prepends retries. Collectors execute this order under30 minutes; reserving slots does not guarantee recent collection capacity. Add durable private scope-bound automatic first-slot alternation and least-recently-selected candidates, reserving both lanes near the front. Recent means the latest three CLOSED New York dates: on November7, November4–6; today is optional provisional capacity after the closed dates and backlog head. At minimum3 slots rotate two closed dates plus one backlog date; the default remains14. A scheduling marker proves selection only; later unstarted slots do not advance fairness or coverage. Pending receipt recovery remains first. Only existing-mapping certified closed days and terminal ineligible days can be skipped; provisional/unresolved days remain visible. Explicit ranges remain chronological and outside automatic fairness. Keep default14/bounds, source/identity/membership/import/quarantine rules and unchanged production configuration. Independent gates and exact release/runtime verification are required before this planning change is Done.

Owner fairness checks:88 focused Python tests pass, including six one-window-capacity invocations/restarts, rejected-date rotation, exact private/corrupt/foreign/symlink markers, original coverage/import proofs, November4 regression, New York midnight/DST, minimum3 and provisional-only fallback. Four trip suites are included in critical protected CI; independent exact-candidate review remains pending. Fresh drivers API correction separately proves21 available and0 assignment-unverified projections; available projections point to the exact new capture IDs.
