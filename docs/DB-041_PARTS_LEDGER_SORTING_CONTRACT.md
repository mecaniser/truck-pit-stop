# DB-041 Parts Ledger Sorting Contract

Status: Architecture contract complete; implementation not started

Version: 1.0

Base: `86c9fc648a9f96d7b978da1208ce37b76a8d7ca3`

Accountable contract owner: Architecture & API Contracts

Implementation owners: Backend & Integrations, then Frontend & UX

## Outcome and boundary

DB-041 adds authoritative, deterministic sorting to the released Parts ledger.
Sorting composes with the existing row-inclusion filter, search, role, tenant, and
pagination contracts. It does not change routes, part fields, stock arithmetic,
purchase preparation, inventory mutations, permissions, or product state.

There is no schema migration, dependency, or new feature flag. The existing
`PARTS_OPERATIONS_V1_ENABLED` compatibility boundary remains authoritative.

## Source map at the accepted base

- `backend/app/api/v1/endpoints/parts_operations.py`
  - `GET /parts-operations/parts` already filters by the server-derived tenant,
    filters/searches, counts, orders, and then paginates.
  - `_part_metric_expressions` and `_part_projection_rows` already calculate the
    actionable recommendation from open-repair shortage, shelf need, and incoming
    supply. They are the only permitted source for reorder urgency.
  - Current sorting supports only `catalog`, `name`, `available`, and `reorder`;
    direction is implicit and `location`/`cost` are absent.
- `backend/app/services/parts_operations_service.py`
  - Read access remains Garage Owner, Garage Admin, and Receptionist. The enabled,
    active tenant is resolved only from the authenticated user; callers cannot
    supply or override a tenant.
- `frontend/src/features/inventory/PartsInventoryWorkspace.tsx`
  - The infinite query currently sends `view`, `attention`, `search`, `sort`,
    `skip`, `limit`, and `paginated`; it has no direction state.
  - Desktop headers are currently static. The Options popover currently owns all
    sorting. Selected part and checked purchase-preparation records are keyed by ID.
- `frontend/src/index.css`
  - The ledger header is visible above 760px and the compact card layout hides it
    at 760px and below. This same visibility boundary owns the fallback sort UI.
- `backend/tests/test_db038_read_contract.py`
  - The existing fixture proves actionable Needs reorder equality between summary
    and collection and excludes threshold-equal, fully covered, placeholder,
    archived/retired, deleted, and foreign-tenant records.
- `backend/tests/test_db038_postgres_operations.py`,
  `frontend/src/features/inventory/__tests__/PartsInventoryWorkspace.test.tsx`, and
  `e2e/tests/db038-parts-operations.spec.ts` are the focused contract, component,
  and responsive-browser test owners to extend. The browser fixture's current
  reorder comparator is naive stock-minus-threshold and must be replaced by the
  accepted actionable recommendation before it can be acceptance evidence.

## Request and response contract

### Endpoint

`GET /api/v1/parts-operations/parts`

Existing query parameters and response behavior remain valid. Additive parameters:

| Parameter | Values | Default when omitted |
|---|---|---|
| `sort` | `catalog`, `name`, `available`, `location`, `cost`, `reorder` | `catalog` |
| `direction` | `asc`, `desc` | Sort-specific legacy/first-use default below |

Direction defaults preserve old calls and the Product-defined first click:

| Sort | Omitted direction | Meaning |
|---|---|---|
| `catalog` | `asc` | Catalog/SKU order |
| `name` | `asc` | Part name A-Z |
| `available` | `asc` | Low to high |
| `location` | `asc` | Bin A-Z, unset last |
| `cost` | `desc` | Average cost high to low |
| `reorder` | `desc` | Most urgent to least urgent |

Examples:

```http
GET /api/v1/parts-operations/parts?view=active&search=brake&sort=cost&direction=desc&skip=0&limit=50&paginated=true
GET /api/v1/parts-operations/parts?view=active&attention=needs_reorder&sort=reorder&direction=desc&skip=0&limit=50&paginated=true
```

The paginated response shape and every item field are unchanged:

```json
{
  "items": [
    {
      "id": "inventory-uuid",
      "sku": "BRAKE-001",
      "name": "Brake shoe",
      "location": "A-01",
      "available_packages": 2,
      "needed_for_open_repairs": 3,
      "reorder_level": 4,
      "incoming_packages": 1,
      "recommended_order_packages": 4,
      "average_unit_cost": "52.50",
      "is_archived": false,
      "is_placeholder": false
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 50,
  "has_more": false
}
```

The example omits unchanged descriptive, supplier, repair-source, and
incoming-source fields only for brevity. `paginated=false` continues to return the
ordered item array directly. Sorting never changes item serialization or totals.

## Authoritative ordering

All text ordering is case-insensitive. Only the named primary key follows
`direction`; the stable fallbacks remain ascending so equal-key records cannot
move between pages.

| Sort | SQL-level primary order | Stable fallback order |
|---|---|---|
| `catalog` | `lower(sku)` in requested direction | `lower(name) ASC`, `id ASC` |
| `name` | `lower(name)` in requested direction | `lower(sku) ASC`, `id ASC` |
| `available` | numeric `coalesce(stock_quantity, 0)` in requested direction | `lower(name) ASC`, `lower(sku) ASC`, `id ASC` |
| `location` | `lower(trim(location))` in requested direction | `lower(name) ASC`, `lower(sku) ASC`, `id ASC` |
| `cost` | numeric `cost` in requested direction | `lower(name) ASC`, `lower(sku) ASC`, `id ASC` |
| `reorder` | numeric actionable recommendation in requested direction | `lower(name) ASC`, `lower(sku) ASC`, `id ASC` |

For `location`, `NULL`, empty, and whitespace-only values are one unset class and
sort last for both directions. They retain the stable fallback order within that
class. Cost ordering is numeric database ordering, never formatted-string order.

The reorder primary value is exactly:

```text
repair_shortage = sum(max(ceil(open_repair_part_quantity) - reserved_packages, 0))
shelf_need      = max(reorder_level - available_packages, 0)
incoming        = legacy_on_order + remaining_submitted_or_partially_received_PO_packages
recommendation  = max(repair_shortage + shelf_need - incoming, 0)
```

Open repair demand retains the existing unlocked, non-deleted repair-order status
boundary. Equality with the reorder threshold creates no shelf need. Incoming
supply fully covering demand produces zero urgency.

Row membership remains owned by `view`, `attention`, and `search`; sorting cannot
add or remove rows. Active, non-placeholder, tenant-owned records may have positive
urgency. Placeholder, archived/retired, deleted, foreign-tenant, and fully covered
records never count as actionable. When such a record is legitimately included by
another view (for example `view=archived`), its effective reorder urgency is zero
and it is ordered deterministically rather than removed by sorting.

The operation order is invariant:

1. Authenticate and resolve the enabled tenant from the user.
2. Apply tenant/deleted scope and role authorization.
3. Apply `view`, `attention`, supplier, and normalized search filters.
4. Count the filtered collection.
5. Apply the authoritative order and stable tie-breakers.
6. Apply `skip`/`limit` pagination.
7. Project only those tenant-scoped rows into the unchanged response.

## UI interaction contract

### Row inclusion and search

The toolbar keeps four mutually exclusive row-inclusion choices:

- All: `view=active`, no attention filter.
- Needs reorder: `view=active&attention=needs_reorder`.
- Out of stock: `view=active&attention=out_of_stock`.
- Archived: `view=archived`, no attention filter.

The existing search text and active row-inclusion choice remain in place when a
sort changes. A filter or search change preserves the chosen sort while retaining
its existing selection-clearing behavior. No new route or URL state is introduced.

### Desktop headers

When the ledger header is visible, its header buttons are the only field-sort
controls. Clicking an inactive header applies its first-click direction; clicking
the active header toggles it:

| Header | Sort | First click | Second click |
|---|---|---|---|
| Part / Description | `name` | A-Z (`asc`) | Z-A (`desc`) |
| Available | `available` | low-high (`asc`) | high-low (`desc`) |
| Bin location | `location` | A-Z (`asc`) | Z-A (`desc`) |
| Average cost | `cost` | high-low (`desc`) | low-high (`asc`) |
| Remarks / Status | `reorder` | most-least (`desc`) | least-most (`asc`) |

Preferred supplier remains non-sortable. Catalog order has no column header.
Options retains Density plus one Catalog order/reset action; it must not repeat
the desktop field-sort menu.

Every sortable columnheader contains a semantic button with a 44px target,
keyboard activation, visible focus, and a visible non-color-only direction icon.
Only the active sorted column carries `aria-sort="ascending"` or
`aria-sort="descending"`; inactive sortable headers do not claim an order. The
button's accessible name describes the next action.

### Compact fallback

Whenever CSS hides the table header (currently 760px and below), Options exposes
Density, Catalog order, and the equivalent directional sort choices:

- Part A-Z / Z-A
- Available low-high / high-low
- Bin A-Z / Z-A
- Average cost high-low / low-high
- Reorder urgency most-least / least-most

The fallback and headers are never simultaneously presented as competing field
sort systems. Catalog order/reset is available at every size.

### Pagination and selection

Changing `sort` or `direction` creates a new infinite-query key, resets `skip` to
zero, and discards already loaded pages before requesting page one. Search and
row-inclusion parameters remain composed into that request. Equal-key tie-breakers
must produce no duplicate or missing IDs across adjacent pages.

Sorting does not clear the selected part or checked purchase-preparation IDs. A
selected part's inspector remains open even if sorting moves its row beyond the
currently loaded page, because sorting does not change eligibility. Existing
filter/search behavior may replace selection only when it changes row membership.
Needs-reorder preselection must include both `sort` and `direction` in its page
identity so a reordered page cannot be mistaken for one already processed.

## Authorization, errors, and compatibility

- Garage Owner, Garage Admin, and Receptionist retain read access. No role gains a
  mutation or additional field. Existing manage-only controls remain unchanged.
- Missing/disabled/inactive tenant and feature-off behavior remains generic 404.
  Disallowed roles remain 403. There is no tenant query parameter.
- Invalid or blank `sort`/`direction` returns 422 and performs no write. Existing
  invalid pagination/filter behavior is unchanged.
- A known foreign part ID or tenant identifier cannot influence this collection;
  tenant filtering precedes ordering and no foreign row, count, tie-breaker, or
  urgency signal is observable.
- Existing callers omitting both new values receive catalog ascending. Existing
  callers using `sort=name`, `sort=available`, or `sort=reorder` without direction
  retain their prior effective order. All old response shapes remain valid.
- No write or idempotency contract applies to this GET-only change.

## Acceptance and negative matrix

Backend must prove, on PostgreSQL:

1. All six sorts in both explicit directions, including first-use defaults.
2. Numeric cost order and location `NULL`/blank/whitespace last in both directions.
3. Deterministic equal-key ordering across at least two pages with no repeated or
   missing ID, with sort applied before pagination.
4. Search plus each row-inclusion filter plus sort/direction composition.
5. Reorder urgency uses the accepted projection: repair-only shortage rises;
   threshold equality does not; fully covered incoming supply is zero; placeholder,
   archived/retired, deleted, and foreign rows are non-actionable.
6. Archived view remains populated under reorder sorting but has zero actionable
   urgency; Needs reorder never includes archived or placeholder records.
7. Omitted-parameter compatibility and `paginated=false` array compatibility.
8. Invalid sort/direction 422; disabled/inactive tenant 404; disallowed role 403;
   foreign tenant has no rows/counts; all cases leave state unchanged.

Frontend component and isolated Playwright acceptance must prove:

1. First click and toggle direction for all five desktop headers, visible icons,
   `aria-sort`, keyboard activation, focus return, and 44px targets.
2. Options contains only Density plus Catalog reset on desktop and the full
   equivalent fallback only when headers are hidden.
3. Sort changes request `skip=0` with explicit sort/direction, keep search/filter,
   and do not mix or append old pages.
4. Selected inspector and eligible checked parts persist by ID through sorting;
   changing filter/search retains its established membership behavior.
5. Updated deterministic fixture orders by `recommended_order_packages`, not
   stock-minus-threshold, and exercises equal keys, blank locations, numeric costs,
   repair shortage, and fully covered incoming supply.
6. Containment and operability at 1440, 1280, 1100, 960, 390, and 320 in all
   supported themes, forced colors, keyboard-only use, and 200% zoom. No clipped
   header control, fallback control, row, inspector, bulk action, or focus ring.

## Implementation handoff

Backend & Integrations owns only:

- `backend/app/api/v1/endpoints/parts_operations.py`: additive `location`/`cost`
  sorts, explicit direction validation/defaults, stable ordering helpers, and the
  accepted reorder urgency ordering without changing projection or membership.
- Focused PostgreSQL/read-contract tests in
  `backend/tests/test_db038_postgres_operations.py` and
  `backend/tests/test_db038_read_contract.py`.

Frontend & UX begins after the Backend request contract is green and owns only:

- `frontend/src/features/inventory/PartsInventoryWorkspace.tsx`: direction state,
  query reset, sortable headers, responsive Options fallback, and ID-stable
  selection/preselection behavior.
- `frontend/src/index.css`: header-button, direction, breakpoint, focus, theme,
  forced-color, target, and containment styling.
- Focused component and browser acceptance in
  `frontend/src/features/inventory/__tests__/PartsInventoryWorkspace.test.tsx` and
  `e2e/tests/db038-parts-operations.spec.ts` (or a focused DB-041 spec/config if
  Release selects one without duplicating fixtures).

Backend must not change schemas, response fields, tenant/role logic, stock state,
or row-inclusion semantics. Frontend must not implement client-side sorting of a
paginated collection, duplicate desktop sort controls, or fabricate urgency from
displayed stock values. Fresh independent Architecture/tenant-boundary review and
QA/runtime acceptance are required on the frozen implementation candidate before
Release may open or merge a focused PR.
