# DB-115 backend implementation evidence

Backend & Integrations implementation handoff, 2026-10-13 local. This is owner evidence, not independent QA/Security approval. Contract: [staff hold](DB115_STAFF_HOLD_CONTRACT.md). No migration, production writes, commit, push or release performed by this owner.

## Implementation

- New staff-only `staff-hold` / `staff-release-hold` routes share a tenant-serialized service using the existing tenant advisory lock before the scoped, refreshed repair-order row lock.
- Strict request bodies validate aware timestamps and trimmed 1–100 character reasons. Exact UTC comparison and a monotonically increasing microsecond timestamp reject stale and repeated transitions. Only editable in-progress work qualifies; fleet-manager scope remains internal or fleet work.
- Hold uses one instant for every matching active technician session and the hold boundary. Existing timer-stop auditing records the staff actor. Release clears hold state without creating a timer or attendance/break activity. All state and history commit together; exceptions roll back the request transaction.
- Internal hold/release history preserves before/after reason/time, actor ID and display-name snapshot. List, basic, detail, projected workspace and fallback workspace responses redact hold values to null for all readers outside authorized staff plus mechanics; both hold event types are excluded from these readers' history. Existing response fields remain compatible. The original customer financial and checklist/operation-history filters remain separate.
- After commit, staff order updates suppress customer delivery and status notifications. Each stopped mechanic receives their own timer update. Failed socket delivery does not convert a committed operation to a failed response or suppress attempts to notify the remaining mechanics.
- Privacy regression checks exposed existing invalid assignments to nonexistent `RepairOrderResponse.labor_discount_amount` / `order_discount_amount` fields in unpublished customer list/workspace reads. Removed those assignments; these fields were never part of that response schema. Customer response paths now execute without that 500.

Application files:

- `backend/app/schemas/staff_work_hold.py`
- `backend/app/services/staff_work_hold.py`
- `backend/app/api/v1/endpoints/repair_orders.py`
- `backend/app/core/websocket.py`
- `backend/app/api/v1/endpoints/dashboard.py`

Tests: `backend/tests/test_staff_work_hold.py`, `backend/tests/test_staff_work_hold_postgres.py`, `backend/tests/test_dashboard_stats_authorization.py`, one corrected accounting-summary fixture role in `backend/tests/test_fleet_workflows.py`.

## Automated evidence

Interpreter: `/Users/sergio_m1_promax/GitHub/truck-pit-stop/backend/venv/bin/python`; cwd is this worktree's `backend`, so imports resolve implementation source. The preview files were not modified by this owner.

```sh
python -m pytest tests/test_staff_work_hold.py tests/test_operation_execution.py \
  tests/test_repair_order_hold_notifications.py \
  tests/test_repair_order_workspace_projection.py tests/test_repair_order_shop_notes.py -q --tb=short
```

Initial implementation result: **95 passed**, 25.56 seconds, including **49** new hold cases plus related operation, legacy hold notification, workspace projection and shop-note regressions. Local log: `/tmp/db115-backend-tests.log`. Security corrections and their final affected-suite results follow below.

Coverage includes every authorized staff role/fleet scope, excluded roles, tenant/missing/deleted boundaries, all non-in-progress stages, effective versus quote-sent pricing locks, exact timestamp offsets/precision, stale/repeated actions, HTTP auth/validation/minimal payload, two-mechanic stop attribution, other order/misc/tenant preservation, timer/operation/completion guards, explicit restart after release and mechanic self-resume compatibility. Database snapshots prove financial/order fields, operation assignments/versions, checklist evidence, recommendation provenance, attendance and break records remain unchanged. Injected second-stop and history failures prove rollback. Notification failures and all customer read paths, projected/fallback and unpublished/published, are exercised.

PostgreSQL races use the existing restricted `/tmp/db110-postgres-test-url` receipt, passed in-process as `DB110_POSTGRES_TEST_URL` without printing its contents:

```sh
python -m pytest tests/test_staff_work_hold_postgres.py -q --tb=short
```

**7 passed**, 5.23 seconds. Fixture rejects any host other than localhost/127.0.0.1 or database not starting `db110_test`; target was the isolated existing `db110_test_operation_execution`. It inserts unique synthetic tenant data and removes only its tenant records; no reset, migration, preview data or production connection. Cases: hold wins timer start; timer start wins and a refreshed hold stops it; competing hold/release; release versus mechanic resume in both directions; completed order and pricing-lock finalization beat hold. Held orders have no active timer; losing contenders have no extra event. The legacy mechanic route retains its existing app-level `invoice_busy` domain-error 409 envelope. Log: `/tmp/db115-postgres-tests.log`.

`compileall` passed for all three changed application files. `git diff --check` passed. Only existing SQLAlchemy/Pydantic deprecations and the known PostgreSQL fixture metadata dependency-cycle warning appeared.

## Independent Security findings returned to implementation

Security identified three alternate disclosure paths after the initial handoff. Owner corrections:

1. A later lead reassignment could call the common order broadcaster with the existing hold reason and default customer delivery. The broadcaster now sends a distinct customer payload with null hold fields, preserving the staff payload unchanged. Actual hold → reassignment regression and direct notification-contract cases reproduced the disclosure before the fix (two failures/one pass) and pass after it. Other public status/update fields remain unchanged.
2. Legacy `/dashboard/stats` allowed authenticated nonstaff principals to read the tenant-wide operational summary, including private holds. It now calls the existing `require_daily_workset_staff` guard before querying. The deliberately supported roles remain owner/admin/receptionist/mechanic; customer, driver, fleet-manager, platform, deleted and unscoped principals are denied. Current frontend has no actual caller of this legacy endpoint. The fleet accounting-summary regression now requests it as owner; dedicated fleet APIs are unchanged. This is an intentional compatibility/security correction for any nonstaff direct stats caller.
3. Legacy repair-order reads also accept DRIVER (and some platform) readers. Hold redaction/history suppression now uses the explicit internal hold-reader allowlist, independent of existing customer-only financial filters. Tests exercise customer, driver and platform readers on published/unpublished orders, projected/legacy lists and projected/fallback workspace, basic/detail and both history events. Assigned mechanics retain hold/history access.

Final affected-suite command:

```sh
python -m pytest tests/test_staff_work_hold.py tests/test_dashboard_stats_authorization.py \
  tests/test_dashboard_daily_workset_authorization.py tests/test_dashboard_performance.py \
  tests/test_repair_order_assign_mechanic_notifications.py \
  tests/test_fleet_workflows.py::test_dashboard_stats_reports_internal_costs_separately_from_revenue -q --tb=short
```

**99 passed**, 23.80 seconds, including **61** hold cases and **11** new stats-authorization cases. Real linked WorkOS customer/driver HTTP credentials are tested through the app's normal authentication boundary. `/tmp/db115-security-fixes.log`; the prior failing disclosure receipt is `/tmp/db115-websocket-regression.log`. Compile checks passed for all updated application modules; whitespace check clean. Transaction logic is unchanged from the seven PostgreSQL races above. Returned to the independent Security reviewer for re-gate; owner does not self-approve that gate.

## Runtime boundary and remaining gates

Fresh preflight confirmed branch `codex/staff-work-hold`, implementation HEAD `b318bb94`; intentional split preview at `127.0.0.1:5174`, Vite PID23640/cwd `ets-parity-preview/frontend`; API container `dieselbridge_api_ets-workflow-parity` publishes 8001 and bind-mounts `ets-parity-preview/backend`. Proxy readiness is healthy; database identity `postgres / truckpitstop_ets_workflow_parity_20261012`. Parent owns source mirroring and runtime restart/acceptance. This owner made no browser-verification or physical-device claim. Independent QA/Security, final signed-in desktop/mobile journeys and protected CI remain parent-owned gates.
