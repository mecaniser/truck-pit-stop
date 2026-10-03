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

Final refinement: legs without actual intermediate stops are static cards, with no chevron or empty disclosure. Stops, when present, retain accessible tap expansion. Capture time remains a card tooltip.27 Trips/navigation tests pass; TypeScript/ESLint pass. CI caught the previous return-navigation label and its test now follows the single summary link. Preview starts at three weeks after refresh.
