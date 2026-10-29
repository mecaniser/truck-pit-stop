# Fuel exception reconciliation — October 29, 2026

Backend & Integrations accountable. Retained receipts from run `93a96619-9e9b-41de-adbb-8f1dd8bc6f93` and the additional bounded run `3a537bc2-d6c3-4ace-a3ea-526d57e7b054` were hash/scope/day validated. The second run completed seven dates / 161 reports, with 65 unchanged rows and zero created rows. Codex automations remain off.

## Affected trucks and dates

The latest ten-date ledger contains 140 explicit source no-results observations, 20 paired truck-26 identity observations, one membership rejection and one immutable source conflict before the reviewed repairs below. Source no-results are unresolved observations, never zero-fuel claims. The original 95 exact no-results keys were also checked by fresh SELECT-only lookup: none had a later saved row at that check.

| Dates | Trucks with explicit no results |
| --- | --- |
| 2026-08-15 | 01, 02, 03, 17, 4, 5, 532, 533, 6, 603, 609, 70, 728, 77, 88, 9, W900 |
| 2026-08-16 | 01, 02, 03, 17, 4, 5, 530, 531, 532, 533, 6, 603, 609, 70, 728, 77, 8, 860, 88, 9, W900 |
| 2026-08-17 | 01, 02, 03, 17, 4, 5, 532, 533, 6, 603, 609, 70, 728, 88, 9, W900 |
| 2026-08-18 | 01, 02, 03, 17, 4, 5, 532, 533, 6, 603, 609, 70, 728, 88, 9, W900 |
| 2026-08-19 | 01, 02, 03, 17, 4, 5, 532, 533, 6, 603, 609, 70, 728, 88, 9 |
| 2026-08-20 | 01, 02, 03, 17, 4, 5, 532, 533, 6, 603, 609, 70, 728, 88, 9 |
| 2026-08-21 | 01, 02, 03, 17, 4, 5, 532, 533, 6, 603, 609, 70, 728, 88, 9, W900 |
| 2026-10-25 | 01, 02, 03, 17, 4, 5, 530, 532, 603, 609, 728, 77, 8, 88, 9 |
| 2026-10-26 | 4, 5, 532, 77, 9 |
| 2026-10-27 | 4, 5, 532, 77 |

## Truck 26: missing VIN and an existing reviewed binding

Both `vin_unavailable` and local `source_missing` observations on each date refer to truck 26: August 15–21 and October 25–27. They are two evidence perspectives per day, not two different trucks. Retained source has reported fuel on August 15, 17, 18 and October 26–27; August 16 and October 25 have no readings.

The reviewed binding for the exact source provider is active and unrevoked, effective October 16 at 21:42:51.108657 UTC; its fleet membership matches and is open from October 7. PR #670 merged as `cecdb7e2712795cd7444de2cb25e42ad09b27cf0`. It adds explicit reviewed-binding provenance, fresh before/after identity proof, a null genuine VIN, and validation of the entire conservative report interval and unique current membership. October 26–27 are the only approved repair candidates; August remains rejected without backdating. No saved null-VIN source is retrospectively promoted into stronger identity proof.

## Truck 01: October 26 source revision

The original saved row has a valid immutable request digest. The later saved source changes measurements, with no non-measurement identity change.

| Field | Verified saved value | Later source value |
| --- | ---: | ---: |
| Idle fuel, gallons | 0.700 | 9.4 |
| Total fuel, gallons | 19.400 | 28.2 |
| Idle time, seconds | 3,660 | 50,340 |

The original row is preserved. The later reading remains in its exact immutable source/receipt evidence as a quarantined revision. No automatic canonical correction, duplicate fuel row, fabricated VIN or membership backdating is allowed. Promoting a revised canonical value would require a separate versioned correction contract.

## Truck 9: October 27 membership rejection

Fresh source now reports a reading. The exact source VIN identifies one active vehicle, but it has no fleet membership covering the source date. Another active vehicle shares the display unit 9; a unit label does not authorize merging identities. Preserve this exception; do not invent or backdate membership.

## Current remediation

The exact two Truck 26 previews are independently approved. The controlled apply must retain both source/preview hash pairs, verify actual persisted measurements, replay unchanged, preserve the original 675 and complete verified 716-row cohorts, then restore canonical worker defaults. Runtime acceptance is pending until those assertions complete.

Health PR #669 merged as `46e6af84a38c12fd13495746e69f4af1d79ee700`, deployed as `eab51ad9-b5df-4524-817d-76015ea6402b`. It handles one confirmed pre-credential legacy redirect loop within the original deadline, without retrying credential submission. Its new-image canary completed 18 rows; exact retained source/receipt acceptance is being independently reconciled during the next natural slot. The database readiness check and SELECT-only audits pass. The screenshot failure was the health login stage, not evidence of a PostgreSQL outage.

This report does not assert complete historical source coverage or sustained recovery of all five workers.
