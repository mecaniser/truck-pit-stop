# DB-052 — Filtered repair-order value totals

Status: Frozen before implementation
Accountable owner: Backend & Integrations
Contributors: Architecture & API Contracts, Frontend & UX

## Outcome

Add two additive, server-authoritative order-value summaries:

- Shop Work: the value of the complete current daily lane/search scope.
- Repair Orders: the value of the complete current list filter/search scope.

Neither total may be calculated from capped or paginated browser rows.

## Amount contract

Both endpoints return:

```json
{
  "order_count": 0,
  "order_value": "0.00",
  "currency": "USD",
  "amount_basis": "repair_order_net"
}
```

`order_value` is the USD sum of canonical persisted `RepairOrder.total_cost`,
quantized to cents and floored at zero per order. It is parts plus labor after
labor/order discounts. It is not revenue, A/R, amount collected, tax, shop
supplies, card fees, payments, or refunds. Shop Work row amounts must use this
same canonical net value rather than the current gross subtotal helper.

## Shop Work interface

`GET /api/v1/dashboard/daily-workset/value-summary`

Parameters:

- `lane=all|needs_action|on_floor|ready_to_close|closed_today`
- optional trimmed `search`; blank equals no search

The response also includes `lane`, tenant `timezone`, and `business_date`.
Lane membership is identical to the existing daily workset:

- `needs_action`: pending-Zelle plus draft, quoted, declined, and
  pending-review orders, deduplicated by repair-order ID.
- `on_floor`: approved, assigned, acknowledged, and in-progress orders.
- `ready_to_close`: completed and invoiced orders with the current imported
  zero-value and pending-Zelle exclusions.
- `closed_today`: paid invoices whose `paid_at` is inside the tenant-local day.
- `all`: a distinct union of the four lanes, never a sum of lane totals.

Search covers order number, rendered customer/company identity, rendered
vehicle identity, description, and assigned mechanic. Count and value are
uncapped by the existing 50-row lane limit.

Authorization is exactly the daily-workset boundary: active owner, admin,
receptionist, or mechanic in an active, nondeleted current tenant. All other
principals fail closed with `403` before protected queries.

## Repair Orders interface

`GET /api/v1/repair-orders/value-summary`

It accepts the list's exact optional filters: `customer_id`, `vehicle_id`,
`status`, `search`, and `deleted=false`. It has no pagination parameters.
Projection and legacy fallback filters must share tenant, customer, fleet,
search, status, vehicle, and deleted semantics. The existing fleet-manager
fallback mismatch (`is_fleet_work` versus projection `is_internal`) is corrected
to `is_internal`.

Shop-authorized staff see only their current tenant. Customer/driver principals
remain denied by the existing Repair Orders shop-access boundary; DB-052 does
not create a new customer-facing financial route. `deleted=true` remains
owner/admin-only. Foreign customer/vehicle filters return an empty summary
without revealing existence.

## Compatibility and negative behavior

- Existing list, status-count, daily-workset, pagination, and row DTOs remain
  backward compatible.
- No matches return count `0` and value `"0.00"`.
- Invalid lane/status values return `422`.
- Values do not change with `skip`, `limit`, loaded pages, or `has_more`.
- No migration, payment, invoice, tenant, or production-data mutation is part
  of DB-052.

## Acceptance evidence

- Focused backend tests cover net cents, each lane, search, tenant-local day,
  pending-Zelle exclusions/deduplication, distinct `all`, more than 50 Shop
  Work rows, more than 25 Repair Orders, list-filter parity, projection/legacy
  parity, tenant/role negatives, and zero/decimal contracts.
- Focused frontend tests cover loading/error/zero states and both totals reacting
  to lane, status, and debounced search without summing rendered rows.
- Runtime acceptance covers Shop Work and Repair Orders on an isolated port.
- Independent QA reviews the exact unchanged candidate; implementation does not
  self-approve its gate.
