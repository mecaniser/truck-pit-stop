import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { 
  TrendingUp, TrendingDown, Users, DollarSign, 
  ShoppingCart, Target, Activity, ArrowLeft, Building2 
} from 'lucide-react'
import api from '../../lib/api'
import { GlassNoirCard, GlassNoirHeader } from '../../components/ui/GlassNoirCard'
import { StatScrollRow, CollapsibleStats, InlineStats } from '../../components/ui/MobileStats'

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
              className="flex-1 bg-gold-500 rounded-t transition-all hover:bg-gold-400"
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
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-500"></div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div>
        <Link 
          to="/dashboard/garages" 
          className="inline-flex items-center gap-2 text-gray-400 hover:text-gold-400 mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Garages
        </Link>
        <GlassNoirCard className="border-red-500/30">
          <p className="text-red-400">{error || 'No data available'}</p>
        </GlassNoirCard>
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
          className="inline-flex items-center gap-2 text-gray-400 hover:text-gold-400 mb-4 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Garages
        </Link>
        <GlassNoirHeader
          title={stats.tenant_name}
          subtitle="Detailed Performance Analytics"
          icon={<Building2 className="w-6 h-6 text-gold-400" />}
        />
      </div>

      {/* Key Metrics - Horizontal Scroll */}
      <StatScrollRow
        stats={[
          { 
            label: 'This Month', 
            value: formatCurrency(stats.revenue.this_month), 
            icon: <DollarSign className="w-4 h-4" />, 
            sublabel: revenueGrowth !== 0 ? `${revenueGrowth > 0 ? '+' : ''}${revenueGrowth}%` : undefined,
            color: 'green' 
          },
          { label: 'Orders', value: stats.repair_orders.total, icon: <ShoppingCart className="w-4 h-4" />, sublabel: `${stats.repair_orders.by_status.in_progress || 0} active` },
          { label: 'Customers', value: stats.customers.total, icon: <Users className="w-4 h-4" />, sublabel: `+${stats.customers.new_this_month} new` },
          { label: 'Conversion', value: `${stats.performance.conversion_rate}%`, icon: <Target className="w-4 h-4" />, color: 'gold' },
        ]}
      />

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue Trend */}
        <GlassNoirCard>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Revenue Trend (30 Days)</h2>
            <Activity className="w-5 h-5 text-gold-400" />
          </div>
          <div className="text-gold-400">
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
        </GlassNoirCard>

        {/* Daily Orders */}
        <GlassNoirCard>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Daily Orders (30 Days)</h2>
            <ShoppingCart className="w-5 h-5 text-gold-400" />
          </div>
          <SimpleBarChart data={stats.trends.daily_orders} dataKey="count" />
          <div className="mt-4 text-sm">
            <p className="text-gray-400">Orders per Customer</p>
            <p className="text-white font-semibold">{stats.performance.orders_per_customer}</p>
          </div>
        </GlassNoirCard>
      </div>

      {/* Status & Team - Collapsible */}
      <div className="space-y-3">
        <CollapsibleStats
          title="Orders"
          summary={
            <InlineStats items={[
              { label: 'In Progress', value: stats.repair_orders.by_status.in_progress || 0, color: 'text-gold-400' },
              { label: 'Completed', value: stats.repair_orders.by_status.completed || 0, color: 'text-green-400' },
              { label: 'Total', value: stats.repair_orders.total },
            ]} />
          }
        >
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.repair_orders.by_status).map(([status, count]) => (
              <div key={status} className="flex items-center gap-2 bg-gold-500/5 border border-gold-500/10 rounded-lg px-3 py-2 text-sm">
                <span className="text-gray-400 capitalize whitespace-nowrap">{status.replace('_', ' ')}</span>
                <span className="font-bold text-white">{count}</span>
              </div>
            ))}
          </div>
        </CollapsibleStats>

        <CollapsibleStats
          title="Team"
          summary={
            <InlineStats items={
              Object.entries(stats.users.by_role).slice(0, 3).map(([role, count]) => ({
                label: role.replace('_', ' '),
                value: count,
              }))
            } />
          }
        >
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.users.by_role).map(([role, count]) => (
              <div key={role} className="flex items-center gap-2 bg-gold-500/5 border border-gold-500/10 rounded-lg px-3 py-2 text-sm">
                <span className="text-gray-400 capitalize">{role.replace('_', ' ')}</span>
                <span className="font-bold text-white">{count}</span>
              </div>
            ))}
          </div>
        </CollapsibleStats>
      </div>
    </div>
  )
}
