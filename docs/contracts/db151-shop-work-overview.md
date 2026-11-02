# DB-151 Shop Work Overview contract v1

Architecture handoff, November 1, 2026. Backend & Integrations owns the read
projection; Frontend & UX owns Overview and exact-record destination adapters.
This is an additive read contract. No migration, mutation, scheduler, financial
reconciliation, importer change, or new editor belongs to this item.

## Endpoint and boundary

`GET /api/v1/dashboard/shop-work-overview?limit=50&upcoming_limit=20`
(`limit` 1–100; `upcoming_limit` 1–50). No client tenant argument.

Use the authenticated active actor and an active, nondeleted server-derived
tenant. Owner/admin/receptionist receive shop work; mechanics receive only their
existing `operation_execution.job_scope` repair/schedule scope. All other roles
receive generic 403. Parts require the existing global and tenant Parts Operations
flags and `PARTS_READ_ROLES` (owner/admin/receptionist). Account review requires
exactly `customer_receivables._authorize`: owner/admin AND
`user_has_permission(actor, 'payments')`. Never query or serialize financial
identities/counts before this check. Restrictions are server-side.

Run source readers in SELECT-only/no-autoflush transactions, rolling back on
exit. Financial reads use a dedicated repeatable-read, read-only session as the
existing account API does. A source failure must not turn its results into zero;
recover using a separate source transaction, not a poisoned shared transaction.
Return `Cache-Control: private, no-store`. No sensitive audit material or raw
exception strings in response. No GET-side repairs, flushes, writes, or events.

## Response

```ts
type SourceId = 'repairs' | 'schedule' | 'inventory' | 'purchasing' |
  'returns' | 'cores' | 'receivables'
type SourceStatus = {
  id: SourceId
  state: 'ready' | 'partial' | 'unavailable' | 'restricted' | 'disabled'
  checked_at: string | null
  reason: string | null // stable code; frontend owns plain-language labels
  total: number | null // full candidate count, never page length
  shown: number
  has_more: boolean
}
type Destination = {
  kind: 'repair_order' | 'inventory' | 'purchase_order' | 'vendor_return' |
    'core' | 'customer_account'
  id: string // immutable canonical UUID, never number/name/index
  view: string | null // needs_action/on_floor/ready_to_close/orders/receiving
}
type WorkItem = {
  id: string // `${kind}:${canonicalId}`, tenant-scoped response/query cache
  source: SourceId
  destination: Destination
  title: string
  reason: string // stable reason code
  action_label: string // Review order, Review stock, Review account, etc.
  status: string
  created_at: string | null
  due_at: string | null
  due_kind: 'repair_promise' | 'repair_start' | 'expected_delivery' | null
  evidence: 'verified' | 'review_required'
  quantity: number | null // existing package/remaining/core quantity only
  related_repair_order_ids: string[]
}
type Overview = {
  as_of: string
  timezone: string | null
  scope: 'shop' | 'assigned'
  active_jobs: number | null // full scoped WIP population; null when repairs unavailable
  sources: SourceStatus[]
  actions: WorkItem[]
  upcoming: WorkItem[]
  actions_total: number | null
  upcoming_total: number | null
  has_more_actions: boolean
  has_more_upcoming: boolean
}
```

There are deliberately no financial amount fields in v1. Counters are candidate
tasks, parts, or records, not money or a universal total-work metric. Calculate
full counts before output slicing. If a safety cap prevents a full source scan,
set that source partial, total null and has_more true; never claim an exact
count. Overall totals are null if a relevant authorized source cannot establish
its population. UI must offer owning-workspace navigation for omitted records.

## Actual source projections

1. **Repairs.** Reuse `services/wip_aging.py` evidence/classification/projection
   and `dashboard._native_billing_work_predicate`, including all tenant/deletion,
   imported-provenance and mechanic assignment rules. Its complete evidence
   snapshot is suitable; a capped public `/wip-aging` page is not. Active rows
   with no hold and no overdue promise are not action tasks. Preserve existing
   reasons and unknown clocks. One RO yields at most one action. Closeout remains in the existing work-view and Overview includes native completed
   orders with no invoice as `review_closeout` / Review closeout. Pending Zelle
   confirmation uses `review_payment` / Review payment under the account payments
   permission. Follow `_load_dashboard_action_queue` native/status predicates
   without its lane cap, with tenant/deletion-safe joins and mechanic assignment.
   Issued-invoice review belongs to the account candidate instead of a duplicate
   closeout task. Never label a candidate Collect money.
2. **Schedule.** Read actual `RepairOrder.scheduled_start_at` and
   `promised_finish_at` from that same scoped evidence; these are not appointments.
   Use `repair_order_schedule` visibility/editable/overdue rules and WIP's invalid
   promise safeguards. Future commitments are chronological, at most one next
   commitment per RO. If an RO is an action, omit its upcoming entry. Do not
   fabricate dates for unscheduled work or assume timezone if invalid.
3. **Inventory.** Reuse `parts_operations._part_metric_expressions` and
   `_part_projection_rows`, or extract unchanged reusable readers. Action
   population is active, nondeleted, nonplaceholder/nonretired parts with
   `recommended_order_packages > 0`. This already subtracts legacy on-order and
   remaining submitted/partially-received supply from repair shortage plus shelf
   replenishment. One action per part; carry real `repair_sources` associations.
   Label Review stock, not an instruction to purchase the displayed quantity.
   Never use stock <= reorder threshold alone or derive demand from RO hold text.
4. **Purchasing.** Reuse list projection in `endpoints/parts_operations.py`.
   Drafts are Review purchase draft. Submitted/partially_received with remaining
   quantity > 0 are Review delivery; expected_at is the sole delivery date and
   means expected, not supplier-confirmed. Future expected deliveries go upcoming;
   undated/due/past-expected orders go actions. Received/cancelled are excluded.
   One PO appears once. No supplier bill, payment due, or delivery-complete claim.
5. **Returns.** Existing VendorReturn states draft/submitted/shipped yield
   Review return / Review shipment / Review supplier credit respectively;
   credited/cancelled excluded. Keep expected credit distinct from received
   credit by omitting currency amounts entirely. No invented return deadline.
6. **Cores.** Existing CoreObligation expected/on_hand yield Review core
   recovery / Review core return. Returned/waived excluded. Suppress a core row
   already linked through a nondeleted VendorReturnLine to an active return
   (draft/submitted/shipped); that return owns the obligation. All join sides
   remain tenant-scoped. Do not turn a core deposit into collectible money.
7. **Receivables, explicitly review-only.** Existing `/customers/{id}/account`
   is per-customer and cannot be fanned out. Implement bounded tenant batch reads
   of issued native Invoice + RepairOrder + resolved bill-to Customer, settlements,
   bad-baseline ledger markers, and imported-payment markers. Identity must obey
   the existing account rule: nonnull billed_customer_id is authoritative; do not
   fall back to the RO customer when that customer no longer resolves. Require
   nondeleted records, sent/paid/overdue invoice state, noninternal customer/RO/
   invoice, no void and no live superseding invoice; exclude ETS invoice/RO and
   historical_export_hold. Apply existing native-record policy; exclude `test`.
   Candidates are real/unknown issued native invoices whose settlement is absent,
   ambiguous, fails `trusted_settlement`, has a bad baseline/imported payment, or
   has principal remaining > 0. These are candidates for account review, not
   verified debt. Group once by resolved customer, title the customer, reason
   `account_verification_required`, action Review account; no invoice amounts,
   balances, due date, overdue badge, or collection instruction. Use the existing
   account screen to perform full credit-graph and latest-attestation validation.
   Source state is always `partial`, reason `account_review_only`: "Account
   review candidates; collectible balances have not been verified." A read made
   now does not make historical evidence fresh. No amounts inferred from paid
   status, customer.balance, payment sums, or imported shared invoices. If policy
   or identity cannot be established, retain scoped unavailable/partial state;
   do not synthesize an account identity. Existing account evaluator semantics
   are unchanged. This bounded review-only slice is the committed v1, not a
   promise of a new tenant-wide receivables ledger.

Service/catalog/team/message modules are navigation destinations, not automatic
tasks: unread messages, catalog entries, and labor reference hours are not proof
of an obligation. Keep services and labor book time in the RO's incumbent
estimate flows and My Shop; no fabricated contextual picker contract here.

## Ordering, deduplication and freshness

Priority: overdue repair promise, other repair hold/review, remaining repair
preparation, current purchasing/return/core/account-review obligations, then stock
preparation. Within band sort known due time, then created_at, then stable ID;
unknown dates remain unknown. No "overdue collections" band exists in v1.
Do not merge an RO hold with inventory demand unless actual PartsUsage links prove
the shared obligation; when proven procurement owns the shortage and the RO is
related context. Preserve independently required RO review/approval work.

Query key includes tenant and actor. Refetch on entering/returning to Overview,
window focus and relevant existing query invalidations. Clicking never dismisses
an obligation. During failed refresh retain verified prior rows only with an
explicit stale state and prior checked_at; do not claim all clear. "No active
jobs" must still show parts, purchase, return, core, and account-review results.
Only fully checked authorized ready sources can support a scoped all-clear;
partial receivables prevents a global "nothing needs attention" claim.

## Destination adapters required in this item

- RO: existing `/dashboard/repair-orders?selected=<id>&queue=<valid-lane>`.
- Inventory: existing `/dashboard/garage/inventory?selected=<part-id>`.
- PO: `/dashboard/garage/purchasing?view=orders&purchase_order=<id>`; receiving
  additionally must pass initialPurchaseOrderId to its existing workspace.
- Return: add `view=returns&return=<id>` to initialize returns custody and ID.
- Core: add `view=returns&core=<id>` to initialize cores custody and ID.
- Account: add `/dashboard/customers?selected=<id>&tab=account`; bind the existing
  CustomerDetailPanel Account view, under its existing permission check.

Use a typed same-origin Shop Work origin/return object or a validated fixed
`/dashboard` return URL with Overview state. Preserve this context on workspace
tab changes and back navigation. Never accept arbitrary external return URLs.
Do not let PartsOperationsWorkspace's current `reconcileVisibleId` fallback
replace a requested PO/return/core with the first row: requested missing,
filtered, forbidden, or deleted records display unavailable and an explicit
return action. Refresh and browser back keep the same requested object.

## Required acceptance and gates

Focused backend tests: tenant A/B linked-record isolation; mechanic assignment;
receptionist/admin-no-payments financial omission before read; disabled parts;
zero WIP with real cross-domain obligations; cap/count honesty; per-source failure;
partly ordered shortages; return/core dedup; invalid/absent timestamps; test,
imported, orphan bill-to and invalid settlement cases; review-only finance labels;
no N+1 customer calls and no write side effects. Frontend tests plus signed-in
runtime: busy/quiet/partial, every exact record, missing-record fallback, return
and refresh, keyboard and narrow viewport. Independent QA and Security gates
are required for the new tenant/financial read boundary. No production mutation
or deployment is implied by this implementation contract.


## Browser-discovered destination cache isolation correction

Same-browser busy-tenant to clear-tenant signout/signin exposed retained incumbent
Closeout rows and badge. Scope DashboardHome action queue, daily workset, value
summary, and Overview caches by tenant, actor, role, payments grant and auth session
epoch; explicitly prohibit previous-context placeholders. Apply the same read-cache
boundary to the canonical RO list/workspace/detail and associated read queries,
Purchasing summary/PO/return/core reads, Inventory list/detail/editor/activity reads,
and Customer directory/detail/vehicle/contact/history reads. Existing query prefixes
remain intact for mutation invalidation. Pagination/search may retain previous rows
only within the same authorization scope. Canonical RO, Customer, Purchasing and
Inventory route content resets local selected/draft display state at identity change.
Customer Account retains its incumbent session-keyed reads and permission gate.

Regression evidence must use a real persistent QueryClient (including a global
keepPreviousData default), show a busy identity, then change identity while the next
response is pending/denied. Prior Closeout rows/totals, selected customer Account,
and selected RO workspace must be absent before the new response settles.
