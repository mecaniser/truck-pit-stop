# DB-036 truck-by-day reconciliation

## October 19–20 priority gap

Exact persisted receipts independently verified source, normalized payload, company, scope, committed readback and unchanged replay. Counts below are newly saved unique trips. `Empty` means the complete source report returned no eligible trips for that truck; it is not an inferred zero from missing local records. PENDING-26 is now accepted through the separately reviewed exact provider/company/tenant binding.

| Truck | October 19 | October 20 |
| --- | ---: | ---: |
| 01 | 6 | 15 |
| 02 | 7 | 8 |
| 03 | 11 | 11 |
| 4 | Empty | Empty |
| 5 | Empty | Empty |
| 6 | 6 | 9 |
| 7 | 6 | Empty |
| 8 | 7 | 7 |
| 17 | 6 | 9 |
| 26 | 11 | 7 |
| 70 | Empty | Empty |
| 77 | Empty | 7 |
| 88 | 6 | 14 |
| 530 | 11 | 13 |
| 531 | 4 | Empty |
| 532 | Empty | Empty |
| 533 | 10 | 12 |
| 603 | 5 | 5 |
| 609 | 3 | 5 |
| 728 | 10 | 13 |
| 860 | 11 | 11 |
| 900 | 4 | 8 |

VIN-backed priority totals: **113 + 147 = 260 new unique trips**. The later bound-priority run adds unit26 **11 + 7 = 18** trips to these dates, producing124 and154 saved trips respectively. All 4,114 original rows retain their prior full-row digest. The unresolved directory and provider entries are two representations of unit 26, not two separate missing trucks.

## Historical scope still in progress

The April 1 baseline is being reconciled in bounded daily batches. Dates before each vehicle membership remain explicit exclusions. Today remains provisional. Historical acceptance requires every relevant truck/date classification, not merely a nonzero fleet total.

## PENDING-26 priority acceptance

PR651 bound-priority execution68ac30c3 exited2026-10-26T04:20:59Z. Independent gate accepted all10 exact daily receipts forOctober16–25:860 readback/unchanged-replay rows,43 new trips (42 unit26 and1 other truck),817 unchanged. Unit26 daily counts:16=2,17=4,18=0,19=11,20=7,21=7,22=4,23=7,24=0,25=0. Every full fleet report was nonempty and fully counted, so zero unit26 rows on18/24/25 are supported per-truck absences. All42 bound rows have null verified VIN, exact reviewed binding, valid full-trip interval and guarded-reader visibility. Earliest bound departure22:02UTC onOctober16 follows the21:42:51.108657UTC effective binding. No earlier binding was invented.

Post-run SQL:4433 total/4433 unique, original4114-row pre189-column projection digest unchanged. October16 remains partial eligibility for26; unit728 has a missing origin. October23 unit530 has a missing endpoint. October25 unit531/533 still have ongoing-trip exclusions. These are unresolved source/eligibility cases, not inferred idle days. Redacted evidence: /tmp/db036-bound-priority-receipts.jsonl and /tmp/db036-bound-priority-db.jsonl. Signed-in UI independently displayed unit26's October19 11segments/535.9mi and October20 7segments/733.3mi.

## Whole-report-empty verification hold

Independent review found the old capture accepts the first rendered empty state without a settled observation. No false-empty event is proven. Earlier whole-report-zero receipts require stronger revalidation before final historical acceptance. This does not invalidate populated reports with individual trucks absent. Older-history drain is held for the focused fix; no all-history completion claim.

The [220-row truck/day matrix](DB036_TRIP_RECONCILIATION_20261016_25.csv) contains aggregate counts and classifications for all22 current trucks acrossOctober16–25, with explicit exclusions and no raw locations or driver identities.

## Signed-in fleet acceptance (2026-10-26 04:33 UTC)

The parent independently verified unit 26 in the signed-in DieselBridge UI for October 19–25: 36 segments, 2,804.7 miles, 54h 14m, with daily segment counts 11/7/7/4/7/0/0. The same date range shows 699 segments across the fleet. This confirms the released reader displays the reconciled priority data; historical whole-report-empty verification remains held as described above.
