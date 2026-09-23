# DB-072: incident to repair-order link contract

- Version: 1.0.0
- Status: Proposed for Architecture review
- Accountable owner: Architecture & API Contracts
- Implementing owner: Backend & Integrations, then Frontend & UX
- Delivery lane: Standard product
- Implementation preserved at: `codex/incident-stack-preserved` (`03a0b183`)

## 1. Why this exists

`FleetIncident.repair_order_id` has always been on the model, but only one
route could set it: `POST /fleet/incidents/{id}/create-repair`, which either
opens a new internal order or appends the complaint to the truck's current
visit.

An incident repaired under an order opened some other way — a walk-in, a PM
that turned up the same fault, an order raised from the board — had no way to
say which order was addressing it. The link that proves an incident was
actually handled stayed unreachable, and the incident sat open with its repair
invisible.

This contract adds the missing direction: point an existing incident at an
existing order, and take it back off again.

## 2. Product boundary

In scope:

- listing the orders a given incident may be attached to;
- attaching that incident to one of them;
- detaching it again.

Explicitly not in scope:

- changing `create-repair`, including its rule that an open visit absorbs a
  new complaint rather than spawning a second order;
- moving work, lines, parts or labor between orders;
- editing the order in any way — attach and detach touch the incident only;
- linking more than one incident to an order (already permitted; unchanged)
  or more than one order to an incident (refused, see §4);
- any driver-portal or customer-facing surface.

## 3. Routes

### 3.1 `GET /fleet/incidents/{incident_id}/linkable-orders`

Returns the orders this incident may be attached to, oldest first.

Response `200`: `LinkableRepairOrderOption[]`

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `order_number` | string | What the shop calls it |
| `status` | `RepairOrderStatus` | Always non-terminal, see §3.4 |
| `is_pm` | bool | Present so the picker can mark a PM visit |
| `description` | string, nullable | |
| `created_at` | datetime | |

An incident that is not found, or belongs to another tenant, returns `404`
through the existing `_load_incident` guard.

### 3.2 `POST /fleet/incidents/{incident_id}/repair-order`

Request: `IncidentRepairOrderLink` — `{ "repair_order_id": UUID }`

Response `200`: the full `IncidentResponse`, so the client re-renders from one
authoritative payload rather than patching its own copy.

Side effects, in order:

1. `incident.repair_order_id` is set;
2. an incident whose status is `open` becomes `in_progress` — work is attached,
   so it is underway rather than merely reported. An incident already
   `in_progress`, `resolved` or `voided` keeps its status;
3. a `FleetIncidentEvent` of type `repair_order_linked` is appended, carrying
   `repair_order_id` and `order_number`.

### 3.3 `DELETE /fleet/incidents/{incident_id}/repair-order`

Response `200`: the full `IncidentResponse`.

Side effects: `repair_order_id` is cleared and a `repair_order_unlinked` event
is appended carrying the previous `repair_order_id`.

Status is **not** rolled back. An incident that moved to `in_progress` stays
there: the work may still have happened, and silently reopening it would
contradict whatever the shop recorded. Detach corrects the link, not history.

The repair order itself is untouched — status, lines and board position are
unchanged.

### 3.4 What counts as linkable

An order is offered, and accepted, when all of:

- `tenant_id` matches the caller's tenant;
- `vehicle_id` matches the incident's vehicle;
- `status` is not in `TERMINAL_RO_STATUSES`
  (`completed`, `invoiced`, `paid`, `cancelled`, `declined`);
- `deleted_at` is null.

**Same vehicle only.** An incident pointed at another truck's order is a
data-integrity defect no UI affordance can undo, and it would corrupt both the
truck's service history and the incident's account of itself.

**Open orders only.** A closed order cannot absorb the work, so it cannot
honestly answer for the incident.

**PM orders are offered here**, although `_open_visit_for_vehicle` excludes
them. That helper excludes PM because folding unrelated repairs into a curated
PM scope happens *silently* there, and completing a PM rolls the odometer
target forward. Here a person is choosing that specific order deliberately;
refusing the explicit choice would leave a real incident with nowhere to point.
This asymmetry is intentional and is the one place this contract diverges from
the existing helper.

## 4. Failure modes

| Condition | Status | Detail |
|---|---|---|
| Incident not found, or another tenant's | `404` | Incident not found |
| Order is another tenant's, another vehicle's, soft-deleted, or absent | `404` | `Repair order not found for this truck` |
| Order exists on this truck but is closed | `400` | `That repair order is already closed. Pick an open order.` |
| Incident already has a linked order | `400` | `This incident is already linked to a repair order. Unlink it first.` |
| Detach when nothing is linked | `400` | `This incident has no linked repair order` |

The cross-tenant and cross-vehicle cases deliberately share one generic `404`.
A caller must not be able to learn that another tenant's order exists by
comparing responses, which is the same rule the codebase already applies to
foreign records.

An incident with an existing link is refused rather than silently reassigned:
re-pointing work is a decision, not a side effect, and the two-step
unlink-then-link leaves both events in the audit trail.

## 5. Authorization and tenancy

All three routes sit behind `require_fleet_access`, as every other fleet
incident route does.

The tenant and vehicle boundary is enforced **on attach**, not only in the
picker. The order is re-read through the same filter that built the list, so a
stale id from an old page, or a hand-crafted one, cannot reach another truck's
or another tenant's work. A picker that filters is a convenience; the server
check is the boundary.

## 6. Data and compatibility

No migration. `FleetIncident.repair_order_id` already exists, is already
nullable, and already carries a foreign key to `repair_orders.id`.

Two new event types join the existing append-only `FleetIncidentEvent`
vocabulary: `repair_order_linked` and `repair_order_unlinked`. Readers of that
timeline must tolerate unknown event types already, so this is additive.

`IncidentResponse` is unchanged. No existing route changes shape, so a client
that knows nothing about these routes is unaffected.

## 7. Acceptance

- An incident with no link attaches to an open order on its own truck, and the
  response shows the link.
- Attaching moves an `open` incident to `in_progress`.
- Attach and detach each append exactly one correctly-typed event.
- An order for a different vehicle is refused with `404`.
- An order belonging to another tenant is refused with the identical `404`,
  proven with the foreign order carrying *this* incident's `vehicle_id` so the
  vehicle filter cannot mask the tenant check.
- A closed order is refused with `400`.
- A second attach to an already-linked incident is refused with `400`.
- Detaching clears the link and leaves the order's status and soft-delete
  state untouched.
- The picker lists only open orders for this truck, and includes a PM visit.

Every boundary above carries a test that has been shown to fail when its guard
is removed.

## 8. Review notes

Two points an Architecture reviewer should weigh rather than take on trust:

1. **The PM asymmetry in §3.4** is a deliberate divergence from
   `_open_visit_for_vehicle`. If Architecture would rather PM orders were
   excluded for consistency, that is a one-line change to the query and one
   test; the incident then has no target while a PM is the only open order.

2. **Detach does not roll back status** (§3.3). The alternative — returning an
   `in_progress` incident to `open` when its last link is removed — is
   defensible, but it would let a mis-click reopen an incident whose work was
   genuinely done. This contract prefers leaving the status and the event trail
   to tell the story.
