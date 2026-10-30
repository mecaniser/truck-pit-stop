# Sync hold reconciliation — October 30, 2026

Backend & Integrations accountable. This report is field-specific: a receipt can report a successful speed update while its location remains held. The retained complete 23-entry source/receipt from run `20261030T162539Z-b6c6a7ab-575a-42e5-b941-2bfd5424d83b` finished at 12:29 Eastern / 16:29 UTC. Exact hashes, company guards and source-prefix identities were checked before SELECT-only inspection.

## Timestamped history holds: repaired

Each of the following 16 trucks has 1,001 location snapshots in the original query scope. Only zero to five can affect the incoming reading; the rest are strictly earlier known observations. An operator SELECT-only comparison loaded complete history and compared it with independently filtered SQL: all sixteen produce the same `update` disposition. This pre-release dry plan was subsequently applied through the verified natural-run release described below.

| Truck | October 30 source observation, Eastern (minute precision) | Potentially relevant rows |
| --- | --- | ---: |
| 01 | 12:25 | 5 |
| 02 | 12:25 | 3 |
| 03 | 11:51 | 3 |
| 17 | 12:26 | 0 |
| 26 | 12:16 | 0 |
| 531 | 11:26 | 3 |
| 533 | 12:04 | 0 |
| 6 | 12:26 | 3 |
| 603 | 12:27 | 0 |
| 609 | 12:24 | 4 |
| 7 | 12:27 | 3 |
| 728 | 12:28 | 0 |
| 8 | 12:26 | 2 |
| 860 | 12:27 | 3 |
| 88 | 12:13 | 3 |
| W900 | 12:28 | 3 |

Some of these trucks were still receiving speed-only snapshots, masking the location backlog in job-level totals. The fix retains unknown-time, overlapping, later and conflicting observations before applying the existing 1,001-row bound. It also preserves the original canonical fallback, tenant/membership scopes, 30-day rule, source identity and immutable request semantics. No history is deleted and no review limit is raised.

## Timestamp holds: remain excluded

- **4, 77:** current source location lacks a verified observation timestamp (`status_unavailable`). Existing timestamped history cannot safely be ordered against it; preserve `prior_time_unknown`.
- **530:** also has no verified source timestamp and more than 1,000 historical rows. Its original full-query history hold remains intact. An unbounded comparison would still require unknown-time review; it is not a safe write candidate.

Capture/read time is not observation time. No timestamps or coordinates are fabricated, and no old verified position is overwritten to make these entries look current.

## Membership: truck 9

The exact source VIN identifies one active local truck. Its canonical customer matches 77 CARGO LLC and is fleet-enabled, but there are **zero membership records, including deleted history, and no operating-authority records**. A customer/owner association alone is not an operating-fleet assignment. No duplicate unit was merged or membership backdated. The human explicitly approved enrolling this exact Motive truck prospectively from now onward. The separately gated operation must add one membership and one operator relationship only, preserve owner/payer/billing data and use a post-lock server timestamp. Membership-interval guard PR #686 prevents older readings from failing the entire batch. Enrollment committed once at **2026-10-30 17:21:13.099577 UTC / 1:21:13 p.m. Eastern**, with fresh readback confirming one membership and one non-primary operator relationship. Historical readings stay excluded.

## Source unavailable

**5 and 532:** Motive reports `provider_location_unavailable`; there is no location reading to repair. Truck 70 was unchanged in the earlier receipt and updated normally in the later receipt; it is not a hold.

## Preservation baseline and gates

The SELECT-only baseline at `2026-10-30T16:31:27.856135+00:00` freezes **25,613 telemetry snapshots**, digest `abffaa77f7b71533ab24dd411b7a5942`, and canonical location/identity fields for the 22 affected local vehicles, digest `174ba1d32ff156d9de0a5a29f34a5357`. The original fixed cohort, not a growing whole-table count, must remain unchanged after legitimate new snapshots are appended.

The scoped implementation and independent QA/Security each passed the documented 107 focused Python cases, including actual SQL/import overflow/interval/isolation tests, exact replay, later-read same-observation duplicate prevention and immutable speed-only/location supplements. CI, merge, deployment, prospective source/receipt/actual saved-value acceptance and frozen-cohort readback passed as recorded below. Production changes were limited to append-only collector snapshots and the explicitly approved prospective membership/operator pair. Codex automations remain off.

## Verified history-query release

PR #685 passed all seven CI checks and merged as `7f5f821c5a0cd1016c77d0b2c15cfba9ef23a5c1`. Deployment `07129ca8-4dfd-4ba4-8551-2acd157e6d11` SUCCESS, image `b473f95756624ec3b0e3e9705a963d0e3ab8d71804252b2da56ff2ae34d1b576`; full canonical manifest/mount and scope are unchanged, with twelve exact module hashes checked against the reviewed merge.

The first natural run `20261030T170036Z-a7a4daa1-8f54-460b-a62d-828aaf13bc56` completed at 17:04 UTC. Its exact receipt path from the new-image execution pinned the audit target. During the next natural active container, SELECT-only acceptance verified **all 16 target location observations**: each was created in that run after release and matched source-derived request identities, actual saved values, tenant/actor/membership/VIN and unique request keys. All 25,613 frozen snapshots and 22 canonical location records retained their original digests. Independent runtime QA/Security GO closed this query-repair gate.

Source SHA-256 `9f445792681e5a511feeda35b3a4b29d2c1d1c90f05b481eb872ca021e3d7bba`; receipt SHA-256 `79c2adaf8273e0ff083817bcc89ebbf79bb4ec5ceb3daa0b01aaf766cafc0122`. The source and receipt each contain 23 entries. Post-release field-level classification confirms 16 location updates; 4/77 remain unknown-time, 530 remains unknown-time/history-held, 5/532 remain unavailable, 70 unchanged, and 9 outside the fleet before enrollment.

These are newly saved authoritative source observations, not a claim that every GPS reading is newly observed: original source times are preserved, including older legitimate parked-truck readings. No fresh replay invocation or later UI projection is inferred from the read-only audit. No manual collection trigger was used.

## Verified prospective membership and interval guard

PR #686 passed all seven CI checks and merged as `5a14da4381a86fcb3360e336a71043f2be5b03e7`. Deployment `4d37463e-87ad-44c2-ad4e-84ec301d4d51`, image `7b71212cc0a11576b53e4427bb49fa6435922b7d04bab2fe68186a1490ec31fa`, is SUCCESS; eighteen deployed module hashes match the merge and the complete manifest/mount/scope remain unchanged. Owner and independent QA/Security each passed 112 focused Python cases, zero skipped. The guard converts only uncovered source-read or observation membership intervals into per-row exclusions; identity, auth, ambiguous membership and source-binding failures retain their existing behavior.

The human explicitly approved enrolling exact Motive truck 9 into 77 CARGO LLC prospectively. The independently reviewed operator capsule and 24 tests verify immutable plan/intent recovery, advisory and row locks, post-lock server time, no financial side effects and no mutation retry after intent. Exactly one approved operation committed membership `214c2d86-0b15-44da-bc0b-d4a574b45966` and operator relationship `7635aff6-9d01-44a5-9da8-72bee9900dbb`, both effective `2026-10-30T17:21:13.099577+00:00`. A separate read-only reconciliation confirms the same IDs, effective time and committed state. All **25,687 pre-enrollment snapshots** retain SHA-256 `baa7598fcacfdb3e9f6d8a240a969b3fe757e25f65e9c01f27a7817e48911f8b`; canonical vehicle/customer, ownership, payer and billing relationships are unchanged. No historical enrollment or reading was backdated.

Natural run `20261030T172100Z-8c7edf77-c77e-4ef6-9f3c-936fe9ef8ebd` completed at `17:25:07.823908 UTC`. Its exact retained completed source/receipt was inspected in a legitimately active container. Truck **9** has verified location and speed updates from its **17:24 UTC / 1:24 p.m. Eastern** observation, with the full observation interval and source-read time covered by the new membership. The complete 23-entry receipt has 14 saved readbacks with actual persisted-value/source-request digests and unique saved request keys verified; all 25,613 original snapshots and 22 canonical records still match their original fixed-cohort digests. Source SHA-256 `7eff6969ddac996f44022fc28ab0c4cbeb1edd3d3680086a4957ad8360534c5b`; receipt SHA-256 `e8710ff67c5640611737d73ab981fab23a3ea8d660fd7c838d72b5a163ff8e13`.

The later receipt also verifies normal unchanged handling for trucks 531, 533 and 88, rather than creating new copies of their earlier source observations. Remaining source holds are **4/77** unknown observation time, **530** unknown time/history review, and **5/532** unavailable source location. The later capture also safely held **W900** with `source_changed_during_capture`; its earlier history-repaired reading was accepted, but this transient capture is not imported. Truck 70 updated normally. Tests exercise exact replay and later-read duplicate prevention; the production audit verifies stored unique request identities and values without launching an additional write/replay. No manual collector trigger, credential change, schedule change or Codex automation was used. Independent post-enrollment runtime QA/Security gave DATA RUNTIME GO after checking these source/receipt and membership-interval proofs. The bounded local read-only observers were stopped or completed.
