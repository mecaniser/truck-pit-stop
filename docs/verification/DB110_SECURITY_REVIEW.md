# DB-110 independent Security & Identity review

2026-10-13. Reviewer: independent `operation_security` agent. The reviewer did
not implement or direct the feature. Product corrections remain with Backend &
Integrations. Scope is operation assignment/execution, timer serialization,
helper access, completion entry points, migration safety and customer privacy.

## Current gate

**Security GO** for `7941f454` (final sensitive file fingerprint verified below), reviewed against
combined base `2e67b78a0657bdfa057a465d9fc55d9329825ac7`. The four security review
findings below are resolved. This is an independent authorization, tenant,
privacy and timer-concurrency gate, not production, merge, deployment or browser
acceptance. QA owns the workflow acceptance recheck of the generic pending-review
timestamp correction; remaining runtime/CI gates also remain with their owners.
This security result does not close those gates. Further sensitive changes
require a narrow recheck.

No product code, preview/runtime data, migrations, credentials or provider
settings were changed by this reviewer. Tests created and cleaned isolated
synthetic test fixtures only.

## Findings and disposition

1. **Resolved — new internal work could remain exempt from completion.** Creating
   a sublet through the legacy labor endpoint and changing its line type to manual
   left `execution_status=None`. The new internal operation then looked like
   historical untracked work and bypassed the operation guard. The owner corrected
   enrollment on this transition; the independent endpoint reproduction passes at
   `e7a91d94`.
2. **Resolved — new service scope could strand pending review.** Adding a flat
   service on a pending-review order created pending execution without returning
   the order to in-progress, where the operation could be completed. The owner
   added enrollment handling to flat-service and fleet scope additions. The
   independent flat-service reproduction passes at `e7a91d94` and `ea8938ce`;
   source inspection confirms the fleet add/reseed enrollment calls.
3. **Resolved, originally P1 — helper permissions were bypassable through generic RO routes.** A
   mechanic assigned only to an operation receives legitimate job discovery but
   can call `PUT /repair-orders/{id}` to change the whole order and
   `GET /repair-orders/{id}/detail` to obtain full customer, financial and history
   data. The initial direct endpoint reproductions both succeeded where the DB-110 helper
   contract requires 403. The generic routes were permissive in the base; the
   newly reachable helper workflow cannot claim a reduced-data/no-general-write
   boundary while they remained available. The owner added the lead-only mechanic
   check to generic access, base/workspace/detail reads and writes, plus source
   and projection filtering for generic list/count/value responses. Independent
   original reproductions now return 403. Canonical regressions additionally cover
   delete, reopen, base, workspace, photos and notes. Helpers retain their reduced
   portal/operation/checklist access; hidden buttons are not the boundary.
4. **Resolved — stale manager timestamp edits.**
   `edit_session` refreshes a session after the tenant lock, then unconditionally
   applies supplied timestamps. A manager edit which discovered an active session
   can overwrite an end timestamp just stamped by operation completion. The
   contract specifically excludes this race. The owner now compares the observed
   start/end/deleted state with the refreshed state after locking and rejects a
   stale edit with 409. An independent two-session reproduction and the PostgreSQL
   race both pass. A newly loaded, deliberate manager correction with a reason
   remains supported.

## Final independent evidence

- Independent source inspection confirms tenant/RO/active-child filters for new
  operation routes, active same-tenant mechanic validation, exact timer-stop
  identity, versioned assignment/completion and helper checklist write filtering.
- New operation history is filtered from customer detail; shared `LaborResponse`
  does not gain execution metadata. Operation assignment does not start timers.
- `test_operation_execution.py`, `test_mechanic_job_scope.py`,
  `test_service_checklists.py` and `test_db003_read_tenant_boundary.py`:
  **94 passed** at `ea8938ce` in isolated SQLite fixtures. Earlier initial review
  had 69 passing tests; the final figure is a rerun, not added to that figure.
- Independent `/tmp/test_db110_security_snapshot.py`: initial scope-enrollment
  reproductions **2 failed**, then **2 passed** at `e7a91d94`. The added helper
  generic-write and full-detail probes initially **2 failed** (authorization was
  not rejected). Final rerun with the additional stale-manager-edit probe:
  **5 passed** at `ea8938ce`. Broadcasts were mocked for mutation probes.
- `test_operation_execution_postgres.py`: **9 passed**, independently run against
  the fixture-validated localhost `db110_test_operation_execution` database.
  Covers assign/start in both orders, complete/start, hold/finalize/remove against
  start, duplicate same-mechanic start replay, required-task reopen against
  completion and stale manager edit against operation stop. The restricted test
  URL was loaded into the test subprocess environment without printing it.
- Inspected new operation projection and helper portal payloads, guarded generic
  routes, customer history filtering, active technician validation, exact session
  stop, atomic completion paths, start/resume rollback, active-timer writers,
  timer attribution snapshots and additive migration168. Migration intentionally
  leaves existing rows untracked; parent preservation/isolated downgrade evidence
  is recorded in `DB110_OPERATION_VERIFICATION.md`. This reviewer did not execute
  a migration or alter the populated preview.

## Narrow final recheck — `724def67`

Reviewed the delta since `ea8938ce`: common completion cutoff, snapshot clearing
on generic/internal reopen and restore, operation-only WebSocket notification
flag, and the frontend compact workspace observer. Existing tenant/lead guards,
transaction order, exact timer identity and customer exclusion remain intact.
The notification flag suppresses a status toast only; it neither widens delivery
recipients nor suppresses cache refresh. The observer uses the already guarded
workspace route and verifies response identity before replacing the selected
record. No new security finding.

- Focused helper, tenant, generic transition and publication checks:
  **15 passed, 23 deselected**.
- Affected PostgreSQL completion/start and hold/finish/remove versus start races:
  **4 passed, 5 deselected**. These are a targeted rerun of part of the prior nine,
  not four additional unique scenarios.
- Prior unchanged-boundary evidence above remains associated with `ea8938ce`;
  QA owns the broader timing and browser acceptance evidence for the new head.

## Boundaries and remaining delivery work

No unresolved security finding remains on the reviewed source. The parent and
independent QA own completion of their remaining workflow/runtime acceptance,
including verification of the generic review timestamp correction.
CI/PR, merge, deployment and release acceptance remain separate. This reviewer
did not operate authenticated browser tabs and does not claim a physical mobile
device test. Existing dependency/type deprecation warnings and test cleanup table
sorting warnings did not fail the checks.

## Final reward, cancellation and caching delta

The final sensitive change was committed by the parent as `7941f454`. The reviewer
verified that the committed file matches the tested, reviewed fingerprint below.
Reviewed file: `backend/app/api/v1/endpoints/repair_orders.py`.

- File SHA-256:
  `161d216eaedd02eea627747034b6a2b2502c2b8349b488bd50750238ad95c3c5`.
- `git diff 724def67 -- backend/app/api/v1/endpoints/repair_orders.py` SHA-256:
  `bd036fdb9ad5ddb8c89698759d052b02d639e98f3326b63fc61d57c888a8cbdd`.

Security GO includes this delta. Completion now checks an existing EARNED entry
by exact tenant and repair order while holding the existing tenant transaction
lock. A prior credit skips the entire reward/balance/streak update; changing the
order lead or repeating the review cycle does not grant a second credit. Existing
reward records are not rewritten. The only EARNED creation path remains inside
this guarded completion route. Operation GET adds `Cache-Control: no-store`.
Force-void stops matching order clocks through the shared serialized timer helper
after its existing step-up and tenant authorization, before committing cancellation.
No permission, customer projection or historical-data boundary was widened.

- Canonical repeated-credit and completion-entry-point checks:
  **10 passed, 29 deselected**.
- Two independent synthetic probes: **2 passed, 5 deselected**. Changing the lead
  after the first completion retains the original award ID/actor/points, leaves
  the original balance totals and streak/date unchanged, and creates no second
  mechanic balance. The helper operation projection remains restricted and sends
  `no-store`.

All security findings are resolved. No claim is made that the separate full suite
or remaining 320px browser layout acceptance has passed; those checks and any
implementation corrections remain parent/QA responsibilities.
