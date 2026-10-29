# DB-145 / A2 — Shop Work aging and bottlenecks

Status: discovery and product direction, 2026-10-29. Architecture design/clock recommendation GO; exact implementation/API contract and completion gates remain pending.
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

## Contract work required before application editing

1. Define a single read-only eligibility scope for active work, supported holds, pending approval and pending review; preserve existing native/ETS ownership vetoes. Keep payment review/collection out of the physical-work denominator.
2. Define canonical quote revision selection, expiration behavior and operation-assignment precedence. Treat insufficient or conflicting evidence as unknown.
3. Define timestamp validity, timezone presentation, future timestamp handling, interval boundaries and permitted role scope. The frontend must not reconstruct restricted durations from masked dates.
4. Aggregate matching jobs before ordering/pagination. A job may have several concerns, so union totals must deduplicate IDs. Define whether each displayed count is shop-wide or search-filtered and keep rows, counts and drill-down in the same scope.
5. Preserve existing API compatibility. Prefer an additive read projection without migrations, history backfills, settings or new source writers. Record the exact request/response and shared fixtures before splitting implementation.
6. Inspect actual timestamp coverage read-only before promising stage-duration completeness. Source schema availability alone is not data coverage.

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

This turn is documentation and read-only source discovery. No services were started and no local or production browser acceptance is claimed. Mandatory local-runtime alignment remains required before application implementation/local QA. No code tests are required for these documentation-only edits; check links and diff integrity instead.
