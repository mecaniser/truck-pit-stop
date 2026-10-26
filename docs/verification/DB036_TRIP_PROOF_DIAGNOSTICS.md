# DB-036 trip empty-proof diagnostics

Backend & Integrations accountable; high-risk worker diagnostics follow-up. Branch `codex/motive-trip-proof-diagnostics`, base `cde4ba4c`. Independent diagnostic_gate required. No production release authorized in this implementation step.

## Acceptance before edits

An empty-date proof failure must expose a static allowlisted category and phase distinguishing picker opening, overlay visibility wait, and selected-date validation. Structural context is limited to bounded counts, booleans and strictly validated ISO dates. Arbitrary exception messages, class names, DOM text, URLs, HTML, rows, driver identities, cookies and secrets must never be serialized. Unknown fields and invalid values are dropped. Missing/multiple/ambiguous controls remain fail-closed; no selector is broadened or evidence requirement waived. Existing valid reports, timeout retry classification, immutable artifacts and imports are unchanged.

Tests must cover each phase, missing versus mismatched dates, malformed and attacker-controlled diagnostics, timeout semantics, and existing capture/DOM regressions. The suspected today-specific selected class remains unproven and is outside implementation scope. A future naturally authorized observation may establish its cause.

## Runtime preflight

2026-10-26 Eastern: clean managed worktree at the stated base, new branch verified; no listeners on 5173/8000. Controller dry-run blocked by missing approved backend/.env and Vite installation. No secrets copied, services changed, migrations or production actions. Isolated tests only; local application runtime is not browser-verified.

## Implemented contract and checks

Static error kinds: `report_empty_picker_click_failed`, `report_empty_picker_wait_failed`, `report_empty_date_proof_unavailable`, and `report_empty_date_proof_mismatch`. Phases are `empty_picker_click`, `empty_picker_wait`, or `empty_date_validation`. The final diagnostic carries only an allowlisted `structure` object. Picker/overlay/label/title/selected counts are nonnegative integers capped at 21 (21 means at least 21). Loading, valid header/day, adjacent-month and collapsed-label agreement are booleans. Selected start/end may appear only as validated ISO calendar dates. No selected class names or raw labels are exported. Output sanitization runs again at the diagnostic sink.

Existing timeout and recognized transient-network causes preserve the bounded retry behavior; wrapped errors retain no raw cause, exception message or URL. No new browser reads, retries, date selection or relaxed acceptance was added. Missing versus mismatched date proof and picker click versus wait are distinguishable. Source document/receipt shapes and database schemas are unchanged.

The adapter imports the shared pure diagnostic helper. The trips Dockerfile explicitly preserves that repository-relative path in its collector layout; an isolated test reconstructs the actual COPY destinations and imports the deployed adapter without a browser.

51 focused Node tests pass across trip collector, actual DOM, task retry and login diagnostics. Negatives cover arbitrary DOM/exception strings, hostile extra fields, malformed dates/counts, duplicate controls, timeout and network preservation. Protected CI already executes these trip suites and task/login diagnostics. Command: `NODE_PATH=/Users/sergio_m1_promax/GitHub/truck-pit-stop/frontend/node_modules node --test scripts/collect_motive_trips.test.mjs scripts/collect_motive_trips.dom.test.mjs backend/scripts/motive_sync/tasks.test.cjs backend/scripts/motive_sync/login_diagnostics.test.cjs`. The NODE_PATH reuses the approved existing jsdom dependency read-only; no dependencies changed. Diff integrity passes.

Independent diagnostic_gate reviewed source, privacy, retry semantics, CI and Docker wiring and passed all 51 tests: GO. Evidence: /tmp/db036-proof-diagnostics-gate-tests.txt. PR/CI and any later production canary remain pending. Rollback changes diagnostic detail only and must not waive the existing empty-proof requirement. Today's selected-cell cause remains unproven.
