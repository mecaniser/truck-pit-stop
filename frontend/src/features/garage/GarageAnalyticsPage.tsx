import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import { Download, Loader2 } from 'lucide-react'
import api from '../../lib/api'
import { useTheme } from '../../contexts/ThemeContext'
import InternalInvoiceList from './InternalInvoiceList'
import {
  ChartCard, ProfitabilityScatter, QuoteFunnel, RankedBar, ParetoChart,
} from '../analytics/ChartKit'
import { SERIES, CATEGORICAL } from '../analytics/chartTheme'

// ============ SHARED TYPES ============

type DateRangePreset =
  | 'this_year' | 'last_year'
  | 'this_quarter' | 'last_quarter'
  | 'this_month' | 'last_month'
  | 'this_week' | 'last_week'
  | 'custom'

const RANGE_LABELS: Record<DateRangePreset, string> = {
  this_year: 'This Year',
  last_year: 'Last Year',
  this_quarter: 'This Quarter',
  last_quarter: 'Last Quarter',
  this_month: 'This Month',
  last_month: 'Last Month',
  this_week: 'This Week',
  last_week: 'Last Week',
  custom: 'Custom',
}

interface TrendPoint {
  label: string
  value: string
}

interface DashboardMetric {
  value: string
  trend: TrendPoint[]
}

interface ReportsDashboardResponse {
  range_start: string
  range_end: string
  revenue: DashboardMetric
  labor_revenue: DashboardMetric
  part_revenue: DashboardMetric
  fees_revenue: DashboardMetric
  parts_profit: DashboardMetric
  inventory_value: DashboardMetric
  invoiced_hours: DashboardMetric
  part_sales_finalized: DashboardMetric
  services_finalized: DashboardMetric
}

interface SalesGroupRow {
  group_key: string
  group_label: string
  labor: string
  parts: string
  fees: string
  sales_tax: string
  discounts: string
  net_sales: string
}

interface ReportsSalesResponse {
  summary: {
    net_sales: string
    labor: string
    parts: string
    discounts: string
    fees: string
    sales_tax: string
  }
  rows: SalesGroupRow[]
}

interface FeeRow {
  fee_name: string
  times_added: number
  average_charge: string
  total_charged: string
}

interface ReportsFeesResponse {
  times_added: number
  average_charge: string
  total_charged: string
  rows: FeeRow[]
}

interface TaxRow {
  rate_label: string
  percentage: string
  tax_collected: string
}

interface ReportsTaxResponse {
  rows: TaxRow[]
}

interface PartRevenueRow {
  invoice_number: string
  revenue: string
  cost: string
  profit: string
  margin_pct: string
}

interface ReportsPartsResponse {
  revenue: string
  cost: string
  profit: string
  margin_pct: string
  rows: PartRevenueRow[]
}

interface InventoryRow {
  sku: string
  name: string
  quantity: string
  unit_cost: string
  total_value: string
}

interface ReportsInventoryResponse {
  part_value: string
  total_value: string
  rows: InventoryRow[]
}

interface ServiceTypeRow {
  name: string
  quantity: number
  hours_billed: string
  total_charged: string
}

interface ReportsServiceTypesResponse {
  service_items: number
  hours_billed: string
  total_charged: string
  rows: ServiceTypeRow[]
}

// ============ HELPERS ============

const fmtMoney = (value: string | number | undefined): string => {
  const n = parseFloat(String(value ?? 0))
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const fmtNumber = (value: string | number | undefined): string => {
  const n = parseFloat(String(value ?? 0))
  return n.toLocaleString('en-US', { maximumFractionDigits: 1 })
}

function exportRowsToCsv(filename: string, headers: string[], rows: (string | number)[][]) {
  const escape = (v: string | number) => {
    const s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [headers, ...rows].map((r) => r.map(escape).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ============ DATE RANGE PICKER ============

function DateRangePicker({
  value,
  onChange,
}: {
  value: DateRangePreset
  onChange: (preset: DateRangePreset) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const options: DateRangePreset[] = [
    'this_year', 'last_year', 'this_quarter', 'last_quarter',
    'this_month', 'last_month', 'this_week', 'last_week',
  ]

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        className="flex items-center gap-2 h-10 px-4 rounded-lg bg-white/10 text-white text-sm font-medium hover:bg-white/15 transition-colors"
      >
        {RANGE_LABELS[value]}
      </button>
      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute z-50 mt-1 w-44 rounded-lg bg-gray-900 border border-white/20 shadow-xl py-1">
            {options.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => {
                  onChange(opt)
                  setIsOpen(false)
                }}
                className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                  opt === value ? 'text-white bg-white/10' : 'text-gray-200 hover:bg-white/5'
                }`}
              >
                {RANGE_LABELS[opt]}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ============ SUMMARY CARD ============

function MetricCard({
  label,
  value,
  trend,
  color = '#60a5fa',
  chartType = 'bar',
}: {
  label: string
  value: string
  trend?: TrendPoint[]
  color?: string
  chartType?: 'bar' | 'line'
}) {
  const chartData = (trend || []).map((p) => ({ label: p.label, value: parseFloat(p.value) }))
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
      <p className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-bold text-white mb-3">{value}</p>
      {chartData.length > 0 && (
        <div className="h-24">
          <ResponsiveContainer width="100%" height="100%">
            {chartType === 'line' ? (
              <LineChart data={chartData}>
                <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#e5e7eb' }}
                  formatter={(v) => fmtMoney(v as number)}
                />
                <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            ) : (
              <BarChart data={chartData}>
                <XAxis dataKey="label" tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip
                  contentStyle={{ backgroundColor: '#111827', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#e5e7eb' }}
                  formatter={(v) => fmtMoney(v as number)}
                />
                <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} />
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

function LoadingBlock() {
  return (
    <div className="flex items-center justify-center gap-2 text-white/50 text-sm py-16">
      <Loader2 className="w-4 h-4 animate-spin" />
      Loading report…
    </div>
  )
}

function ExportButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 h-10 px-4 rounded-lg bg-white/10 text-white text-sm font-medium hover:bg-white/15 transition-colors"
    >
      <Download className="w-4 h-4" />
      Export
    </button>
  )
}

// ============ TAB: DASHBOARD ============

function DashboardTab({ range }: { range: DateRangePreset }) {
  const { accentColors } = useTheme()
  const { data, isLoading } = useQuery<ReportsDashboardResponse>({
    queryKey: ['reports-dashboard', range],
    queryFn: async () => (await api.get('/reports/dashboard', { params: { range } })).data,
  })

  if (isLoading || !data) return <LoadingBlock />

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
        <MetricCard label="Revenue" value={fmtMoney(data.revenue.value)} trend={data.revenue.trend} color={accentColors[500]} />
        <MetricCard label="Labor Revenue" value={fmtMoney(data.labor_revenue.value)} trend={data.labor_revenue.trend} color={SERIES.cumulative} />
        <MetricCard label="Part Revenue" value={fmtMoney(data.part_revenue.value)} trend={data.part_revenue.trend} color={SERIES.parts} />
        <MetricCard label="Fees Revenue" value={fmtMoney(data.fees_revenue.value)} trend={data.fees_revenue.trend} color={SERIES.margin} />
        <MetricCard label="Parts Profit" value={fmtMoney(data.parts_profit.value)} trend={data.parts_profit.trend} color={SERIES.margin} />
        <MetricCard label="Inventory Value" value={fmtMoney(data.inventory_value.value)} chartType="line" color={SERIES.parts} />
        <MetricCard label="Invoiced Hours" value={`${fmtNumber(data.invoiced_hours.value)} hrs`} trend={data.invoiced_hours.trend} color={SERIES.danger} />
        <MetricCard label="Part Sales Finalized" value={fmtNumber(data.part_sales_finalized.value)} trend={data.part_sales_finalized.trend} color={SERIES.cumulative} />
        <MetricCard label="Services Finalized" value={fmtNumber(data.services_finalized.value)} trend={data.services_finalized.trend} color={accentColors[500]} />
      </div>

      <InsightsSection range={range} />
    </div>
  )
}

// ---- Advanced analytics charts (wired to /reports/analytics/*) ----
interface ProfitabilityResp { ros: { type: string; subtotal: number; marginPct: number; hours: number }[] }
interface AccountsResp { accounts: { name: string; revenue: number; marginPct: number; cumPct: number }[] }
interface FunnelResp { sent: number; approved: number; invoiced: number }
interface TruckCostResp { trucks: { unit: string; ytdCost: number }[] }

function InsightsSection({ range }: { range: DateRangePreset }) {
  const profit = useQuery<ProfitabilityResp>({
    queryKey: ['analytics-profitability', range],
    queryFn: async () => (await api.get('/reports/analytics/profitability', { params: { range } })).data,
  })
  const accounts = useQuery<AccountsResp>({
    queryKey: ['analytics-accounts', range],
    queryFn: async () => (await api.get('/reports/analytics/accounts', { params: { range } })).data,
  })
  const funnel = useQuery<FunnelResp>({
    queryKey: ['analytics-funnel', range],
    queryFn: async () => (await api.get('/reports/analytics/quote-funnel', { params: { range } })).data,
  })
  const trucks = useQuery<TruckCostResp>({
    queryKey: ['analytics-trucks', range],
    queryFn: async () => (await api.get('/reports/analytics/truck-costs', { params: { range } })).data,
  })

  const hasProfit = (profit.data?.ros.length ?? 0) > 0
  const hasAccounts = (accounts.data?.accounts.length ?? 0) > 0
  const hasFunnel = (funnel.data?.sent ?? 0) > 0
  const hasTrucks = (trucks.data?.trucks.length ?? 0) > 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <ChartCard title="Labor vs. Parts Profitability" subtitle="Each bubble is a repair order — subtotal × margin %, sized by labor hours">
        {hasProfit ? <ProfitabilityScatter ros={profit.data!.ros} /> : <EmptyChart loading={profit.isLoading} />}
      </ChartCard>

      <ChartCard title="Quote → Approval Funnel" subtitle="Sent → approved → invoiced">
        {hasFunnel ? <QuoteFunnel funnel={funnel.data!} /> : <EmptyChart loading={funnel.isLoading} />}
      </ChartCard>

      <ChartCard title="Revenue by Account" subtitle="Which accounts are your 80/20 — bars are revenue, line is cumulative %">
        {hasAccounts ? <ParetoChart accounts={accounts.data!.accounts.slice(0, 12)} /> : <EmptyChart loading={accounts.isLoading} />}
      </ChartCard>

      <ChartCard title="Cost per Truck" subtitle="Internal-fleet maintenance spend, top 10" height={380} fit>
        {hasTrucks
          ? <RankedBar
              data={trucks.data!.trucks}
              dataKey="ytdCost"
              nameKey="unit"
              tickFormatter={(v) => '$' + (v / 1000).toFixed(1) + 'k'}
              tooltipFormatter={(v) => '$' + v.toLocaleString()}
            />
          : <EmptyChart loading={trucks.isLoading} />}
      </ChartCard>
    </div>
  )
}

function EmptyChart({ loading }: { loading: boolean }) {
  return (
    <div className="flex h-full items-center justify-center text-sm text-white/40">
      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'No data for this range yet'}
    </div>
  )
}

// ============ TAB: SALES ============

function SalesTab({ range }: { range: DateRangePreset }) {
  const { accentColors } = useTheme()
  const { data, isLoading } = useQuery<ReportsSalesResponse>({
    queryKey: ['reports-sales', range],
    queryFn: async () => (await api.get('/reports/sales', { params: { range } })).data,
  })

  if (isLoading || !data) return <LoadingBlock />

  const handleExport = () => {
    exportRowsToCsv(
      'sales-report.csv',
      ['Customer', 'Labor', 'Parts', 'Fees', 'Sales Tax', 'Discounts', 'Net Sales'],
      data.rows.map((r) => [r.group_label, r.labor, r.parts, r.fees, r.sales_tax, r.discounts, r.net_sales])
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-4">
        <MetricCard label="Net Sales" value={fmtMoney(data.summary.net_sales)} chartType="line" color={accentColors[500]} />
        <MetricCard label="Labor" value={fmtMoney(data.summary.labor)} chartType="line" color={CATEGORICAL[4]} />
        <MetricCard label="Parts" value={fmtMoney(data.summary.parts)} chartType="line" color={SERIES.parts} />
        <MetricCard label="Discounts" value={fmtMoney(data.summary.discounts)} chartType="line" color={SERIES.danger} />
        <MetricCard label="Fees" value={fmtMoney(data.summary.fees)} chartType="line" color={SERIES.margin} />
        <MetricCard label="Sales Tax" value={fmtMoney(data.summary.sales_tax)} chartType="line" color={CATEGORICAL[2]} />
      </div>

      {data.rows.length > 0 && (
        <ChartCard title="Top Customers by Net Sales" subtitle={`Top ${Math.min(10, data.rows.length)} of ${data.rows.length}`} height={380} fit>
          <RankedBar
            data={[...data.rows].sort((a, b) => parseFloat(b.net_sales) - parseFloat(a.net_sales)).slice(0, 10)
              .map((r) => ({ label: r.group_label, value: parseFloat(r.net_sales) }))}
            dataKey="value"
            nameKey="label"
            tickFormatter={(v) => '$' + (v / 1000).toFixed(1) + 'k'}
            tooltipFormatter={(v) => '$' + v.toLocaleString()}
          />
        </ChartCard>
      )}

      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <span className="text-sm text-white/70">Grouped by customer &middot; {data.rows.length} results</span>
          <ExportButton onClick={handleExport} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Customer</th>
                <th className="px-4 py-3 text-right font-medium">Labor</th>
                <th className="px-4 py-3 text-right font-medium">Parts</th>
                <th className="px-4 py-3 text-right font-medium">Fees</th>
                <th className="px-4 py-3 text-right font-medium">Sales Tax</th>
                <th className="px-4 py-3 text-right font-medium">Discounts</th>
                <th className="px-4 py-3 text-right font-medium">Net Sales</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {data.rows.map((row) => (
                <tr key={row.group_key} className="hover:bg-white/5">
                  <td className="px-4 py-3 text-white font-medium">{row.group_label}</td>
                  <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.labor)}</td>
                  <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.parts)}</td>
                  <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.fees)}</td>
                  <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.sales_tax)}</td>
                  <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.discounts)}</td>
                  <td className="px-4 py-3 text-right text-white font-semibold">{fmtMoney(row.net_sales)}</td>
                </tr>
              ))}
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-white/50">No sales in this range</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ============ TAB: FEES ============

function FeesTab({ range }: { range: DateRangePreset }) {
  const { data, isLoading } = useQuery<ReportsFeesResponse>({
    queryKey: ['reports-fees', range],
    queryFn: async () => (await api.get('/reports/fees', { params: { range } })).data,
  })

  if (isLoading || !data) return <LoadingBlock />

  const handleExport = () => {
    exportRowsToCsv(
      'fees-report.csv',
      ['Fee Name', 'Times Added', 'Average Charge', 'Total Charged'],
      data.rows.map((r) => [r.fee_name, r.times_added, r.average_charge, r.total_charged])
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard label="Times Added" value={fmtNumber(data.times_added)} />
        <MetricCard label="Average Charge" value={fmtMoney(data.average_charge)} />
        <MetricCard label="Total Charged" value={fmtMoney(data.total_charged)} />
      </div>
      {data.rows.length > 0 && (
        <ChartCard title="Fees by Total Charged" height={380} fit>
          <RankedBar
            data={[...data.rows].sort((a, b) => parseFloat(b.total_charged) - parseFloat(a.total_charged)).slice(0, 10)
              .map((r) => ({ label: r.fee_name, value: parseFloat(r.total_charged) }))}
            dataKey="value" nameKey="label"
            tickFormatter={(v) => '$' + (v / 1000).toFixed(1) + 'k'}
            tooltipFormatter={(v) => '$' + v.toLocaleString()}
          />
        </ChartCard>
      )}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="flex items-center justify-end px-4 py-3 border-b border-white/10">
          <ExportButton onClick={handleExport} />
        </div>
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Fee Name</th>
              <th className="px-4 py-3 text-right font-medium">Times Added</th>
              <th className="px-4 py-3 text-right font-medium">Average Charge</th>
              <th className="px-4 py-3 text-right font-medium">Total Charged</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {data.rows.map((row) => (
              <tr key={row.fee_name} className="hover:bg-white/5">
                <td className="px-4 py-3 text-white font-medium">{row.fee_name}</td>
                <td className="px-4 py-3 text-right text-white/70">{row.times_added}</td>
                <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.average_charge)}</td>
                <td className="px-4 py-3 text-right text-white font-semibold">{fmtMoney(row.total_charged)}</td>
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-white/50">No fees charged in this range</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ============ TAB: SALES TAX ============

function TaxTab({ range }: { range: DateRangePreset }) {
  const { data, isLoading } = useQuery<ReportsTaxResponse>({
    queryKey: ['reports-tax', range],
    queryFn: async () => (await api.get('/reports/tax', { params: { range } })).data,
  })

  if (isLoading || !data) return <LoadingBlock />

  const handleExport = () => {
    exportRowsToCsv(
      'sales-tax-report.csv',
      ['Rate', 'Percentage', 'Tax Collected'],
      data.rows.map((r) => [r.rate_label, r.percentage, r.tax_collected])
    )
  }

  return (
    <div className="space-y-4">
    {data.rows.length > 0 && (
      <ChartCard title="Tax Collected by Rate" height={380} fit>
        <RankedBar
          data={[...data.rows].sort((a, b) => parseFloat(b.tax_collected) - parseFloat(a.tax_collected)).slice(0, 10)
            .map((r) => ({ label: r.rate_label, value: parseFloat(r.tax_collected) }))}
          dataKey="value" nameKey="label"
          tickFormatter={(v) => '$' + (v / 1000).toFixed(1) + 'k'}
          tooltipFormatter={(v) => '$' + v.toLocaleString()}
        />
      </ChartCard>
    )}
    <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
      <div className="flex items-center justify-end px-4 py-3 border-b border-white/10">
        <ExportButton onClick={handleExport} />
      </div>
      <table className="w-full text-sm">
        <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
          <tr>
            <th className="px-4 py-3 text-left font-medium">Rate</th>
            <th className="px-4 py-3 text-right font-medium">Percentage</th>
            <th className="px-4 py-3 text-right font-medium">Tax Collected</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/10">
          {data.rows.map((row) => (
            <tr key={row.rate_label} className="hover:bg-white/5">
              <td className="px-4 py-3 text-white font-medium">{row.rate_label}</td>
              <td className="px-4 py-3 text-right text-white/70">{row.percentage}%</td>
              <td className="px-4 py-3 text-right text-white font-semibold">{fmtMoney(row.tax_collected)}</td>
            </tr>
          ))}
          {data.rows.length === 0 && (
            <tr>
              <td colSpan={3} className="px-4 py-8 text-center text-white/50">No tax collected in this range</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
    </div>
  )
}

// ============ TAB: PART REVENUE ============

function PartsTab({ range }: { range: DateRangePreset }) {
  const { data, isLoading } = useQuery<ReportsPartsResponse>({
    queryKey: ['reports-parts', range],
    queryFn: async () => (await api.get('/reports/parts', { params: { range } })).data,
  })

  if (isLoading || !data) return <LoadingBlock />

  const handleExport = () => {
    exportRowsToCsv(
      'part-revenue-report.csv',
      ['Invoice', 'Revenue', 'Cost', 'Profit', 'Margin %'],
      data.rows.map((r) => [r.invoice_number, r.revenue, r.cost, r.profit, r.margin_pct])
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <MetricCard label="Revenue" value={fmtMoney(data.revenue)} />
        <MetricCard label="Cost" value={fmtMoney(data.cost)} />
        <MetricCard label="Profit" value={fmtMoney(data.profit)} />
        <MetricCard label="Margin" value={`${data.margin_pct}%`} />
      </div>
      {data.rows.length > 0 && (
        <ChartCard title="Parts Profitability by Invoice" subtitle="Revenue × margin %, sized by profit — spot underpriced parts jobs">
          <ProfitabilityScatter
            ros={data.rows.map((r) => ({
              type: 'Part sale',
              subtotal: parseFloat(r.revenue),
              marginPct: parseFloat(r.margin_pct),
              hours: parseFloat(r.profit),
            }))}
          />
        </ChartCard>
      )}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <span className="text-sm text-white/70">Grouped by invoice &middot; {data.rows.length} results</span>
          <ExportButton onClick={handleExport} />
        </div>
        <table className="w-full text-sm">
          <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Invoice</th>
              <th className="px-4 py-3 text-right font-medium">Revenue</th>
              <th className="px-4 py-3 text-right font-medium">Cost</th>
              <th className="px-4 py-3 text-right font-medium">Profit</th>
              <th className="px-4 py-3 text-right font-medium">Margin</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {data.rows.map((row) => (
              <tr key={row.invoice_number} className="hover:bg-white/5">
                <td className="px-4 py-3 text-white font-medium">{row.invoice_number}</td>
                <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.revenue)}</td>
                <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.cost)}</td>
                <td className="px-4 py-3 text-right text-white font-semibold">{fmtMoney(row.profit)}</td>
                <td className="px-4 py-3 text-right text-white/70">{row.margin_pct}%</td>
              </tr>
            ))}
            {data.rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-white/50">No part sales in this range</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ============ TAB: INVENTORY ============

function InventoryTab() {
  const { data, isLoading } = useQuery<ReportsInventoryResponse>({
    queryKey: ['reports-inventory'],
    queryFn: async () => (await api.get('/reports/inventory')).data,
  })

  if (isLoading || !data) return <LoadingBlock />

  const handleExport = () => {
    exportRowsToCsv(
      'inventory-value-report.csv',
      ['SKU', 'Part', 'Quantity', 'Unit Cost', 'Total Value'],
      data.rows.map((r) => [r.sku, r.name, r.quantity, r.unit_cost, r.total_value])
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <MetricCard label="Part Value" value={fmtMoney(data.part_value)} />
        <MetricCard label="Total Value" value={fmtMoney(data.total_value)} />
      </div>
      {data.rows.length > 0 && (
        <ChartCard title="Top Parts by Inventory Value" height={380} fit>
          <RankedBar
            data={[...data.rows].sort((a, b) => parseFloat(b.total_value) - parseFloat(a.total_value)).slice(0, 10)
              .map((r) => ({ label: r.name, value: parseFloat(r.total_value) }))}
            dataKey="value" nameKey="label"
            tickFormatter={(v) => '$' + (v / 1000).toFixed(1) + 'k'}
            tooltipFormatter={(v) => '$' + v.toLocaleString()}
          />
        </ChartCard>
      )}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <span className="text-sm text-white/70">{data.rows.length} parts in stock</span>
          <ExportButton onClick={handleExport} />
        </div>
        <div className="max-h-[32rem] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider sticky top-0">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Part</th>
                <th className="px-4 py-3 text-right font-medium">Quantity</th>
                <th className="px-4 py-3 text-right font-medium">Unit Cost</th>
                <th className="px-4 py-3 text-right font-medium">Total Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {data.rows.map((row) => (
                <tr key={row.sku} className="hover:bg-white/5">
                  <td className="px-4 py-3">
                    <div className="text-white font-medium">{row.sku}</div>
                    <div className="text-xs text-white/50">{row.name}</div>
                  </td>
                  <td className="px-4 py-3 text-right text-white/70">{row.quantity}</td>
                  <td className="px-4 py-3 text-right text-white/70">{fmtMoney(row.unit_cost)}</td>
                  <td className="px-4 py-3 text-right text-white font-semibold">{fmtMoney(row.total_value)}</td>
                </tr>
              ))}
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-white/50">No inventory on file</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ============ TAB: SERVICE TYPES ============

function ServiceTypesTab({ range }: { range: DateRangePreset }) {
  const { data, isLoading } = useQuery<ReportsServiceTypesResponse>({
    queryKey: ['reports-service-types', range],
    queryFn: async () => (await api.get('/reports/service-types', { params: { range } })).data,
  })

  if (isLoading || !data) return <LoadingBlock />

  const handleExport = () => {
    exportRowsToCsv(
      'service-types-report.csv',
      ['Name', 'Quantity', 'Hours Billed', 'Total Charged'],
      data.rows.map((r) => [r.name, r.quantity, r.hours_billed, r.total_charged])
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard label="Service Items" value={fmtNumber(data.service_items)} />
        <MetricCard label="Hours Billed" value={`${fmtNumber(data.hours_billed)} hrs`} />
        <MetricCard label="Total Charged" value={fmtMoney(data.total_charged)} />
      </div>
      {data.rows.length > 0 && (
        <ChartCard title="Top Service Types by Charges" height={380} fit>
          <RankedBar
            data={[...data.rows].sort((a, b) => parseFloat(b.total_charged) - parseFloat(a.total_charged)).slice(0, 10)
              .map((r) => ({ label: r.name, value: parseFloat(r.total_charged) }))}
            dataKey="value" nameKey="label"
            tickFormatter={(v) => '$' + (v / 1000).toFixed(1) + 'k'}
            tooltipFormatter={(v) => '$' + v.toLocaleString()}
          />
        </ChartCard>
      )}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <span className="text-sm text-white/70">{data.rows.length} service types</span>
          <ExportButton onClick={handleExport} />
        </div>
        <div className="max-h-[32rem] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-white/5 text-white/70 text-xs uppercase tracking-wider sticky top-0">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Name</th>
                <th className="px-4 py-3 text-right font-medium">Quantity</th>
                <th className="px-4 py-3 text-right font-medium">Hours Billed</th>
                <th className="px-4 py-3 text-right font-medium">Total Charged</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {data.rows.map((row) => (
                <tr key={row.name} className="hover:bg-white/5">
                  <td className="px-4 py-3 text-white font-medium">{row.name}</td>
                  <td className="px-4 py-3 text-right text-white/70">{row.quantity}</td>
                  <td className="px-4 py-3 text-right text-white/70">{fmtNumber(row.hours_billed)}</td>
                  <td className="px-4 py-3 text-right text-white font-semibold">{fmtMoney(row.total_charged)}</td>
                </tr>
              ))}
              {data.rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-white/50">No service items in this range</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ============ MAIN PAGE ============

type ReportTab = 'dashboard' | 'sales' | 'fees' | 'tax' | 'parts' | 'inventory' | 'service-types' | 'internal'

const TABS: { id: ReportTab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'sales', label: 'Sales' },
  { id: 'fees', label: 'Fees' },
  { id: 'tax', label: 'Sales Tax' },
  { id: 'parts', label: 'Part Revenue' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'service-types', label: 'Service Types' },
  { id: 'internal', label: 'Internal Fleet Costs' },
]

const DATE_FILTERED_TABS: ReportTab[] = ['dashboard', 'sales', 'fees', 'tax', 'parts', 'service-types']

export default function GarageAnalyticsPage() {
  const { accentColors } = useTheme()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab') as ReportTab | null
  const activeTab: ReportTab = tabParam && TABS.some((t) => t.id === tabParam) ? tabParam : 'dashboard'
  const setActiveTab = (id: ReportTab) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (id === 'dashboard') next.delete('tab')
      else next.set('tab', id)
      return next
    })
  }
  const [range, setRange] = useState<DateRangePreset>('this_month')

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 sm:mb-6 flex-shrink-0 gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-white">Shop Analytics</h1>
          <p className="text-sm text-white/50">Performance overview and insights</p>
        </div>
        {DATE_FILTERED_TABS.includes(activeTab) && <DateRangePicker value={range} onChange={setRange} />}
      </div>

      <div className="mb-4 flex-shrink-0 flex gap-1 overflow-x-auto scrollbar-hide border-b border-white/10">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px ${
              activeTab === tab.id ? 'text-white' : 'text-white/50 hover:text-white/80 border-transparent'
            }`}
            style={activeTab === tab.id ? { borderColor: accentColors[500] } : undefined}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-dark">
        {activeTab === 'dashboard' && <DashboardTab range={range} />}
        {activeTab === 'sales' && <SalesTab range={range} />}
        {activeTab === 'fees' && <FeesTab range={range} />}
        {activeTab === 'tax' && <TaxTab range={range} />}
        {activeTab === 'parts' && <PartsTab range={range} />}
        {activeTab === 'inventory' && <InventoryTab />}
        {activeTab === 'service-types' && <ServiceTypesTab range={range} />}
        {activeTab === 'internal' && <InternalInvoiceList />}
      </div>
    </div>
  )
}
