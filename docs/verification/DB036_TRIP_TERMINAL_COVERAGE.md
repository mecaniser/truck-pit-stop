# DB-036 terminal trip coverage

Accountable owner: Backend & Integrations. High-risk worker follow-up, separate from PR651. Branch `codex/motive-trip-terminal-coverage`, base64351919502c10c40fbc857d37af7bfb571420d8. Independent diagnostic_gate required; no production action authorized to this owner.

## Contract and acceptance before implementation

Closed, source-complete, hash-bound committed receipts may be terminal for their current mapping scope when each source provider is verified saved/empty or demonstrably wholly outside its authorization interval. At least one provider must be wholly ineligible; its eligible count is zero, eligibility is outside_membership, only exclusion is outside_membership, and effective eligibility starts at or after the New York day end. This denotes unauthorized history, never no driving. Source read time must prove day closure. Missing mappings/trucks, unknown identity, conflicts, malformed exclusions, partial-day eligibility and provisional observations cannot gain this classification. Existing strict verified semantics remain unchanged.

The planner skips these days only for automatic retry allocation. Explicit bounded backfill still includes them. Mapping-hash invalidation remains unchanged and discards certification after identity/membership/binding changes. Full proof stays in immutable receipts; classification is derived when reading them, allowing safe historical compatibility without rewriting artifacts. `complete_through` stays strictly verified. New `reconciled_through` crosses verified and terminal-ineligible days; `ineligible_days` names the intentional exclusions. `unresolved_days` excludes proven terminal days but retains provisional/partial/unknown/conflict observations.

Acceptance: terminal history consumes no retry slots; mixed full-day verified/ineligible providers qualify; partial-day and uncertain providers do not; New York DST midnight uses source observation time; changed mapping invalidates; explicit backfill includes terminal dates; strict completion and reconciliation cursors remain distinguishable.

## Runtime preflight

2026-10-26 Eastern: new clean managed worktree and branch verified at the stated base. No listeners5173/8000. Controller switch --dry-run blocked missing approved backend/.env and frontend Vite. No secrets copied, services replaced, local product browser acceptance claimed, or production state touched. Isolated fixture verification applies to this worker-only change.

## Owner verification and handoff

74 tests passed: terminal coverage, existing catchup, worker imports, reviewed placeholder, and Node-to-Python worker process suites. Command: `/tmp/db036-terminal-coverage-owner-20261026/bin/python -m pytest backend/tests/test_motive_trip_terminal_coverage.py backend/tests/test_motive_trip_catchup.py backend/tests/test_motive_trip_worker.py backend/tests/test_motive_trip_placeholder.py backend/tests/test_motive_trip_worker_process.py -q`. New uniquely owned virtualenv inherits approved local application dependencies and installs pinned pytest8.4.2/pytest-asyncio0.26.0/pytest-cov5.0.0; original shared recovery virtualenv had lost pytest source files, an environment issue unrelated to source. Existing test environments were preserved.

No migration, importer, collector authentication, public API or source capture change. Derived coverage adds source_read_at only in memory from hash-validated source, never rewrites prior receipts. New strict helper validates all source-provider rows, closure, and wholly ineligible bounds before skipping retries. Partial-day provider alongside an ineligible provider remains unresolved. Mapping invalidation still occurs before planning. Rollback to prior planner simply resumes unnecessary retries; immutable data is unchanged.

Independent diagnostic_gate GO: independently reran all 74 focused tests and diff checks. Reviewed hash-derived closure, exact whole-day ineligibility, mixed verified providers, negative partial/unknown/conflict/provisional cases, mapping invalidation, explicit backfill and separate cursors. Protected CI and exact production release remain pending.
