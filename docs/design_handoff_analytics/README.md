# Handoff: Shop Analytics — Recharts Enhancement

## What this is (read this first)
**This is a design reference only. No code in the real `truck-pit-stop` repo has been changed.** This handoff describes how to *enhance* the existing `frontend/src/features/garage/GarageAnalyticsPage.tsx` with real charts (it currently has none — see "What's there today" below). Everything here uses **mock/illustrative data**; wiring to the real `/dashboard/stats` API is implementation work for whoever builds this.

## What's there today (grounded in the real repo)
`GarageAnalyticsPage.tsx` already exists with two tabs — **Overview** and **Internal Fleet Costs** — pulling from `GET /dashboard/stats`. Today it renders:
- 4 KPI cards (This Month Revenue, Active Orders, Total Customers, Conversion Rate) — `bg-gray-800/50 border border-gray-700/50 rounded-lg p-6` cards, lucide icons in tinted `/10` boxes.
- An "Order Pipeline" section — plain CSS **progress bars** (no chart) showing count per status.
- A "Key Insights" list — plain text/number rows, no visualization.
- "Technician Workload" — plain progress bars per mechanic (assigned vs. in-progress).
- "Internal Fleet Costs" tab — 3 cost KPI boxes (today/week/month) + `<InternalInvoiceList />`.

**The gap this closes:** none of the above are real charts — everything is text and CSS progress bars. This handoff replaces/augments those with actual interactive Recharts visualizations and adds a third tab for account-level analytics.

## Fidelity
High-fidelity for layout, chart choice, and interaction. Colors/tokens are pulled directly from the real `tailwind.config.js` and `DashboardLayout.tsx` — see Design Tokens. Data is **illustrative**; the shape it's bound to is documented below as the real contract to build against.

---

## Recommended library: Recharts
The app doesn't use a chart library today (the analytics doc in the repo explicitly notes hand-rolled SVG "to keep bundle size small"). Recharts is the right upgrade because:
- It's React-native (JSX components), matching the app's existing React + TypeScript + Vite stack — no new build tooling needed, just `npm install recharts`.
- Composable — the revenue/margin combo chart, bubble scatter, and Pareto chart all need dual-axis + mixed series, which Recharts handles by nesting `<Bar>`/`<Line>`/`<Scatter>` inside one `<ComposedChart>`/`<ScatterChart>`.
- Native `<FunnelChart>` for the quote→approval funnel — no custom HTML needed.
- Easy to theme via props/CSS to match the app's dark BlueNoir palette and configurable accent color.

**One implementation note found while prototyping:** Recharts animates chart geometry in on mount (default `isAnimationActive`). This is fine for normal use, but caused charts to intermittently render blank in automated screenshot/export contexts because the animation was caught pre-paint. **Set `isAnimationActive={false}` on every series** (`<Bar>`, `<Line>`, `<Area>`, `<Scatter>`, `<Funnel>`) — charts render in final state immediately, which is also better for print/PDF export and has no real UX cost since the underlying data isn't itself animating.

---

## Screens / structure

### Tab 1 — Overview (enhances the existing tab)
Keep the 4 existing KPI cards as-is. Then, in place of the current plain-text/progress-bar sections, add:
1. **Revenue & Profit Trend** — `ComposedChart`: stacked bars (parts revenue + labor revenue) + a margin % line on a secondary right-hand axis. Replaces nothing currently there — net-new, and probably the single highest-value addition since there is currently no revenue chart at all.
2. **Labor vs. Parts Profitability** — `ScatterChart` with `ZAxis` for bubble size (hours). X = RO subtotal, Y = margin %, colored by RO type/category. Surfaces large, underpriced jobs.
3. **Quote → Approval Funnel** — native `<FunnelChart>` (Sent → Viewed → Approved → Invoiced). Replaces nothing existing (there's no funnel visualization today) but directly reflects the same `orders_by_status` data already fetched.
4. **Technician Productivity** — horizontal ranked `<BarChart>` (billed vs. available hours, color-flagged by efficiency threshold). **Replaces** the existing "Technician Workload" progress-bar section with a real chart driven by the same `mechanic_workload` data already in the API response.

Each chart card has an **"Act on it"** callout — a short, concrete recommendation derived from the chart's current data (not decorative; regenerate this text from real thresholds, e.g. margin dips, efficiency cutoffs).

### Tab 2 — Internal Fleet Costs (enhances the existing tab)
Keep the existing 3 cost KPI boxes and `<InternalInvoiceList />` as-is. Add below them:
1. **Cost per Truck (YTD)** — ranked horizontal bar, top 10 trucks by total maintenance spend.
2. **Fleet Cost per Mile** — 12-month area/line trend, whole fleet. Rising trend = aging fleet signal.
3. **Preventive vs. Unplanned Cost** — stacked bar over time; a rising "unplanned" share is a leading indicator that the PM program is falling behind.
4. **Parts Markup & Turnover** — quadrant scatter (turnover × markup), shop-wide parts portfolio. Median reference lines split the field into 4 quadrants; color-code winners (green) vs. dead stock (red) vs. mixed (amber).

### Tab 3 — Customer Accounts (**new tab**, not in the real app yet)
1. **Revenue by Account** — Pareto chart: `ComposedChart` with revenue bars + a cumulative-% line on a secondary axis. Answers "which accounts are my real 80/20."
2. **Account Detail table** — ranked list: account name, revenue, margin (color-coded pill).

---

## Design tokens (pulled directly from the real repo)

**Tailwind config extensions** (`frontend/tailwind.config.js`) — reuse as-is, do not reinvent:
```js
colors: {
  gold:     { 400:'#D4A84B', 500:'#B8860B', 600:'#9A7209', 700:'#7C5C07' },
  noir:     { 900:'#0a0a0f', 800:'#12121a', 700:'#1a1a24' },
  blueNoir: { 900:'#0a0f14', 800:'#101820', 700:'#182028' },
  accent: {
    cyan:    { 400:'#22D3EE', 500:'#06B6D4', 600:'#0891B2' },
    indigo:  { 400:'#818CF8', 500:'#6366F1', 600:'#4F46E5' },
    emerald: { 400:'#34D399', 500:'#10B981', 600:'#059669' },
    rose:    { 400:'#FB7185', 500:'#F43F5E', 600:'#E11D48' },
    amber:   { 400:'#FBBF24', 500:'#F59E0B', 600:'#D97706' },
  },
}
```
- **Page background:** `bg-blueNoir-900` (garage/staff routes — this is what `DashboardLayout.tsx` already applies via `isGarageUser`).
- **Card:** `bg-gray-800/50 border border-gray-700/50 rounded-lg p-6` — exact class string used throughout `GarageAnalyticsPage.tsx` today; keep using it for consistency.
- **Accent color:** the app already has a live `ThemeContext` with `accentColors` (5 options, default cyan) used for active nav links etc. — the chart set should read the *same* context and use `accentColors[500]` for primary series/bars, not a hardcoded color, so charts stay in sync with a user's chosen accent.
- **Chart-specific colors** (not in the app's theme, additive): parts revenue `#3b82f6` (blue-500), margin line `#34d399` (emerald-400), cost/danger `#f87171` (red-400), Pareto cumulative line `#a78bfa` (violet-400).
- **Type:** system sans stack (`ui-sans-serif, system-ui, -apple-system, sans-serif` per `index.css` — no custom webfont).
- **Icons:** the real app uses `lucide-react`. The prototype hand-draws equivalent stroke icons (same visual language: 2px stroke, 24×24 viewBox) — swap for the actual `lucide-react` imports (`TrendingUp`, `DollarSign`, `Wrench`, `Clock`, `Target`, `Activity`, `Users`, `ShoppingCart`) already used elsewhere in the codebase.

---

## Data contract
The real `/dashboard/stats` endpoint already returns much of what Tab 1/2 need (see `DashboardStats` interface in `GarageAnalyticsPage.tsx`): `revenue.daily_trend`... *(actually check: current interface has `revenue.today/this_week/this_month` but not a daily array — confirm with backend whether a time-series revenue endpoint exists or needs adding)*, `orders_by_status`, `mechanic_workload`, `internal_costs`.

**New data likely needed from backend** to fully power these charts:
```
revenue.daily_trend: [{ date, partsRevenue, laborRevenue, profit }]   // for the trend chart
repairOrders: [{ id, type, subtotal, hours, marginPct }]              // for the profitability scatter
trucksCost: [{ unit, ytdCost, miles }]                                // for cost-per-truck + cost-per-mile
pmVsUnplanned: [{ month, pmCost, unplannedCost }]                     // for the stacked bar
partsPortfolio: [{ name, turnoverRate, markupPct }]                   // for the quadrant scatter
accounts: [{ name, revenue, marginPct }]                              // for the Pareto + table (new tab)
quoteFunnel: { sent, viewed, approved, invoiced, avgApproveHrs }      // for the funnel (may be derivable from orders_by_status)
```

## Files in this bundle
- `Analytics (Recharts).html` — the working design reference (open in a browser). Includes the accent-color picker and a 7D/30D/90D/YTD range toggle.
- `analytics-data.jsx` — **mock** data generator matching the shapes above. Replace with real API calls (React Query, matching the pattern already used in `GarageAnalyticsPage.tsx`'s `useEffect` + `api.get`).
- `analytics-recharts-charts.jsx` — all Recharts chart components (dark-theme styled, tooltip/legend styling, the animation-off fix noted above).

## Build order (suggested)
1. `npm install recharts` in `frontend/`.
2. Port `RevenueTrendChart` first (highest-value, currently zero coverage) into the Overview tab, wired to real revenue data (add the daily-trend field to the backend response if it doesn't already exist beyond the 30-day version mentioned in `ANALYTICS_IMPLEMENTATION.md`).
3. Replace the "Technician Workload" progress bars with `RankedBar`, same underlying `mechanic_workload` data.
4. Add the Funnel using existing `orders_by_status` counts.
5. Add the two Internal Fleet Costs charts (cost/truck, cost/mile) — needs new truck-cost aggregation from backend.
6. Add the new Customer Accounts tab last — needs a new accounts-revenue aggregation endpoint.
7. Wire the accent-color context into chart series colors so charts follow the user's theme choice.
