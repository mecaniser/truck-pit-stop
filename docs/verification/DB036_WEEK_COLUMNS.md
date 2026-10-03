# DB-036 weekly trip columns

Owner: Frontend & UX. Fast UI lane, existing read-only API contracts.

## Acceptance and evidence

- Partition inclusive selected dates into disjoint Monday–Sunday windows, clipped at the selected boundaries. Keep full-range totals from the original server summary.
- Fetch and paginate each week independently so later weeks are visible even when an earlier week exceeds 50 trips. Preserve truck filters, chronological order and existing expansion.
- Wide screens show responsive columns; tablet layouts stack. Departure and arrival retain labels and blue/green differentiation.
- 23 focused FleetTrips tests pass, including week/date boundaries, DST/year transitions, independent pagination, filter reset, empty week and recoverable weekly errors. TypeScript and changed-source ESLint pass.
- Browser actual-component synthetic fixture: three aligned desktop columns, each 552px wide; selected-truck aggregate 18 trips / 786mi / 16h18m equals three weekly totals of 6 / 262mi / 5h26m. At 768px, columns stack with no horizontal overflow; expansion works, row targets exceed 44px.
- Local Vite PID68375 owns this worktree, port5173, branch codex/trip-week-columns. Local backend configuration is absent; synthetic local evidence does not establish authenticated backend acceptance.
- Private screenshots: output/trips-qa/week-columns-desktop.png and week-columns-tablet.png.

## Release

PR461, candidate289e569ef9e5d63c8b752d25a947895b29026cca. CI and authenticated production acceptance pending at time of this receipt.

## Requested refinement

Weekly headers now fit date/trips/miles/time on one row (46px at 768px). Fuel and idle readings are inline below distance/duration. Expanded details retain actual intermediate stops and capture information without repeating endpoints. Selected-truck navigation appears once in the summary. 23 focused tests, TypeScript and ESLint pass; duplicate-endpoint and single-link assertions added. Desktop and768px synthetic browser verified, no horizontal overflow. Refined candidate supersedes289e569e; fresh CI required.

Final refinement: legs without actual intermediate stops are static cards, with no chevron or empty disclosure. Stops, when present, retain accessible tap expansion. Capture time remains a card tooltip.27 Trips/navigation tests and TypeScript pass. FleetTrips ESLint passes; whole-file FleetApp lint reports pre-existing any-type/hook warnings outside the changed lines. CI caught the previous return-navigation label and its test now follows the single summary link. Preview starts at three weeks after refresh.

Compact top controls verified:54px desktop toolbar,110px at768px with no horizontal overflow; first week begins about178px higher. Weekly cards are now flat transparent rows, zero radius, only horizontal separators. Three columns remain side by side. Evidence output/trips-qa/week-columns-flat.png.27 tests and TypeScript/FleetTrips lint pass.

Shared legend refinement: selected-truck leg headings removed visually, endpoint labels retained for accessibility with one visible route legend. Dates/times identify journeys. Five weeks stay on one desktop row,380px minimum,1980px content within1696px horizontal scroller.27 focused tests, TypeScript and FleetTrips ESLint pass. Three-week preview restored; screenshot output/trips-qa/week-columns-shared-legend.png.

Latest user refinement: removed the visible route legend while retaining blue/green endpoints and screen-reader labels. Idle values below1800seconds are hidden in metrics and stop details;1800seconds displays30m. Busy-day synthetic preview now has3,4,5 trips per day across the three weeks; all rows render without a per-day cap. Reverted the horizontal-week scrolling change after clarifying loads meant daily trips.30 focused Trips/navigation tests passed before the final legend-only removal; browser confirms legend absent and endpoint colors retained.


## 2026-10-03: Day columns and viewport containment

- Single calendar week: one column per selected date, including clearly labeled empty dates. Multi-week: one column per week, first day expanded, other days collapsed; opening another day closes the previous one in that column.
- Full selection summary remains server-derived. Each day/week requests its own bounded interval and owns pagination. Day accordion summaries say “shown” when only a page is available.
- 31 focused FleetTrips/return-context tests pass; TypeScript and FleetTrips ESLint pass. Existing unrelated FleetApp lint failures remain as recorded above.
- Local preview uses synthetic fixtures and the actual components; desktop outer scroll client/scroll heights both1250; all columns equal height. Tablet768x1024 outer heights both960. Backend configuration remains unavailable, so this is frontend preview acceptance, not authenticated integration acceptance.
- Evidence: private `output/trips-qa/day-columns-desktop.png` and `day-columns-tablet.png`.

### Impeccable audit and Emil design review

Scope: FleetTrips.tsx, trips.css, rendered preview. No claim of complete WCAG certification or real-iPad hardware testing.

| Dimension | Score | Evidence |
|---|---|---|
| Accessibility | 3/4 | Named controls, visible focus, keyboard operation; hover-only capture/estimate details remain a touch limitation. |
| Performance | 3/4 | Bounded per-column queries and pagination; custom-date reveal still uses a keyframe animation on keyboard activation. |
| Responsive | 3/4 | Equal-height columns and contained overflow; visible toolbar targets measured44px. Secondary labels remain small. |
| Theming | 2/4 | Existing fleet tokens retained, but route/metric colors are local literals. |
| Implementation integrity | 2/4 | Product-specific chronology and honest import states; accumulated CSS overrides need consolidation. |
| Total | 13/20 | Significant polish remains; functional preview is not final design approval. |

Integrity verdict: functional structure passes; styling maintainability needs improvement. Detector returned one `side-tab` finding on the2px summary accent. This is an existing fleet summary treatment, not a newly nested card; low-priority contextual finding rather than a release blocker.

| Severity | Before | After / recommendation | Why |
|---|---|---|---|
| P1, fixed | Week used full-width day rows | Day columns with separately filtered totals | Makes dates comparable without scrolling the whole page. |
| P1, fixed | Narrow columns crushed route labels | Container-aware layout gives routes the full row | Preserves readable locations. |
| P2 | Capture and estimate provenance use native title | Follow-up: tap-accessible detail affordance | iPad users cannot depend on hover. |
| P2 | Repeated CSS overrides | Follow-up: consolidate component rules | Reduces regressions between single-week and multi-week layouts. |
| P2 | Very small secondary labels | Follow-up: increase essential metadata type size | Improves standing/tablet readability. |
| P2 | Date reveal animates on keyboard activation | Follow-up: instant keyboard transition, retain pointer reveal | Repeated keyboard actions should respond immediately. |
| P3 | Detector flags summary accent | Retain incumbent treatment for this scoped change | Do not redesign unrelated summary styling during layout repair. |

Positive findings: no empty leg disclosures, no nested day boxes, hollow/filled route markers supplement color, short idle readings suppressed, one selected-truck navigation link,44px visible control heights. Next targeted commands: `impeccable harden` for touch detail access, `impeccable typeset` for small metadata, `impeccable polish` for final consolidation. These audit findings remain explicit follow-ups, not claimed fixed.
