# Direct Motive source hold inspection — October 30, 2026

Backend & Integrations accountable. Read-only investigation of trucks **4, 77, 530, 5, 532 and W900**. No importer, repair write, manual worker trigger, authentication/configuration change or Codex automation was used. This is an operational evidence report; no application implementation or new release is required.

## Direct visible-source check

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

Additional saved-panel inspection found absolute date candidates for 4 (Oct13 5:34PM), 530 (Oct28 5:05PM), and 77 (Oct29 9:37PM), all2026. Their event ownership remains under investigation. Missing `.current-location-status` alone does not establish that Motive provides no location timestamp. Keep the current exclusions until location ownership, time zone, stable source identity and interval/history safety are verified. For **4/77/530**, obtain a source-owned absolute last-location timestamp or restore Motive’s timestamped reporting; then the normal collector can validate the complete observation interval against history and membership. For **5/532**, resolve the gateway assignment/reporting shown by Motive and wait for an actual timestamped position. This investigation does not authorize device reassignment or invent a device fault diagnosis. No verified historical row is changed to clear a hold.

Codex automation records `hourly-motive-map-coordinates`, `daily-motive-trip-refresh` and `finish-driver-record-release` remain **PAUSED**. The old heartbeat remains absent. No new recurring work was created. Existing Railway production schedules remain unchanged.
