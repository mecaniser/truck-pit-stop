import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { 
  TrendingUp, TrendingDown, Users, DollarSign, 
  ShoppingCart, Target, Activity, ArrowLeft 
} from 'lucide-react'
import api from '../../lib/api'

interface GarageStats {
  tenant_id: string
  tenant_name: string
  is_active: boolean
  users: {
    by_role: Record<string, number>
    total: number
  }
  customers: {
    total: number
    new_this_month: number
  }
  repair_orders: {
    by_status: Record<string, number>
    total: number
  }
  revenue: {
    total: number
    this_month: number
    last_month: number
    average_order_value: number
    daily_trend: Array<{ date: string; revenue: number }>
  }
  performance: {
    conversion_rate: number
    orders_per_customer: number
  }
  trends: {
    daily_orders: Array<{ date: string; count: number }>
    revenue_growth: number
  }
}

export default function GarageAnalyticsPage() {
  const { garageId } = useParams()
  const [stats, setStats] = useState<GarageStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (garageId) {
      fetchStats()
    }
  }, [garageId])

  const fetchStats = async () => {
    try {
      const response = await api.get(`/admin/tenants/${garageId}/stats`)
      setStats(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load analytics')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
    }).format(amount)
  }

  const SimpleLineChart = ({ data, dataKey }: { data: any[], dataKey: string }) => {
    if (!data || data.length === 0) return null

    const values = data.map(d => d[dataKey])
    const max = Math.max(...values)
    const min = Math.min(...values)
    const range = max - min || 1

    const points = data.map((d, i) => {
      const x = (i / (data.length - 1)) * 100
      const y = 100 - ((d[dataKey] - min) / range) * 80
      return `${x},${y}`
    }).join(' ')

    return (
      <svg className="w-full h-32" viewBox="0 0 100 100" preserveAspectRatio="none">
        <polyline
          points={points}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    )
  }

  const SimpleBarChart = ({ data, dataKey }: { data: any[], dataKey: string }) => {
    if (!data || data.length === 0) return null

    const values = data.map(d => d[dataKey])
    const max = Math.max(...values) || 1

    return (
      <div className="flex items-end justify-between h-32 gap-1">
        {data.slice(-30).map((d, i) => {
          const height = (d[dataKey] / max) * 100
          return (
            <div
              key={i}
              className="flex-1 bg-amber-500 rounded-t transition-all hover:bg-amber-400"
              style={{ height: `${height}%`, minHeight: '2px' }}
              title={`${d.date}: ${d[dataKey]}`}
            />
          )
        })}
      </div>
    )
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
      <div>
        <Link 
          to="/dashboard/garages" 
          className="inline-flex items-center gap-2 text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Garages
        </Link>
        <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-6">
          <p className="text-red-400">{error || 'No data available'}</p>
        </div>
      </div>
    )
  }

  const revenueGrowth = stats.trends.revenue_growth

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link 
          to="/dashboard/garages" 
          className="inline-flex items-center gap-2 text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Garages
        </Link>
        <h1 className="text-2xl font-bold text-white mb-2">{stats.tenant_name}</h1>
        <p className="text-gray-400">Detailed Performance Analytics</p>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div className="p-3 bg-green-500/10 rounded-lg">
              <DollarSign className="w-6 h-6 text-green-400" />
            </div>
            {revenueGrowth !== 0 && (
              <div className={`flex items-center gap-1 text-sm ${revenueGrowth > 0 ? 'text-green-400' : 'text-red-400'}`}>
                {revenueGrowth > 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                {Math.abs(revenueGrowth)}%
              </div>
            )}
          </div>
          <p className="text-gray-400 text-sm">This Month Revenue</p>
          <p className="text-2xl font-bold text-white mt-1">{formatCurrency(stats.revenue.this_month)}</p>
          <p className="text-gray-500 text-xs mt-2">Last month: {formatCurrency(stats.revenue.last_month)}</p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-blue-500/10 rounded-lg w-fit mb-4">
            <ShoppingCart className="w-6 h-6 text-blue-400" />
          </div>
          <p className="text-gray-400 text-sm">Total Orders</p>
          <p className="text-2xl font-bold text-white mt-1">{stats.repair_orders.total}</p>
          <p className="text-gray-500 text-xs mt-2">
            {stats.repair_orders.by_status.in_progress || 0} in progress
          </p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-purple-500/10 rounded-lg w-fit mb-4">
            <Users className="w-6 h-6 text-purple-400" />
          </div>
          <p className="text-gray-400 text-sm">Total Customers</p>
          <p className="text-2xl font-bold text-white mt-1">{stats.customers.total}</p>
          <p className="text-gray-500 text-xs mt-2">
            +{stats.customers.new_this_month} this month
          </p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-amber-500/10 rounded-lg w-fit mb-4">
            <Target className="w-6 h-6 text-amber-400" />
          </div>
          <p className="text-gray-400 text-sm">Conversion Rate</p>
          <p className="text-2xl font-bold text-white mt-1">{stats.performance.conversion_rate}%</p>
          <p className="text-gray-500 text-xs mt-2">Quoted → Paid</p>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue Trend */}
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Revenue Trend (30 Days)</h2>
            <Activity className="w-5 h-5 text-gray-400" />
          </div>
          <div className="text-green-400">
            <SimpleLineChart data={stats.revenue.daily_trend} dataKey="revenue" />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-gray-400">Total Revenue</p>
              <p className="text-white font-semibold">{formatCurrency(stats.revenue.total)}</p>
            </div>
            <div>
              <p className="text-gray-400">Avg Order Value</p>
              <p className="text-white font-semibold">{formatCurrency(stats.revenue.average_order_value)}</p>
            </div>
          </div>
        </div>

        {/* Daily Orders */}
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Daily Orders (30 Days)</h2>
            <ShoppingCart className="w-5 h-5 text-gray-400" />
          </div>
          <SimpleBarChart data={stats.trends.daily_orders} dataKey="count" />
          <div className="mt-4 text-sm">
            <p className="text-gray-400">Orders per Customer</p>
            <p className="text-white font-semibold">{stats.performance.orders_per_customer}</p>
          </div>
        </div>
      </div>

      {/* Status Breakdown */}
      <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Order Status Breakdown</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
          {Object.entries(stats.repair_orders.by_status).map(([status, count]) => (
            <div key={status} className="text-center p-4 bg-gray-700/30 rounded-lg">
              <div className="text-2xl font-bold text-white">{count}</div>
              <div className="text-xs text-gray-400 capitalize mt-1">
                {status.replace('_', ' ')}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Team Breakdown */}
      <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Team Composition</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {Object.entries(stats.users.by_role).map(([role, count]) => (
            <div key={role} className="text-center p-4 bg-gray-700/30 rounded-lg">
              <div className="text-2xl font-bold text-white">{count}</div>
              <div className="text-xs text-gray-400 capitalize mt-1">
                {role.replace('_', ' ')}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
