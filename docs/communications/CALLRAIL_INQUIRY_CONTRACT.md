# DB-COMMS-010 — CallRail new inquiries, contract v1

Status: Approved by Product & Delivery Lead before implementation split, including the company-scoped receiver below. Accountable outcome owner: Backend & Integrations. High-risk lane: public signed intake, tenant isolation, nullable customer relationships and manual provider sends require independent Security/QA. This extends the existing [manual inbox contract](CALLRAIL_INBOX_CONTRACT.md); it does not enable automation.

## Outcome and boundaries

A new person texting an explicitly enabled shop CallRail number appears in the shared inbox as **New inquiry**, identified by phone and receiving shop number. Staff can reply manually from that receiving number. No Customer, repair order, quote, appointment or automation intent is created. Existing customer conversations, DBN/ETS records, provider history and preserved old-number reply routes remain unchanged.

Product & Delivery Lead approved one inquiry per `(tenant, receiving CallRail binding, normalized remote phone)`. Distinct receiving numbers retain distinct inquiry threads. Phone evidence does not establish customer identity: never search Customer by phone/name to auto-link, merge or label the inquiry. An existing explicit route for the exact binding and remote phone takes precedence; a damaged, deleted or rebound explicit route is quarantined rather than replaced with a new inquiry.

## Minimal additive data changes

Use the existing MessageThread, SMSMessage, workflow/read-watermark and durable manual send-operation tables. Avoid a parallel inbox or fake Customer.

1. `message_threads.thread_kind VARCHAR(16) NOT NULL DEFAULT 'customer'`, values `customer`, `inquiry`.
2. Make `message_threads.customer_id` nullable. Add `inquiry_binding_id UUID NULL REFERENCES callrail_number_bindings(id)` and `inquiry_opted_out BOOLEAN NOT NULL DEFAULT false`. Retain `customer_phone` as the canonical remote address.
3. Enforce a thread shape check: customer kind requires nonnull customer_id and null inquiry_binding_id; inquiry kind requires null customer_id, nonnull inquiry_binding_id and nonnull customer_phone. Missing/unknown kinds never bypass customer validation. Validate active binding tenant and normalized US/Canadian phone in services; SQL shape checks cannot prove cross-table tenant membership.
4. Add a partial unique index on `(tenant_id, inquiry_binding_id, customer_phone)` for nondeleted inquiry threads. Existing `(tenant_id, customer_id)` uniqueness stays intact. Add no uniqueness that merges existing customer records.
5. Make `sms_messages.customer_id` nullable. A null customer requires `provider='callrail'` and nonnull callrail_binding_id; the SQL check must explicitly require provider IS NOT NULL (SQL NULL must not pass an OR/CHECK accidentally). Service additionally requires an authorized inquiry thread and exact route. Legacy/Twilio writes retain a customer. Existing rows are unchanged.
6. Make `callrail_conversations.customer_id` nullable, with service validation requiring the thread's matching customer relationship, or the exact inquiry shape above. Existing binding/phone reservation, thread/binding uniqueness, one selected outbound route and retained inbound routes remain.
7. `callrail_number_bindings.accept_new_inquiries BOOLEAN NOT NULL DEFAULT false` is a reviewed intake setting, separate from the three rollout flags. Only explicitly inventoried active tenant/account/company/tracker/sender bindings may opt in. Existing bindings do not silently start accepting new contacts on schema upgrade.

SMSSendOperation already has no customer_id. Keep its actor, tenant, thread, binding/account, from/to and payload snapshots; dispatch must revalidate inquiry kind, binding and canonical phone. No nullable actor, thread or recipient is introduced. Message serialization/audit may expose customer_id=null without inventing a name. No broad customer/tenant join may drop legitimate inquiry rows or admit malformed customer rows.

Use the next migration after the actual current graph head; preserve all existing data. Downgrade must refuse if inquiry data would violate restored nonnull columns, rather than deleting it. Runtime rollback disables new intake per binding; it does not delete threads or disable existing replies. An enabled existing inquiry may still receive/reply when accept_new_inquiries becomes false; disabled/retired provider bindings block sends and quarantine callbacks as before.

## Signed intake and concurrency

Keep existing `/webhooks/callrail/{binding_id}/received|sent` callbacks and raw-body Signature verification, request limit, dedicated server-side secret references, trusted company/binding/receiving-number checks, timestamp bounds and SCI aliases. Invalid signature is rejected before parsing. Missing/invalid SCI, malformed phone/time/type, unsupported MMS, unrecognized sender number, foreign company, inactive/deleted tenant and mismatched explicit routes stay quarantined. Do not trust company, tenant, destination or direction from unsigned browser input.

For a valid **received SMS**:

1. Resolve and lock its known binding, verify the trusted shop identity and exact normalized destination. Check SCI/optional numeric aliases; replay returns the original message without new thread, workflow, unread increment or customer changes.
2. Find the existing explicit `(binding, remote phone)` route. If present, validate its canonical customer or inquiry relationship and retain that thread, regardless of selected outbound sender.
3. Only if no route/reservation exists, `enabled && accept_new_inquiries` is true, and the tenant is active and messaging-enabled, create the inquiry thread plus its pinned CallRail route, workflow and inbound SMS in one transaction. Recheck customer_id=null/kind/binding/phone invariants. The signature supplies evidence of a new remote contact, not a customer match.
4. Binding-before-thread lock order, SCI uniqueness and the inquiry partial index serialize simultaneous first messages and webhook replay. Two different valid first messages produce one thread and two messages; duplicate SCI across webhooks/API produces one message. A uniqueness race is resolved by rereading the winning route/receipt, never by guessing another customer.
5. Set preview/unread/status using existing monotonic timestamp rules. Inbound reopens the workflow once. STOP/CANCEL/UNSUBSCRIBE/QUIT/END sets inquiry_opted_out; it does not opt in or modify unrelated Customer rows. A later START or provider event does not automatically clear this hold.

A **sent** callback never creates an inquiry or missing route. Known outbound intents reconcile once using existing conservative body/receipt rules; uncertain or ambiguous outcomes remain held. Manual CallRail sends retain the 140-character limit, exactly one provider attempt, no retry, no fake Twilio SID and Sent-versus-Delivered distinction.

Old quarantined unknown contacts are not replayed automatically when intake is enabled. A future reviewed import/reprocessing operation must explicitly opt in to particular receipts, establish receiving-number provenance, respect freshness decisions and existing aliases, and record its operator/evidence. Historical API conversation-level current_tracking_number alone is not per-message sender proof.

## Authenticated inbox API

Retain the existing communications permission and tenant authorization. Thread lookup/listing accepts only either a valid active customer thread, or a valid inquiry joined to its own tenant-owned intake binding/route. All list, detail, read, workflow, send-operation lookup and background dispatch paths apply the same rule. Customer-facing and legacy customer-message endpoints must not expose inquiries or dereference null customers.

Existing conversation JSON adds `conversation_kind: 'customer' | 'inquiry'`. Inquiry shape:

```json
{
  "id": "thread UUID", "tenant_id": "authorized tenant UUID",
  "conversation_kind": "inquiry", "customer_id": null,
  "customer_name": "New inquiry", "company": null,
  "identity_label": "+15005550002", "channel": "sms",
  "channel_account_id": "binding snapshot identity UUID",
  "contact_identity_id": "thread plus canonical phone identity UUID",
  "version": 2,
  "context": {
    "sms_provider": "callrail", "sender_number": "+15005550001",
    "selected_sender_id": "receiving binding UUID",
    "sms_sender_options": [{"id":"receiving binding UUID","provider":"callrail","sender_number":"+15005550001","enabled":true}],
    "sender_selection_allowed": false
  },
  "send_policy": {"can_send": true, "reason": null, "max_length": 140}
}
```

Merge these context keys into existing context; do not remove existing fields. Customer conversations keep existing behavior and serialize conversation_kind='customer'. Search includes canonical inquiry phone and message body without requiring a Customer join; pagination/unread counts include inquiries without double rows. GET accepts optional `conversation_kind=customer|inquiry` for the New inquiries view; omitted means both. Invalid filter values return422 and cursor binding includes the filter.

POST `/communications/conversations/{id}/send-operations` retains its request, Idempotency-Key, version check and replay semantics. The recipient and sender come exclusively from the pinned inquiry route; client cannot choose an arbitrary address or bind an inquiry to another number. Same-phone tenant-level pending/uncertain manual and automated holds remain effective across customer and inquiry threads. STOP suppresses sending. Snapshot changes, disabled binding, malformed inquiry shape, unknown provider outcome or changed permissions block dispatch.

PATCH `/communications/conversations/{id}/sender` rejects any inquiry switch with409 `inquiry_sender_locked`; no Twilio fallback or cross-number selection for inquiries. It may return a harmless no-op for the exact existing binding/version, but must not change workflow version. No customer-link/create/merge endpoint is included. All wrong-tenant IDs return404; stale versions and held/invalid route states retain existing409 error envelopes. Auth failures retain existing401/403 behavior.

## UI and drafts

Show a New inquiries filter with the number of matching unread inquiries; keep All conversations and existing customer views. An inquiry row and header display **New inquiry**, canonical remote phone and receiving CallRail number. Do not show “Unavailable customer,” a guessed company or a customer-profile link. Detail/history/read/resolve/assignee behavior remains available to authorized staff. Composer says Reply, displays the pinned receiving number and140-character counter, and disables Send for provider/permission/STOP/uncertain holds. Drafts remain keyed by thread/account; no customer_id assumption and no draft loss on refetch/filter change. Do not offer sender switching, automation or customer creation for inquiries. Desktop and390px mobile must fit without horizontal overflow.

## Required evidence and handoff

Backend & Integrations owns schema, signed intake, routing, null-safe API/policy and focused integration tests. Frontend & UX owns the approved fixture contract, inquiry filter/identity/composer and tests after approval. Root integrates; independent reviewers must not implement their own gates.

Required negatives: wrong tenant/company/sender/signature; malformed/unknown-kind thread; inactive tenant/disabled binding/intake off; MMS; sent event without route; existing damaged/deleted/rebound route; duplicate customers and existing DBN/ETS; simultaneous first-message duplicates; two distinct inbound messages; SCI-only replay and API alias dedup; same phone on two receiving numbers and across tenants; STOP; manual send replay and timeout hold; same-phone cross-thread uncertain operation; old-number customer replies after outbound changes; inquiry sender-switch rejection; old quarantine not auto-imported; legacy customer endpoints null-safe. Retained explicit customer routes must behave identically with intake off/on.

Migration rehearsal must retain existing customer/messages/routes and defaults, upgrade with existing data and refuse lossy downgrade once inquiries exist. Signed-in isolated desktop/mobile must demonstrate new inbound inquiry, one visible row, manual simulated send, signed reply, replay once, STOP hold, filtering and preserved customer history/drafts. Protected CI and independent Security/QA precede release. Production/provider mutations and live send acceptance require the root's explicit authorized release path; this contract does not itself perform them.

`SMS_TENANT_ROUTING_ENABLED`, `SMS_AUTOMATION_OUTBOX_ENABLED` and `SMS_RECOVERY_ENABLED` remain false. CallRail is manual P2P only. No forwarding, call flow, old webhook, number provisioning, registration or secret-value changes are part of this item.


## Company-scoped SMS receiver (approved addition)

POST `/webhooks/callrail/{anchor_binding_id}/company/{received|sent}` validates the raw body Signature with the configured anchor signing-secret reference before parsing. The anchor must be an active enabled binding belonging to an active messaging-enabled tenant. Require payload company_resource_id to equal the anchor company; if an account identifier is provided, it must equal the anchor account. Resolve normalized destination (received) or source (sent) only among explicit same-tenant/account/company bindings; require exactly one enabled nondeleted match and the same signing_secret_ref as the anchor. Resolve and validate the secret at the anchor only; never trust a payload to select credentials or tenant. Unknown numbers, company/account mismatches, inconsistent signing references or malformed signed payloads become one durable anchor quarantine receipt, never one quarantine per configured number. Foreign tenant bindings are never selected. The resolved binding runs the normal apply_event transaction and alias dedup rules.

Keep existing binding-scoped receiver semantics unchanged. After independent gates, the reviewed release may replace only DieselBridge-owned text-received/text-sent webhook URLs with these two company receivers, preserving ELIS call receivers, forwarding and old message history. Do not add sixteen binding callbacks or fan out one event across bindings. Number inventory explicitly records each tenant/account/company/tracker/sender and intake opt-in; session trackers can have multiple configured sender numbers. No number provisioning or porting is authorized.


## Released-main migration integration (2026-10-19)

Architecture approved graph-only revision `185_callrail_inquiry_main_merge`, joining inquiry revision `184_callrail_inquiries` and released-main revision `184_db135_callrail_merge` after main `c66cabf2` integration. Its upgrade and downgrade are no-ops. All 199 pre-existing migration files remain byte-identical; application contracts and source are unchanged by this integration. The reviewed inquiry schema remains the only inquiry data-model change. Do not rewrite earlier revisions or remove either branch history. The final expected schema head is `185_callrail_inquiry_main_merge`; independent integration review, protected CI and release verification remain required.
