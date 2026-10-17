# SMS callback reliability contract — DB-COMMS-001C

Architecture & API Contracts, 2026-10-16. Existing delivery statuses: pending may advance to any known state; queued to sent or terminal; sent to terminal. Delivered, failed and undelivered are sticky terminal states. Conflicting terminal evidence needs reconciliation.


Existing schema can support this without adding shared-inbox tables:

- Recognize queued, sending/sent, delivered, undelivered, failed/canceled. Empty/unknown status is acknowledged no-op, not pending.
- Apply progression above. Duplicate state preserves original timestamps. Update SMS and linked Notification consistently in one transaction only for accepted progression. A known failure receipt carrying 21610 can still enforce opt-out independently of a rejected delivery transition.
- Missing SID: 400. If no SMSMessage exists, look up SMS-type Notification by external_id (at most two rows): exactly one means a valid legacy Notification-only send; acknowledge 200 without mutation, preserving baseline behavior. Multiple matches are ambiguous: 503, never pick a tenant/customer arbitrarily. No match in either table means retryable 503 because current send can receive callback before the SID transaction commits. Do not log body/phone. Unknown status with known SID: 200 no-op. Notification-only callbacks do not infer a customer or change opt-out; their monotonic delivery tracking remains a separate slice.
- Processing/persistence exceptions: rollback and return non-2xx (503 preferred); never report success. Invalid signature remains 400. Post-commit websocket errors may cause a retried callback; duplicate handling must be harmless.
- This is not a durable receipt inbox, sender idempotency, or guaranteed provider retry configuration. Those remain separate work. Existing webhook route paths and successful response shape remain compatible.

Required fixtures/tests: queued->sent->delivered; pending->delivered; delivered->queued ignored; sent->queued ignored; terminal conflict ignored; duplicate delivered preserves timestamp; unknown status no-op; malformed missing SID; unknown SID; unique Notification-only SID acknowledged without mutation (including 21610); ambiguous Notification SID fails closed; database failure returns non-2xx and rollback; invalid signature; opt-out receipt; two tenants cannot reference each other's operations/conversations; same key concurrent submit; timeout held; draft switching; opt-out composer disabled. Backend-only requirements beyond bounded correction are future acceptance criteria, not passing tests today.
