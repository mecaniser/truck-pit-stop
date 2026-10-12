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

## Final local acceptance and independent gates — 2026-10-12

Frontend source45baf26f adds explicit checklist light/dark contrast after the first Modern browser pass exposed unreadable task fields. The correction is confined to checklist components/styles. Frontend137files/1173tests, final13focusedcases, TypeScript/Vite and scoped ESLint pass. Fresh independent review reran184backend,4real PostgreSQL races and13initialfrontend tests, then48combined recommendation/checklist frontend cases after visual corrections. Security/data integrity and final local QA: **GO**; reviewer had no implementation participation. Detailed local report: `/tmp/db102-independent-gates.md`.

Authenticated real-API acceptance ran in the synthetic `ets-parity-qa` tenant:

1. Owner created a service with two required tasks and one optional task, saved it, then applied it to assigned `QA-CHECKLIST-JOB`. All three tasks were read-only before work started.
2. Owner edited the template first task to include air hoses; existing job retained its original wording. A subsequently created fleet PM got the updated wording.
3. Assigned synthetic mechanic clocked in and started work. Quick Job Done returned409 for two missing required tasks, left the timer/order active, and opened the checklist. First check recorded Casey Checklist QA and server time and survived reload. Both required tasks complete with the optional unchecked allowed pending review.
4. Owner finalized review into a synthetic local invoice. All task controls immediately became read-only; names/times and optional-open evidence remained. No payment was recorded.
5. Fleet PM creation produced the same shared checklist. Its actual completion submit returned409 with one required task still open and displayed guidance. Checking it allowed completion200; truck returned On the road and next-PM mileage advanced by its25,000-mile interval. An existing missing invoice-contact guard was respected; only the synthetic truck received an `.invalid` invoice address for acceptance.
6. Started PM scope reseeding returned409 without changing checked task identity/time/actor/version. A separate draft PM retained three task IDs while labor rows were reseeded; adding/removing/re-adding scope created, archived and then created fresh unchecked task identity correctly. Auxiliary draft was soft-deleted and temporary service deactivated. Receipt: `/tmp/db102_pm_api_receipt.json`.

Modern desktop and compact template inputs, required status, task text, actor/time and read-only controls were visually checked after correction. Compact mechanic checklist is readable and usable. A separate DB099 mobile scrolling correction is needed alongside this feature to make Modern staff RO content comfortably scroll; it is tested in the combined preview and should land before DB102's Modern rollout. Desktop/compact evidence stays local in preview `output/ets-parity/checklist-{template-fixed-desktop,template-fixed-mobile,mechanic-mobile,finalized-desktop,finalized-mobile,fleet-desktop,fleet-blocked}.jpg`.

Final combined preview source: `a0ba3f5324aa48dbe665ae9c39dbd9ce93f23568`, including DB0984462851a, DB0996c8dac80, DB1006b1eac5b and DB10245baf26f. FrontendPID61599 at `http://127.0.0.1:5174` serves its confirmed preview/frontend cwd and explicit API8001 proxy. API container `da0d8e5e2be1…` binds preview/backend. Direct and proxied `/health/ready`200; database/Redis healthy. Isolated database `truckpitstop_ets_workflow_parity_20261012` upgraded164→165; original local database retained149. Redis9; no worker. Only preview process Resend/Twilio credentials were blanked with a temporary compose override to prevent synthetic notification transport. Original environment/provider configuration is unchanged. UI wording about customer notification is not evidence of delivery; test notifications were not sent.

Mandatory runtime preflight rerun after integration/restarts; matching rendered build indicator and changed feature checked. Combined142files/1247frontendtests pass. Production build passed3219modules before the final CSS-only refinement; the final focused CSS branch build also passes. This is **aligned and browser-verified local work**, not merge/deployment evidence.

## Release gate

Land the additive migration165 after164 before serving checklist code; verify a single migration head. DB099's compact Modern scrolling change should precede or accompany the UI rollout. Existing orders receive no retroactive tasks. Roll back application code while retaining additive schema/evidence; do not downgrade away collected checklist history. Watch template/task errors, completion409 reasons and completion rates on synthetic then operator-approved rollout; stop if required tasks can be bypassed, cross-tenant data appears, or historical orders regress. Protected PR checks, merge and production migration/deployment remain outstanding.
