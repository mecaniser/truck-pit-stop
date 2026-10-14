# DB-115 independent security gate

Reviewer: independent Security & Identity agent, no implementation or contract-authoring participation. Scope: uncommitted DB115 source on `codex/staff-work-hold`, base `b318bb94`, 2026-10-13 local. This report is not a browser, production, merge or release approval.

## Final gate: GO for the scoped DB115 change

The three initial privacy blockers below are fixed and independently verified. No unresolved DB115 security finding remains in the reviewed source. This does not replace QA, protected CI or release approval.

## Initial findings and resolution

The initial new endpoint/service boundary passed review and 49 focused hold tests, but three alternate disclosure paths violate the staff-only reason/history boundary:

1. **P1 — Customer websocket disclosure after technician reassignment.** `assign_mechanic` forwards the held order's raw `hold_reason`/`held_at` to `broadcast_repair_order_update` with default customer delivery. The helper originally sent the identical staff payload to the customer. An independent mock of the real helper confirmed `Internal staff-only reason` in the customer message. Redacting HTTP reads and suppressing only the initial hold broadcast do not protect later updates. Required: strip/null internal hold fields at the shared customer-message boundary and retain staff payload; prove a subsequent held-order reassignment does not disclose them.
2. **P1 — Legacy dashboard stats discloses staff reasons to customers.** `GET /api/v1/dashboard/stats` originally depended only on authenticated user, queried by tenant, and rendered raw hold fields in its floor queue. A selected-shop CUSTOMER principal has a tenant ID. Independent in-memory SQLite reproduction (`/tmp/test_db115_security_dashboard_probe.py`, log `/tmp/db115-security-dashboard-probe.log`) confirms a DB115 reason appears in the customer's response. Required: apply the existing supported shop-staff access boundary before protected queries, with valid staff and excluded-role regression coverage.
3. **P1 — Driver reads disclose staff reason and actor history.** Legacy repair-order access permits a same-tenant DRIVER through detail/list/workspace reads. New redaction was CUSTOMER-only. Independent in-memory SQLite reproduction (`/tmp/test_db115_security_driver_probe.py`, log `/tmp/db115-security-driver-probe.log`) confirms a driver receives the free-form reason and hold history. Required: limit the new hold fields/events to supported operational readers across all alternate reads, preserving other existing access/financial rules.

These defects were returned to Backend & Integrations. The owner implemented the fixes; this reviewer changed no application or tracked test source.

- Finding 1 resolved centrally: customer order messages use a separate dictionary with null hold fields, preserving the complete staff payload. The real hold → reassignment path and a direct independent helper probe pass.
- Finding 2 resolved: legacy stats now applies `require_daily_workset_staff` before querying. Exact shop staff roles remain supported; customers (including a real linked WorkOS principal), drivers, fleet managers, unscoped platform users, deleted users and missing-tenant staff are rejected. The accounting test now uses an owner; no active application frontend consumer of legacy stats was found. The existing dedicated fleet routes are unchanged.
- Finding 3 resolved narrowly: `staff_work_hold.can_read` admits authorized hold staff plus mechanics. All list/workspace/basic/detail paths null hold fields for other readers and detail excludes only the new hold events; existing customer finance/checklist/operation history protections remain in place. Owner and assigned-mechanic reads retain the reason/history. The independent driver reproduction now passes.

## Reviewed boundaries

- Both new write routes enforce an exact role allowlist through existing authenticated active-user dependency and again in the service. Fleet manager retains internal/fleet scope. Missing tenant, missing/deleted/wrong-tenant order and excluded roles fail before mutation.
- Tenant advisory try-lock precedes fresh tenant-scoped row lock. Status/editability and exact UTC version are checked under the lock. Replays/stale intent and final/effectively locked orders reject; legacy quote-sent behavior is preserved.
- Hold stops matching order/tenant sessions through the established audited helper, one shared timestamp and staff actor. Release starts no timer or attendance. The transaction owns all hold, timer and history writes; injected failures roll back. Post-commit notification failure does not falsely report a failed write.
- Existing operation execution, timer starts and completion reject held orders. SQL source and owner-provided seven real PostgreSQL race cases were reviewed; this reviewer has not rerun PostgreSQL or touched the shared preview database.
- UI retains the raw version captured on opening, does not optimistically mutate state or automatically replay failed writes, disables pending/stale submissions and uses text rendering for reasons/history. Server authority remains decisive.

## Independent checks to date

`python -m pytest tests/test_staff_work_hold.py -q --tb=short`: **49 passed** in 11.83 seconds; `/tmp/db115-security-tests.log`. Tests use isolated in-memory SQLite. Existing SQLAlchemy/Pydantic deprecation warnings only. Separate deliberate privacy probes reproduced findings 2 and 3; these are failed security assertions, not application verification passes.

Final independent rerun:

```sh
python -m pytest tests/test_staff_work_hold.py \
  tests/test_dashboard_stats_authorization.py \
  tests/test_dashboard_daily_workset_authorization.py \
  tests/test_dashboard_performance.py \
  tests/test_repair_order_hold_notifications.py -q --tb=short
```

**91 passed**, 22.07 seconds; `/tmp/db115-security-regate.log`. The two independent disclosure probes also pass after remediation (stats now denies with 403, driver detail excludes reason/events): **2 passed**, 2.61 seconds; `/tmp/db115-security-probes-regate.log`. Direct mocked websocket reproduction independently confirms null customer hold fields and an unchanged separate staff payload. `git diff --check` passes.

PostgreSQL concurrency evidence remains owner-run and independently source-reviewed, not rerun by this reviewer. No runtime service/browser/shared database/production state changed during this gate. Reviewed scope covers DB115's new operational fields/events and affected paths, not an exhaustive audit of legacy endpoint permissions. Protected CI, signed-in runtime acceptance and release evidence remain separate gates.
