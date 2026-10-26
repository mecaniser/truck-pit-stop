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

## Reviewed identity retry extension — acceptance before edits

A later historical batch accepted nine daily receipts, then failed with a browser timeout between the previous import and the next trip-window task. The exact operation remains unproven; source review confirms reviewed placeholder identity reads lack the bounded transient retry used by VIN reads. Extend only the trip collector's directory, before-day and after-day reviewed reads with the existing three-attempt transient policy and fresh browser observation per attempt. Contradictory identity, VIN changes and unknown errors must not retry. No identity cache across days or attempts.

Expose static reviewed-identity phase labels. Enforce a fixed 30-minute invocation deadline and the existing task deadline before/after every retry attempt, including pre-day reads; expiration must prevent day collection/import. Tests: timeout then valid, three exhausted attempts, contradictions not retried, deadline before/after attempt and during backoff, and no downstream import after expiration. No other worker adopts the new retry wrapper. Independent gate must re-review this extended scope before merge/release.

The trip-only wrapper now calls the existing transient retry helper with three attempts and a fresh `readReviewedIdentity` invocation each time. Static phases identify directory, before-day and after-day observations. Fixed invocation freshness is checked alongside task freshness before/after attempts and before import; failed attempts also check expiry before permitting retry. Identity contradictions retain one-attempt failure behavior. 53 focused Node tests pass, including timeout recovery/exhaustion, all three phases, contradiction rejection, and expiration before/after reads and during backoff. Independent review of the extension is pending; diagnostic-only GO is historical evidence, not approval of this new scope.

## Merge evidence

PR654 merged `98e51f408ce9404e8c4a62ae7b5f3adecf431f76` at 2026-10-26T05:22:13Z after all seven checks in run40273220401 passed. Final reviewed head `7eedeee865efbc7bcd5e49fecd36720f9ba643fd`, fresh base `cde4ba4ca2bae8276402e499c654418fda740c4c`, and CLEAN merge state were verified immediately before squash merge. Release owner is preparing one May9 historical canary; production acceptance is pending.

## Production acceptance

Deployment `015a45bc-12b2-4224-a02b-361b18b6434d` uses approved image `sha256:d6cc44b1f56c470560833e5b3802cd90fa480e9c0873536fd19bbbcce3ee2aab`, exact merged source and verified full manifest/mount parity. May9 execution `a3f4aa7b-9e9b-4f5d-a4a7-64cc1fdad687` exited after94seconds at2026-10-26T05:27:47Z. Independent gate accepted exact committed receipt: renderedMay9/EDT/no-loader,13observations over9.042seconds, source/receipt/scope/hash/readback/replay parity, zero imports,22outside-membership. Startup reconciled nine preceding Apr30–May8 receipts and no ambiguous May9 write. SQL confirms4433unique, original4114 pre189projection unchanged,42bound trips valid/visible. Evidence `/tmp/db036-654-canary-receipts.jsonl` and `/tmp/db036-654-canary-db.jsonl`.

Automatic Web `714b4393-e0dd-4e31-b66b-c10feefc0418` is SUCCESS on98e51f40; build-version matches and readiness200 confirmsDB/Redis. No duplicate Web deployment. May10–June9 historical batch cleared next; October26 remains unresolved, and full historical drain is not complete.

## Historical drain checkpoint — 2026-10-26 06:38 UTC

PR654 batches May10–June9, June10–July10, and July11–August10 each passed 31 exact persisted-receipt audits. August11–31 passed 21 receipts covering 645 existing trips, all unchanged. Empty reports establish observed source output only; they do not establish that trucks did not drive. Membership exclusions remain distinct from verified zero eligible imports.

Execution `47496258-11ce-485a-a46f-ee1e804aba6e` halted before September1 import with `incomplete_prior_coverage: prior=80 covered=48 missing=32`. Saved source has 50 valid unique rows, matching its footer and expected count. No September1 normalized artifact or receipt exists. Aggregate inspection found no timestamp-only, one-hour shift, VIN, current membership, or deleted-row explanation. All 80 prior rows were created and source-read on October3. Cause remains unresolved; September1 is quarantined and existing rows are preserved.

One distinct September2 run, `c49edd9c-7f19-49ab-a598-9f6be258df97`, passed independent exact-receipt acceptance: 65 unchanged, zero new, EXITED after118seconds at06:37:47UTC. Database integrity remains4433unique, original4114 pre189projection unchanged,42bound valid/visible. An aggregate arrival check found78of80 prior September1 trips arrive the same New York day; ordinary midnight crossing cannot explain all32 unmatched identities. One distinct September3 run is authorized for source reconciliation and its own receipt acceptance; no broad batch or September1 retry is authorized. Evidence remains redacted in `/tmp/db036-sep1-shapes-live.jsonl` and `/tmp/db036-654-batch4-coverage-failure.json`.

## September3 stop — 2026-10-26 06:41 UTC

Execution `eef5ba43-8d86-4a26-aadd-dd47d349ec97` stopped after7seconds at06:40:51.831UTC with `login_legacy_redirect_loop`, before credentials, collection or import. No retry was issued. All manual historical runs are stopped pending fresh assessment. Release owner is authorized to restore empty explicit date selectors and MAX14 without triggering or redeploying; readback remains pending at this checkpoint.

The aggregate truck-day matrix is preserved in `DB036_CURRENT_TRUCK_DAY_RECONCILIATION.csv`:3608rows,164examined closed dates,22current trucks. This is the examined-date matrix, not proof that all configured dates are complete. September1 and September3–October15 comprise44 closed dates without accepted current reconciliation; October26 remains a separate unresolved current day. A source-only broad September1–15 comparison helper is prepared for independent review but has not run. Its caller needs a fresh isolated login and is parked while manual authentication/runs are stopped.
