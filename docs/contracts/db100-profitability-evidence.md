# DB-100: truthful cost and margin evidence

- Version: 1.0.0
- Status: Architecture correction contract; implementation and runtime acceptance pending
- Accountable owner: Backend & Integrations
- Contract owner: Architecture & API Contracts
- Intake: DB-101 ETS capability audit; independent from DB-098/DB-099
- Lane: Standard product, existing financial read permissions; independent QA and focused financial-data review. Escalate if implementation changes access, settlement accounting or financial mutations.
- Source inspected: `91045a6`, 2026-10-12

## 1. Reproduced source defect

`services/pricing.py:58-89` defines the misleadingly named RO fields:

- `total_parts_cost` is the sum of customer-facing `PartsUsage.total_price`.
- `total_labor_cost` is the sum of customer-facing `Labor.total_cost`.
- `total_cost` is their net customer charge after labor/order discounts.

`api/v1/endpoints/reports.py:1171-1179` subtracts those retail totals as expense
and clamps the result to 0..100. `:1233-1248` repeats it for account margins.
An undiscounted $100 labor + $200 parts order consequently shows 0%, regardless
of its actual costs. A discounted order's negative result is hidden. The scatter
also uses a fixed nonnegative axis (`frontend/src/features/analytics/ChartKit.tsx:106`).

Available actual expense evidence is narrower:

- `PartsUsage.unit_cost * quantity` is the cost-at-use snapshot; null means
  unavailable, and an explicitly stored zero is valid data (`models/inventory.py:118`).
- `Labor.vendor_cost` is the whole sublet line's vendor expense. Do not multiply
  by labor hours. Sublet creation stores charge-to-customer separately in
  `Labor.total_cost` (`endpoints/repair_orders.py:3941-3953`).
- Ordinary labor has billed hours/rate, not wage, burden or actual labor-cost
  snapshots (`models/labor.py:27-42`; `models/user.py:64-67`). Attendance time does
  not establish a wage rate. Labor expense and whole-job/account profit are unknown.

The existing parts report uses real parts costs (`reports.py:773-788`); reporting
is present. This item corrects unsupported whole-job/account claims rather than
introducing a second reporting system.

## 2. Minimal response correction

Preserve routes, existing permission checks, tenant range resolution, row selection,
`ros`/`accounts` envelopes, row ordering and existing non-margin fields for:

- `GET /reports/analytics/profitability`
- `GET /reports/analytics/accounts`

Keep the `marginPct` key but explicitly widen its schema/type to `number | null`.
Set it to null because the original whole-job/account margin has no supported
expense basis. It is deprecated; do not repurpose it as parts-only margin or
retain the old false value for compatibility. Update all in-repository consumers
in the same change. Existing readers must tolerate the widened nullable field;
this is a documented semantic correction, not a claim of unchanged numeric behavior.

Add `cost_basis: "current_lines_before_order_discounts"` and
`labor_cost_status: "unavailable"` at response level. On each `ros` item add
`repair_order_id` and `order_number` (existing RO label, approved additive usability field) plus `parts_contribution` and `sublet_contribution`:

```json
{
  "revenue": "200.00",
  "known_cost": "120.00",
  "line_count": 1,
  "missing_cost_line_count": 0,
  "status": "complete",
  "contribution": "80.00",
  "margin_pct": "40.00"
}
```

Each object has exactly the same shape. Decimal amounts and percentages are
strings; `contribution` and `margin_pct` are nullable. Status is
`complete | partial | unavailable | not_applicable`:

- No lines: `not_applicable`, zero revenue/known_cost/count, null contribution/margin.
- Lines, all relevant cost snapshots known: `complete`. Contribution is revenue
  minus expense, including negative values. Margin is contribution / revenue *
  100 only for positive revenue; zero/negative revenue gives null percentage,
  while the supported contribution amount remains visible.
- Mixed known/unknown cost snapshots: `partial`; expose known_cost and missing
  count, but null contribution/margin. Do not calculate profit over only the
  known-cost subset while showing revenue from all lines.
- All cost snapshots unknown: `unavailable`; null contribution/margin.

Use `Decimal` for aggregation and round only serialized totals to cents and
percentages to two decimals. A null field is never coerced through `Number(null)`,
`float(value or 0)`, SQL coalesce or equivalent into an apparently known zero.
No clamping of negative contributions or percentages.

For `/analytics/accounts`, only null the unsupported margin and add the response
coverage/basis fields in this minimal slice. Enforce tenant-equality and deleted-related-row guards on invoice/RO/customer joins. Preserve the valid invoice revenue/Pareto behavior;
do not invent account-level component expense allocations.

## 3. Supported basis and exclusions

Parts revenue is `sum(PartsUsage.total_price)`, retaining any discount already
embodied in that line. Parts expense is `sum(unit_cost * quantity)` for all
known-cost parts. Sublet revenue is `sum(Labor.total_cost)` for
`line_type == SUBLET`, and expense is `sum(vendor_cost)` for those lines.

These are **current recorded line contributions before order-level discounts**;
sublet contribution is also before any aggregate labor discount. Display those
qualifiers with the metric. Do not proportionally allocate order/labor discounts,
fees, sales tax, payment/processor fees, returns or customer credits to components
without a separate accounting contract. No payment allocation or collection-time
profit recognition is implied. Existing `subtotal` may include order discounts
and therefore must not be the denominator for a component margin.

Do not call these numbers net profit or whole-job gross profit. They exclude
ordinary labor expense and overhead. Do not use today's inventory cost when a
historical unit_cost snapshot is missing. Do not claim an immutable invoice-cost
snapshot: this slice reads current recorded RO line data. Preserve existing
report date/row selection; changing recognition dates, canceled-order treatment
or payment semantics is a separate concern, not a hidden side effect.

Aggregate through explicit tenant-equality joins from each returned RO to its
PartsUsage/Labor. Scope every related row independently and filter deleted
children. Foreign or orphaned child data cannot alter amounts, counts or labels.
No per-row provider calls, writes, backfill, wage capture, schema migration or
current-inventory mutations.

## 4. UI behavior

Rename the current whole-job "Profitability" presentation to a precise component
label such as "Parts and sublet contribution". Use supported component amounts
and margins from the new fields; a small table/cards may be clearer than forcing
the old bubble chart to plot two different bases. Show the full-RO margin as
unavailable only where it is useful, with the reason "Labor costs not recorded".

Unknown, partial, zero and negative must be distinct. Zero is displayed as zero;
partial costs show coverage rather than profit; losses remain visible. A chart,
if retained, derives an axis including the actual negative minimum/positive
maximum and only plots finite, supported margins. It must summarize omitted
unknown-cost rows rather than presenting them as absent work. Never keep the
existing 0..60 axis for signed data.

The new frontend must handle both absent coverage fields (older backend =>
"Cost breakdown unavailable") and null margins, without falling back to legacy
marginPct. Account revenue/Pareto remains useful independently of unavailable
margin. Keep errors separate from legitimate empty/unknown states.

## 5. Verification and rollout

Focused backend fixtures: $200 parts revenue/$120 cost => $80/40%; zero known
cost => valid 100%; $100 revenue/$120 cost => -$20/-20%; zero-price work with
$20 cost => -$20/null margin; missing and mixed costs => null contribution/margin;
sublet $300 charge/$220 vendor cost => $80/26.67%; ordinary labor expense unknown;
no component lines => not_applicable; fractional quantities and rounding;
line discount retained while order/labor discounts remain unallocated; foreign,
deleted and malformed-tenant children excluded. The original $100 labor + $200
parts example must no longer claim whole-job 0% margin.

Frontend fixtures cover absent new fields, null/partial costs, zero, negative and
positive amounts, component labels/basis text, account revenue retained, no
misleading empty state, and mobile readability. Relevant existing regression
paths are `backend/tests/test_reports_source_tenant_defense.py`,
`backend/tests/test_report_timezone_boundaries.py`, and
`frontend/src/features/garage/__tests__/GarageAnalyticsRange.test.tsx`.

Ship backend and frontend together through the focused PR; nullable legacy
fields are intentional. Independent QA checks the calculation fixtures and
affected signed-in analytics route. No production data mutation is required.
Rollback is source deployment rollback, with the caveat that old code restores
the known inaccurate display. Local API/runtime remains blocked until approved
worktree configuration is available and dieselbridge-local-runtime verifies it.
