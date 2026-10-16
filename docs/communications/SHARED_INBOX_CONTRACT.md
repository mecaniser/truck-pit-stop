# Shared inbox contract v1 — DB-COMMS-001

Owner: Architecture & API Contracts. Date: 2026-10-16.
Status: proposed backend foundation; approved fixture boundary for a local prototype. This document does not mean the endpoints or tables below exist. Existing `/messages` SMS APIs remain authoritative until an implementation/release receipt says otherwise. No WhatsApp or Telegram connection is introduced by the prototype.

## Acceptance boundary

One inbox presents separate, explicitly identified channel conversations; SMS is the first supported transport. Assignment, open/resolved, customer/order context, channel filters and drafts can be demonstrated with synthetic fixtures. Prototype send adds a local demo message only and is visibly labelled. Unconnected channels, opt-out, missing identity, and uncertain provider outcomes cannot send. No prototype action imports the live API client or mutates provider/customer state.

## Entity and authorization contract

Every entity carries `tenant_id`; server derives it from the authenticated principal, never from request JSON. Preserve existing messaging role/grant and tenant feature checks (`messages.py:33-59`). Foreign tenant IDs return 404, even to otherwise authorized staff. Unauthenticated is 401; missing permission/disabled messaging is 403. Apply these checks to HTTP, websocket subscriptions, search, drafts, assignments, and contextual repair-order links.

| Entity | Required fields and constraints |
|---|---|
| ChannelAccount | id, tenant_id, channel, provider, provider_account_ref, sender_identity, connection_state, capabilities. Unique routing binding `(provider, provider_account_ref, sender_identity)` across active accounts; ambiguous inbound ownership fails closed. No global sender fallback. Credentials stay server-side. |
| ContactIdentity | id, tenant_id, channel_account_id, channel, address, verification_state, customer_id nullable, consent_state. Normalize provider addresses; shared/ambiguous phone matches require explicit staff resolution. Provider reachability does not prove customer ownership. |
| Conversation | id, tenant_id, channel_account_id, contact_identity_id, customer_id nullable, status open/resolved, assignee_id nullable, unread_count, last_message_at, version. One active conversation per account + identity; customer context does not collapse channels. |
| Message | id, tenant_id, conversation_id, channel, direction, source, body, created_at, delivery_status, send_operation_id nullable, provider_message_id nullable, event timestamps, sanitized error. Immutable actual sender/recipient snapshots. Provider SID uniqueness scoped to provider account. |
| SendOperation | id, tenant_id, idempotency_key, payload_hash, conversation_id, account_id, identity_id, message_id, state, attempt_count, reconciliation_state. Unique tenant + idempotency key. Persist before provider I/O. |
| Receipt | id, provider_account_id, provider_message_id, normalized status, raw status, received_at, processing state, dedupe key. Durable before acknowledgement in the eventual event-inbox implementation. |

Identity linking is explicit, tenant scoped, audited and reversible. Changing a customer's phone never rewrites historical message addresses. Inbound messages with unresolved customer ownership remain triage conversations; do not auto-merge people. Resolve is workflow state, distinct from archive; new inbound opens a resolved conversation. Per-user read watermarks replace shared zero-on-GET counters; GET must be read-only.

## Frontend fixture model

```ts
type Channel = 'sms' | 'whatsapp' | 'telegram'
type DeliveryStatus = 'received' | 'pending' | 'queued' | 'sent' |
  'delivered' | 'undelivered' | 'failed' | 'unknown'
type SendBlock = 'not_connected' | 'opted_out' | 'identity_unverified' |
  'ambiguous_outcome' | 'template_required' | 'not_started'
interface InboxMessage {
  id: string; conversationId: string; channel: Channel
  direction: 'inbound' | 'outbound'; source: 'customer' | 'staff' | 'automation'
  body: string; createdAt: string; deliveryStatus: DeliveryStatus
  errorCode?: string; sendOperationId?: string
}
interface Conversation {
  id: string; customerId: string | null; customerName: string
  channel: Channel; channelAccountId: string; contactIdentityId: string
  identityLabel: string; status: 'open' | 'resolved'; assigneeId: string | null
  unreadCount: number; lastMessageAt: string; preview: string
  messages: InboxMessage[]
  sendPolicy: {canSend: boolean; reason: SendBlock | null}
  context: {vehicleLabel?: string; repairOrderLabel?: string}
}
```

Draft key: tenant + user + conversation + channel account + contact identity. Switching thread/filter/channel restores only that exact draft; logout/tenant changes cannot reveal another user's draft. A successful send clears only the submitted draft revision, not newer text typed while sending. Failed/unknown sends preserve text and the operation ID. Prototype uses in-memory synthetic data; persistence of real drafts needs retention and security design. API serialization uses snake_case with an explicit frontend adapter.

## Proposed API examples (not implemented)

UUIDs are represented by short fixture labels below; actual APIs validate UUIDs. ISO timestamps include timezone.

```http
GET /api/v1/communications/conversations?channel=sms&status=open&limit=30
```
```json
{"items":[{"id":"conv-a","channel":"sms","channel_account_id":"acct-a","contact_identity_id":"identity-a","customer_id":"customer-a","customer_name":"Alex Morgan","status":"open","assignee_id":null,"unread_count":1,"version":3,"send_policy":{"can_send":true,"reason":null}}],"next_cursor":null,"has_more":false}
```

Use opaque cursors bound to tenant/filter and `(last_message_at,id)` ordering. Response permits server-added fields. Search applies tenant filtering before pagination.

```http
POST /api/v1/communications/conversations/conv-a/send-operations
Idempotency-Key: 8ac43074-b8f7-455a-80fb-1104789dc070
Content-Type: application/json

{"channel_account_id":"acct-a","contact_identity_id":"identity-a","body":"Your estimate is ready.","expected_version":3}
```
```json
{"id":"op-a","message_id":"message-a","state":"pending","delivery_status":"pending","replayed":false}
```

Return 202 only after operation/message/outbox are durable. Same tenant/key and same canonical payload returns original operation (200, `replayed:true`); different payload returns 409 `idempotency_conflict`. Concurrent duplicates create one operation. Server never trusts browser send policy: recheck ownership, consent, channel readiness, account/identity relationship, permissions and content limits immediately before dispatch. Missing key/blank body is 422; rate limit is 429 with Retry-After. Unknown provider outcome is an accepted operation state, not a retry invitation.

```http
GET /api/v1/communications/send-operations/op-a
```
```json
{"id":"op-a","message_id":"message-a","state":"unknown","delivery_status":"unknown","reconciliation_state":"required","can_retry":false}
```

Errors use `{ "error": { "code": "identity_unverified", "message": "Verify the recipient before sending.", "request_id": "req-a" } }`. 409 codes include opted_out, identity_unverified, account_not_connected, template_required, not_started, stale_version, ambiguous_outcome. Never return provider credentials or raw request bodies in errors.

`PATCH /conversations/conv-a` accepts `{status, assignee_id, expected_version}` and returns updated conversation/version. Assignee must be active, messaging-permitted and same tenant. Conflicting version is 409. `POST /conversations/conv-a/read` accepts `{through_message_id}`; update only the current user's watermark through that message, preserving newer arrivals. All referenced objects require the same tenant check.

## Send safety and statuses

Operation states: pending -> dispatching -> accepted | rejected | unknown. Once dispatch may have reached the provider, timeouts/crashes become unknown; do not retry automatically. Reconcile by recorded provider identifier/receipt when possible. An operation with no conclusive provider identity remains held; never match solely on body/time and claim certainty. A separately authorized resend creates a linked new operation and keeps original audit history.

Automations use unique `(tenant, domain_event_id, template_version, identity_id, channel_account_id)` intent keys. Transactional outbox creation belongs in the same transaction as the domain event. An unchanged repeated workflow action must not dispatch again. User-authored identical text with a new explicit send intent is permitted.

Provider acceptance, carrier sent, delivered, and customer read are different evidence. SMS delivered is not read. Unknown provider statuses are retained as receipts without downgrading display status. Initial pending can advance directly to any known state; queued -> sent or terminal; sent -> terminal. Terminal delivered/failed/undelivered is sticky. Conflicting terminal evidence requires reconciliation, not last-write-wins. Inbound uses received, not outbound delivered.

## Bounded SMS callback correction for this slice

Existing schema can support this without adding shared-inbox tables:

- Recognize queued, sending/sent, delivered, undelivered, failed/canceled. Empty/unknown status is acknowledged no-op, not pending.
- Apply progression above. Duplicate state preserves original timestamps. Update SMS and linked Notification consistently in one transaction only for accepted progression. A known failure receipt carrying 21610 can still enforce opt-out independently of a rejected delivery transition.
- Missing SID: 400. If no SMSMessage exists, look up SMS-type Notification by external_id (at most two rows): exactly one means a valid legacy Notification-only send; acknowledge 200 without mutation, preserving baseline behavior. Multiple matches are ambiguous: 503, never pick a tenant/customer arbitrarily. No match in either table means retryable 503 because current send can receive callback before the SID transaction commits. Do not log body/phone. Unknown status with known SID: 200 no-op. Notification-only callbacks do not infer a customer or change opt-out; their monotonic delivery tracking remains a separate slice.
- Processing/persistence exceptions: rollback and return non-2xx (503 preferred); never report success. Invalid signature remains 400. Post-commit websocket errors may cause a retried callback; duplicate handling must be harmless.
- This is not a durable receipt inbox, sender idempotency, or guaranteed provider retry configuration. Those remain separate work. Existing webhook route paths and successful response shape remain compatible.

Required fixtures/tests: queued->sent->delivered; pending->delivered; delivered->queued ignored; sent->queued ignored; terminal conflict ignored; duplicate delivered preserves timestamp; unknown status no-op; malformed missing SID; unknown SID; unique Notification-only SID acknowledged without mutation (including 21610); ambiguous Notification SID fails closed; database failure returns non-2xx and rollback; invalid signature; opt-out receipt; two tenants cannot reference each other's operations/conversations; same key concurrent submit; timeout held; draft switching; opt-out composer disabled. Backend-only requirements beyond bounded correction are future acceptance criteria, not passing tests today.

## Migration and rollout sequence

1. Ship bounded callback correction with mock-provider tests, independent review and normal release evidence. No resend/backfill of existing failed messages.
2. Add tenant-scoped accounts, identities, operation/outbox/receipt tables and nullable compatibility links; database composite ownership constraints. Audit normalized sender collisions and shared customer numbers first. Ambiguous rows remain unlinked/read-only.
3. Backfill existing SMS records preserving IDs, addresses, timestamps, opt-outs and archive history. Mark imported identity provenance as legacy, never verified by inference. Existing one-thread-per-customer may contain multiple historical phone addresses; split into address-specific conversations with a legacy history link, never assign every old message to today's phone.
4. Shadow-read compare counts/ownership without sending. Retain old `/messages` adapter; prevent dual writers. Roll out new dispatch to a controlled tenant only after outbox/idempotency/concurrency tests and independent security/QA. Rollback changes read/UI routing; never replay outbox by reverting code.
5. Add provider adapters later. WhatsApp/Telegram remain unavailable until account onboarding and provider policy checks exist. No automatic fallback between channels.
