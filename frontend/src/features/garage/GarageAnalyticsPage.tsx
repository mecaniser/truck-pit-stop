import { useEffect, useState } from 'react'
import { 
  TrendingUp, TrendingDown, Users, DollarSign, 
  ShoppingCart, Target, Activity, Wrench, Clock
} from 'lucide-react'
import api from '../../lib/api'
interface DashboardStats {
  total_customers: number
  total_vehicles: number
  total_repair_orders: number
  orders_by_status: Array<{ status: string; count: number }>
  active_orders: number
  awaiting_approval: number
  pending_invoices: number
  low_stock_count: number
  revenue: {
    today: string
    this_week: string
    this_month: string
    total_paid_orders: number
    today_parts_margin: string
    this_week_parts_margin: string
    this_month_parts_margin: string
    today_gross_profit: string
    this_week_gross_profit: string
    this_month_gross_profit: string
    today_ppi: string
    this_week_ppi: string
    this_month_ppi: string
  }
  mechanic_workload?: Array<{
    mechanic_id: string
    mechanic_name: string
    assigned_count: number
    in_progress_count: number
  }>
}

export default function GarageAnalyticsPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const response = await api.get('/dashboard/stats')
      setStats(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load analytics')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (amount: string | number) => {
    const num = typeof amount === 'string' ? parseFloat(amount) : amount
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(num)
  }

  const getStatusCount = (status: string) => {
    return stats?.orders_by_status?.find((s) => s.status === status)?.count || 0
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-6">
        <p className="text-red-400">{error || 'No data available'}</p>
      </div>
    )
  }

  const thisMonthRevenue = parseFloat(stats.revenue.this_month)
  const thisWeekRevenue = parseFloat(stats.revenue.this_week)

  // Calculate week-over-week growth estimate
  const estimatedMonthlyFromWeek = thisWeekRevenue * 4.33 // avg weeks per month
  const projectedGrowth = estimatedMonthlyFromWeek > 0 && thisMonthRevenue > 0
    ? ((thisMonthRevenue / estimatedMonthlyFromWeek - 1) * 100).toFixed(1)
    : null

  const conversionRate = stats.total_repair_orders > 0
    ? (stats.revenue.total_paid_orders / stats.total_repair_orders * 100).toFixed(1)
    : '0.0'

  const avgOrderValue = stats.revenue.total_paid_orders > 0
    ? thisMonthRevenue / stats.revenue.total_paid_orders
    : 0
  const thisMonthGrossProfit = parseFloat(stats.revenue.this_month_gross_profit || '0')
  const thisMonthPartsMargin = parseFloat(stats.revenue.this_month_parts_margin || '0')
  const thisMonthPpi = parseFloat(stats.revenue.this_month_ppi || '0')

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Garage Analytics</h1>
        <p className="text-gray-400">Performance overview and insights</p>
      </div>

      {/* Revenue Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div className="p-3 bg-green-500/10 rounded-lg">
              <DollarSign className="w-6 h-6 text-green-400" />
            </div>
            {projectedGrowth && parseFloat(projectedGrowth) !== 0 && (
              <div className={`flex items-center gap-1 text-sm ${parseFloat(projectedGrowth) > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {parseFloat(projectedGrowth) > 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                {Math.abs(parseFloat(projectedGrowth))}%
              </div>
            )}
          </div>
          <p className="text-gray-400 text-sm">This Month Revenue</p>
          <p className="text-2xl font-bold text-white mt-1">{formatCurrency(stats.revenue.this_month)}</p>
          <p className="text-gray-500 text-xs mt-2">This week: {formatCurrency(stats.revenue.this_week)}</p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-blue-500/10 rounded-lg w-fit mb-4">
            <ShoppingCart className="w-6 h-6 text-blue-400" />
          </div>
          <p className="text-gray-400 text-sm">Active Orders</p>
          <p className="text-2xl font-bold text-white mt-1">{stats.active_orders}</p>
          <p className="text-gray-500 text-xs mt-2">
            {stats.total_repair_orders} total orders
          </p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-purple-500/10 rounded-lg w-fit mb-4">
            <Users className="w-6 h-6 text-purple-400" />
          </div>
          <p className="text-gray-400 text-sm">Total Customers</p>
          <p className="text-2xl font-bold text-white mt-1">{stats.total_customers}</p>
          <p className="text-gray-500 text-xs mt-2">
            {stats.total_vehicles} vehicles
          </p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-amber-500/10 rounded-lg w-fit mb-4">
            <Target className="w-6 h-6 text-amber-400" />
          </div>
          <p className="text-gray-400 text-sm">Conversion Rate</p>
          <p className="text-2xl font-bold text-white mt-1">{conversionRate}%</p>
          <p className="text-gray-500 text-xs mt-2">Orders → Paid</p>
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Order Pipeline */}
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Order Pipeline</h2>
            <Activity className="w-5 h-5 text-gray-400" />
          </div>
          <div className="space-y-3">
            {[
              { status: 'quoted', label: 'Quoted', color: 'bg-blue-500' },
              { status: 'approved', label: 'Approved', color: 'bg-cyan-500' },
              { status: 'in_progress', label: 'In Progress', color: 'bg-amber-500' },
              { status: 'completed', label: 'Completed', color: 'bg-green-500' },
              { status: 'invoiced', label: 'Invoiced', color: 'bg-purple-500' },
              { status: 'paid', label: 'Paid', color: 'bg-emerald-500' },
            ].map(({ status, label, color }) => {
              const count = getStatusCount(status)
              const percentage = stats.total_repair_orders > 0
                ? (count / stats.total_repair_orders * 100).toFixed(0)
                : 0
              return (
                <div key={status}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-gray-300">{label}</span>
                    <span className="text-white font-semibold">{count} ({percentage}%)</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-2">
                    <div 
                      className={`${color} h-2 rounded-full transition-all`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Key Insights */}
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Key Insights</h2>
            <TrendingUp className="w-5 h-5 text-gray-400" />
          </div>
          <div className="space-y-4">
            <div className="flex items-start gap-3 p-3 bg-gray-700/30 rounded-lg">
              <div className="p-2 bg-green-500/10 rounded">
                <DollarSign className="w-4 h-4 text-green-400" />
              </div>
              <div>
                <div className="text-sm text-gray-400">Avg Order Value</div>
                <div className="text-lg font-semibold text-white">{formatCurrency(avgOrderValue)}</div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 bg-gray-700/30 rounded-lg">
              <div className="p-2 bg-blue-500/10 rounded">
                <ShoppingCart className="w-4 h-4 text-blue-400" />
              </div>
              <div>
                <div className="text-sm text-gray-400">Orders Per Customer</div>
                <div className="text-lg font-semibold text-white">
                  {(stats.total_repair_orders / stats.total_customers).toFixed(2)}
                </div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 bg-gray-700/30 rounded-lg">
              <div className="p-2 bg-amber-500/10 rounded">
                <TrendingUp className="w-4 h-4 text-amber-400" />
              </div>
              <div>
                <div className="text-sm text-gray-400">This Month Gross Profit</div>
                <div className="text-lg font-semibold text-white">{formatCurrency(thisMonthGrossProfit)}</div>
                <div className="text-xs text-gray-500">Parts margin: {formatCurrency(thisMonthPartsMargin)}</div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 bg-gray-700/30 rounded-lg">
              <div className="p-2 bg-violet-500/10 rounded">
                <Target className="w-4 h-4 text-violet-400" />
              </div>
              <div>
                <div className="text-sm text-gray-400">PPI (This Month)</div>
                <div className="text-lg font-semibold text-white">{formatCurrency(thisMonthPpi)}</div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 bg-gray-700/30 rounded-lg">
              <div className="p-2 bg-amber-500/10 rounded">
                <Clock className="w-4 h-4 text-amber-400" />
              </div>
              <div>
                <div className="text-sm text-gray-400">Pending Actions</div>
                <div className="text-lg font-semibold text-white">
                  {stats.awaiting_approval + stats.pending_invoices}
                </div>
                <div className="text-xs text-gray-500">
                  {stats.awaiting_approval} approvals, {stats.pending_invoices} invoices
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mechanic Performance */}
      {stats.mechanic_workload && stats.mechanic_workload.length > 0 && (
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Technician Workload</h2>
            <Wrench className="w-5 h-5 text-gray-400" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.mechanic_workload.map((mechanic) => (
              <div key={mechanic.mechanic_id} className="bg-gray-700/30 rounded-lg p-4">
                <div className="font-medium text-white mb-2">{mechanic.mechanic_name}</div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-400">Assigned:</span>
                  <span className="text-white font-semibold">{mechanic.assigned_count}</span>
                </div>
                <div className="flex items-center justify-between text-sm mt-1">
                  <span className="text-gray-400">In Progress:</span>
                  <span className="text-amber-400 font-semibold">{mechanic.in_progress_count}</span>
                </div>
                <div className="mt-2 w-full bg-gray-600 rounded-full h-1.5">
                  <div 
                    className="bg-amber-500 h-1.5 rounded-full"
                    style={{ 
                      width: `${mechanic.assigned_count > 0 ? (mechanic.in_progress_count / mechanic.assigned_count * 100) : 0}%` 
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alerts & Actions */}
      {(stats.awaiting_approval > 0 || stats.pending_invoices > 0 || stats.low_stock_count > 0) && (
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Action Items</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {stats.awaiting_approval > 0 && (
              <div className="flex items-center gap-3 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                <Clock className="w-5 h-5 text-yellow-400" />
                <div>
                  <div className="text-white font-semibold">{stats.awaiting_approval}</div>
                  <div className="text-sm text-gray-400">Awaiting Approval</div>
                </div>
              </div>
            )}
            {stats.pending_invoices > 0 && (
              <div className="flex items-center gap-3 p-4 bg-purple-500/10 border border-purple-500/30 rounded-lg">
                <DollarSign className="w-5 h-5 text-purple-400" />
                <div>
                  <div className="text-white font-semibold">{stats.pending_invoices}</div>
                  <div className="text-sm text-gray-400">Pending Invoices</div>
                </div>
              </div>
            )}
            {stats.low_stock_count > 0 && (
              <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                <Activity className="w-5 h-5 text-red-400" />
                <div>
                  <div className="text-white font-semibold">{stats.low_stock_count}</div>
                  <div className="text-sm text-gray-400">Low Stock Items</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
