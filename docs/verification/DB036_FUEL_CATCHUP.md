# DB-036 durable fuel catchup contract

Status: independent contract GO; implementation underway with fairness and exact daily receipt gates. Backend & Integrations owns codex/motive-fuel-catchup, based on merged diagnostics f7c62619. Incorporate the diagnostics release before final source review; do not overwrite its lifecycle behavior. No catchup deployment/import before diagnostic release acceptance. No production authority in this worktree.

## Outcome and horizon

The normal scheduled worker must discover and retain missed closed report dates after an outage longer than three days. No manual per-window configuration is needed for ordinary catchup. Existing rows remain immutable and replay produces no duplicates. This is separate from lifecycle diagnostics and from API enablement.

Bootstrap horizon proposed:2026-08-15, the beginning of the explicitly collected Aug15–Oct4 fuel-history scope documented on the project board. Evidence: the project board entry “DB-036 fuel history / COLLECTED (2026-10-05)” records51 dates Aug15–Oct4,457 rows and15 source units, with Oct4 explicit no-source results and no production import/VIN join. This establishes prior collection scope only, not provider retention or historical availability. This is a scope boundary, not a claim that earlier source is absent or any day is complete. MOTIVE_FUEL_BASELINE may select a reviewed horizon; pin tenant, actor, company ID/label, baseline and date-policy version in a private immutable scope file. Changing it fails closed for explicit reconciliation. Legacy receipts remain recoverable but do not silently certify new day coverage.

Fuel report timezone remains unverified. Preserve source_timezone=null and existing conservative date interval (UTC date midnight minus14hours through next date noon). Only dates whose entire interval has ended may be scheduled, imported or certified. Do not borrow the trip collector's NY date semantics or interpret Eastern settings as report timezone proof.

## Fuel-specific source evidence

Reuse the existing single-provider daily fuel report contract, not trip pagination: exact official origin/report48/normal/provider/date URL, unique visible report table with exact headers, selected vehicle label plus verified directory provider/VIN, visible date label, exactly one stable report row or explicit no-results state, repeated identical bounded observations, and company/settings checks before and after. More than one row, changing filter/layout/identity, partial loading or absent terminal state fails before import. Keep source evidence versioned and retain all source-missing/excluded results; no inferred zero or completeness from footer counts.

A report with explicit no results or no fuel readings is an observed absence, never a saved zero or a fully resolved eligible day. The existing collapsed date label lacks a rendered year; do not promote such absence into terminal historical completeness. Its requested full date is source-bound by the existing exact URL/filter contract, with that limitation retained. A later separately grounded stronger source/date proof can revalidate observations. No guessed selectors, API endpoints, new login handling or response-schema assumptions in this outcome.

Every day must account for the entire current source directory and every authorized local truck. Source-directory omission, missing VIN, missing source readings, membership gaps, invalid readings, deleted/conflicting identity and changed immutable readings remain explicit exceptions. Do not drop a truck from scope to make a day complete. Missing versus failed/unexamined is distinct. Eligibility uses the existing conservative whole-report-date membership interval plus source-read membership gates.

## Bounded scheduling and execution

Default seven dates per invocation (hard maximum seven, preserving the existing maximum source-date count); preserve recent-three overlap, then oldest never-examined/reopened dates, with a reserved bounded oldest-observation retry slot when prior exceptions exist. Under the exclusive lock and only after successful recovery, persist a private immutable automatic run plan bound to exact tenant/actor/company/baseline scope and run identity. Alternate its first lane between oldest unexamined backlog and recent overlap across invocations; the first automatic run starts with backlog. This scheduling marker is never source coverage. Malformed or cross-scope markers fail closed; explicit manual windows neither consume nor reset automatic alternation. Order the remaining reserved lanes deterministically, with oldest-observation exception rotation. Thus repeated runs capable of completing only one day alternate backlog progress and fresh observations rather than permanently starving either lane. A permanently failing day is retained as failed, not complete; provider unavailability or insufficient budget for one complete day remains an explicit capacity blocker, never a guarantee of successful collection. If fewer than seven eligible dates exist, select only those. Explicit bounded FROM/TO remains available for reviewed reconciliation and always forces capture without changing the pinned baseline or other pending gaps.

One browser login, company verification, complete directory and VIN discovery per bounded invocation. Reorder collection date-first, all providers for that day; finalize immutable per-day source and importer receipt before advancing. Later capture failure or deadline retains already committed days. Never share a mutable daily source/receipt across attempts. Existing per-report checkpoints are read-only bounded resume aids; durable day progress is derived from committed exact receipts, not their30minute lifetime.

Retain exclusive worker lock and recovery-before-capture, scanning both legacy top-level and new daily receipts. Recover only exact saved source/normalized intent. Any ambiguous/failed recovery stops all new capture. Do not recapture to freshen uncertain attempts. Preserve30minute collector budget, existing task freshness limits and importer timeout; the supervisor's full duration can include separate recovery and import work. Bound the batch by dates and reports; do not promise seven dates finish in one run. No retry policy or schedule changes.

## Coverage and immutable import contract

Private fuel_coverage helper rebuilds day index only from verified committed receipts with exact source/normalized hashes, tenant/actor/company/scope binding, source version, full provider/date accounting, saved IDs, readback and unchanged replay parity. Persist coverage inside immutable normalized intent and the corresponding receipt. Dry runs and partial source never count. Reuse reviewed private-file/hash patterns only where identical; do not reuse trip proof or trip timezone schemas.

Canonical mapping hash includes source provider/VIN identity and authorized current local vehicle/membership identity, effective interval and relevant deletion/status facts, sorted independently of presentation order. Source-read timestamps are excluded from mapping identity. Latest hash-bound mapping/observation must invalidate older scope even if the latest proof is not coverage-eligible; do not resurrect old certification. Always refresh recent observations so changed scope is noticed; subsequent plans reopen affected historical dates.

Per-provider/day statuses: verified_saved; observed_source_absence; ineligible_with_reason; unresolved_identity; immutable_source_conflict. Locally authorized trucks absent from the directory have source_missing. Whole-day status is verified only when every in-scope eligible provider is saved with exact readback/replay and every excluded provider has explicit proven eligibility evidence. A conservative first version may keep all exclusions unresolved rather than invent terminal eligibility. Distinguish examined-with-exceptions from failed/unexamined. Strict complete_through is contiguous from baseline and never jumps holes. Exclusions and observed absence remain visible and fairly revisited; unexamined dates take backlog priority without endlessly revisiting the same absence.

Existing fuel immutable importer remains authority: same values replay using original read/capture identity; changed values are quarantined as conflicting_immutable_fuel and prior rows retained. Do not overwrite/delete, synthesize VIN, backdate membership or weaken current read visibility. A day can have a verified saved subset and visible unresolved exceptions, never a false full-coverage claim. Retention/old-date unavailability is explicit observed absence, not assumed provider retention or a permanent empty claim.

No database migration expected: private durable /data source/normalized/receipt evidence supplies the ledger; existing FleetFuelDaily and importer idempotency remain. Public/manual import behavior and legacy recovery digest compatibility remain unchanged. New plan-bound historical dates require an explicit validated plan branch; legacy source validation retains its original recent contiguous-date rules.

## Required acceptance

- Outage longer than three/seven days: automatic default plans retain every missed closed date and eventually visit all unexamined dates while preserving recent overlap.
- Interrupted capture after one completed date: next run retains exact receipt and resumes backlog; interrupted/ambiguous commit recovers before browser and cannot duplicate or refresh source.
- Exact replay, existing saved subset, source absence after prior reading and changed readings preserve original rows and identities; changed source stays quarantined.
- Wrong tenant/actor/company/baseline, forged or stale hashes, missing current truck, changed membership/VIN/deletion, ordering-only directory changes, symlinks and cross-run receipt substitution fail or reopen appropriately.
- Partial source, extra provider rows, conflicting identity, changed filters, missing/unknown readings and no-results never become zero/full coverage.
- UTC-noon closure, boundary days, leap dates and DST transitions preserve the unverified-zone conservative interval; today/future or not-closed dates reject.
- Actual Node-to-Python per-day boundary, bounded deadline, late failure, no second login, legacy recovery and independent saved receipt/readback gate.
- Independent source/security review, protected CI and exact runtime canary required. Catchup release/import waits for lifecycle diagnostics release acceptance.

## Runtime preflight

New worktree has no5173/8000 listeners. Mandatory controller dry-run blocked by missing backend/.env and Vite. No secrets copied or local browser acceptance claimed. Only intake documentation changed before independent contract review.


## Source handoff (2026-10-26)

Rebased onto diagnostics merge f7c62619. Normal commit-enabled runs now pin scope and use automatic daily planning; commit-disabled runs retain their prior bounded recent dry-run path. New historical imports require the private worker's explicit immutable plan. Each complete day commits and validates its exact saved receipt in the importer child, a separate read-only child and the outer supervisor. Ambiguous child outcomes stop; pending daily receipts recover before new browser work, and orphan normalized intents require reconciliation.

Owner verification:53 focused Python tests,24 other-worker compatibility checks and19 Node checks pass, including the actual Node-to-Python read-only saved-proof verifier (the import child is stubbed in that boundary test; DB import/replay is tested separately), DB immutable replay/conflict/absence, malformed/scope/hash cases, conservative UTC-noon closure, date-first interruption and12 single-day-capacity invocations alternating six backlog dates with all three recent dates. Protected Node workflow includes fuel capture and boundary suites. Independent QA/security GO:52 Python and19 Node checks independently passed, followed by15 catchup tests after the private-plan freshness assertion. Runtime capacity acceptance remains pending. Ruff and diff checks pass.

The seven-date limit is a bound, not a completion forecast. A fixed per-day elapsed counter supports runtime capacity review; no provider timing or22-vehicle day capacity is asserted from fixtures. If the provider cannot finish one whole day within the existing budget, the run fails without inventing coverage; partial report checkpoints retain the existing30-minute freshness rule and are not reused after expiration. Completed daily receipts remain durable. Auth/session outages remain a separate limitation.

After rebase, the mandatory runtime dry-run reports the intentionally dirty checkout; no5173/8000 listeners and no secrets copied. Earlier preflight also found missing approved backend/.env and Vite. No local browser or production acceptance claimed.

Private historical plan freshness is checked again in Python before DB work and before normalized intent creation:0–30minutes. Legacy and exact saved-intent recovery keep their previous semantics. Independent final re-review of this added assertion passed15 catchup tests; source/security GO retained.
