import { Link } from 'react-router-dom'

export interface ComponentContribution {
  revenue: string
  known_cost: string
  line_count: number
  missing_cost_line_count: number
  status: 'complete' | 'partial' | 'unavailable' | 'not_applicable'
  contribution: string | null
  margin_pct: string | null
}

export interface ContributionOrder {
  repair_order_id?: string
  order_number?: string
  type: string
  subtotal: number
  marginPct: number | null
  hours: number
  parts_contribution?: ComponentContribution
  sublet_contribution?: ComponentContribution
}

export interface ProfitabilityResp {
  ros: ContributionOrder[]
  cost_basis?: 'current_lines_before_order_discounts'
  labor_cost_status?: 'unavailable'
}

const money = (value: string) => Number(value).toLocaleString('en-US', {
  style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2,
})

function ComponentCost({ label, data }: { label: string; data?: ComponentContribution }) {
  if (!data) return <p className="text-xs text-gray-400">{label}: Cost breakdown unavailable</p>
  if (data.status === 'not_applicable') return <p className="text-xs text-gray-400">No {label.toLowerCase()} lines</p>

  const complete = data.status === 'complete' && data.contribution !== null
  const loss = complete && Number(data.contribution) < 0
  return (
    <section aria-label={`${label} contribution`} className="min-w-0 space-y-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="text-xs font-medium text-gray-300">{label}</h4>
        <span className={`text-sm font-semibold tabular-nums ${loss ? 'text-red-400' : 'text-white'}`}>
          {complete ? money(data.contribution!) : 'Contribution unavailable'}
        </span>
      </div>
      {complete ? (
        <p className="text-xs text-gray-400">
          {data.margin_pct !== null ? `${data.margin_pct}% margin` : 'Margin unavailable — no positive revenue'}
        </p>
      ) : (
        <p className="text-xs text-amber-300">
          {data.status === 'partial' ? 'Partial costs' : 'Costs unavailable'} · {data.line_count - data.missing_cost_line_count} of {data.line_count} lines have costs
        </p>
      )}
      <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400">
        <div><dt className="inline">Revenue </dt><dd className="inline tabular-nums text-gray-300">{money(data.revenue)}</dd></div>
        <div><dt className="inline">{complete ? 'Cost ' : 'Known cost '}</dt><dd className="inline tabular-nums text-gray-300">{money(data.known_cost)}</dd></div>
      </dl>
    </section>
  )
}

export default function CostContributionBreakdown({ data }: { data?: ProfitabilityResp }) {
  if (!data || data.cost_basis !== 'current_lines_before_order_discounts') {
    return <p className="text-sm text-gray-400">Cost breakdown unavailable</p>
  }
  if (data.ros.length === 0) return <p className="text-sm text-gray-400">No repair orders in this date range.</p>

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-400">Current recorded lines before order discounts; sublet also before labor discounts. Excludes ordinary labor costs and overhead.</p>
      <p className="text-xs text-gray-400">Whole-job margin unavailable: Labor costs not recorded.</p>
      <ul aria-label="Repair order cost breakdown" className="max-h-96 space-y-4 overflow-y-auto pr-1">
        {data.ros.map((order, index) => (
          <li key={order.repair_order_id ?? index} className="min-w-0 border-t border-gray-700/60 pt-3">
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs">
              {order.repair_order_id ? (
                <Link to={`/dashboard/repair-orders?selected=${order.repair_order_id}`} className="font-medium text-sky-400 hover:text-sky-300">
                  {order.order_number ?? order.type}
                </Link>
              ) : <span className="text-gray-300">{order.type}</span>}
              <span className="tabular-nums text-gray-400">{money(String(order.subtotal))} order subtotal</span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <ComponentCost label="Parts" data={order.parts_contribution} />
              <ComponentCost label="Sublet" data={order.sublet_contribution} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
