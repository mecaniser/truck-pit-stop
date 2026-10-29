# Messages contact and repair context v1

DB-COMMS-023. Architecture & API Contracts. Frozen for implementation October 28, 2026.
Owner: Backend & Integrations; Frontend & UX consumes this contract.
Branch: `codex/messages-contact-repairs`. This contract is not release evidence.

## User outcome and scope

Staff can link a conversation to an existing customer/person or create a customer
and person, associate specific repairs with that person, and open those repairs
from the Messages sidebar. Contact-specific repairs are the default; fleet history
is an explicit separate view. Serviced trucks derive from linked repair orders.

A customer is the billing company. A contact is a person under that customer.
Creating a customer uses the existing required company/name/email validation.
Creating/linking CRM records does not establish SMS consent, verify phone ownership,
change billing, authorize repair work or unblock a send policy.

Not in v1: general contact-to-truck assignment, automatic inference from current
vehicle driver fields, historical backfill, merging customers/conversations,
provider changes, message sending, automation activation or changing repair status.

## Immutable transport boundary

Do not write `MessageThread.customer_id`, `thread_kind`, `customer_phone` or
`inquiry_binding_id`; do not write CallRail mappings, SMS messages, routing bindings,
consent or send operations. An inquiry remains an inquiry in transport identity:
its database check and `valid_thread_identity()` require NULL customer IDs.
CRM display association is separate from message delivery identity. Existing
customer threads retain their transport customer; their CRM association cannot
point at a different billing customer. Their exact person remains explicit.

Keep existing API conversation fields and draft keys unchanged. New display data
is returned only by the context endpoints below. A linked inquiry may show the
person in the sidebar while the existing thread list continues to say New inquiry.
Changing a display label is not permission to rewrite existing API identity.

## Data additions

Add an additive migration using the actual current migration head; never edit
old revisions or assume a revision number from this document.

1. `conversation_contact_links`: one active row per `(tenant_id, thread_id)`;
   customer_id, contact_id, version (starts at 1), actor_id, linked_at/updated_at.
   Retain an audited link change event with previous/new target IDs. Default absent
   link has version 0. Do not automatically create links in GET handlers.
2. `contact_repair_links`: unique `(tenant_id, contact_id, repair_order_id)`;
   actor_id and linked_at. Contact.customer_id, RepairOrder.customer_id and
   Vehicle.customer_id must all match the selected customer and tenant.
3. Durable mutation idempotency records: tenant, actor, UUID key, operation/path,
   canonical payload hash, response status and result IDs. Unique tenant/actor/key.
   Same key and payload returns the committed result; changed payload/path is409.
   Store no credentials/provider data. First request and idempotency record commit
   atomically with all new CRM records. Concurrent repeated requests create one set.

Use tenant-scoped lookups for every relationship even when a foreign key exists.
Use composite constraints where practical; application validation remains mandatory.
New associations do not cascade-delete SMS or repair records. No automatic repair
association follows a driver reassignment or a customer phone change.

## Authorization

Every endpoint requires existing communications `authorize()` and `thread_for()`
checks plus role GARAGE_OWNER, GARAGE_ADMIN or RECEPTIONIST. This narrow v1 grant
matches customer/contact write roles and does not expand access for a user who
only has messaging permission. Do not use caller-supplied tenant IDs.

All customers, contacts, orders and vehicles must be active/non-deleted within the
current tenant. Contact and repair ownership must match the linked customer.
Unknown, foreign or deleted IDs return404 without revealing which condition failed.
A linked target deleted later produces an unavailable context, not stale details.
Existing customer/repair visibility restrictions apply in addition to these roles.
No financial amounts, balances, internal notes or customer-private fields in summaries.

## API prefix and response conventions

All paths below start `/api/v1/communications/conversations/{conversation_id}`.
UUIDs are strings; timestamps are ISO8601 UTC. Unknown request properties reject422.
Errors follow existing `detail: {code, message}` convention.

### GET `/customer-context`

```json
{
  "version": 0,
  "link_state": "unlinked",
  "can_manage": true,
  "customer": null,
  "contact": null,
  "default_scope": "contact",
  "fleet_available": false
}
```

Linked response has `link_state: "linked"`, version >=1, and:

```json
{
  "customer": {"id":"uuid","company_name":"Example Fleet","display_name":"Alex Owner"},
  "contact": {"id":"uuid","first_name":"Taylor","last_name":"Driver","role":"Driver","phone":"+15555550123","email":null}
}
```

`link_state` is `unlinked|linked|unavailable`. Existing customer threads without an
explicit contact return the existing customer summary, null contact, version0,
unlinked state and fleet_available=true. Contact scope remains empty until linked.
Unavailable returns null summaries and fleet_available=false; do not disclose
soft-deleted/foreign details. No mutation occurs from reading context.

### GET `/customer-options?q=...&limit=20`

Bound q to200 characters and limit1..50. Return `{items:[customer summary]}`;
search active tenant companies and customer names, without private financial data.
No blank-query exhaustive dump beyond the bounded limit. No phone auto-linking.

### GET `/customer-options/{customer_id}/contacts`

Return `{items:[contact summary]}` for the active accessible customer. Bound to100
contacts in v1; response includes `has_more` when truncated so UI does not claim
exhaustiveness. For customer-kind transport threads, reject another customer404.

### PUT `/customer-context`

Headers: `Idempotency-Key: <UUID>`. Required `expected_version` >=0.
The discriminator `action` supports exactly these alternatives:

```json
{"action":"link","expected_version":0,"customer_id":"uuid","contact_id":"uuid"}
```

```json
{"action":"create_contact","expected_version":0,"customer_id":"uuid","contact":{"first_name":"Taylor","last_name":"Driver","role":"Driver","email":null,"phone":"+15555550123"}}
```

```json
{"action":"create_customer","expected_version":0,"customer":{"company_name":"Example Fleet","first_name":"Taylor","last_name":"Driver","email":"taylor@example.test","phone":"+15555550123"},"contact":{"first_name":"Taylor","last_name":"Driver","role":"Owner","email":"taylor@example.test","phone":"+15555550123"}}
```

Restrict create_customer to inquiry threads; customer-kind threads already own a
billing customer. Reuse existing CustomerCreate validation with `no_vehicle=true`
and no initial_vehicle. Do not call the existing HTTP endpoint and leave an orphan
on link failure; use a shared transactional service or equivalent validated model
construction in this transaction. Reuse existing customer-creation invariants and
side effects, explicitly excluding SMS/provider work. If those cannot be preserved,
return this contract to Architecture before coding a shortcut.

New contacts are always non-primary; no notification recipient selection changes.
Require at least one nonblank person name. Match current model length limits;
trim names, reject invalid/oversized phones and email using existing shared rules.
Phone prefill from the conversation is only an editable suggestion. The staff
selection is explicit; no claim of verified ownership follows.

Lock the thread and context link before version comparison. A first mutation uses
version0; success increments version once. Check idempotency replay before stale
version rejection, after authorization and target visibility checks. Return200 and
the current customer-context shape for all three actions. `version_conflict`409
requires refresh. No implicit customer or conversation merge.

### GET `/repairs?scope=contact&status=active&cursor=...&limit=20&q=...`

Scope is `contact|fleet`; default contact. Status is `active|history|all`; default
active. q optional max200, filtering order number or unit. Limit1..50. Cursor is
opaque and bound to tenant/thread/context version/scope/status/query; invalid or
mismatched cursor422. Stable ordering created_at DESC then id DESC.

Contact scope reads only explicit ContactRepairLink rows for the linked contact.
Fleet scope reads repairs owned by the linked customer's account (or the existing
transport customer if no person selected). Neither scope queries by phone/name.
No contact returns empty contact items; missing customer returns empty fleet items.

History statuses: completed, invoiced, paid, cancelled. Other current statuses are
active. Return status unchanged; cancelled repairs are clearly labelled.

```json
{"items":[{"id":"uuid","order_number":"RO-100","status":"in_progress","created_at":"2026-10-28T12:00:00Z","description":"Brake inspection","vehicle":{"id":"uuid","unit_number":"12","make":"Example","model":"Truck","year":2020},"linked_to_contact":true}],"has_more":false,"next_cursor":null}
```

Description is the public repair description, never internal_notes/shop_notes;
truncate bounded summaries. Fleet rows expose linked_to_contact, permitting an
explicit link action; no side effect follows merely selecting Fleet history.

### PUT `/repairs/{repair_order_id}/contact-link`

Headers: `Idempotency-Key: <UUID>`.
Body: `{"expected_version":1}` where version is conversation context version.
Require an explicit linked contact, customer ownership, visible order/vehicle and
same-tenant consistency. Lock conversation context before checking the version.
Existing link is an idempotent success; no duplicate link or extra audit record.
Response200: `{"repair_order_id":"uuid","linked":true}`. Context version does
not increment because its identity has not changed. No unlink in v1: correction
is a separately reviewed later workflow, not silently deleting history.

### GET `/vehicles?scope=contact&cursor=...&limit=20`

Contact default returns distinct vehicles represented in explicitly linked repairs;
fleet scope returns active vehicles owned by the selected account. Stable order
unit_number then id. Apply the same tenant/customer/deleted access rules and bound
cursor. Return `{items:[vehicle summary],has_more,next_cursor}`. Contact results
are labelled Serviced trucks; fleet results Fleet trucks. Do not infer truck
ownership/driver history from a current driver phone match.

## UI behavior

The right sidebar offers Link customer / Add customer when unlinked. Existing
customer selection includes choosing or adding the person. Show person and billing
company distinctly after linking. Do not duplicate a company for every driver.

Default Contact view has Active / History / All repairs and Serviced trucks.
Fleet history is an explicit separate tab/scope. Clicking a repair navigates to
`/dashboard/repair-orders?selected=<encoded UUID>`. Preserve the draft and selected
conversation for return. Do not invent unsupported customer/vehicle deep links;
use the existing customer route or an inspected existing navigation contract.

Linking, scope switches and navigation never send, change consent, enable
service updates, alter sending number or assign/resolve the conversation. Confirm
customer/person selection before committing. Empty, loading, failure and retry
states must remain distinct. Compact layout exposes the same details in a drawer.

## Acceptance and shared fixture

Use synthetic Fleet A with contacts Driver A and Dispatcher A, trucks A1/A2;
Fleet B with Driver B/truck B1; same phone on a different tenant. Driver A has
explicit repair A1-current and A1-old links, but not A2-old. A changed current
vehicle.driver_phone must not alter those results. Include a customer-kind thread
and an inquiry with retained CallRail bindings, draft and original history.

Required checks: foreign/deleted IDs and disallowed roles; mismatched contact,
customer, repair and vehicle; context version conflicts; duplicate/concurrent
create replay; payload-changed key conflict; rollback leaves no orphan; read
endpoints produce no records; complete pagination; contact/fleet separation;
route/history/consent/flags unchanged; draft survives link/navigation; active,
completed/cancelled status grouping; desktop/compact UI and usable deep links.

Migration rehearsal preserves all prior rows. Fresh independent Security/QA must
review identity, permissions, transactional creation and concurrent idempotency.
Owner cannot issue those gates. All providers are disabled/mocked locally; no
production linking, customer creation or send is authorized as a test.

## Handoff

Board ID: DB-COMMS-023.
From / To: Architecture & API Contracts to Backend & Integrations / Frontend & UX.
Scope completed: source-grounded API/data boundary frozen above.
Scope not completed: implementation, migration, tests, runtime, independent gates,
PR/merge/deploy or production acceptance.
Next action: implement against this contract in the approved isolated runtime.
Return condition: existing customer-creation invariants cannot be reused safely,
missing row visibility policy, migration conflict, or any need to change transport
identity, permissions, consent, provider configuration or automation.
