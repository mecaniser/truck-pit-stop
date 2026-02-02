import { useEffect, useState } from 'react'
import { 
  Building2, Users, DollarSign, Activity, 
  TrendingUp, ShoppingCart, CheckCircle, XCircle 
} from 'lucide-react'
import api from '../../lib/api'

interface PlatformStats {
  tenants: {
    total: number
    active: number
    inactive: number
  }
  users: {
    by_role: Record<string, number>
    total: number
  }
  customers: {
    total: number
  }
  repair_orders: {
    by_status: Record<string, number>
    total: number
  }
  revenue: {
    total: number
  }
}

interface TenantSummary {
  id: string
  name: string
  is_active: boolean
  owner_email: string | null
  created_at: string
}

export default function PlatformAnalyticsPage() {
  const [stats, setStats] = useState<PlatformStats | null>(null)
  const [tenants, setTenants] = useState<TenantSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [statsRes, tenantsRes] = await Promise.all([
        api.get('/admin/platform/stats'),
        api.get('/admin/tenants'),
      ])
      setStats(statsRes.data)
      setTenants(tenantsRes.data)
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

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
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

  const activeRate = stats.tenants.total > 0 
    ? (stats.tenants.active / stats.tenants.total * 100).toFixed(1)
    : '0.0'

  const avgRevenuePerGarage = stats.tenants.active > 0
    ? stats.revenue.total / stats.tenants.active
    : 0

  const avgCustomersPerGarage = stats.tenants.active > 0
    ? Math.round(stats.customers.total / stats.tenants.active)
    : 0

  const avgOrdersPerGarage = stats.tenants.active > 0
    ? Math.round(stats.repair_orders.total / stats.tenants.active)
    : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Platform Analytics</h1>
        <p className="text-gray-400">Overview of your entire platform</p>
      </div>

      {/* Top Level Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-start justify-between mb-4">
            <div className="p-3 bg-blue-500/10 rounded-lg">
              <Building2 className="w-6 h-6 text-blue-400" />
            </div>
            <div className="text-right">
              <div className="text-green-400 text-sm">{activeRate}% active</div>
            </div>
          </div>
          <p className="text-gray-400 text-sm">Total Garages</p>
          <p className="text-3xl font-bold text-white mt-1">{stats.tenants.total}</p>
          <p className="text-gray-500 text-xs mt-2">
            {stats.tenants.active} active, {stats.tenants.inactive} inactive
          </p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-green-500/10 rounded-lg w-fit mb-4">
            <DollarSign className="w-6 h-6 text-green-400" />
          </div>
          <p className="text-gray-400 text-sm">Total Revenue</p>
          <p className="text-3xl font-bold text-white mt-1">
            {formatCurrency(stats.revenue.total)}
          </p>
          <p className="text-gray-500 text-xs mt-2">
            Avg: {formatCurrency(avgRevenuePerGarage)}/garage
          </p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-purple-500/10 rounded-lg w-fit mb-4">
            <Users className="w-6 h-6 text-purple-400" />
          </div>
          <p className="text-gray-400 text-sm">Total Customers</p>
          <p className="text-3xl font-bold text-white mt-1">{stats.customers.total}</p>
          <p className="text-gray-500 text-xs mt-2">
            Avg: {avgCustomersPerGarage}/garage
          </p>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="p-3 bg-amber-500/10 rounded-lg w-fit mb-4">
            <ShoppingCart className="w-6 h-6 text-amber-400" />
          </div>
          <p className="text-gray-400 text-sm">Total Orders</p>
          <p className="text-3xl font-bold text-white mt-1">{stats.repair_orders.total}</p>
          <p className="text-gray-500 text-xs mt-2">
            Avg: {avgOrdersPerGarage}/garage
          </p>
        </div>
      </div>

      {/* Platform-wide Metrics Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* User Distribution */}
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">User Distribution</h2>
            <Users className="w-5 h-5 text-gray-400" />
          </div>
          <div className="space-y-3">
            {Object.entries(stats.users.by_role)
              .sort((a, b) => b[1] - a[1])
              .map(([role, count]) => {
                const percentage = (count / stats.users.total * 100).toFixed(1)
                return (
                  <div key={role}>
                    <div className="flex items-center justify-between text-sm mb-1">
                      <span className="text-gray-300 capitalize">{role.replace('_', ' ')}</span>
                      <span className="text-white font-semibold">{count} ({percentage}%)</span>
                    </div>
                    <div className="w-full bg-gray-700 rounded-full h-2">
                      <div 
                        className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                )
              })}
          </div>
          <div className="mt-4 pt-4 border-t border-gray-700/50">
            <div className="text-sm text-gray-400">
              Total Users: <span className="text-white font-semibold">{stats.users.total}</span>
            </div>
          </div>
        </div>

        {/* Order Status Distribution */}
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Order Status</h2>
            <Activity className="w-5 h-5 text-gray-400" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(stats.repair_orders.by_status).map(([status, count]) => {
              const percentage = (count / stats.repair_orders.total * 100).toFixed(0)
              return (
                <div key={status} className="bg-gray-700/30 rounded-lg p-3">
                  <div className="text-xs text-gray-400 capitalize mb-1">
                    {status.replace('_', ' ')}
                  </div>
                  <div className="text-xl font-bold text-white">{count}</div>
                  <div className="text-xs text-gray-500">{percentage}%</div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Garage List with Quick Stats */}
      <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Garages Overview</h2>
          <div className="text-sm text-gray-400">
            {stats.tenants.active} active of {stats.tenants.total} total
          </div>
        </div>
        
        <div className="space-y-2">
          {tenants.map((tenant) => (
            <a
              key={tenant.id}
              href={`/dashboard/garages/${tenant.id}/analytics`}
              className="flex items-center justify-between p-4 bg-gray-700/30 hover:bg-gray-700/50 rounded-lg transition-colors group"
            >
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg ${tenant.is_active ? 'bg-green-500/10' : 'bg-gray-500/10'}`}>
                  <Building2 className={`w-5 h-5 ${tenant.is_active ? 'text-green-400' : 'text-gray-400'}`} />
                </div>
                <div>
                  <div className="text-white font-medium group-hover:text-amber-400 transition-colors">
                    {tenant.name}
                  </div>
                  <div className="text-xs text-gray-400">
                    {tenant.owner_email} • Joined {formatDate(tenant.created_at)}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {tenant.is_active ? (
                  <span className="flex items-center gap-1 px-2 py-1 bg-green-500/10 text-green-400 rounded text-xs">
                    <CheckCircle className="w-3 h-3" />
                    Active
                  </span>
                ) : (
                  <span className="flex items-center gap-1 px-2 py-1 bg-gray-500/10 text-gray-400 rounded text-xs">
                    <XCircle className="w-3 h-3" />
                    Inactive
                  </span>
                )}
                <TrendingUp className="w-4 h-4 text-gray-400 group-hover:text-amber-400 transition-colors" />
              </div>
            </a>
          ))}
        </div>

        {tenants.length === 0 && (
          <div className="text-center py-8 text-gray-400">
            No garages yet. Create your first garage to get started!
          </div>
        )}
      </div>

      {/* Platform Health Indicators */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
          <div className="text-sm text-gray-400 mb-1">Active Rate</div>
          <div className="flex items-baseline gap-2">
            <div className="text-2xl font-bold text-white">{activeRate}%</div>
            <div className={`text-sm ${parseFloat(activeRate) >= 80 ? 'text-green-400' : 'text-yellow-400'}`}>
              {parseFloat(activeRate) >= 80 ? 'Healthy' : 'Monitor'}
            </div>
          </div>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
          <div className="text-sm text-gray-400 mb-1">Avg Revenue/Garage</div>
          <div className="text-2xl font-bold text-white">{formatCurrency(avgRevenuePerGarage)}</div>
        </div>

        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
          <div className="text-sm text-gray-400 mb-1">Total Platform Users</div>
          <div className="text-2xl font-bold text-white">{stats.users.total.toLocaleString()}</div>
        </div>
      </div>
    </div>
  )
}
