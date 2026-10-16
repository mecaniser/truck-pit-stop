# Automated SMS and recovery contract — DB-COMMS-003

Owner: Architecture & API Contracts. Accepted implementation boundary: 2026-10-16. Deployment HOLD until approved real SMS acceptance. This contract specifies required behavior, not a completion claim.

## Persistence and service boundary

Use a separate `AutomatedSMSOperation` durable outbox because existing manual `SMSSendOperation` requires an actor, customer thread and message. Staff alerts must not create a fake customer or attach staff messages to a customer's conversation. Keep existing manual idempotency and authorizations intact.

`enqueue_automated_sms(db, *, tenant_id, domain_event_id, template_name, template_version='1', to, body, customer_id=None, recipient_user_id=None)` creates or returns an intent and flushes only. It NEVER commits, calls Twilio, or schedules a task before the caller's transaction commits. A validated tenant-contact recipient may be supported explicitly for existing staff fallback. Missing domain-event identity is a fail-closed error. No generic sender/body/task-ID deduplication.

Persist tenant, event identity, template/version, explicit recipient kind/ID, normalized sender/recipient snapshots, immutable body/hash, source, optional Notification/SMS links, state, attempt count, timestamps, reconciliation state and sanitized error. Unique tenant plus deterministic event/template/recipient identity key is enforced in PostgreSQL. Stable recipient identity is customer/user/tenant ID, not a changing address; address and sender changes on replay must not produce a second send for the same recipient/event. Normalize staff phone sets before fanout so one event does not send twice to identical phone formatting variants. Same event/key with changed payload must hold/reject rather than dispatch another message; template version deliberately changing is an explicit code-controlled new intent, never a retry mechanism.

Customer intents create tenant-qualified AUTOMATED SMS history using the existing thread and immutable address snapshots. Staff intents retain Notification-only history. New pending history must not claim sent/delivered. Accepted is provider receipt only; callback owns terminal delivery. Existing callbacks must locate the correct linked record without guessing customer ownership.

## Producer inventory and event identities

Every listed producer must switch from direct sending to transactional enqueue. Resolve recipients and render the SMS before the domain commit; leave email and websocket effects after it. Existing email helpers commit internally, so no email helper may execute between domain mutation and SMS enqueue. Rollback of the domain transaction must also roll back intents. Do not swallow enqueue/database failures and then claim the domain transition committed reliably.

| Producer | Stable business event identity |
| --- | --- |
| `api/v1/endpoints/repair_orders.py`: assignment | Order ID + mechanic ID + persisted assignment occurrence (`assigned_at` or durable assignment event). Repeating unchanged assignment must preserve occurrence; real reassignment creates a new occurrence. |
| Same: start work | Order ID + actual persisted work-start occurrence. An unchanged repeated action must not refresh occurrence solely for a new key. |
| Same: mechanic complete + admin complete | Both paths use the SAME order/work-completion occurrence and template, not route-specific keys. |
| Same: approve completion / ready pickup | Order ID + stable completion approval occurrence; repeated approval does not create another intent. Use durable event/transition identity, not generic `updated_at`. |
| `api/v1/endpoints/quotes.py`: publish/send | Quote ID + immutable revision/publication occurrence. Repeating the same publication is one intent. A genuine revised quote has a new revision/publication identity. |
| Same: authenticated decline + token decline | Both paths use quote ID/revision + decline occurrence, one event identity across routes and staff recipients. |
| `tasks/invoice_reminders.py` | Invoice ID + reminder sequence number persisted with reminder counters under the existing financial lock. Email must not release the financial transaction before enqueue. |
| `services/pending_zelle_staff_notification_service.py`: submission, called by `payments.py` and `invoice_access.py` | Invoice ID + durable pending-submission occurrence (persisted submission timestamp/claim ID), same identity across both routes. A later genuinely new submission is distinct. |
| Same: reminder, called by `tasks/pending_zelle_reminders.py` | Same pending-submission occurrence + stage 24h or 48h. Not task execution time. Preserve existing financial mutex. |
| `tasks/mechanic_timer_maintenance.py`, producer `services/mechanic_time_service.py:evaluate_idle_alerts` | Durable `MechanicIdleAlertStreak.id`. Include the streak ID in returned alert data and enqueue before the streak transaction commits. A later new streak may alert again. |
| `tasks/notifications.py:send_notification_sms` | Require explicit caller-supplied stable domain_event_id plus recipient identity. Missing legacy arguments fail closed without provider call; do not invent a Celery request ID. Use a synchronous Celery entrypoint running async logic, not a bare async Celery task. |

Legacy manual `messages.py` is outside automation semantics; preserve explicit manual behavior and do not dedupe intentional identical staff text. The automated default of `twilio_service.send_sms` must no longer provide an unprotected fallback. Require a valid event identity or reject automated calls; source scans/tests must show all automated producers migrated.

## Dispatch and recovery

`process_pending_automated_operations(db, sender, limit=50, tenant_id=None)` and manual `process_pending_operations` use bounded batches. Lock each pending operation, refresh current state, revalidate, set dispatching + attempt_count=1, and commit BEFORE provider I/O. Worker overlap/redelivery must produce one provider call. The durable operation itself is the queue; broker delivery is only a wakeup. Restart must find committed pending rows with no broker enqueue requirement.

Actor-less automation is authorized by a known internal producer/template and persisted tenant/event/recipient binding, never merely by actor_id being null. Before dispatch require active nondeleted tenant, tenant messaging/SMS enabled, explicit configured tenant sender (no global fallback), ready provider, supported template, valid normalized recipient and same-tenant recipient ownership. Customer sends additionally honor opt-out, unambiguous identity and current phone matching the frozen snapshot. No persisted service-update preference exists in the current schema; the prototype toggle is not authorization and must not be represented as an enforced backend control. Staff sends require active permitted same-tenant staff/user or explicit validated tenant-contact fallback, not customer permissions. Changed identity/sender, deleted recipient or changed eligibility rejects/holds without provider traffic. Unknown outcomes cannot be silently retried by a new task/event ID.

Definite provider rejection may become rejected; timeout, transport uncertainty, missing SID, server failure or crash after dispatch claim becomes unknown/reconciliation required. Never automatically resend unknown/dispatching/accepted/rejected rows. Stale dispatching is marked unknown after a bounded timeout exceeding provider call duration. A conclusively persisted SID/callback may reconcile status, but no phone/body/time matching. Isolate per-row recovery failures with rollback so one poison row does not starve other pending rows; infrastructure failures are visible as task failures, not success with an error string.

## Production schedule and controls

Add an explicitly imported synchronous Celery recovery task and a 60-second beat entry with 60-second expiry; default batch 10, processing budget 50 seconds, soft limit 70 seconds, hard limit 90 seconds. Check elapsed budget before each attempt; timeout after a dispatch claim leaves a held operation, never a retry invitation. One task invokes both manual and automated recovery. Registration and execution both honor `SMS_RECOVERY_ENABLED`; default false until authorized rollout. Disabling stops new provider attempts but never deletes queued/history rows. Worker startup schema readiness must include the new migration; missing tables/readiness prevent sending. No deployment configuration is changed in this task.

Production task uses the live adapter only; fake provider stays in isolated harness/tests. Validate configuration before scanning or dispatching and fail closed on missing/invalid sender credentials. Test default-disabled behavior, enabled registration, process restart, two overlapping runs, poison row isolation, pending recovery, stale unknown conversion and repeated ticks with zero repeat sends. Report bounded aggregate counters (examined/accepted/rejected/unknown/remaining or equivalent), elapsed duration and last-success/failure through existing logging/metrics conventions; never emit body, phone or secrets. Runbook records schedule name, enable flag, schema, worker/beat health checks, backlog/unknown inspection and rollback pause. No assertion of production activation based only on committed schedule code.

## Verification and ownership handoff

Backend owner: new outbox model/migration/service, actor-less guards, duplicate constraints, automated fallback removal, callback projection and real PostgreSQL concurrency tests. Producer owner: all inventory endpoints/tasks/helpers, stable event identities and transactional boundaries, rollback/replay/new-occurrence tests. Release/root owner: scheduler/settings/schema readiness, isolated runtime verification, workflow checks, board/PR and deployment HOLD. These scopes must agree on enqueue signature before editing.

Required evidence: same-event concurrent attempts -> one operation/provider call; replay changed body/phone held; distinct legitimate event allowed; domain rollback -> zero intent/provider call; tenant/opt-out/staff-deactivated negatives; sender change and unknown outcome no send; customer history versus staff-only Notification; every producer covered; required CI and independent fresh Security/QA gate. Real Twilio/carrier acceptance remains pending and required before deployment.

New automated producers enqueue even while recovery is disabled; they must remain visibly pending and may not fall back to the legacy provider sender. Production rollout enables recovery only after real SMS acceptance. PostgreSQL row claims remain the correctness mechanism even if an optional overlap-suppression lease expires or a worker restarts.
