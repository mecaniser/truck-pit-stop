# DB-036 truck-by-day reconciliation

## October 19–20 priority gap

Exact persisted receipts independently verified source, normalized payload, company, scope, committed readback and unchanged replay. Counts below are newly saved unique trips. `Empty` means the complete source report returned no eligible trips for that truck; it is not an inferred zero from missing local records. PENDING-26 remains unresolved until the separately reviewed binding release.

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
| 26 | Pending binding | Pending binding |
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

Totals: **113 + 147 = 260 new unique trips**. All 4,114 original rows retain their prior full-row digest. The unresolved directory and provider entries are two representations of unit 26, not two separate missing trucks.

## Historical scope still in progress

The April 1 baseline is being reconciled in bounded daily batches. Dates before each vehicle membership remain explicit exclusions. Today remains provisional. Historical acceptance requires every relevant truck/date classification, not merely a nonzero fleet total.
