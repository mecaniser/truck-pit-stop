# Shared inbox implementation contract — DB-COMMS-002

Owner: Architecture & API Contracts. Date: 2026-10-16. Status: approved implementation boundary, not release evidence.

This specifies the first persisted SMS inbox slice of `SHARED_INBOX_CONTRACT.md`. It deliberately reuses `MessageThread`/`SMSMessage` history rather than silently migrating historical identities. WhatsApp and Telegram remain unavailable. An isolated PostgreSQL database with synthetic customers and a simulated provider is the acceptance environment; real provider/carrier delivery is a separate pre-deployment gate.

## Scope and compatibility decision

Use existing thread IDs as conversation IDs. Add workflow status, assignee and optimistic version (either columns on `MessageThread` or a one-to-one tenant-scoped metadata table), a per-user read watermark, and a dedicated durable SMS send-operation table. An operation is also the durable work queue; it must not pass through the email outbox worker's lease-expiry retry path.

For this SMS-only compatibility slice, `channel_account_id` and `contact_identity_id` are stable opaque UUID handles derived server-side from tenant + configured sender and tenant + thread + normalized actual recipient respectively (UUIDv5 with fixed application namespaces is acceptable). They are not claims of provider onboarding or independently verified identity. Include immutable actual sender/recipient on the persisted send operation and SMS message. The server reconstructs and checks both handles at send time; changed sender/recipient invalidates stale forms.

Do not assign every historical message to today's customer phone. Return historical messages unchanged. Sending is blocked with `identity_unverified` if historical remote addresses conflict, the current normalized phone disagrees with the established remote address, or another active same-tenant customer owns the same normalized phone. A thread with one consistent legacy remote address and matching unique current customer phone is eligible under existing SMS compatibility provenance; do not label that identity independently verified. Missing sender blocks `not_connected`; no global sender fallback. Legacy archive/deletion behavior stays intact; inbox resolution is separate from archive. New inbound reopens the workflow. No WhatsApp/Telegram rows are fabricated by the real adapter.

The existing `/messages` API remains compatible. This first slice guarantees duplicate safety for new `/communications` send operations only; existing automated and legacy sends must be explicitly identified as outside that guarantee until migrated. Never claim global SMS idempotency from this slice. The old APIs must not be used by the connected prototype. No background replay/backfill of old messages.

## Authentication and tenancy

All routes below are under `/api/v1/communications`, authenticated with the application's existing `get_current_active_user` and messaging permission rules. Require a real active tenant and `messaging_enabled`; missing tenant/disabled messaging is 403, missing login is 401, unauthorized role/grant is 403. Derive tenant and actor only from auth. Every conversation, message, operation, assignee, customer and context query has an explicit tenant predicate. Foreign or deleted IDs are 404. Assignment additionally requires an active user with a messaging-capable role or grant. No alternate preview authentication in production routes.

## Exact wire shapes

JSON uses snake_case. UUIDs are strings, timestamps timezone-aware ISO strings. Frontend maps explicitly to its existing camelCase model. Extra fields may be added without breaking clients.

`GET /bootstrap` returns:

```json
{"tenant_id":"UUID","user_id":"UUID","delivery_mode":"simulated","assignees":[{"id":"UUID","name":"Alex Morgan"}],"channels":[{"channel":"sms","connected":true},{"channel":"whatsapp","connected":false},{"channel":"telegram","connected":false}]}
```

`delivery_mode` is `simulated` or `live`, derived from the server provider adapter. Never infer it from frontend config.

`GET /conversations?limit=100&cursor=...&channel=sms&status=open&search=...` returns `{"items":[Conversation],"next_cursor":null,"has_more":false}`. Optional status is open/resolved; omitted means both. Optional channel restricts channel (unsupported channels yield empty items). Search is tenant-scoped, matches customer name/company/phone/message body, bounded to 200 characters. Pagination limit 1–100, default 100. Cursor is bound to tenant and active filters and orders descending by `(last_message_at,id)`; malformed/mismatched cursor is 400. GET never changes read state. Clients must consume pages rather than silently treating the first 100 as the complete inbox.

```json
{"id":"UUID","tenant_id":"UUID","customer_id":"UUID","customer_name":"Daniel Brooks","company":"Northline Transport","channel":"sms","channel_account_id":"UUID","contact_identity_id":"UUID","identity_label":"+12025550101","status":"open","assignee_id":null,"unread_count":1,"last_message_at":"2026-10-16T16:00:00Z","preview":"Any update?","version":1,"messages":[],"send_policy":{"can_send":true,"reason":null},"context":{"vehicle_label":"Truck 402","repair_order_label":"RO-1042","repair_status":"In progress","concern":"Air leak"}}
```

Context is optional (empty object allowed) and must come only from tenant-owned records, never fixture defaults. List messages may be empty to avoid large response bodies.

`GET /conversations/{id}` returns Conversation with latest 50 messages (oldest first) plus `messages_has_more` and `messages_next_cursor`. `GET /conversations/{id}/messages?limit=50&cursor=...` returns `{"items":[Message],"has_more":false,"next_cursor":null}`; cursor walks older messages. Message:

```json
{"id":"UUID","conversation_id":"UUID","channel":"sms","direction":"outbound","source":"staff","body":"Your estimate is ready.","created_at":"2026-10-16T16:00:00Z","delivery_status":"queued","error_code":null,"send_operation_id":"UUID"}
```

Source maps existing inbound/manual/automated to customer/staff/automation. Inbound always displays `received`. Outbound statuses are pending/queued/sent/delivered/failed/undelivered/unknown. Unknown comes from associated operation state, without forcing an unsafe PostgreSQL enum rewrite. Provider errors are sanitized; no raw exception payloads.

`PATCH /conversations/{id}` accepts `{ "expected_version":1, "status":"resolved", "assignee_id":null }`. Fields other than expected_version are optional; omitted assignment means unchanged, explicit null means unassign. Return updated Conversation. Atomic expected-version comparison; conflict 409 `stale_version` with no partial mutation. Increment version for workflow or new message changes, not read watermarks.

`POST /conversations/{id}/read` accepts `{ "through_message_id":"UUID" }`; returns `{ "unread_count":0 }`. Referenced message must belong to tenant+conversation. Persist current user's maximum `(created_at,id)` watermark without moving it backwards. Count only later inbound messages; another user's unread count is unchanged; later arrivals remain unread. Empty threads need no read call.

`POST /conversations/{id}/send-operations` requires `Idempotency-Key` (nonempty, maximum 128 characters) and body:

```json
{"channel_account_id":"UUID","contact_identity_id":"UUID","body":"Your estimate is ready.","expected_version":1}
```

Return 202 once the operation and pending SMSMessage are durable; same-key replay returns 200 with original operation. Shape, also returned by `GET /send-operations/{id}`:

```json
{"id":"UUID","conversation_id":"UUID","message_id":"UUID","state":"pending","delivery_status":"pending","replayed":false,"can_retry":false,"reconciliation_state":"none"}
```

States pending/dispatching/accepted/rejected/unknown. Reconciliation none/required. `can_retry` is false throughout this first slice: no resend endpoint. A new intentional manual message with a new key is allowed except while the conversation has an unresolved unknown/dispatching operation. UI polls the operation and refetches conversation; it never optimistically claims delivery. If browser transport fails, retain the exact key/body/account/identity snapshot and recover by resubmitting that same intent, not generating another key. Payload hash covers tenant+conversation+account+identity+canonical trimmed body (exclude expected_version, which may change because the original operation itself appended a message). Replay lookup and hash comparison happen before current version/policy checks, but after auth/tenant checks. Same key/different payload returns 409 `idempotency_conflict`.

API errors use the repository's FastAPI envelope with a structured detail: `{"detail":{"code":"stale_version","message":"Conversation changed. Refresh and try again."}}`. This is an explicit adaptation from v1's proposed error envelope. Frontend also handles existing string `detail` authentication errors. 409 codes: stale_version/idempotency_conflict/opted_out/identity_unverified/not_connected/ambiguous_outcome. Validation is 422; rate limiting 429 with Retry-After. Replayed operations do not consume a second send-rate slot.

## Durable dispatch and failure boundary

Database enforces unique `(tenant_id,idempotency_key)` and one operation/message linkage. Handle the concurrent insert race with PostgreSQL conflict handling or savepoint rollback+lookup, never a second provider invocation. An accepted creation transaction includes the operation, pending SMSMessage, corresponding Notification if existing receipt compatibility needs it, and thread preview/version update. Commit before provider I/O.

A separate dispatcher claims `pending` by atomic state comparison/row lock, changes it to `dispatching`, increments attempt count to exactly 1 and commits that state before calling provider. Recheck tenant feature, current actor access, consent, configured sender and exact identity immediately before claim. Rejection before I/O is conclusive and creates no provider attempt. No database transaction remains open across external provider I/O. A bounded background/task dispatcher may be scheduled after commit, but persisted pending rows must also be recoverable by an explicit bounded processor after restart.

Only pending operations are dispatchable. Never reclaim dispatching for a second send. Stale dispatching becomes unknown/reconciliation-required after a documented timeout longer than provider timeout. A timeout, network exception, process death after dispatching commit, or database failure after provider acceptance is uncertain: preserve the durable operation, expose unknown/held, attempt_count remains 1, no automatic or manual retry. Confirmed provider rejection may be `rejected`; generic exceptions are never conclusive failure. Provider acceptance with SID persists accepted + SID + delivery state atomically. Callback-before-SID-commit remains retryable 503 per PR559. Accepted SID callbacks advance normal message state; unknown without SID is not reconciled by body/time guesses.

PR559 callback correction is a prerequisite: preserve monotonic statuses, terminal stickiness, tenant-qualified linked Notification updates, 21610 opt-out, unknown SID503, unique legacy Notification-only no-op200 and rollback on failure. Do not weaken signature verification for simulation. Callback changes may update linked operation state when exact SID proves acceptance; never regress accepted to pending or resend an unknown operation.

## Simulation and isolated acceptance

Simulation must be dependency-injected in tests or selected by explicit nonproduction configuration. Fail startup if simulated mode is selected in production. Default production path remains real adapter; missing real credentials fails closed, never silently simulates. Do not infer simulation from missing credentials. The local launcher must verify dedicated synthetic database identity and no production Twilio credentials, and bind locally. Simulated provider returns deterministic fake SIDs and records durable call evidence so duplicate assertions survive process restart. Its controls are CLI/test-harness only or a separate development-only application; no public unauthenticated injection endpoint and no production route accepting caller-selected provider outcomes.

Exercise accepted→sent→delivered, confirmed rejection, accepted-but-timeout unknown, duplicates/concurrent requests, delayed/out-of-order/duplicate callback handling, inbound reply reopening resolved, persistent assignment, two independent user read watermarks, opt-out blocking, switched-recipient stale form, cross-tenant IDs/assignment/read/send and missing permission. Database acceptance must prove one operation, one SMS history row and one simulated provider invocation for concurrent same-key submissions. Restart/recovery must prove pending dispatch and no replay of dispatching/unknown. Browser acceptance includes refresh persistence, safe drafts across selection, double click/network retry behavior, failure visibility and desktop/mobile.

## Migration, rollout and remaining boundaries

Use an additive Alembic migration from the verified current single head. No production data rewrite or seeded rows in migration. Index tenant/status and unique tenant/key; enforce tenant ownership with composite foreign keys where practical and service predicates everywhere. Per-user watermark migration must not erase legacy global unread fields. Existing messages/history IDs remain exact. Test upgrade against isolated PostgreSQL, relevant downgrade behavior, and verify migration graph.

This is ready for implementation, not production enablement. Legacy automated/manual send paths still require their own migration to durable intents and domain-event idempotency before any platform-wide duplicate-safety claim. Multi-channel account/identity onboarding and durable inbound receipt inbox remain next slices. Deployment requires independent QA/Security, protected checks, migration/rollback review and separately authorized real SMS test. Rollback disables new send entry points/dispatch and preserves all operation rows; never reset or replay unknown work.
