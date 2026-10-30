# Direct Motive source hold inspection — October 30, 2026

Backend & Integrations accountable; Release & Reliability owns verified release. Direct diagnostic inspections were read-only. The reviewed collector fix was deployed through the normal pipeline; full-fleet natural scheduled collectors performed the imports. No diagnostic subset, manual collection/import trigger, authentication/configuration change or Codex automation was used. The initial discovery sections below are superseded by the verified production results.

## Verified production result

PR [#691](https://github.com/mecaniser/truck-pit-stop/pull/691) merged as `0f369f980fdee3c2f37981082f238630ae0b64c5` after all seven CI checks passed on exact head `84f82853050d6bf8efd3a3f8b5f6c8a6eec2255b` (run `41105873759`). Independent source QA/Security passed **170 Node/isolated Chromium checks** and **112 Python data regression cases**, zero skipped. Collector SHA-256 `aa95323f0f6c68d070e433d767cc412590954df8243463124c755119c525190f` also passed against actual retained Motive markup.

| Truck | Verified Motive observation, Eastern | Production outcome |
| --- | --- | --- |
| 4 | October 13, 2026, 5:34 p.m. EDT | Known minute interval; unchanged against one existing matching saved location. No new snapshot. |
| 77 | October 29, 2026, 9:37 p.m. EDT | Known minute interval; unchanged against one existing matching saved location. No new snapshot. |
| 530 | October 28, 2026, 5:05 p.m. EDT | One new immutable location-only snapshot; speed omitted. Exactly one matching location row. |
| W900 | October 30, 2026, 2:37 p.m. EDT | Location and speed update accepted and verified in the same full-fleet run. |
| 5, 532 | No provider location | Motive explicitly requires a vehicle gateway. Both remain excluded; device assignment/reporting must be resolved in Motive. No fabricated coordinates or device reassignment. |

These preserve Motive’s actual observation dates; old observations are not presented as current GPS.

Deployment `50b343b5-514c-4132-b9eb-89037433e67d` is SUCCESS, image `sha256:49b2a0fce2a6efa4b8a3155d9c7acbeec06ddde7a3cec53c5776a3c7032ba089`. A fresh exact-merge archive was uploaded once during a confirmed natural idle window. Full manifest, `/data` mount and build-only mode match the prior release. Command `python -m scripts.motive_sync.run_worker`, schedule `*/5 * * * *`, restart `NEVER` and one replica remain unchanged. Eighteen runtime modules and the tenant/actor/company scope match the reviewed release; no container was started for SSH.

First natural writer `20261030T183519Z-dc6a91e0-9a39-4d93-a4f9-2229eb8a3217` completed at `2026-10-30T18:38:34.909450806Z`. A different subsequently running cron execution, `3d682296-96f2-4bac-ab98-f8dacbc9167d`, supplied the read-only audit after completion. Exact committed **23-source / 23-receipt** acceptance checked **15 actual saved bodies**, source-derived and stored request digests, actor/tenant/VIN/membership intervals and unique saved request keys. Truck 530’s row is created in this exact run and captured after release; trucks 4/77 have no new receipt IDs. Source SHA-256 `d88c421b06f286d70566b81a51a28e90897abce2a807d65aab87395aa10d619a`; receipt SHA-256 `16f1b16a3e1503029c40b7230620e1dcb56037970691da5d1de7caa74fb99e14`.

All **25,613 baseline snapshots** retain digest `abffaa77f7b71533ab24dd411b7a5942`; all **22 canonical vehicle records** retain digest `174ba1d32ff156d9de0a5a29f34a5357`. Independent first production runtime gate **GO**. The later natural collection passed the separate no-duplicate gate below. No replay or manual collection was invoked.

## Initial direct visible-source check

A six-target visible Motive UI inspection completed **1:57:53–1:59:09 p.m. Eastern** (17:57:53–17:59:09 UTC). The company was visibly verified before and after, the full directory had 23 vehicles, and all six exact source identities passed the existing VIN/live-provider guards. Eighteen runtime module hashes matched the reviewed deployed source. The diagnostic reused the deployed visible-UI capture logic in memory, including stable coordinate/time and identity checks, without changing application files. It wrote a separate private diagnostic under nested `operator_tools`, never a normal collector intent/source directory. It did not invoke an importer or database writer.

| Truck | Direct Motive result | Safe disposition |
| --- | --- | --- |
| 4 | Coordinates present; no observation-time status element, no raw timestamp or source age, on both bounded reads. | Keep `prior_time_unknown`; reading time cannot substitute for observation time. |
| 77 | Same missing observation-time evidence on both reads. | Keep `prior_time_unknown`. |
| 530 | Coordinates present but no observation-time status or raw timestamp on both reads; existing history exceeds the bounded review scope. | Keep `history_review_required`; unknown-time source cannot safely filter prior history. |
| 5 | Motive explicitly displays **Add Vehicle Gateway to see location data**; no captured location. | Keep `provider_location_unavailable`; verify the vehicle’s gateway assignment/reporting in Motive before expecting location collection. |
| 532 | Same explicit Motive gateway message, no captured location. | Same source-side action; do not synthesize location or infer zero activity. |
| W900 (Motive unit 900) | Stable timestamped coordinates; source tooltip **Oct 30, 2026, 1:58 PM**, minute interval 17:58–17:59 UTC. | No longer held. Earlier natural-run recovery independently verified below; diagnostic subset is not imported again. |

Private diagnostic source file SHA-256: `f10976a3f4961a7b157d2e36d7f24f02de21ec0f8edf314fb076816d3ded6b1a`. Raw source coordinates, addresses, VINs and panel text remain in the cloud. Exported evidence contains only units, status/precision/reasons, timestamp values and presence/count booleans.

The first SSH diagnostic attempt returned a connection timeout. A separate read-only reconciliation confirmed the diagnostic cloud directory did not exist before the next attempt. The successful attempt uses exclusive directory creation; no ambiguous partial diagnostic was overwritten or blindly rerun. It completed with company guards and process exit zero.

## W900 natural recovery and immutable-data acceptance

The retained complete source/receipt for natural run `20261030T175017Z-200af1d8-dc12-4e5b-8a59-4413656bb0fa` contains W900 location and speed updates observed at **1:54 p.m. Eastern / 17:54 UTC**. This predates and is independent of the six-target read-only diagnostic. Its saved location was created in that natural run, matches actual Motive-derived stored values and request digest, and has a unique saved request key. There is no need for another capture/import to clear the earlier transient `source_changed_during_capture` hold; that failed capture remains excluded.

Complete scope/company/source-prefix acceptance: **23 source rows / 23 receipt entries**, **15 actual saved readbacks**, source-request and actual persisted-value digests match, unique saved request keys. Source SHA-256 `17efd5b5ac31df865c41c5dd5f4b85053aba037f7fa467a55a45b6691f2e0ee4`; receipt SHA-256 `77b5f88311a91261ab3e628ddf6b03076e4972beb955138c05a0c8c99afdabaf`.

The original fixed **25,613 snapshot** cohort retains digest `abffaa77f7b71533ab24dd411b7a5942`; all **22 canonical vehicle records** retain digest `174ba1d32ff156d9de0a5a29f34a5357`. The acceptance transaction enforced READ ONLY. Natural scheduled appends are distinct from this investigation, which performed no database writes. No live replay/import was launched as a verification test.

## Remaining external evidence and next action

Only **5 and 532** remain source-blocked: Motive explicitly displays **Add Vehicle Gateway to see location data** and provides no location. Verify gateway assignment and reporting for these exact vehicles in Motive. The inspection does not establish whether a device is absent, disconnected or assigned incorrectly, and does not authorize guessing a device identity or changing an assignment. No synthetic position, timestamp or zero activity was imported.

The inline-date defects for 4/77/530 are resolved through the verified collector release, preserving their real source dates rather than retimestamping them. W900’s transient source-change hold recovered naturally.

Codex automation records `hourly-motive-map-coordinates`, `daily-motive-trip-refresh` and `finish-driver-record-release` remain **PAUSED** on fresh final inspection; the old heartbeat file is absent. No new recurring work was created. Existing Railway production schedules remain unchanged. All owned local bounded observer/reader processes completed.

## Inline timestamp contract and safe dry plan

A follow-up three-target visible-UI probe completed **2:06:44–2:07:36 p.m. Eastern**, with full company/directory/identity guards. Source file SHA-256 `7ffda42cbff57ae764246b063c54b69e36f56d7f90f28387d37f02121d973bca`. The absolute date is a visible `span.upper-case` in a direct flex/body-medium/grey-70 row within the exact `current-location` component that owns the single location/copy-coordinates control. Device-disconnection text lies outside this component. This is a second timestamp layout that the collector currently misses; missing `.current-location-status` is not sufficient evidence of absent source time.

The narrow contract permits this inline fallback only when the tooltip status selector is absent. Require one visible location section/component, the same unique owned coordinate control, one exact visible leaf date in the grounded direct-child row, and no unrelated/ambiguous/hidden dates or disconnected/device-update semantics within the location component. Normalize case and whitespace only through the existing New York date parser. Preserve minute precision and DST/future/staleness rejection, identity/company checks, and two-coordinate/two-time stability. The inline date proves location time only: omit speed, with explicit provenance, rather than assigning that date to another measurement. Tooltip behavior and all importer/history/membership/idempotency guards remain unchanged.

Before implementation, a hash-pinned READ ONLY comparison normalized these source dates, verified exact vehicle identity and full membership/source-read/observation interval coverage, and compared complete history with the existing bounded relevant-history query:

| Truck | Verified Motive observation (Eastern) | Complete/relevant history | Existing location decision |
| --- | --- | --- | --- |
| 4 | October 13, 2026, 5:34 p.m. | 3 / 1 | Unchanged: same saved observation and coordinates; no new snapshot needed. |
| 77 | October 29, 2026, 9:37 p.m. | 25 / 1 | Unchanged: same saved observation and coordinates. |
| 530 | October 28, 2026, 5:05 p.m. | 1,001 / 3 | Update: all three unknown-observation prior captures are strictly earlier than this verified incoming observation, as already handled by existing disposition policy. |

All three complete-history and bounded decisions agree. No unknown row was assigned a new timestamp or overwritten; diagnostic subsets are not production importer inputs. Acceptance required focused fixture and real DOM/Chromium negatives, independent QA/Security, protected CI, exact deployed bytes/config and a subsequent full natural source/receipt/actual readback. These gates passed in the verified release. The initial five-source-blocker classification above is superseded by this grounded contract; only 5 and 532 have confirmed gateway-source blockers.

## Source gate and real provider markup

The actual inline date leaf includes an explicit **EDT** suffix, confirmed for all three vehicles from retained private markup. The collector canonicalizes the date for the existing parser while retaining the exact displayed date/zone as `timestampSourceText` and `timestampBasis=inline_location`. Only explicit EDT/EST consistent with the uniquely resolved America/New_York minute is permitted; mismatch, unsupported zones and DST gaps/folds remain unknown. Full visible owner-row and leaf date text must agree; device-event sibling labels are rejected. Source text and timestamp basis must remain stable across coordinate copies. Inline location dates do not timestamp speed.

Owner commits `ca8e8ba7` and `d661f619` passed **170 Node/isolated Chromium checks**, zero failures/skips, including grounded three-vehicle EDT rows, EST winter, mismatches, DST negatives, hidden/ambiguous/unrelated dates, device-event labels, actual date/basis/source-text mutation, preserved login/health/tasks behavior and existing collector tests. Protected CI includes these actual DOM fixtures after Playwright installation. A cloud-only isolated Chromium reader also accepted the **actual retained provider markup** for all three vehicles, with exactly the minute intervals shown above and exact EDT provenance. Synthetic fixtures alone are not the runtime acceptance claim.

Independent QA/Security, protected CI, merge/deploy parity, the first complete natural 23-vehicle source/receipt/actual persisted-value proof and later-read duplicate suppression all passed as recorded above and below. No private diagnostic subset will be imported, and no new collection is triggered just for verification. Local runtime controller dry-run is blocked by missing approved backend/.env and Vite in the isolated worktree; no service, listener or secret was changed. Product browser QA is not claimed; source/isolated DOM tests and production natural collection are distinct evidence.

## Later scheduled no-duplicate verification

The next normal collection, `20261030T184008Z-6e105a59-bb0f-407f-ae85-5410006f3c18`, completed at `18:43:57.074365282 UTC`. Its exact receipt is linked by `worker_complete` on the same verified deployment; the corresponding cron execution began at 18:40:08, after the first writer completed. Complete **23-entry source/company/receipt** validation shows **4, 77 and 530 unchanged**, no new snapshot IDs for those rows, the same source observation intervals and coordinates, and **exactly one** matching saved location for each. Truck 530 retains the first run’s original saved ID with no speed value.

Source SHA-256 `de9abc365bffb675f8a9342461e0e96691d5612fa6b4574129a53b37bc271860`; receipt SHA-256 `81c9b858e31b99969bf9fac17e240b76124acffa3f9c4eade55439d67fcd23e8`.

The initial read emitted every acceptance marker after database rollback and engine disposal, then SSH returned 1 as the scheduled container exited, without an audit traceback. A fresh read-only reconciliation of the **same committed artifacts** during subsequent legitimate activity completed with transport/process **exit 0** at 2026-10-30T18:46:11.276808+00:00. No collector, importer or replay was retriggered. This proves observed later-read duplicate suppression, separately from deterministic-key tests; it is not a claim that a manual production replay was invoked.

Independent final QA/Security/runtime gate **GO**: source tests, actual provider markup, exact image/module/config/scope checks, first persisted-row acceptance, frozen-data preservation and clean later-read no-duplicate reconciliation all passed. Source/device holds **5/532 remain OPEN**. No all-workers or all-trucks-current claim is made.
