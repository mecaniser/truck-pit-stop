# DB-036 settled empty report proof

Accountable owner Backend & Integrations; high-risk source completeness follow-up. Branch codex/motive-trip-empty-proof, base b00e75f0. Independent diagnostic_gate required before release. Parent owns integration of pending release notes from terminal-coverage worktree.

## Acceptance before source edits

Whole-report empty may complete only with exact visible selected date range, trusted matching URL filters and timezone/company guards, zero rows, no contradictory loading state, and consecutive stable empty observations over at least 9 seconds under existing bounded worker/read deadlines. Missing/ambiguous/wrong selected date evidence fails closed. Loading or delayed rows reset empty settling; populated reports keep existing count/bottom/source guards. No assumed fuel-report selectors: trip date controls must be grounded in actual rendered trip DOM before acceptance.

Persist a versioned empty proof with selected start/end, observation timestamps/count and settled duration. Python source acceptance checks the proof; receipt-derived coverage reopens older whole-report empty evidence without rewriting it. Nonempty source receipts stay valid, including individual trucks with no rows within a fully captured populated report. Recovery preserves already committed receipts, but legacy empty evidence cannot certify a day. No zero-driving/retention claim follows from report-empty observation.

Negative fixtures: transient empty then loading/rows; missing or mismatched selected dates; ambiguous date controls; loading/empty contradiction; empty alongside rows; short settling duration; changing date evidence; stale proof/version; whole-report legacy empty invalidation; populated receipt compatibility. Positive fixture must be grounded, stable and bounded.

## Runtime preflight

2026-10-26 Eastern: managed worktree verified at stated base; no listeners on 5173/8000. Controller switch --dry-run blocked missing approved backend/.env and Vite. No secrets copied or services replaced. Isolated fixtures only; no product browser readiness claimed.

## Live DOM grounding

On 2026-10-26 the parent inspected the existing signed-in Motive Chrome Trips report for April 1, 2026. No new authentication or production record mutation was used. The collapsed date label was only “Apr 1”, which is insufficient to establish the year. Opening the existing picker exposed the visible “Apr 2026” header and one selected current-month day with direct text node “ 1 ”. This supplies the year independently of the requested URL.

Grounded selectors: `phx-filter-row[data-e2e="trips-filter-row"] phx-date-picker[data-testid="date-picker"]`, trigger `.phx-date-picker-selector`, collapsed `.phx-date-picker-range-labels .phx-date-picker-label`; visible overlay `.cdk-overlay-pane.phx-date-picker-overlay-pane`; title `.phx-date-picker phx-date-picker-header .phx-date-picker-header-label`; selected span `phx-date-picker-body .phx-date-picker-body-date-wrapper span.phx-date-picker-body-date-cell-active-selected`. Adjacent-month cells use `.phx-date-picker-body-date-cell-prev-next-month`. Selected day text is read from direct text nodes, excluding the event-container child. The `#module-loading-spinner` remains present while hidden, so loading depends on rendered visibility.

The extractor requires exactly one visible picker, overlay, title, selected day and collapsed label; the full date must agree with both the collapsed month/day and requested single-day bounds. Range ambiguity, absent year, adjacent-month selection, wrong dates or hidden controls fail closed. It only opens the existing picker after an empty candidate, with bounded click/wait; it does not select or apply dates. Nonempty collection does not open the picker. The picker remains open during consecutive empty observations.

## Implementation verification

119 focused Python tests and 28 Node tests pass. Python covers fresh proof acceptance, malformed/version/date/count/time negatives, old whole-report empty invalidation, populated-report compatibility, catchup/recovery and placeholder/terminal coverage regressions. Node includes real readReport callback fixtures matching the grounded structure, direct-text-only day extraction, wrong year, adjacent-month/multiple/hidden selections, picker opening, loading visibility, transient empty, delayed rows and bounded settling.

Local runtime remains unavailable as described above; fixture success is not deployed acceptance. Independent diagnostic gate and a bounded reviewed production canary remain required. No false empty has been demonstrated. Earlier whole-report empty receipts must be revalidated; their artifacts remain immutable and do not justify a no-driving or provider-retention claim.

## Independent gate corrections

The gate found that filtering legacy empty receipts before selecting the latest mapping could revive older mapping coverage. Reconstruction now retains every hash-bound receipt's mapping and recency signals before filtering coverage. Two regressions cover a later unproven empty with a new mapping and a later unproven empty for the same day; neither restores older certification.

Live DOM clarification showed intermediate wrappers between `.phx-date-picker` and `phx-date-picker-header`. The selector uses a scoped descendant, preserving uniqueness. `scripts/collect_motive_trips.dom.test.mjs` uses jsdom's actual selector engine and the observed `.main`, `.phx-menu-header-body-wrapper`, and `.phx-header-body-wrapper` ancestry. It proves the direct-child selector cannot match and the corrected selector can. Run after frontend dependencies are installed: `node --test scripts/collect_motive_trips.test.mjs scripts/collect_motive_trips.dom.test.mjs`. In the isolated worktree, the test used the existing approved frontend dependency tree via `NODE_PATH=/Users/sergio_m1_promax/GitHub/truck-pit-stop/frontend/node_modules`; no package or application runtime changes were required.

## Protected CI

Both Node trip suites now run in the protected `Frontend checks` job after restoring its verified existing frontend installation. No new dependencies or jobs are added. The protected-base conservative classifier requires frontend checks for backend, root scripts and workflow changes; only Markdown-only changes may omit this application check. This closes the gate's CI coverage finding.

Independent diagnostic_gate final GO: 48 changed Python tests, 28 Node tests, and 9 scope tests passed. Reviewed stale mapping and same-day receipt invalidation, actual calendar wrapper topology, and protected CI wiring. No production empty-report acceptance yet; one genuine historical-day canary precedes backlog drain.
