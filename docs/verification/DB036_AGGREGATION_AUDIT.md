# DB-036 aggregation audit — October 3, 2026

Owner: QA Gatekeeper. Read-only verification of deployed42917864197c3aed4d8010d9a6bb4396816de130. No application edits, server restarts or new deployment.

## Independent oracle

2529 committed normalized source rows independently grouped by local departure date using Python zoneinfo and Decimal distance sums. Compared with deployed list_trips through a PostgreSQL READ ONLY transaction:14 scopes (all plus13 verified VINs),8 date ranges,2 zones (America/New_York and UTC) =224 passing cases. Distance comparison tolerance1e-7mi for stored Float summation; counts and seconds exact.52 first/last-page summary comparisons passed. Foreign tenant returns zero; reversed dates and >31-day ranges reject422. No database writes.

Ranges: today, Monday-to-today, month-to-today, September, August, empty July, Sep30–Oct1 boundary, Sep28 alone. Tests also confirm frontend20/20 and backend55/55 passing; backend includes spring/fall DST, cross-midnight departure, membership/tenant isolation, precision and pagination. SQLite test fixture only; production oracle is PostgreSQL. Local app serving not needed for this read-only audit.

## Live browser acceptance

| Scope | Period | Trips | Miles displayed | Driving displayed |
|---|---|---:|---:|---|
| All | Day Oct3 |6|101.7|1h47m|
| All | Week Sep28–Oct3 |356|26029|470h54m|
| All | Month Oct1–3 |136|9177.1|170h22m|
| All | Custom Sep30–Oct1 |136|9809.3|175h52m|
| 609 | Day Oct3 |0|0|0m|
| 609 | Week Sep28–Oct3 |33|2486.6|43h40m|
| 609 | Month Oct1–3 |12|727.9|12h55m|
| 609 | Custom Sep30–Oct1 |18|1256.2|22h14m|

Selected truck persists across period changes; all-trucks restores fleet totals. Empty selection shows No imported trips. Presets hide custom dates; Custom reveals and applies both dates. Restored All trucks Week. Private screenshot output/daily-2026-10-03-0600/aggregation-week.png.

Semantics: Day=today; Week=Monday through today; Month=first of current month through today. Custom inclusive dates, maximum31 days. Whole completed trip belongs to its departure date in displayed timezone; overnight mileage/time is not apportioned between days. Summary covers every matching imported trip, not just50 visible page rows. Distance displays up to1 decimal and total seconds round once to nearest minute. History remains partial; missing data is not certified zero activity. Fuel is not a summary total.

## Refresh receipt

160 source rows reconciled Oct1–3.136 accepted:5 created,131 unchanged;24 unverified-unit26 rows excluded. Committed receipt, exact unchanged replay and unchanged vehicles/fleet_telemetry_snapshots/repair_orders fingerprints confirmed. Prior advanced to2529 only after commit. New units: W900(two),03(two),88(one). Private applied receipt in output/daily-2026-10-03-0600/applied.json.
