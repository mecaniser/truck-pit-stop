# DB-145 / A2 — Shop Work aging and bottlenecks

Status: implementation contract v1 frozen by Architecture & API Contracts, 2026-10-29. User authorized implementation in Shop Work. Implementation, independent verification and release gates remain pending.
Accountable owner: Frontend & UX. Product & Delivery Lead owns intake; Architecture & API Contracts owns the read projection and clock semantics.
Source inspected: `81fac6dc2e1a1f422b62969cee42169ba1ce2fc3`.

## User outcome and placement

Shop Work answers what needs attention now, why it is waiting, how long it has waited, and which existing job to open. Repair Orders remains the full record directory and history. A2 belongs in the existing Shop Work queue, not a separate report the dispatcher must visit.

The user selected A2 first, followed by C3, R3, A3 and S1. Those are separate outcomes. No importer release or financial mutation is authorized.

## Proposed operating view

- Keep search, quick/full order entry, Activity and existing job drill-down.
- Add a compact bottleneck summary above the queue. Clicking a reason filters matching jobs; it must not trigger a workflow change.
- Display reason, supported current-wait duration, technician/assignment state, record age and promised deadline where permitted. Keep nonessential evidence in an accessible detail/tooltip.
- Distinguish active work from payment-only closeout. Do not label every completed or invoiced order a truck still occupying the shop.
- Prioritize recorded holds and missed promises, then older supported waits. Unknown timing is visible and sortable separately, never silently zero.
- Preserve source-owned ETS history outside native operational/billing actions. Do not turn imported timestamps into local arrival or occupancy evidence.
- On mobile, show truck/customer, reason and duration first; let one tap open the existing workspace. Avoid horizontal scrolling and long explanatory text.

Illustrative data only: a native order created three days ago, put on a parts hold five hours ago, and promised two hours ago may show `Waiting for parts · 5h`, `Order age · 3d`, and `Promise overdue · 2h`. Those are three different clocks. Creation time does not prove the truck arrived three days ago.

## Verified source capabilities and limits

| Evidence | Safe use | Boundary |
|---|---|---|
| `RepairOrder.created_at` | Order/record age | Not arrival time or time in current stage; import creation is not historical operational age |
| `hold_reason`, `held_at` | Current in-progress hold and its supported start | Free-text reason; missing start remains unknown; never classify arbitrary text as a parts or approval hold by substring guessing |
| `assigned_at`, `acknowledged_at` | Recorded assignment/acknowledgement transitions | Must agree with current state and operation-level assignment before deriving a wait |
| `work_started_at`, `work_completed_at` | Recorded work boundaries; candidate quality-review clock while `pending_review` | Work completion is not payment, vehicle release, or proof of every quality transition |
| `Quote.sent_at`, revision, sent/approved/declined flags, `decision_at` | Candidate current pending-approval clock after canonical revision selection | An unsent draft, expired/replaced quote, or decided revision must not create a customer-wait clock |
| `scheduled_start_at`, `promised_finish_at` | Planning and deadline lateness where authorized | Not actual work/arrival timestamps; retain existing schedule visibility |
| `updated_at` | Last record update only | Never substitute it for wait start or operational progress |
| Existing daily-workbench queue | Navigation and existing lane behavior | Each lane is limited to 50; visible-row counts are not complete shop totals |

Sources: `backend/app/db/models/repair_order.py`, `backend/app/db/models/quote.py`, `backend/app/services/staff_work_hold.py`, `backend/app/api/v1/endpoints/dashboard.py`, `frontend/src/features/dashboard/ShopCockpitActionLedger.tsx`.

## Architecture source review — 2026-10-29

Architecture independently inspected the read paths and approved the placement and evidence-based clock direction. Latest approval revision must be selected by same-tenant/order, undeleted Quote, revision DESC then created_at DESC **before** testing its pending/sent state. A newer draft must suppress an older pending approval link. `sent_at` proves publication, not provider delivery. Expired or contradictory evidence requires a distinct state, never customer-wait inference.

Known hold categories can use exact values `waiting_for_parts`, `waiting_for_customer_approval`, `need_more_info` and `switched_to_other_ro`; arbitrary text stays Other hold. Legacy NULL operation execution remains unknown. `total_hold_minutes` is not a categorized historical wait ledger. All elapsed clocks include nights/weekends, not labor or business hours.

The daily workset accepts active tenant-bound owner/admin/receptionist/mechanic principals. Mechanic overdue summaries and filters must apply the existing same-tenant order/operation-assignment visibility before aggregation, not mask timestamps after a count has leaked. No newly exposed hold/review details may broaden exact-order access.

## Frozen v1 read contract

Add `GET /api/v1/dashboard/wip-aging`. This is a side-effect-free projection: SELECT only, no locks, flush/commit, snapshots, background work, external calls or source repair. Existing daily-workset/action-queue/value-summary responses remain compatible. Existing payment-only closeout remains separate; A2 does not relabel or repair its financial lifecycle.

### Request

| Query | Type / default | Meaning |
|---|---|---|
| `search` | optional string, trimmed, maximum 200 characters | Literal case-insensitive substring over order number, customer display/name/company, vehicle display/unit and permitted assigned technician names. Escape SQL wildcard characters; do not treat `%` or `_` as user wildcards. |
| `category` | category enum or `all`; default `all` | One disjoint primary operational category below. |
| `overdue_only` | boolean, default false | True restricts rows to the existing permitted promised-finish overdue predicate. False adds no deadline restriction. |
| `timing` | `all`, `known`, `unknown`; default `all` | Filters the **current wait** clock state; active work with no wait is `not_applicable`, not unknown. |
| `sort` | `priority`, `oldest_wait`, `oldest_order`; default `priority` | Deterministic ordering defined below. |
| `offset` | integer >=0, default 0 | Offset into the fully filtered result. |
| `limit` | integer 1–100, default 50 | Page size. |

Unknown enum values, oversized search and invalid numeric values return the standard FastAPI 422. Unsupported/inactive/deleted actors or absent/inactive/deleted tenant return 403 before data loading. The endpoint has no caller-supplied tenant or actor parameter.

### Response shape (normative TypeScript; Pydantic mirrors these fields)

```typescript
type WipCategory = 'approval' | 'parts' | 'technician' | 'review'
  | 'other_hold' | 'active' | 'preparation'
type ClockState = 'known' | 'unknown' | 'not_applicable'
type ClockIssue = 'missing_timestamp' | 'future_timestamp'
  | 'inconsistent_evidence' | null
interface WipClock {
  state: ClockState
  since: string | null                 // ISO 8601 UTC, only for known clocks
  seconds: number | null               // nonnegative whole elapsed seconds
  issue: ClockIssue
}
interface WipAgingRow {
  id: string
  order_number: string
  status: string
  customer_name: string
  vehicle_info: string
  vehicle_unit_number: string | null
  category: WipCategory
  reason: 'waiting_for_parts' | 'approval_hold' | 'awaiting_customer_decision'
    | 'awaiting_acknowledgment' | 'ready_to_start' | 'technician_timing_unknown'
    | 'awaiting_quality_review' | 'need_more_info' | 'technician_switched'
    | 'other_hold' | 'work_in_progress' | 'prepare_estimate' | 'revise_estimate'
    | 'quote_not_sent' | 'quote_expired' | 'quote_evidence_unknown'
  hold_reason: string | null            // recorded source reason, text-escaped in UI
  assignment: 'assigned' | 'unassigned' | 'unknown'
  technician_names: string[]            // distinct, sorted; same-tenant valid identities only
  order_age: WipClock
  current_wait: WipClock
  promised_finish_at: string | null
  overdue_seconds: number | null       // null unless permitted and actually overdue
  is_overdue: boolean
  action_lane: 'needs_action' | 'on_floor'
}
interface WipAgingResponse {
  as_of: string                        // one UTC instant used throughout this response
  timezone: string | null              // valid configured shop zone; null if invalid/missing
  scope: 'shop' | 'assigned'            // mechanic is assigned, never shop-wide
  filters: {
    search: string
    category: WipCategory | 'all'
    overdue_only: boolean
    timing: 'all' | 'known' | 'unknown'
    sort: 'priority' | 'oldest_wait' | 'oldest_order'
  }
  summary: {                           // authorized eligibility + search, BEFORE narrow filters
    total_jobs: number
    category_counts: Record<WipCategory, number>
    overdue_jobs: number
    unknown_wait_jobs: number
  }
  filtered_total: number               // AFTER category/overdue/timing, BEFORE pagination
  offset: number
  limit: number
  has_more: boolean
  items: WipAgingRow[]
}
```

All category keys occur even when zero. `summary.total_jobs` equals the sum of disjoint category counts. Deadline and unknown-wait counts overlap categories and must never be summed into total jobs. Summary facets describe the searched authorized workset; changing a narrow filter does not erase the other category counts. UI labels the list result count with `filtered_total`; it must not present `items.length` as the complete count. `has_more = offset + items.length < filtered_total`. No monetary, payment, quote-token or customer contact fields are returned.

### Eligibility and principal scope

1. Authenticated active, undeleted owner/admin/receptionist/mechanic with an active, undeleted selected tenant. Owner/admin/receptionist receive tenant scope. Mechanic receives **only** `operation_execution.job_scope(tenant_id, actor.id)`; apply it before any joins, counts, filtering or paging. Fleet/customer/driver/platform/unknown roles are denied. This additive endpoint is deliberately narrower than legacy tenant-wide mechanic rows; it does not change those legacy endpoints.
2. Repair order belongs to the selected tenant, is undeleted and `vehicle_released_at IS NULL`; status is one of `draft`, `quoted`, `declined`, `approved`, `assigned`, `acknowledged`, `in_progress`, `pending_review`.
3. Apply the existing native-ownership veto to all qualifying statuses: RO source must not equal `easy_truck_shop_import`; no same-tenant/order Invoice may have ETS source or `historical_export_hold` accounting policy. Tombstoned/cancelled invoices still carry ownership evidence. Never add a cross-tenant invoice predicate without matching both tenant and order. This endpoint calls the cohort **active jobs**, not proof the vehicles physically occupy the shop.
4. Join customer, vehicle, quote, labor, user and any ancillary evidence on both selected tenant and identity/order. Ignore foreign-tenant matches. Invalid relationships must not leak names, evidence or counts. Existing internal-fleet native operational jobs may appear; no pricing/invoice policy changes follow.
5. Completed/invoiced/paid/cancelled/released/deleted jobs are excluded regardless of `updated_at`, invoice balance or payment state. An own-truck invoice updated today is still not proof of physical work or a newly started wait. No test/real financial classification or B1-policy coupling is introduced.

### Canonical evidence and category precedence

Each eligible order receives one primary category. Apply these rules in order:

1. **Recorded current hold**: only `in_progress` plus nonblank `hold_reason`. Exact `waiting_for_parts` maps to category `parts` / reason `waiting_for_parts`; exact `waiting_for_customer_approval` maps to `approval` / `approval_hold`; all other reasons map to `other_hold`, with `need_more_info`, `technician_switched` (exact `switched_to_other_ro`) or `other_hold` reason. The wait clock uses `held_at`. A recorded approval hold proves the shop recorded that reason; it does **not** prove a current approval link or customer message exists. UI says **Approval hold**, not **Customer has not replied**. No keyword inference from free text. Hold fields outside in-progress are stale and ignored.
2. **Quality review**: `pending_review` maps to `review` / `awaiting_quality_review`, using `work_completed_at`. Require no contradictory live work/hold evidence; timestamps before `work_started_at` are inconsistent. Missing completion stays unknown.
3. **Quoted order**: select the latest same-tenant/order undeleted quote by `revision DESC, created_at DESC, id DESC` **before** testing state. A quote qualifies for `approval` / `awaiting_customer_decision` only if it is sent, neither approved nor declined, has no decision timestamp, has a valid `sent_at`, and is not expired. Expiry is the earlier of `sent_at + 7 days` and explicit `expires_at`, matching current approval-link policy. It is expired only when `as_of > expiry`; impossible expiry-before-publication is inconsistent. Do not borrow an older sent quote beneath a newer draft. Missing sent timestamp or conflicting decision flags maps to `preparation` / `quote_evidence_unknown`, with unknown wait. A valid unsent latest draft maps to `preparation` / `quote_not_sent`; an expired latest pending quote maps to `preparation` / `quote_expired`. Both have unknown current-stage timing; never use old sent time as their current wait. Any other unsupported quoted/quote combination is `quote_evidence_unknown`. Publication is not a delivery receipt.
4. **Before work starts**: `approved`, `assigned`, `acknowledged` map to `technician`. `assigned` with a valid current order-level technician, no work-start/completion contradiction, and valid `assigned_at` uses `awaiting_acknowledgment`. `acknowledged` with a valid current order-level technician and valid `acknowledged_at` uses `ready_to_start`; when both timestamps exist require acknowledgment >= assignment. `approved` uses `ready_to_start` with unknown timing. Inconsistent assignment/lifecycle evidence uses `technician_timing_unknown` with unknown timing. Do not borrow quote decisions or creation time as technician-wait start. Operation-only assignments do not establish a whole-order acknowledgment timestamp.
5. **Unheld in-progress**: category `active` / `work_in_progress`. Current wait is `not_applicable`; this asserts recorded work status, not a running timer or productive labor hours.
6. **Preparation**: `draft` uses `prepare_estimate`; `declined` uses `revise_estimate`. Current-stage duration is unknown because no dedicated entry timestamp proves the current episode.

Current assignment is separate from category. Inspect the order assignment plus undeleted, same-tenant non-sublet operations whose execution is pending or legacy NULL. A valid assignee is an active undeleted mechanic in the same tenant. Names contain distinct valid assignees only. Any non-null invalid assignee makes assignment `unknown`; otherwise any valid assignee makes it `assigned`; otherwise it is `unassigned`. NULL operation execution never proves completion or delay; exclude completed operations from pending-assignment display. Use existing `job_scope` verbatim for mechanic authorization, independently of display state, so presentation rules do not expand permissions.

### Clock and deadline rules

- Capture one `as_of` server instant per response; compute whole elapsed seconds in UTC. Legacy naive stored datetimes follow existing backend UTC normalization. UI uses response clocks and may refresh, but does not invent elapsed evidence from `updated_at`.
- A known order-age clock requires valid `created_at <= as_of`; label **Order age**, never **Time in shop**. A known current-wait clock requires a present timestamp, valid record creation, `created_at <= since <= as_of` and the stage-specific constraints above. Invalid/future creation also makes dependent wait evidence unknown. Missing evidence uses `missing_timestamp`; future evidence uses `future_timestamp`; lifecycle/order contradictions use `inconsistent_evidence`. Never coerce these to zero. `not_applicable` has null since/seconds/issue. `unknown` has null since/seconds and a nonnull issue. `known` has nonnull since/seconds and null issue.
- Use `repair_order_schedule.is_overdue` semantics, including its status set, release and deletion safeguards. An impossible promise before record creation or contradictory start/finish ordering yields no overdue claim. Future promises are valid deadlines, not invalid clocks. Set `overdue_seconds = floor(as_of - promise)` only when actually overdue; otherwise null.
- Role/assignment scope is applied before overdue aggregation. Every mechanic row is already in exact-order assignment scope. No hidden schedule may affect summary counts, filters or sorting. An invalid/missing configured shop timezone returns null timezone; render absolute dates with an explicit UTC label, never silently guess the shop zone.
- Durations include nights/weekends. No business-hours, arrival, occupancy, historical stage-total or technician productivity claim is made. `total_hold_minutes` and current timer lengths are not substitutes for categorized wait evidence.

### Filtering, aggregation and ordering

Build one authorized eligible projection with category/clock/deadline evidence. Apply literal search. Compute summary over that entire search result, not the existing 50-row action lanes. Apply category, overdue-only and timing filters to derive `filtered_total`, then sort and page. Implementation may use bounded SQL aggregation/projection; it must not expose a partial result as complete. Avoid per-row queries. Use a consistent database read snapshot or one statement so concurrent updates cannot make rows and counts describe different source versions within one response.

Default `priority` sorts overdue first, then current recorded holds, then quality review, approval, technician, preparation and active work. Within a priority group, known current-wait duration descending, unknown waits next, then no-wait jobs; valid creation ascending, then order UUID ascending provides stable ties. `oldest_wait` places known wait seconds descending, unknown waits next, not-applicable last; stable ties use valid creation then UUID. `oldest_order` uses known order age descending, unknown age last, then UUID. Sort always uses server evidence; changing pagination does not reset priority or clocks. Offset pagination is deterministic for a response snapshot, not a guarantee against new concurrent work between requests.

### UI integration and compatibility

Shop Work gets an **Active work** operational view with compact category counts and an **Overdue** filter. Existing **Ready to Close** stays separately reachable as **Closeout** or its existing name; do not redesign payment state or combine its value/count into A2 active jobs. Existing Activity, order entry and history remain reachable. The A2 report opens an existing record with `action_lane` (`needs_action` for draft/quoted/declined/pending_review, otherwise `on_floor`). Navigation is read-only. The existing workspace can expose its existing permitted actions; the A2 filter/open interaction performs no mutation.

Wait label examples: `Waiting for parts · 5h`, `Awaiting review · Unknown`, `Approval hold · 2h`. Active rows show `Work in progress`, not a zero-hour wait. Order age and promise are separately labeled supporting evidence. Primary controls and durations remain compact on desktop/mobile; evidence/help text stays in accessible details. Production data coverage may be incomplete; never seed production fixtures or repair rows to make a demonstration populated.

### Shared implementation fixtures

- Native in-progress parts hold: created at T-3d, held at T-5h, promised T-2h => parts, wait18000, age259200, overdue7200.
- Same order with only `updated_at=T` => identical A2 clocks/classification.
- Native pending-review with missing completion => review with unknown wait, not zero.
- Latest quote revision2 unsent above sent revision1 => preparation/quote_not_sent, no approval-delay clock.
- Latest sent pending quote at T-8d with no explicit expiry => preparation/quote_expired; explicit hold remains separately labeled recorded hold if status is in-progress.
- Assigned order with valid same-tenant mechanic and assignment T-1h => technician/awaiting_acknowledgment, wait3600. Operation-only technician with no order acknowledgment => assigned display can be known while whole-order wait stays unknown.
- Completed/invoiced own-truck orders with payment unrecorded and `updated_at=T` => excluded from active WIP; existing closeout unaffected.
- ETS order, or nominal native with same-tenant historical invoice tombstone => excluded; foreign-tenant invoice/assignment/quote cannot change local output.
- Fifty-one qualifying rows => complete summary51, first page50 with has_more true, final page1; multi-concern order counts once by primary category.
- Mechanic assigned by one valid operation => only authorized order visible, and no counts/timing leakage from another mechanic's order.

## Acceptance gates

- Current wait is derived from evidence specific to that wait; editing a description does not reset its age.
- Missing, invalid, contradictory or future timestamps never produce fabricated negative/zero durations or false overdue claims.
- No technician assignment inference from only a missing display name; operation assignments are respected.
- Draft/unsent, expired, decided and superseded quotes do not falsely count as customer approval delays.
- Completed/invoiced payment-only jobs, cancelled/deleted jobs and source-owned ETS history do not inflate active physical-work counts.
- More than 50 matching jobs produce complete counts, stable pagination and matching drill-down; overlapping concerns do not inflate the union total.
- Tenant joins and counts are scoped before aggregation; existing principal/order/schedule visibility applies to durations and summaries as well as row fields.
- Clicking a bottleneck only filters/opens an existing order. No new invoice, financial/status/source change, outreach or provider action occurs.
- Real component/runtime acceptance covers Day/Night, desktop and 390px mobile, keyboard navigation, loading/error/empty/unknown states, filtering and return from a selected job.
- Relevant focused tests, independent journey QA and targeted tenant/access review are required before release. Merge/deployment evidence is separate from source completion.

## Protected boundaries and current evidence

Financial records, invoice/payment/settlement/credit rows, selling prices, inventory, labor/time/attendance/break rows and order statuses remain unchanged. No production fixtures, collection calls, provider actions or statement sends. B4 importer `codex/db139-importer-money-held` remains held; existing collectors/configuration/watch exclusions are untouched.

Architecture finalized this contract through read-only source review and a documentation edit. Application implementation is now authorized under the defined boundaries. This contract is not evidence of tests, runtime acceptance or release. Mandatory local-runtime alignment is required before application implementation/local QA; fresh independent journey QA and targeted tenant/access review remain required.

## Density refinement — 2026-10-29

User prioritizes screen real estate before release. The existing operational surface must show jobs sooner: compact title/actions, fewer always-visible control rows, secondary filters and timing explanations behind accessible disclosure. Preserve complete counts, all filters, keyboard access, mobile target sizes, Unknown timing, closeout separation and existing drill-down. No API, authorization, clock or financial semantics change. Compare first visible row position at1280desktop and390mobile against the initial layout; record actual measurements and interaction evidence.
