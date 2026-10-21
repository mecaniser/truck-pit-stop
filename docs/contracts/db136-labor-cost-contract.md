# DB-136 / A1 — direct job contribution and technician cost contract

Status: **Architecture implementation-contract GO**, 2026-10-20. This authorizes the bounded implementation described here, not production release or fabricated cost rates. Backend & Integrations is accountable. Independent QA/Security, migration rehearsal, protected CI and actual owner-only runtime acceptance remain required.

The owner approved loaded hourly cost, activation on 2026-10-20 in the shop timezone, owner-only cost access and separate overhead. No actual technician rates were supplied. The preceding [discovery proposal](db136-labor-cost-policy-proposal.md) remains evidence of sparse coverage, not permission to populate missing financial history. ETS importer remains held.

## Surface, authority and compatibility

Add **Job Contribution** beside Sales in Shop Analytics, with **Technician Costs** opening its protected rate editor. Existing Sales, Internal Fleet, cash receipts and current-lines component reports retain their names, payloads, calculations and permissions. Hide the tab/control from other roles; backend authorization is mandatory independently of the UI.

Every route below requires an active, undeleted authenticated `GARAGE_OWNER`, an active exact actor tenant, and a valid IANA shop timezone. No garage-admin, mechanic, receptionist, customer, fleet or platform role inherits access. Do not accept tenant identity from a body/query. A cross-tenant or absent technician/order is 404, before exposing existence or policy details. Role denial is 403. A technician must be an undeleted same-tenant mechanic; an inactive historical mechanic can be read but cannot receive a new rate revision. No rates, derived costs, review decisions or sensitive fingerprints enter ordinary user/mechanic/report responses, shared frontend caches, URLs, application logs or public artifacts. Responses use `Cache-Control: private, no-store`; clear protected frontend state on sign-out, role/tenant change and permission failure. No cost values in error detail.

This feature writes only new A1 policy/review metadata. It never updates invoices, invoice snapshots, payments, settlements, credits, inventory, labor charges, time/attendance/break source rows, order statuses or existing report projections. No provider, payroll, notification or collector invocation. Every GET is bounded and uses one `REPEATABLE READ READ ONLY` snapshot; it creates no snapshot/review implicitly. A1 is management costing, not payroll reconciliation, wages owed, net profit or cash flow.

## Versioned technician cost policy

Add an append-only `technician_cost_policy_revisions` table, with UUID id, tenant, mechanic, positive integer version, nullable predecessor UUID, policy JSON, canonical request SHA256, idempotency key, approving owner UUID and UTC creation time. Unique `(tenant_id, mechanic_id, version)` and `(tenant_id, idempotency_key)`; same-tenant predecessor and actor/mechanic identity validation are mandatory. Version 1 has no predecessor; a later version must reference the current sole head and increment exactly once. No UPDATE/DELETE route, cascade deleting evidence, or direct edit of a previous revision. Prevent update/delete at the database layer. Add migration after rechecking current main's exact graph; preserve all existing migration bytes and use a separate no-op head merge if necessary.

Each revision contains the **whole replacement rate schedule** for this mechanic, not a delta. Fields are exactly `policy_version: 1`, `currency: "USD"`, `basis: "owner_declared_loaded_direct"`, `shop_timezone`, `activation_local_date: "2026-10-20"`, `activation_at` (UTC), `segments`, and `reason`. `activation_at` is the UTC instant of shop-local midnight on that date, resolved server-side; do not hardcode an offset or reinterpret old policies if the shop timezone changes. A timezone mismatch requires a deliberate replacement schedule preserving the original activation instant and a recorded reason; never silently move historical boundaries.

Each segment has exactly `effective_from` (UTC RFC3339), `effective_to` (UTC or null, exclusive), `hourly_cost` (decimal string), and `inclusions` (owner-supplied text). Loaded cost includes owner-declared direct compensation/employment burden only; no guessed tax/benefit/overtime/salary conversion and no separately reported shop overhead allocation. Positive rates from `0.0001` through `10000.0000` USD/hour, at most four fractional digits, no exponent, float, NaN or boolean. Zero/unpaid work is unsupported in V1 and remains unavailable unless a later explicit policy supports it. Each segment has positive duration, begins no earlier than activation, and is sorted/nonoverlapping; only the last may have null end. Gaps are allowed and mean unknown, never carry-forward by guess. Maximum 100 segments per revision; reason/inclusions each 1–500 characters after trimming. Reject duplicate JSON keys, unknown fields and a payload over 64 KiB. No billing/internal-rate fallback.

`GET /api/v1/reports/technician-costs?limit=50&cursor=...&q=...` lists same-tenant mechanics, including missing-rate state. Limit 1–100; search at most 100 characters, case-insensitive literal technician display name; signed keyset cursor binds actor tenant, filter and `(display_name, mechanic_id)`. Include only id, display name, active state, current revision id/version and protected schedule/coverage. No salary, bank, provider or other account fields. `GET /api/v1/reports/technician-costs/{mechanic_id}` returns the current revision and a bounded version list (newest first, same limit/cursor rules); no policy yields version 0 and empty segments, not a zero rate.

`POST /api/v1/reports/technician-costs/{mechanic_id}` requires header `Idempotency-Key` (UUID) and body `{expected_version, policy_version:1, currency:"USD", basis:"owner_declared_loaded_direct", segments:[...], reason}`. Server supplies activation/timezone and actor identity. `expected_version` is a strict integer >=0, never boolean. Lock the actor tenant row before head/idempotency validation and insertion; create first revision against 0. Atomic insert with immutable audit fields. Identical canonical body + same actor + key returns the original 200 result; new revision returns 201. Reuse with a different actor/body or stale expected version is 409, with generic refresh guidance. Roll back completely on validation/concurrency failure. Enforce source, interval and predecessor rules in transactional service and migration constraints/triggers where applicable. No external side effects. Rate changes may restate a current view after activation; prior review/export evidence is never overwritten.

### Friendly shop-local rate boundaries — approved contract delta

Owners enter ordinary date/time controls labeled with the **shop timezone**, never UTC, RFC3339 text, offsets or the browser's timezone. Keep the canonical UTC rate POST transport internal. Initial activation can use the server-returned activation instant directly. For other boundaries resolve server-side before submission:

`GET /api/v1/reports/technician-costs/time-boundaries?local=2026-10-20T09:00` optionally accepts `&fold=0` or `&fold=1`. This is a pure, bounded **one-boundary** conversion, with the same owner/tenant checks and no rate, audit, financial, session or configuration write. No actual cost policy or technician is required. Register this static path before `/{mechanic_id}`. Query fields are exactly `local` and optional `fold`; reject duplicate/unknown parameters. `local` must be a valid calendar datetime in exact `YYYY-MM-DDTHH:MM` form (16 characters, no offset or seconds); `fold` accepts literal `0` or `1` only. Invalid format is 422. Resolve using the authoritative valid tenant timezone and the existing `repair_order_schedule.resolve_wall`/round-trip candidate semantics. Invalid shop timezone returns 503, never a browser/default-zone fallback. The resulting instant is not approval to create a pre-activation rate: rate POST independently validates its activation/schedule bounds.

Normative success JSON:

```json
{"contract_version":1,"shop_timezone":"America/New_York","local":"2026-10-20T09:00","fold":null,"effective_at":"2026-10-20T13:00:00Z","activation_at":"2026-10-20T04:00:00Z"}
```

For an unambiguous instant normalize response `fold` to null. A repeated wall time without a fold returns 422 with existing `detail.code="schedule_time_ambiguous"`, `field="local"` and two `choices` containing strict folds 0 and 1. The frontend offers **First occurrence / Second occurrence**, then resolves again with the chosen fold; transport UTC/offset diagnostics are not owner input fields. A chosen ambiguous fold is echoed in success. A nonexistent spring-forward time returns 422 `schedule_time_nonexistent`; ask the owner to choose another local time. Fold1 on a non-repeated time returns 422 `schedule_fold_invalid`; date overflow uses `schedule_time_out_of_range`. Preserve the existing human-friendly messages. No local `Date` constructor, guessed offset, UTC text entry or silent DST adjustment. Stale responses must not replace a newer draft boundary; saving waits for every changed boundary to resolve successfully.

V1 rate history is **metadata only**: version, revision/predecessor IDs and approval timestamp. The existing mechanic detail route always returns the current full schedule/head; do not invent a `version` query or historical-policy fetch route. The head's dated segments are sufficient for the editor. Old review snapshots retain their bound evidence server-side; showing a prior schedule is a separate future read contract.

## Time eligibility, scope and coverage

The A1 scope is **not** the B1 invoice allowlist. An owner A1 review can classify an exact native order `real`, `test`, or `unknown`; unreviewed/new/source-drifted work defaults unknown. Unknown/test records have no included contribution; tests are excluded from summary money and retained only as an owner exclusion/review count. Native source alone does not establish real business activity. Known ETS RO, any same-tenant/order ETS invoice or historical-export hold vetoes native costing/contribution irrespective of classification. Keep ETS history separate and never inspect it as wage evidence.

Cost closed, nondeleted RO timer intervals only after same-tenant mechanic/order validation, with strictly increasing timezone-aware UTC endpoints and exact source technician attribution. General RO time stays RO-level. An operation is attributed only by its preserved `labor_id_snapshot` with valid same-tenant/order lineage; never by today's assignee, line descriptions or billed hours. Deleted operations can preserve an explicit historical snapshot, but unresolved lineage is held. Exclude sublet timers from ordinary direct-technician labor cost; conflicting attribution is review-required, not silently double-counted.

Split valid intervals at activation and rate boundaries. Pre-activation seconds remain unavailable. Compute unrounded Decimal `elapsed_microseconds / 3600000000 * hourly_cost`; round aggregate money to cents with ROUND_HALF_UP. Sum valid different-technician person-time; do not count one technician twice. For each candidate, inspect same-technician RO and misc sessions intersecting it, including open/deleted evidence, plus attendance and breaks and their audits. Overlap, open endpoint, invalid interval, source tombstone/identity discrepancy, incomplete attendance coverage or any intersecting break holds the whole affected source session; do not clip, divide or silently repair it. Open intervals are provisional and never finalized cost. Non-manual auto-stop and manager-corrected/deleted source history needs the explicit review below; it cannot become approved merely because it is closed. A deleted interval is not charged; its audit provenance remains a completeness exception until reviewed. Use interval union for attendance coverage, never sum overlapping attendance. Do not require a mechanic to remain currently assigned to historical work.

Miscellaneous work, idle attendance and breaks are separate **time** totals with no job allocation and no inferred paid/unpaid treatment. V1 does not claim their cost is zero or include them in direct contribution. Closed unrelated misc work is not job time. Report `recorded_seconds`, `costed_seconds`, `unrated_seconds`, `pre_activation_seconds`, `held_seconds`, `open_session_count`, `operation_attributed_seconds`, `general_ro_seconds` and stable reason codes. The first five closed-time buckets must reconcile without duplication; operation/general attribution is a separate axis. No sessions means unavailable, not zero. Overall status is unavailable if no eligible cost is known, partial if any missing/held/provisional/completeness issue exists, otherwise complete for the **reviewed recorded scope**. `not_applicable` is permitted only with a current explicit owner no-internal-labor assertion; it is never inferred from absent timers or zero billed hours.

### Separate shop-time window — bounded evidence clarification

Separate time in a job detail is scoped to **`selected_job_timer_window`**, not a whole attendance day. For each technician with valid, retained, closed timers on the selected job, define one half-open window from that technician's earliest selected timer start to latest selected closed timer end. Return these exact `scope_windows` with mechanic identity and UTC start/end. An open timer does not supply an invented closed endpoint. If there are no valid closed timers, no window exists: return unavailable with null time amounts, not an inferred day of idle. If additional open/invalid selected time exists, disclose partial scope and do not claim coverage of that time.

Within each window, clip **every** relevant attendance, break, miscellaneous and all-job busy interval to the same bounds before union/difference. Load all same-tenant/mechanic peer job/misc/break evidence intersecting that window. `idle_seconds = duration(union(clipped attendance) minus union(clipped all-job timers + misc timers + breaks))`. Do not subtract only this job's timers or load peer occupancy for a narrow job window while retaining an entire attendance interval. Misc/break durations are their own clipped unions, not sums of duplicate intervals. Count once within a technician; add person-seconds across different technicians. These totals are operational observations, not wages, cost allocation or absence-of-work proof. Use a bounded complete set of interval evidence; missing/malformed/open evidence affecting a window makes its idle amount unknown, never fabricated zero. Hard load-limit failure is 413, not a partial numeric total.

Detail `separate_shop_time` is exactly `{scope:"selected_job_timer_window", scope_windows:[{mechanic_id,started_at,ended_at}], time_status:"complete"|"partial"|"unavailable", misc_seconds:integer|null, idle_seconds:integer|null, break_seconds:integer|null, cost_status:"unavailable"}`. Complete means complete observed interval coverage for these windows only, never a full shop day. If no scope exists all three amounts are null. A partial result can expose known misc/break subtotals with partial labeling, but idle is null for incomplete occupancy evidence. UI label **Shop time during this job's timer window**, with visible local start/end and partial/unavailable state; never **Daily idle** or **Whole-day shop time**. No direct-job-cost calculation changes follow from this clarification.

## A1 review metadata and source snapshots

Add append-only `job_cost_reviews`: id, tenant/order, version/predecessor, business classification, owner UUID, reason, canonical source fingerprint, policy-head map digest, calculation version, time-capture assertion (`complete`, `incomplete`, `no_internal_labor`), reviewed exception IDs, immutable cost/revenue/coverage snapshot and created_at. Unique tenant/order/version, tenant/idempotency key and strict sole-head successor validation; database update/delete guards. No source foreign key uses destructive cascade. A review can acknowledge a legitimate auto-stop, correction or removed mistaken timer; it cannot waive active overlap, missing rate, wrong tenant, ETS ownership, missing attendance, break conflict, ambiguous financial provenance or return/credit evidence. `complete` asserts all direct labor for that job was captured; it is not payroll approval. Require a nonempty reason and show these assertions plainly in the owner review UI.

`GET /api/v1/reports/job-contribution/{order_id}` returns the current derived view, latest review status and `source_fingerprint`, never mutating. `POST` to the same path with `/review` suffix requires UUID Idempotency-Key and `{expected_version, source_fingerprint, policy_heads_digest, business_classification, time_capture, reviewed_exception_ids, reason}`. Bound exception IDs to 500 UUIDs and reason to 500 characters. Under the tenant lock reload/recompute source, validate policy heads and expected version, then append the exact server-calculated snapshot; client supplies no amounts/rates/actor. Drift yields 409; unsupported completeness yields 422. Identical actor/body/key replays the original response; conflicting use is 409. Snapshot evidence covers invoice/revision/charge adjustments, labor/parts, timers including deleted/open rows, relevant attendance/break/audits, rates, source flags and relevant credit/return/refund relations, in deterministic id order with every material value/update/tombstone marker. A later change makes the previous review stale; the current view shows held/incomplete until refreshed, while old evidence remains intact. GET never falls back to an older approval when the head is stale. Version all canonical serialization/calculation rules; exclude free-form private time notes and provider secrets from responses/fingerprint preimages exposed to clients.

`reviewed_exception_ids` contains **MechanicTimeSession UUIDs**, not audit UUIDs. Each must identify an exact same-tenant session of this order carrying a currently reviewable auto-stop/correction/deletion exception. This includes an **attendance or break correction affecting that session**, not only an edit audit on the timer itself. Its relevant current audit state is bound into the source fingerprint; acknowledging a session acknowledges that observed exception state only. Unknown/foreign/unrelated IDs, duplicate IDs and sessions without a reviewable exception are 422 (without exposing foreign existence). It cannot waive an open interval, overlap, missing rate, attendance gap, break conflict or other non-waivable hold. The owner UI selects session-based exceptions using current detail rows and readable provenance; it never asks owners to paste raw UUIDs or audit hashes.

### Attendance/break audit relevance and acknowledgment — clarification

For each job timer, load attendance/break audit provenance only through exact same-tenant and same-mechanic source identities. A correction is relevant when its linked attendance/break source interval intersects that timer in its **current or material before/after state**. Include relevant deleted source rows and snapshots so moving/deleting an interval cannot erase its provenance. Compare half-open intervals; touching endpoints alone do not intersect. A break audit is scoped by the break's interval, not every break belonging to an otherwise relevant day/attendance session. An old unrelated edit, audit creation timestamp, current mechanic identity alone or common calendar date is not sufficient relevance. Do not load all lifetime mechanic audits and convert their mere presence into a job hold. All relevance joins and snapshot identities retain the tenant/mechanic boundary; malformed current/snapshot evidence on an otherwise relevant linked source is a hold, not permission to skip it. Bounded source loading must inspect the relevant before/after intervals as well as current intervals.

`attendance_correction_review_required` and the equivalent break-correction provenance exception are acknowledged through each affected **timer session UUID**. The review service derives the current relevant audit IDs/state server-side, validates that this is a reviewable exception, binds them into that timer's source fingerprint, then checks every non-waivable current condition again. A valid manual job timer with full valid current attendance coverage may therefore acknowledge the attendance correction; it need not invent a timer edit audit to qualify. A new relevant audit or changed linked source after acknowledgment makes the review stale. No attendance/break/timer source row is edited by this acknowledgment.

A removed mistaken source timer/attendance/break may have its **documented historical correction** acknowledged, without charging the deleted interval, only when the surviving current evidence independently supports valid coverage, timing and identity. A deletion is never automatically proof that a break was unpaid/nonexistent or that missing work cost zero. Deleted/malformed audit evidence itself, unresolved source identity, an open/invalid current job interval, active same-person overlap, missing rate/pre-activation time, current attendance gap or current break intersection cannot be waived by any review checkbox. Those hold codes remain present and final contribution stays null. A reviewable correction and a non-waivable hold may coexist; acknowledging the former does not clear the latter.

## Revenue, discounts, returns and combined contribution

V1 basis is `issued_native_net_direct_v1`, a management issued-revenue basis, not payment-period cash. Choose the sole same-tenant, nondeleted, noninternal, nonvoided finalized native Invoice (SENT/OVERDUE/PAID) for the exact order, with active same-tenant authoritative bill-to. Reject draft/ambiguous multiple heads, unresolved supersession/customer lineage and ETS/hold. A correctly linked single replacement invoice may be shown, but revision chains with unresolved economics remain held rather than adding old and new amounts. Internal/warranty work can show direct cost; do not invent external revenue or margin. An unissued order may show cost and separately labeled provisional current charges, never final contribution.

Require immutable `line_items_snapshot.version == 1` with bounded, valid nonnegative decimal labor totals and parts totals. Let `G` be their summed charged amount. Invoice `subtotal` is already net of RO discounts at issuance: **do not subtract current RO discounts again**. Require `0 <= subtotal <= G`, invoice `discount_amount == 0`, and `total_amount == subtotal + shop_supplies_amount + service_fee_amount + tax_amount` to the cent. Otherwise revenue basis is held. `D = G - subtotal` is the issued aggregate discount. Allocate D proportionally to nonzero snapshot line gross amounts for management display using integer cents, floor shares, then distribute leftover cents by descending fractional remainder, breaking ties by `(kind, snapshot_index)` with labor before parts. This is a labeled management allocation, not a reconstruction of historical labor-only discount intent; line nets sum exactly to subtotal. Zero G supports zero subtotal only. Fees, supplies and tax are shown separately, excluded from direct revenue/cost contribution.

Existing snapshot v1 lacks labor/parts UUIDs, operation type, discount split and cost provenance. Therefore do not map its expense by a name/array position or borrow current inventory unit cost. For V1 complete combined cost, require current same-tenant live labor/parts financial line multisets to reconcile exactly to snapshot financial facts with unique structural identity; ambiguous duplicates, deleted/changed/missing lines or inability to identify sublet expense make combined contribution unavailable. Preserve recorded `PartsUsage.unit_cost * quantity`; missing unit_cost is unknown. Recorded zero remains recorded zero, with provenance shown, not a fallback. Sublet `vendor_cost` is whole-line expense, once only. Cost completeness includes every relevant part/sublet and reviewed labor; do not use selling rate as expense.

Read relevant same-tenant invoice adjustments, credit entries including origin/target lineage, refunds/returns and overpayment/dispute evidence without provider calls. Any unresolved return, refunded/reversed economic event, historical-credit source ambiguity or charge adjustment not proven compatible with this basis holds **combined contribution**, without fabricating an allocated revenue reduction. A completed payment or ordinary credit application is funding, not extra revenue or discount; it must not be added/subtracted again. V1 may conservatively hold all invoices with charge-adjustment/return/refund evidence; expose `revenue_adjustment_review_required`. Do not inspect only undeleted children or silently omit inconvenient evidence. Current settlement principal does not replace issued revenue.

`direct_contribution = net_direct_revenue - known_direct_technician_cost - parts_expense - sublet_expense` only when business scope is real, issued-revenue identity/basis is valid, time coverage review is current/complete (or valid no-internal-labor), all cost components complete and no holds exist. Otherwise final contribution/margin is null; known components remain separately labeled and never aggregated into a purported complete profit. `margin_pct` is null when net_direct_revenue <=0; otherwise Decimal contribution / net revenue *100, serialized to two decimals. No claim of net profit, payroll actuals or full overhead absorption.

## Report, pagination and response contract

`GET /api/v1/reports/job-contribution?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=50&cursor=...&q=...&scope=all` uses inclusive shop-local dates converted to a half-open UTC window; default current shop month, maximum 366 days. Anchor orders by work_completed_at when present, otherwise created_at, labeled `date_basis`; this is job-cohort selection, not an issued-revenue-period or historical-as-of balance claim. Include zero-charge/internal/in-progress rows; do not reuse the old positive-total scatter filter. `scope` is all/real/review/test/history; default all shows review rows and history with null included monetary totals. Search is bounded literal order number or customer display name, not hidden notes. Limit 1–100; signed keyset cursor bound to tenant, range, scope, search and `(cohort_at, order_id)` descending. Invalid/forged/cross-tenant cursor is 422. Summary covers the whole filtered cohort, not just its page; explicitly count excluded/history/review rows. Cap cohort at 2,000 orders, all relevant sessions/attendance/breaks at 20,000 each, audits at 50,000 and financial child rows at 20,000 each per request; return 413 on limit+1 rather than silently truncate. Policy history per mechanic is capped at 1,000 revisions; excessive load is 413. All supporting overlapping intervals must be bounded too, not just selected order timers.

Response: `{contract_version:1, calculation_version:"db136-v1", generated_at, shop_timezone, activation_local_date, activation_at, from, to, next_cursor, summary, rows}`. Summary has row counts by real/test/unknown/history and complete/partial/unavailable, reviewed_complete_contribution (nullable when none), complete_row_count, incomplete_row_count, known_recorded_direct_cost, cost coverage totals and `is_complete` for included real cohort. Never call complete-row contribution subtotal the whole-shop profit. Each row has `order_id/order_number`, owner-only customer label, type, status, cohort_at/date_basis, business_classification, review_status (none/current/stale), `source_owner`, `revenue_basis/status/hold_reasons`, net_direct_revenue (null if untrusted), separate taxes/fees/supplies, known_direct_cost and all coverage fields, parts/sublet expense coverage, final direct_contribution/margin_pct (nullable), review version and drilldown. All money is fixed decimal strings; all durations are nonnegative integer seconds (round down display only; costing uses microseconds). Detail adds bounded source IDs/attribution/reason codes, rate segment bases and current review fingerprint. Never return provider identifiers, private audit notes, bank data or another tenant's identities. Unknown/test/history rows expose no included contribution; zero values must not imply missing facts are zero expense.

Other errors: strict request/body/date/decimal/schema validation 422; owner authentication failure 401/403; missing/external object 404; stale/concurrent metadata 409; row/size bounds 413; invalid tenant timezone/unsupported safe source loading 503. No silent fallback, side effects or partial writes on failures.

### Exact V1 JSON shape for frontend/backend handoff

The following group names are normative; `labor` groups the coverage fields described above, and `revenue`/`parts`/`sublet` group their component fields. All UUID/date/money examples below are synthetic. The report envelope is exactly:

```json
{
  "contract_version": 1,
  "calculation_version": "db136-v1",
  "generated_at": "2026-10-20T18:00:00Z",
  "shop_timezone": "America/New_York",
  "activation_local_date": "2026-10-20",
  "activation_at": "2026-10-20T04:00:00Z",
  "from": "2026-10-20",
  "to": "2026-10-31",
  "next_cursor": null,
  "summary": {
    "order_count": 1,
    "real_count": 1,
    "test_count": 0,
    "unknown_count": 0,
    "history_count": 0,
    "complete_row_count": 1,
    "partial_row_count": 0,
    "unavailable_row_count": 0,
    "incomplete_row_count": 0,
    "reviewed_complete_contribution": "230.00",
    "known_recorded_direct_cost": "120.00",
    "recorded_seconds": 10800,
    "costed_seconds": 10800,
    "unrated_seconds": 0,
    "pre_activation_seconds": 0,
    "held_seconds": 0,
    "open_session_count": 0,
    "is_complete": true
  },
  "rows": [
    {
      "order_id": "00000000-0000-4000-8000-000000000001",
      "order_number": "SYNTHETIC-001",
      "customer_name": "Synthetic fixture",
      "type": "repair",
      "status": "invoiced",
      "cohort_at": "2026-10-20T17:00:00Z",
      "date_basis": "work_completed_at",
      "business_classification": "real",
      "source_owner": "native",
      "review_status": "current",
      "review_version": 1,
      "cost_status": "complete",
      "revenue": {
        "basis": "issued_native_net_direct_v1",
        "status": "complete",
        "net_direct_revenue": "500.00",
        "issued_discount": "0.00",
        "tax": "0.00",
        "fees": "0.00",
        "supplies": "0.00",
        "hold_reasons": []
      },
      "labor": {
        "status": "complete",
        "known_cost": "120.00",
        "recorded_seconds": 10800,
        "costed_seconds": 10800,
        "unrated_seconds": 0,
        "pre_activation_seconds": 0,
        "held_seconds": 0,
        "open_session_count": 0,
        "operation_attributed_seconds": 0,
        "general_ro_seconds": 10800,
        "hold_reasons": []
      },
      "parts": {"status": "complete", "known_cost": "150.00", "line_count": 1, "missing_cost_line_count": 0},
      "sublet": {"status": "not_applicable", "known_cost": "0.00", "line_count": 0, "missing_cost_line_count": 0},
      "direct_contribution": "230.00",
      "margin_pct": "46.00",
      "hold_reasons": [],
      "drilldown": "/dashboard/repair-orders?selected=00000000-0000-4000-8000-000000000001"
    }
  ]
}
```

Enums: type `repair|pm|internal|warranty`; source_owner `native|ets_history|review_required`; business_classification `real|test|unknown`; review_status `none|current|stale`; cost/component status `complete|partial|unavailable|not_applicable`. Revenue additionally permits `provisional`. Hold reasons are bounded machine-readable string codes, no private prose. `known_cost` is a known subtotal, not a claimed complete expense. Unknown/test/history rows do not contribute any money to summary; summary cost totals include real scope only. If no real rows exist, `is_complete=false`, contribution null and included counts/totals zero with scope counts explaining why. If real rows have no complete contribution, `reviewed_complete_contribution=null`. Incomplete_row_count counts real rows lacking final contribution, not intentionally excluded tests/history. Absent revenue fields are null (never guessed zero). Detail response is `{contract_version, calculation_version, generated_at, row, source_fingerprint, policy_heads_digest, review, sessions, policy_segments, discount_allocation, separate_shop_time}`. `row` is the same shape; session entries use `{id, mechanic_id, mechanic_name, labor_id_snapshot, started_at, ended_at, recorded_seconds, costed_seconds, known_cost, hold_reasons}`. Rate segments use the protected policy shape plus mechanic/policy revision IDs. Discount allocations use `{kind, snapshot_index, gross, allocated_discount, net}`. Separate shop time uses the exact selected-job-window shape defined above, including scope/windows, time_status and nullable amounts; it is never included in job expense. Detail lists obey the same hard source bounds; review fields contain exact metadata and monetary snapshot but never private raw source notes.

Rate POST body example: `{"expected_version":0,"policy_version":1,"currency":"USD","basis":"owner_declared_loaded_direct","segments":[{"effective_from":"2026-10-20T04:00:00Z","effective_to":null,"hourly_cost":"40.0000","inclusions":"Synthetic direct pay and employment burden"}],"reason":"Synthetic initial policy"}`. The successful POST/detail response is `{mechanic_id, mechanic_name, is_active, version, revision_id, supersedes_id, policy, approved_by_user_id, approved_at}`; `policy` is the complete server-bound policy object above. A missing policy has version0, null revision/predecessor/approval fields, `policy:null`. List response is `{contract_version:1, generated_at, next_cursor, items:[same mechanic head shape]}`. Rate history detail adds `history:[{version,revision_id,supersedes_id,approved_at}]` and `next_cursor`; V1 exposes history metadata only and has no prior-policy selection/fetch endpoint.

Review POST body example: `{"expected_version":0,"source_fingerprint":"<64-lowercase-hex>","policy_heads_digest":"<64-lowercase-hex>","business_classification":"real","time_capture":"complete","reviewed_exception_ids":[],"reason":"All direct work recorded for synthetic job"}`. Success is `{contract_version:1, review_id, order_id, version, supersedes_id, business_classification, time_capture, source_fingerprint, policy_heads_digest, approved_at, row}`. No config/report/review route accepts monetary outcome fields. These examples are fixtures, never production rate defaults.

## Required fixtures and release evidence

Prove role/tenant denial across list/detail/rates/review/pagination/cache; no inherited admin cost access. Rates: activation midnight, DST, rate gap/boundary, four-decimal precision, zero/float/boolean rejection, duplicate JSON, overlapping interval, stale version, identical replay, conflicting replay and concurrent writers. Time: multiple technicians, same-person RO/misc/open/deleted overlaps, no timers, pre-activation split, partial attendance, break conflict, corrected/auto-stopped review, operation snapshot absent/deleted/foreign, no assignment inference and no sublet double cost. Review drift must invalidate current cost completeness while retaining immutable prior evidence. No guessed rates in synthetic/prod defaults.

Revenue: invoice subtotal already discounted, deterministic cent allocation/remainder, zero gross, negative/malformed snapshot, superseded/void/draft/multiple head, altered live line, missing/recorded-zero parts cost, ambiguous duplicate expense mapping, sublet whole-line cost, return/refund/credit contamination, ordinary applied credit not counted twice, ETS/hold, internal/warranty and zero-charge jobs. List summary must match all filtered pages; unsupported rows retain null final contribution. Same request cannot cross tenant/shop data through malformed source children. Include a real PostgreSQL immutable-table/concurrency and read-only GET rehearsal.

Independent QA/Security review the exact source/schema candidate. Protected CI, normal migration and Web/Worker readiness, fixed-cohort financial/time/stock retention, and actual signed-in owner Light/Night desktop/mobile report, missing-rate/editor, validation/cancel and permission-negative journeys precede Done. Use local synthetic rate/review fixtures; production acceptance is existing-record reads/cancelled drafts only until the owner deliberately supplies actual cost configuration. Do not create real invoices, service/time/financial rows, provider actions or collector changes for QA. Application rollback disables/removes the new route/UI; additive evidence remains, and downgrade must refuse deleting nonempty approved policy/review tables.
