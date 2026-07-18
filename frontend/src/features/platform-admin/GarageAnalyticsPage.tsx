import { useEffect, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useParams, Link } from 'react-router-dom'
import { 
  Users, DollarSign, 
  ShoppingCart, Target, Activity, ArrowLeft, Building2 
} from 'lucide-react'
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts'
import api from '../../lib/api'
import { GlassNoirCard, GlassNoirHeader } from '../../components/ui/GlassNoirCard'
import { StatScrollRow, CollapsibleStats, InlineStats } from '../../components/ui/MobileStats'
import { CHART } from '../analytics/chartTheme'

// Super-admin theme uses gold; validated as sufficient-contrast single-series
// colour on the noir surface.
const GOLD = '#B8860B'

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

  // Themed Recharts area chart — replaces the hand-rolled SVG polyline.
  const SimpleLineChart = ({ data, dataKey }: { data: any[], dataKey: string }) => {
    if (!data || data.length === 0) return null
    return (
      <div className="h-32">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="gAdminRev" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={GOLD} stopOpacity={0.35} />
                <stop offset="100%" stopColor={GOLD} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="date" hide />
            <YAxis hide />
            <Tooltip
              contentStyle={{ background: CHART.tooltipBg, border: CHART.tooltipBorder, borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: CHART.tooltipMuted }}
              formatter={(v) => ['$' + Number(v ?? 0).toLocaleString(), 'Revenue']}
            />
            <Area type="monotone" dataKey={dataKey} stroke={GOLD} strokeWidth={2} fill="url(#gAdminRev)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }

  // Themed Recharts bar chart — replaces the hand-rolled flex bars.
  const SimpleBarChart = ({ data, dataKey }: { data: any[], dataKey: string }) => {
    if (!data || data.length === 0) return null
    return (
      <div className="h-32">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data.slice(-30)} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="date" hide />
            <YAxis hide />
            <Tooltip
              cursor={{ fill: CHART.cursorFill }}
              contentStyle={{ background: CHART.tooltipBg, border: CHART.tooltipBorder, borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: CHART.tooltipMuted }}
            />
            <Bar dataKey={dataKey} fill={GOLD} radius={[3, 3, 0, 0]} maxBarSize={14} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="xl" />
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
          Back to Shops
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
          Back to Shops
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
