# DB102 service-template checklists — implementation evidence

Accountable owner: Backend & Integrations. Contract:
[`db102-service-template-checklists.md`](../contracts/db102-service-template-checklists.md).
Implementation branch: `codex/service-template-checklists`, baseline
`91045a625f89d84221aaf8ed74d1cdc7d92438b6`.

## Backend behavior

- Staff-only template GET/PUT use explicit tenant/deleted-service predicates,
  strict payloads, stable server task IDs, whole-list replacement, optimistic
  versions, and a Service row lock. Customer ServiceResponse is unchanged.
- New canonical, legacy, repair-operation and fleet service applications create
  immutable execution snapshots in the same transaction. Reapply and historical
  empty snapshots stay unchanged. PM reseeding reattaches retained task IDs and
  evidence; removed work archives its task rows; ambiguous mappings fail first.
- Tenant/order/live-labor scoped task reads and writes enforce role, assignment,
  fleet scope, open state and pricing locks. Server identity/time is recorded;
  reopening retains prior evidence in internal history. Same-state retries do
  not overwrite evidence or create events; stale versions fail with 409.
- All four completion routes and generic final-status changes run the shared
  full-scope guard before status/timer/points/invoice/notification/PM/incident
  effects. Required tasks block; optional tasks and historical orders do not.
  Row locks serialize task changes, line removal, completion and assignment.
- Both line-removal paths retain scope-removal history. Cancel, soft delete,
  restore and internal reopen retain progress. Customer detail excludes all four
  internal checklist event types; new routes deny customer/driver/super-admin.

## Runtime preflight (2026-10-12)

Read the mandatory local-runtime and delivery skills before editing. Intended
checkout is `/Users/sergio_m1_promax/.codex/worktrees/service-template-checklists/truck-pit-stop`.
At intake only the DB102 board/contract files were dirty. Vite port 5174/PID52233
and API port8001/container `dieselbridge_api_ets-workflow-parity` both served the
separate `ets-parity-preview` checkout. Their source cwd/bind mount were checked;
those processes and the original 5173 runtime were preserved. No server was
started by the backend implementer; this checkout was **not browser-verified**
at this handoff. No environment/provider settings were changed.

## Migration and concurrency

Product & Delivery Lead created and authorized the dedicated local PostgreSQL
clone `truckpitstop_db102_test_20261012` at revision164. Only this clone was
upgraded. `alembic upgrade head` succeeded from `164_motive_driver_journal` to
`165_service_checklists`; `alembic current` reports165 as the sole head. Original
and preview databases were not migrated by this implementation step.

The migration adds two Service columns and the indexed/constraint-checked task
table, with no historical task backfill. Labor FK removal preserves evidence;
true order purge cascades. After adoption, roll back application code while
retaining the additive schema. A downgrade intentionally removes new evidence
and is not the normal rollback procedure.

Four real PostgreSQL two-session cases pass:

1. Uncheck holds the RO lock; finalization waits, then fails with the required
   task count after the uncheck commits.
2. Finalization holds the RO lock; uncheck waits, then fails because the order is
   finalized after completion commits.
3. A template save holds the Service lock; a competing stale save waits, then
   gets409 and cannot overwrite the winning revision.
4. Labor removal holds the RO lock; a competing task check waits, then gets404.
   The archived snapshot and scope-removal evidence remain.

The opt-in test requires a localhost database name containing `db102_test`, uses
fresh synthetic tenant IDs, and cleans only those tenant-scoped fixture records.
It never drops or recreates shared tables and invokes no external provider.
From the repository root, using the project's Python runtime and the dedicated
local development DSN supplied through `DB102_POSTGRES_TEST_URL`:

```sh
python -m pytest backend/tests/test_service_checklists_postgres.py -q
```

Result: **4 passed**, twice after integration/formatting. SQLite alone is not used
as row-lock evidence.

## Automated verification

```sh
python -m pytest backend/tests/test_service_checklists.py -q
python -m pytest backend/tests/test_fleet_board.py backend/tests/test_price_build_service.py -q
python -m pytest backend/tests/test_repair_order_finalization.py backend/tests/test_fleet_workflows.py backend/tests/test_repair_order_danger_action_rules.py -q
```

- Checklist contract suite: **49 passed**, including successful mechanic/admin/approval/fleet completion with required tasks complete and optional task unchecked.
- Existing fleet board/price builder: **37 passed**.
- Checklist suite plus finalization/fleet workflow/danger-action regressions:
  **143 passed** before the four extra positive completion-route cases were added.
- New model/schema/helper/migration/tests: Ruff checks pass. Changed integration
  modules: undefined-name checks pass. Python compilation and `git diff --check`
  pass.

The fixtures use synthetic `.invalid` accounts. Blocked completion explicitly
asserts unchanged order status/time and zero email/SMS/timer/broadcast calls.
Positive completion cases mock messaging transports; invoice persistence stays
inside the isolated test database and no payment provider is invoked.

Coverage includes template limits/identity/versioning; snapshot independence;
all application hooks; task attribution/no-op/stale state; denied roles,
assignment and tenant scope; frozen/deleted/foreign/malformed live-labor joins;
108-task pagination and whole-order gate counts; both removal paths; PM retained,
empty, added, removed and ambiguous service selections; customer-history privacy;
and cancel/delete/restore/reopen preservation.

## Handoff boundary

Implementation and implementer checks are not independent approval. Fresh
Security and QA review, authenticated desktop/compact browser acceptance,
protected PR checks, merge, production migration and release remain separate
required evidence. Root owns browser/runtime integration and outbound messaging
suppression for synthetic acceptance. No production mutation, release, or
provider-account change was performed by this backend work.
