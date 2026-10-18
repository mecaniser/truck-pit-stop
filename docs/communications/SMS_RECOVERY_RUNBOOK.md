# SMS recovery — DB-COMMS-003

The user authorized merging and deployment of the dormant foundation. Live SMS
rollout and Twilio registration submissions remain on hold pending real delivery
and callback acceptance. No production setting is enabled by this branch.

## Rollout contract

Apply migration178 through the existing Web migration owner before workers run.
Worker startup checks the installed Alembic head and physical outbox columns.
The migration is additive and does not enqueue historical notifications.

`SMS_RECOVERY_ENABLED=false` is the default. Disabled Beat instances register no
SMS cadence; the task also checks the flag before any provider, Redis or DB work.
`SMS_AUTOMATION_OUTBOX_ENABLED=false` preserves existing immediate automated
SMS behavior at its original transaction boundary. It creates no durable SMS
intents. The isolated harness explicitly enables this flag for duplicate-safety
tests. When true, migrated producers write transactional intents and require
recovery to dispatch them; enabling producers without recovery pauses delivery.
A pending record is not provider acceptance or delivery.

After real SMS acceptance and explicit enablement authorization, configure the
same settings for Web, Worker and Beat. Automation rollout is global: the recovery
allowlist must cover every tenant producing automated intents before enabling it.
Do not enable automation for shops outside that dispatcher scope:

- `SMS_AUTOMATION_OUTBOX_ENABLED=true`.

- `SMS_RECOVERY_ENABLED=true`.
- `SMS_RECOVERY_TENANT_IDS=<explicit comma-separated tenant UUID allowlist>`.
  Empty or invalid production lists fail closed.
- `SMS_RECOVERY_BATCH_SIZE=10` (range1–25, per queue/tenant per tick).
- `SMS_RECOVERY_BUDGET_SECONDS=50` (maximum50).

Production requires the live provider adapter and available credentials. Both
manual and automated dispatch recheck current recipient/sender and tenant access.
The schedule runs every60seconds; queued ticks expire after60seconds. Tasks use
soft70/hard90second limits and an overlapping-worker Redis lease of110seconds.
Database row claims supply duplicate protection even if the lease expires.
The work budget covers the whole tick, with rotating tenant/queue priority.
No provider call is made while holding a database transaction.

## States and incident handling

Only `pending` may dispatch. The claim commits `dispatching` and attempt1 before
provider I/O. Acceptance stores the provider receipt, while callbacks establish
delivery. Provider timeouts, missing receipts and interrupted dispatches are held;
stale dispatching rows become `unknown` after5minutes. Unknowns never automatically
return to pending. Malformed individual operations are held for reconciliation so
they cannot starve later batches. Infrastructure failures remain failed tasks.

Observe Celery task outcomes plus `sms_recovery_completed`,
`sms_recovery_budget_exhausted` and `sms_recovery_failed` events. Counters report
examined/accepted/rejected/unknown/skipped/errors and elapsed time without message
bodies or phone numbers. Check oldest pending age and state counts scoped to the
allowlisted tenants in both `sms_send_operations` and `automated_sms_operations`.
Sustained backlog, unknown growth, readiness failures or repeated budget exhaustion
require investigation; queued/accepted is not proof of handset delivery.

Pause dispatch by setting `SMS_RECOVERY_ENABLED=false` for Worker and Beat and
restarting those services. Keep the automation outbox flag enabled after adoption
so new events cannot fall back to unprotected immediate delivery. Disabling the
automation flag after queued operations exist requires a separate reconciliation
and rollback review; never dispatch queued operations and legacy copies together.
An in-flight provider call may finish, but redelivery cannot reclaim its operation.
To investigate an unknown, reconcile the provider receipt/status through the
existing signed-callback path and read-only provider evidence. Do not reset its
state, clear its key, create a new event identity or replay it to “try again.”
No automatic reconciliation/resend feature is implied by this foundation.

## Local reproduction

Use `docs/communications/LOCAL_SETUP.md` for the explicitly isolated environment.

```sh
python scripts/communications_local.py exec python -m pytest tests/test_automated_sms_outbox.py tests/test_automated_sms_guards.py tests/test_automated_sms_producers.py tests/test_sms_recovery.py tests/test_communications_service.py tests/test_sms_callback_reliability.py tests/test_worker_schema_readiness.py
python scripts/communications_local.py exec python ../scripts/verify_sms_recovery_local.py
```

The second command starts actual Celery Worker and Beat child processes with a
local-only two-second cadence, only the communications queue, explicit tenant
scope, the simulated adapter and a Twilio network-denial guard. It verifies
persistence, same-event replay, restart and uncertain-outcome no-retry behavior,
then stops only its own child processes. Production uses the60second cadence.

Financial reminders are revalidated under the tenant financial mutex at dispatch.
A paid/cancelled invoice, replaced/resolved Zelle event, changed debt/payment
snapshot, reassigned mechanic or resolved idle streak suppresses the stale alert.
Mutex contention leaves the intent pending for a later tick. Invoice reminder
copy currently quotes the full invoice total; rows with preexisting partial or
refunded payments/confirmed settlement principal are conservatively rejected as
`financial_balance_review_required` until balance-aware copy is implemented.
