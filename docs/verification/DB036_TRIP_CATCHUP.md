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
PR #650 passed all seven exact-head CI checks (run 40263512628) and merged at a6a6af962a851b077ddb8d46a6a20faedc97e561. Reviewed head d433d7df and merged tree are identical. Trips-only priority deployment `56c9b647-5ec2-4731-a699-b23f5ed43701` succeeded with image `sha256:920d3fdd082db977b7b066d866edc90775d30da217abbf29f35ace5b8ed5a2e9`. Full service manifest and `/data` parity checked; restart NEVER, one replica, 09:15 UTC schedule and buildOnly=true retained. One authorized priority execution `463a1409-4698-4263-a450-d3f9cd6a704a` started October 26 at 03:33:14 UTC. Exact daily receipt acceptance is pending. Only date selectors FROM=2026-10-19 / TO=2026-10-20 were set with automatic deployment suppressed. Default backlog planning must be restored after priority acceptance; these selectors must not remain the final daily mode.

## Priority backfill evidence
Independent SELECT-only audit found 113 unique trips on October 19 and 147 on October 20, totaling 260 new rows. All 4,114 preexisting rows retain the identical aggregate full-row digest under the original capture cutoff. October 19 exact receipt passed 124 captured / 113 normalized, created, readback and unchanged replay with source/scope/hash parity. October 20 exact receipt remains pending next active authorized backlog container; container exit prevented its first audit. Independent safety gate permitted one real bounded backlog batch because startup validates saved receipts and reconciles uncertain attempts before planning.

Live signed-in Fleet view refreshed after backfill: October 19–25 has 647 driving segments (previously 387), with October 19 at 5,795 miles / 16 reporting trucks and October 20 at 7,784.8 miles / 15 reporting trucks. Coverage remains Partial; one absent directory truck and one unverified VIN require diagnosis. No full-history completion claim.

## Default planning acceptance
Default deployment `fa910430-228e-459c-ba49-e0b2d6dd5633` retained the same image and full manifest, with FROM/TO empty. Execution `cebfca3f-f4da-4bc1-98d9-1d59d3dc444c` completed in 211 seconds. Independent streaming audit captured all 14 exact daily receipts: April 1–11 returned zero source rows and explicit membership/identity exclusions; October 23 replayed 112 unchanged, October 24 replayed 27 unchanged, and October 25 replayed 2 unchanged plus 16 new trips while correctly provisional. October 20 priority receipt independently passed during this active run: 154 source / 147 normalized, created, readback and unchanged replay, with all hashes and expected environment scope matching. Both priority dates are now accepted imports.

The two identity exclusions represent one truck, unit 26: Motive provider 5981300 has no displayed VIN and the corresponding local vehicle has reference PENDING-26. Existing reviewed binding permits telemetry and drivers only, not trips; this backfill does not weaken that identity gate. Prior complete-summary/admin evidence corroborates the missing VIN.

Independent gate permits temporary 31-day batches to reduce repeated logins, retaining the reviewed hard cap and 30-minute bound. Release owner runs serial batches only after independent preceding-batch acceptance; uncertain operations are reconciled. Restore default 14-day cap after historical drain. Full historical reconciliation remains in progress.

## Controlled historical drain
The first temporary 31-day execution failed before credential submission or import with the known provider legacy redirect loop. Independent SELECT-only reconciliation confirmed 4,390 unique trips and unchanged original 4,114-row digest. One controlled retry was queued after reconciliation and a fresh no-active-execution check. Railway later created replacement `5345f418-97ba-4897-9914-910f61698aae` with the same approved image and manifest; no duplicate trigger or upload was issued. Execution `14144b7e-71d3-4e31-a312-3eb945d602cc` completed in 280 seconds. All 31 exact receipts passed: April 12–May 9 and October 23–25, 157 unchanged trips and no new trips. Independent post-run SQL confirmed 4,390/4,390 unique trips and the unchanged original 4,114-row digest. The next single batch was cleared. April 12–May 9 precedes membership; these dates are exclusions, not verified idle days.

The user has now authorized collecting unit 26 through PENDING-26. Its separately reviewed trip implementation is tracked in [the binding contract](DB036_TRIP_PLACEHOLDER.md). Current PR650 backfill still excludes it. The [truck-by-day matrix](DB036_TRIP_RECONCILIATION.md) records accepted priority counts without treating unresolved identity as zero.
