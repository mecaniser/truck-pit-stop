# DB-036 trip history reconciliation and durable catch-up

Accountable owner: Backend & Integrations. Independent gate: diagnostic_gate.

## Authorized outcome
Reconcile every truck missing days against Motive, backfill gaps without duplicate trips, and prevent outages from losing days. Preserve immutable historical rows, tenant/member/VIN gates, source verification and uncertain-commit recovery. No credential changes or unrelated worker release.

## Initial evidence
Live Fleet Trips week October19–25 shows only October21 onward. SELECT-only production audit independently confirms zero retained trips October19 and20 for every vehicle. Retained history has4114trips/18vehicles spanning August15–October25; other days having records does not establish complete truck/day coverage. Recent totals130/116/112/27/2. Trip collector runs once daily09:15UTC and hardcodes today+two previous days. October20 failed, October21–22 scheduled slots missing; October22 off-slot attempt failed login. October23 recovery cannot revisit October19–20 with current fixed range.

## Local runtime preflight
2026-10-25 Eastern: clean new worktree motive-trip-catchup, branch codex/motive-trip-catchup, base0cec39f976b7d6e45a1d44326a857ec5ce353794. No listeners5173/8000. Runtime controller switch --dry-run blocked: approved backend/.env and Vite absent. No services replaced or secrets copied. Local product browser acceptance not claimed. Worker tests use isolated fixtures.

## Acceptance
- Every requested date has per-provider verified-import, verified-empty, ineligible or explicit unresolved status, with exact source evidence.
- No cursor skips holes or treats today/exclusions as complete.
- Source and normalized hashes, actor/tenant/company/scope identities, committed readback and unchanged replay required for completion.
- Interrupted collection retains completed daily evidence; ambiguous writes reconcile exact original attempts.
- Bounded execution, serialized imports, reusable login/directory within batch, controlled retry/backoff and redacted diagnostics.
- Regression, tenant/security, stale/corrupt-state, partial-source, duplicate/revision and restart tests independently reviewed before release/backfill.

## Independent gate
Initial QA/Security NO-GO: a report read before New York midnight could be certified complete when imported after midnight. Independent DB-backed reproduction: `/tmp/test_db036_midnight_gate.py`. Returned to Backend owner for source-time completeness and midnight/DST regressions. Per-day subprocess interruption and ambiguous-commit integration coverage also requested. Directory/membership hashes must be invariant to ordering changes.

## Release and recovery plan
Release only the reviewed, merged source to the existing trips service, retaining `/data`, `worker.lock`, one replica, restart NEVER and daily 09:15 UTC schedule. First bounded batch targets October 19–20. Verify exact daily receipts, source/normalized hashes, committed readback and unchanged replay before another run. Then restore default April 1 baseline planning with bounded historical batches. Reconcile any uncertain upload, trigger or commit before retry. Preserve all completed evidence when rolling back code; never delete or replay ambiguous attempts blindly.

## Owner verification
Final focused worker/history/catch-up Python suite: 66 passed. Node collector and isolated login fixture suite: 48 passed. Actual Node-to-Python subprocess integration preserves the verified first day, times out the second with pending intent, and reconciles the original second-day attempt. Midnight reproduction now passes; source read time governs DST-aware full-day closure. Mapping hashes are order-invariant. Membership-bound days report ineligible or partial eligibility. Backend CI partition verification: 33 critical + 284 remaining = 317 files, no overlap. Independent QA/Security GO: 43 Python + 22 Node passed, including original midnight reproduction and actual child timeout/recovery. Scope: offline implementation only; exact-head CI and production acceptance remain required.

## Status
Implementation passed independent QA/Security and is ready for protected CI. No production backfill or collector deployment yet.
