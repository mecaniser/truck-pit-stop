# Sync hold reconciliation — October 30, 2026

Backend & Integrations accountable. This report is field-specific: a receipt can report a successful speed update while its location remains held. The retained complete 23-entry source/receipt from run `20261030T162539Z-b6c6a7ab-575a-42e5-b941-2bfd5424d83b` finished at 12:29 Eastern / 16:29 UTC. Exact hashes, company guards and source-prefix identities were checked before SELECT-only inspection.

## Timestamped history holds: safe candidates

Each of the following 16 trucks has 1,001 location snapshots in the original query scope. Only zero to five can affect the incoming reading; the rest are strictly earlier known observations. An operator SELECT-only comparison loaded complete history and compared it with independently filtered SQL: all sixteen produce the same `update` disposition. This is a concrete dry plan, not proof of an applied repair.

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

The exact source VIN identifies one active local truck. Its canonical customer matches 77 CARGO LLC and is fleet-enabled, but there are **zero membership records, including deleted history, and no operating-authority records**. A customer/owner association alone is not an operating-fleet assignment. No duplicate unit was merged or membership backdated. The human is asked whether to enroll this exact Motive truck prospectively; until confirmed, its source reading remains `outside_current_fleet`. Historical readings remain excluded under a prospective enrollment.

## Source unavailable

**5 and 532:** Motive reports `provider_location_unavailable`; there is no location reading to repair. Truck 70 is an ordinary unchanged reading and is not a hold.

## Preservation baseline and gates

The SELECT-only baseline at `2026-10-30T16:31:27.856135+00:00` freezes **25,613 telemetry snapshots**, digest `abffaa77f7b71533ab24dd411b7a5942`, and canonical location/identity fields for the 22 affected local vehicles, digest `174ba1d32ff156d9de0a5a29f34a5357`. The original fixed cohort, not a growing whole-table count, must remain unchanged after legitimate new snapshots are appended.

The scoped implementation and independent QA/Security each passed the documented 107 focused Python cases, including actual SQL/import overflow/interval/isolation tests, exact replay, later-read same-observation duplicate prevention and immutable speed-only/location supplements. CI, merge, deployment, prospective source/receipt/actual saved-value acceptance, and frozen-cohort readback remain pending. No production data write has been performed for this reconciliation. Codex automations remain off.
