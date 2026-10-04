# DB-036 OTR owner overview — 2026-10-04

Owner: Frontend & UX. Fast UI lane; existing read-only API contract. User authorized iterative redesign with all trucks treated as OTR.

## Implemented
- Ranked truck distance/driving comparison, with days containing imported segments.
- Daily truck matrix and daily fleet chart; a cell or chart selection opens supporting routes.
- Selected-truck daily chart/list, one truck link, route fuel estimates and measured metrics when available.
- No claims about loads, profitability, underuse or measured efficiency from mileage alone.
- Partial coverage retained. Missing truck/date records use dashes, not downtime or fabricated zero driving.
- All pages fetched with cancellation; every page and final count, unique identities, truck count, distance and duration reconcile before aggregates render. A changing import fails with Retry instead of a partial comparison.
- Existing calendars, 31-day limit, tenant API and source records unchanged. Daily totals follow the existing departure-date contract, including overnight segments.

## Verification
- 27 tests: FleetTrips, tripAggregation, FleetApp return context. Day/week/month/custom recalculation; unknown vehicle and invalid range; loading/error/retry; matrix drill; full pagination; duplicate/changing/empty/misordered pages; timezone/DST/year boundaries; measured versus estimated fuel; idle threshold.
- TypeScript, production build, focused ESLint and diff whitespace checks passed.
- CUA desktop and 1024x768 tablet-size inspection. All-trucks comparison and chart visible together on desktop; matrix and touch targets verified at tablet size. Truck609 week selection and Oct2 detail verified; 3 routes total131.2mi and estimates6.1/3.9/10.2gal, no repeated truck link. Native iPad hardware not tested.
- Private imported-data preview reconciles368 week segments /13 trucks /26963.4mi /486h15m, with selection changes tested. Private rows and screenshot stay in untracked output/preview files, excluded from Git/build entrypoints.

## Runtime receipt
- Checkout: /Users/sergio_m1_promax/.codex/worktrees/db036-motive-sandbox/truck-pit-stop
- Branch: codex/otr-fleet-overview; base44d196ef71781b83f90abc325e2b7992d2d450cb plus scoped edits.
- Frontend127.0.0.1:5173 PID62713 verified by lsof cwd and HTTP200. Proxy remains local8000.
- Backend config absent; no backend started, no database or secrets changed. This is an intentional frontend-only preview with a local imported-data adapter, not authenticated full-stack acceptance.
- Preview: http://127.0.0.1:5173/otr-preview.html — aligned frontend and browser-verified.
- Not merged or deployed. Product iteration remains open. Provider/auth/schema/security boundaries unchanged.

## Visual refinement — 2026-10-04

Impeccable Operate principles and Emil design-engineering guidance applied to this scoped refinement.

| Before | After | Why |
| --- | --- | --- |
| Staggered chart/comparison headings | Shared72px panel headings and aligned dividers | Establish a common reading baseline |
| Pale blue for both metrics | Scoped amber distance and sage driving tokens | Color follows the selected measure |
| Quiet state changes | Selected control, metric caption, visible date range and180ms transform feedback | Explain what changed without blocking interaction |

Browser check: desktop heading rectangles both top375.890625/bottom447.890625. Driving-hours pointer activation sets seconds/on and updates chart colors; keyboard Enter on Miles sets miles/off.1024x768 tablet viewport has no outer horizontal overflow. Reduced-motion CSS removes scoped animation/transitions while retaining colors, labels and pressed state. No dependencies or data-contract changes. Runtime remains frontend PID62713 from this worktree, private imported-data adapter; no backend configured. Private screenshot: output/otr-overview-refined.png.27 existing focused tests pass.

Color clarification: amber now identifies truck comparison and blue identifies daily activity, independent of metric. This supersedes the earlier amber-distance/sage-hours choice. Existing monthly selection preserved and browser-verified; screenshot output/otr-panel-colors.png.

View/Measure correction: separately labeled groups now expose Comparison/Daily pattern and Miles/Driving hours. Regression covers independent selection and exactly one pressed option per group. Browser DOM confirms both groups; private screenshot output/otr-separated-controls.png.

## Follow-through: heatmap, activity, fuel, driver identity
- Both fleet views use the bounded two-column layout. At1280x800 matrix right786.61 and chart left814.61; matrix top375.89 remains below controls bottom359.89, no outer vertical scroll.
- Activity bands use median reporting-truck miles/hours, high>125%, typical75–125%, low<75%; no band for missing records or fewer than3 reporting trucks. Relative truck activity, not driver assessment.
- Diesel column separates measured Used from Est.; partial trip coverage is explicit and measured/estimated values are never added together.
- Existing BoardTruck.driver_name shown beside truck identity in both views, with current-assignment heading and Unassigned fallback. Actual names verified read-only on production Fleet Board; private preview updated without committing driver data. No historical driver attribution or database edits.
-31 focused tests cover these changes and preceding filters, pagination, fuel integrity and navigation. Screenshot output/otr-drivers.png. Not deployed.

Scan hierarchy update: large unit number and larger blue driver name in both fleet views. Removed median band text/function; continuous bars compare to highest selected measure and trophy marks tied leaders. Zero-only/missing data has no leader.31 tests pass including tie/ratio/missing cases. Browser checked comparison and daily pattern; private output/otr-activity-bars.png. This supersedes earlier median-band behavior.

## Activity explanation popover — 2026-10-04

Frontend & UX, Fast UI. Existing contracts and aggregation unchanged. Leader trophy and per-truck information button open an anchored Headless UI popover in both comparison and daily pattern. Shows selected metric/date range, competition rank among reporting trucks, total, fleet median, proportion of leader and days with imported trips. Review prompts distinguish investigation from proven causes, current assignment from historical driver attribution, and estimated fuel from measured efficiency. Missing imports remain unranked. Navigation and explanation controls are siblings (no nested buttons).

Verification: 32 focused tests pass, including criteria, absent-data explanation, Escape/focus return; TypeScript and focused ESLint pass. CUA checked leader and lower-activity cases, Escape and outside dismissal, both views; popover escapes scroll clipping and stays within desktop viewport. Screenshot output/otr-activity-explanation.png. Local imported-data preview only; no backend, PR, merge or deployment claim.

## Distilled differences — 2026-10-04

Replaced repeated rank/total and review prose with signed selected-measure delta, percentage versus reporting-fleet median, secondary measure delta and miles-per-imported-day delta. Each metric uses its own median across reporting trucks; this is not a matched peer or causal efficiency score. Singleton/missing data has no comparison. Fuel coverage stays explicit with no unproven savings. Higher-luminance popover surface, brighter border and stronger shadow. Frontend PID62713 remains aligned to this worktree; intentional frontend-only imported preview, backend absent. CUA verified Truck03 +598.5mi/+24%, +13.1h, +93.5mi/day and readable popover. Screenshot output/otr-popover-distilled.png. 29 focused tests, TypeScript and changed-source ESLint passed; includes signed deltas and hours conversion. Not deployed.

Focus-ring follow-up: activity trigger uses 2px inset outline (-3px offset) to avoid clipping at table scrollport edges. CUA keyboard Enter verified complete visible outline and popover opening. Screenshot output/otr-popover-focus-fixed.png. CSS-only; no aggregation changes.

## Diesel comparison — 2026-10-04

Popover shows covered gallons, gal/100mi and signed percent versus the median of truck rates with the same fuel source (estimated or measured). Fuel numerator and mileage denominator use exactly the same trips; no full-period extrapolation, no mixed source comparison, no ratio when mileage or baseline is zero. Estimates explicitly retain 30-day MPG basis and trip/mileage coverage. This is not observed selected-period fuel efficiency when estimates are used. Browser verified Truck03 396.5 estimated gal /2696.3 covered mi =14.7gal/100mi, −7.4% against15.9 median;39/45trips. 29 tests pass including matched coverage/source handling and numerical rate comparisons; TypeScript and focused ESLint pass. Screenshot output/otr-diesel-comparison.png. Local preview only, not deployed.

## Comparison interpretation correction — 2026-10-04

Removed ambiguous standalone difference values and per-day delta. Actual distance/hours/days are now beside their respective fleet medians; headline explicitly says at/above/below median. Truck609 verified 2489.6mi vs2489.6mi,43.9h vs43.9h,6days vs5. Fuel model explicitly names 30-day MPG and unverified weekly performance; percentage wording says modeled fuel/mile rather than implying realized savings. Source totals unchanged.29 focused tests and ESLint pass. Browser screenshot output/otr-609-clarified.png. Local only.

Headline follow-up: actual selected metric now leads (Truck609:2,489.6mi), with Matches fleet median below. Removed repeated Against/At headings; table retains explicit values. Browser verified output/otr-headline-609.png.

## In-panel routes — 2026-10-04

Cell drilldown replaces only the left comparison panel. Fleet chart, totals, filters and measure controls stay visible. Matrix remains mounted and hidden to preserve scroll; Back restores triggering-cell focus. Selected truck name appears once in detail header, not every leg. Route scroll bounded independently. 34 focused tests pass including persistent chart, matrix scroll and focus restoration; TypeScript and changed-source ESLint pass. CUA Truck531 Sep28 verified7trips743.1mi13.3h, chart retained, Back and cell focus. Screenshot output/otr-inline-routes.png. Local imported preview, not deployed.

## Compact route ledger — 2026-10-04

Scoped CSS refinement: paired endpoints6px gap, horizontal miles/duration/fuel; retain full addresses and overnight dates, container-based compact fallback. CUA at normal desktop: all7Truck531Sep28rows visible, heights69px for6rows/78px for overnight row versus previous roughly126px. Tablet1024x768 panel scrollWidth=clientWidth887px; labels and numbers readable. Restored default viewport. Screenshot output/otr-compact-route-ledger.png. No logic change or new tests needed; prior34focused tests cover route interaction. Local preview only.

## Meaningful route focus — 2026-10-04

Added explicit display-only grouping: short movements ≤1mi and≤15min; remaining trips shown by default for truck/day. All-short days retain all records. Show all toggles full chronological record list, does not change aggregates. Summary reconciles travel and short movement mileage plus longest trip share. No inferred loads/fueling/yard purposes. Departure-date and overnight allocation explicit. Overview subtitles explain ranked measure and heatmap missing-data semantics. Browser verified Truck531Sep28 four travel trips741.6mi +three short movements1.5mi =743.1mi; longest496mi67%; toggle4→7→4.36focused tests, TypeScript and focused lint pass. Screenshot output/otr-route-story.png. Local only.

Source research: Motive Vehicle History describes trips/stops, start/end times and distance; Safety Events mentions engine-on start for forward parking, while Zero Telematics Mode describes movement thresholds. No universal segmentation rule established for imported records; do not equate every trip with ignition cycle or a dispatched load.

Route footer refinement: moved dense story text below routes as Travel / Longest trip / Short movements numerical strip; grouping/date notes in anchored info popover. Show-all remains visible.21component tests pass; CUA verified bottom placement, info opening and Escape dismissal. Screenshot output/otr-route-footer.png. Local preview only.

Journey bookends: below route footer, first origin by departure timestamp and latest destination by arrival timestamp for selected truck/period. First/latest timestamps honor timezone; overnight latest endpoint opens its departure day. Labels distinguish start/continuation/latest/only recorded day without claiming actual end-of-week destination.22component tests, TypeScript, ESLint pass. CUA verified Truck531Sep28 start→Oct2 latest, endpoint navigation. Screenshot output/otr-journey-bookends.png. Local only.

Inline endpoint correction: removed separate journey strip/navigation. Pass selected-period first/latest trip identities into route renderer, emphasize only matching departure/arrival with16px700weight amber/violet and matching time/marker; intermediate stops unchanged. Accessible names specify recorded period boundary.22component tests/tsc/lint pass. CUA checked531Sep28first andOct2latest. Screenshot output/otr-inline-endpoint.png.

## Release gate — 2026-10-04
User approved release. Production build passed; focused FleetTrips (22), aggregation (11), and return-context (4) tests passed: 37 total. Private preview entrypoints and output data excluded from commit. Production www.dieselbridge.com is served by Railway diesel-bridge-network with frontend bundled through backend/Dockerfile.
