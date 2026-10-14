# DB118 Operation-specific shop notes contract

Status: approved for implementation, 2026-10-14. Architecture & API Contracts owns this contract; Backend & Integrations owns DB118. Additive API, no migration, no customer-visible content. Independent QA and a fresh privacy/security reviewer remain required.

## Outcome and identity

Append an internal finding to the exact work item, retaining author and time through collapse, reload and operation completion. Both service packages and standalone labor operations are `Labor` rows: the identity is **order ID + labor ID**, never service ID, description or array index. Notes do not affect prices, technician assignment, execution versions, checklists, timers, order status or completion snapshots.

Use the existing `RepairOrderHistoryEvent` table. One note is one event:

- `id`: client-generated UUID, globally unique primary key and retry key.
- `tenant_id`, `repair_order_id`: server-derived from the authorized order.
- `event_type`: `operation_note_shop`.
- `entity_id`: the exact `Labor.id` (not an FK, so history survives physical labor removal).
- `detail`: trimmed plain-text note, 1–4000 characters. Do not embed JSON or an execution snapshot.
- `label`: `Shop note · {operation description}`, truncated to the existing 255-character column. This description snapshot makes surviving staff history intelligible after line removal/rename; exact identity remains `entity_id`.
- `actor_user_id`, `actor_name`, `created_at`: authenticated actor identity, display-name snapshot (existing safe `service_checklist.actor_name` convention), server UTC timestamp. Clients cannot supply these.

Do **not** add this event to the existing order-level `NOTE_EVENT_TYPES`: order-level read/delete routes must not return or delete operation notes. Initial scope is append-only, with no editing, deletion, audience toggle, publication, attachments, or notification delivery. New text remains outside legacy `internal_notes`, `shop_notes`, customer notes and invoice/quote fields.

## API and shared fixture

Routes are relative to `/api/v1` and require an active authenticated user. Both send `Cache-Control: no-store`.

`GET /repair-orders/{order_id}/operations/{labor_id}/notes` returns 200:

```json
{
  "items": [
    {
      "id": "5113c328-e933-449e-9439-5aec39a55118",
      "labor_id": "2d2fae28-9e4d-49e3-977d-29bd5e2c4a64",
      "body": "Air leak confirmed at the rear fitting. Recheck after replacement.",
      "actor_user_id": "9ed1c0ee-0446-4430-9fbd-bcb78561dff2",
      "actor_name": "Casey Technician",
      "created_at": "2026-10-14T15:00:00Z"
    }
  ],
  "can_add": true,
  "read_only_reason": null
}
```

Items are ordered oldest first by `(created_at, id)`, scoped by tenant, order, event type and labor ID, excluding soft-deleted history events. `actor_user_id` is nullable to match durable historical identity; `actor_name` is a string with safe fallback. No pagination in this initial per-operation collection. An empty authorized collection is `items: []`, not an error. The server supplies `can_add` and a human-readable reason when false; clients must not reconstruct authorization from role alone.

`POST /repair-orders/{order_id}/operations/{labor_id}/notes` request:

```json
{
  "id": "5113c328-e933-449e-9439-5aec39a55118",
  "body": "Air leak confirmed at the rear fitting. Recheck after replacement."
}
```

Response is the single note item above: **201 Created** for a new row, **200 OK** for an exact authorized replay. Reject extra fields (`audience`, supplied author/time/tenant etc.), invalid UUIDs, non-string/null/blank body and a normalized body above 4000 characters with 422. Trim surrounding whitespace before nonblank/length comparison and persistence; preserve interior whitespace/newlines. Render as text, never HTML.

## Authorization and lifecycle

Positive shop-note role allowlist is `garage_owner`, `garage_admin`, `receptionist`, `mechanic`. `fleet_manager`, `customer`, `driver`, and platform-only `super_admin` have **no** access to this API or event content. An internal fleet order is not permission for a fleet manager to read shop-only notes.

Every route first validates role, tenant and order membership; foreign/missing order or labor IDs return 404 without disclosing existence. Missing actor tenant follows existing 400 convention. Owner/admin/receptionist may read/write all active labor rows within their tenant. Mechanic access follows operation execution scope:

- Order lead can read notes on all active non-sublet operations on the assigned order.
- A helper can read only the non-sublet operation currently assigned to that mechanic.
- Either mechanic can append only to an operation currently assigned to them; order-lead status alone does not grant append authority on someone else's operation.
- Assignment is re-evaluated on every GET/POST/replay. An unassigned/reassigned mechanic receives 403; cached browser data is not authority.
- Shop staff may annotate sublet labor because a note is not technician execution. Mechanics do not acquire sublet access through this feature.

Dedicated GET/POST require an active (not deleted) order and active labor row. Deleted orders and removed/missing labor rows return 404, including for owner/admin; keep these panels unmounted on deleted orders. Existing owner/admin deleted-order history remains governed by its existing permission and can retain shop note history. Removed labor notes remain in staff history; this feature creates no orphan-operation browsing endpoint.

An active, held order or a completed operation on an otherwise editable order permits notes. Do not stop a timer, reopen a completed operation, release a hold or change order status. New writes are frozen if the order is completed, invoiced, paid, cancelled, deleted, or has a pricing lock other than `quote_sent`; use the existing `operation_execution.editable` semantics. Pending-review notes are permitted. GET on finalized/cancelled nondeleted orders remains readable with `can_add: false`. A mechanic with read-only scope gets `can_add: false` and an assignment explanation. New POST when readable but lifecycle-frozen is 409 with a usable explanation. Exact replay on a now-finalized order may return the already-created note after current identity/read/write-role-and-assignment authorization; it creates no new mutation. Deleted/removed target checks still precede replay and return 404.

## Privacy across every serializer

The full repair-order detail history currently filters `operation_execution.INTERNAL_EVENT_TYPES` only for `CUSTOMER`; that is **insufficient** for shop notes. Add an explicit positive visibility rule for `operation_note_shop` before constructing `RepairOrderHistoryEventResponse`:

- Authorized garage owner/admin/receptionist: event is visible on an already authorized same-tenant order, including preserved history for removed labor.
- Lead mechanic: active same-order, same-tenant non-sublet operation notes only; helper projection, if introduced, must restrict to their currently assigned active operations. Existing detail endpoint still separately restricts access to the order lead.
- All other roles: omit the event entirely, including ID, label, body, actor and time. An unsupported role reaching a broad legacy detail endpoint still must not receive a note.

Only the dedicated API and this explicitly authorized staff history may serialize the new body. Do not copy it into repair-order read-model payloads, customer history, fleet/driver responses, vehicle history, invoice/quote/PDF/email snapshots, authorization history, messages, or websocket payloads. Existing authorization history already allowlists its four authorization event types. Existing order-note routes already allowlist `note_customer` and `note_shop`; retain that boundary. Any optional staff invalidation event must contain only existing order identity and use `send_to_customer=False`; no note body or author belongs in a broadcast. No broad privacy cleanup of unrelated legacy note types is required by this contract.

## Retry, concurrency and failures

Use existing transaction ordering: tenant financial serialization lock, then order row lock, then labor row, even though this mutation changes no financial value. Reuse shared helpers where they preserve the narrower shop-only role policy. This serializes a note save with reassignment, finalization and line removal, avoiding a stale permission/lifecycle decision. Do not take the tenant lock after holding the order lock.

Under the lock, authorize current actor/target, then look up the request ID. Return 200 only when the existing live event matches **tenant, order, labor ID, `operation_note_shop`, actor ID and normalized body** exactly. Actor display-name changes do not invalidate a replay; return the original stored name/time. An existing different event or same key with changed body/target/actor returns generic 409 (`This note save ID has already been used. Refresh and try again.`), never the colliding record's data. A matching soft-deleted record is a conflict, not permission to recreate it.

The history primary key enforces global uniqueness. Different-tenant requests are not serialized by the tenant lock: protect INSERT with a savepoint and handle a primary-key collision by reloading/comparing or returning generic 409, preserving the outer transaction. Do not return an uncaught integrity error, roll back unrelated work or disclose collision scope. Distinct request IDs with identical text are intentional separate notes; do not deduplicate by text/time. This append-only endpoint needs no optimistic execution version.

The frontend creates a UUID once for a submitted normalized body, retains it for an ambiguous failed response/retry, and discards it after confirmed success or when the draft changes. Disable duplicate submit while pending; no automatic mutation retry. Query/draft/mutation identity includes authenticated session scope, order ID and labor ID; a delayed completion must not clear another operation's draft. Preserve unsaved text and show explicit retry/error inline. Collapsing the operation should not destroy its draft. GET failure must offer retry rather than pretend there are no notes; failed mutation must not publish a success state. Invalidate/refetch only the correct note collection and relevant staff history after success.

## Required focused evidence

Backend coverage: package and manual labor; ordered read; exact author/time/text; whitespace/4000/4001/invalid UUID/extra field; direct foreign-tenant and foreign-order IDs; customer/fleet/driver/super-admin denial; lead/helper assignment boundaries including reassignment; sublet staff/mechanic boundary; holds and completed-operation notes; all final/deleted/removed states; same-key replay, changed-body/actor/target collision, concurrent same-key insert and distinct-key identical-body append; no financial/timer/execution/order side effects. Test full-detail history redaction for every denied role as well as direct API denial, staff history retention after removal, and exclusion from order-level notes/authorization/customer/invoice projections.

Frontend coverage: loading/error/empty/read-only states; author/time and literal text; maximum/nonblank validation; failed GET retry; failed POST retains draft and key; double click; collapse/reopen; switch order/operation during pending save; server-provided read-only state; explicit shop-only label; accessible named controls. Runtime: signed-in desktop plus 320/390 portrait and 740×400 landscape, append/read/reload/retry/read-only on controlled synthetic data, one scroll area, no horizontal clipping. Production verification requires actual deployed source and appropriate synthetic fixture, not local evidence.

## Code handoff and rollout

- Persistence: `backend/app/db/models/repair_order_history.py`, `backend/app/db/base.py`.
- Scope/locks/lifecycle: `backend/app/services/operation_execution.py` (`load_order`, `load_labor`, `editable`, `require_executor`, `page`); do not inherit its broader fleet role allowlist.
- Note/history projections: `backend/app/api/v1/endpoints/repair_orders.py` (`get_repair_order_detail`, `NOTE_EVENT_TYPES`, list/add/delete order notes); `backend/app/api/v1/endpoints/quotes.py` authorization event allowlist.
- Operation removal: `backend/app/services/price_build_service.py::remove_line` physically deletes labor; `operation_execution.remove` preserves execution history. Note entity IDs must survive without an FK.
- Frontend: shared operation-note component within existing operation expansion in `PriceBuilderPanel` and `MechanicOperations`; full staff activity uses existing history rendering, with the operation snapshot in label.

Backend and frontend can proceed against this exact schema in parallel. No schema migration, dependencies, feature flags, provider changes or historical backfill. Keep client rendering off for denied roles and deleted orders. Roll back application code if cross-role leakage, lost/duplicate notes or runtime workflow regressions are found; durable append-only rows remain compatible with older code, but the **old full-detail serializer does not know this new event type**, so a rollback must retain the privacy filter or disable full-detail exposure until patched. Do not roll back to a serializer that leaks existing new events.
