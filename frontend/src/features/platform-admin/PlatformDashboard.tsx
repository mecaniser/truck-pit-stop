import { useEffect, useState } from 'react'
import { Building2, Users, TrendingUp, Activity } from 'lucide-react'
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

export default function PlatformDashboard() {
  const [stats, setStats] = useState<PlatformStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const response = await api.get('/admin/platform/stats')
      setStats(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load platform stats')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-6">
        <p className="text-red-400">{error}</p>
      </div>
    )
  }

  if (!stats) return null

  const statCards = [
    {
      title: 'Total Garages',
      value: stats.tenants.total,
      subtitle: `${stats.tenants.active} active`,
      icon: Building2,
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/10',
    },
    {
      title: 'Total Users',
      value: stats.users.total,
      subtitle: `${stats.users.by_role.garage_owner || 0} owners`,
      icon: Users,
      color: 'text-green-400',
      bgColor: 'bg-green-500/10',
    },
    {
      title: 'Repair Orders',
      value: stats.repair_orders.total,
      subtitle: `${stats.repair_orders.by_status.in_progress || 0} in progress`,
      icon: Activity,
      color: 'text-amber-400',
      bgColor: 'bg-amber-500/10',
    },
    {
      title: 'Total Revenue',
      value: `$${(stats.revenue.total / 1000).toFixed(1)}k`,
      subtitle: 'All time',
      icon: TrendingUp,
      color: 'text-emerald-400',
      bgColor: 'bg-emerald-500/10',
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-2">Platform Overview</h1>
        <p className="text-gray-400">Monitor your SaaS platform performance</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((stat) => (
          <div
            key={stat.title}
            className="bg-gray-800/50 backdrop-blur-sm border border-gray-700/50 rounded-lg p-6"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-gray-400 text-sm font-medium">{stat.title}</p>
                <p className="text-3xl font-bold text-white mt-2">{stat.value}</p>
                <p className="text-gray-500 text-sm mt-1">{stat.subtitle}</p>
              </div>
              <div className={`${stat.bgColor} ${stat.color} p-3 rounded-lg`}>
                <stat.icon className="w-6 h-6" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* User Breakdown */}
      <div className="bg-gray-800/50 backdrop-blur-sm border border-gray-700/50 rounded-lg p-6">
        <h2 className="text-xl font-bold text-white mb-4">User Breakdown</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {Object.entries(stats.users.by_role).map(([role, count]) => (
            <div key={role} className="text-center">
              <div className="text-2xl font-bold text-white">{count}</div>
              <div className="text-sm text-gray-400 capitalize">
                {role.replace('_', ' ')}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Repair Orders Status */}
      <div className="bg-gray-800/50 backdrop-blur-sm border border-gray-700/50 rounded-lg p-6">
        <h2 className="text-xl font-bold text-white mb-4">Repair Orders by Status</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
          {Object.entries(stats.repair_orders.by_status).map(([status, count]) => (
            <div key={status} className="text-center">
              <div className="text-2xl font-bold text-white">{count}</div>
              <div className="text-sm text-gray-400 capitalize">
                {status.replace('_', ' ')}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-gray-800/50 backdrop-blur-sm border border-gray-700/50 rounded-lg p-6">
        <h2 className="text-xl font-bold text-white mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <a
            href="/dashboard/garages"
            className="flex items-center gap-3 p-4 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/30 rounded-lg transition-colors"
          >
            <Building2 className="w-6 h-6 text-blue-400" />
            <div>
              <div className="font-semibold text-white">View All Garages</div>
              <div className="text-sm text-gray-400">Manage your customers</div>
            </div>
          </a>
          <a
            href="/dashboard/analytics"
            className="flex items-center gap-3 p-4 bg-green-500/10 hover:bg-green-500/20 border border-green-500/30 rounded-lg transition-colors"
          >
            <TrendingUp className="w-6 h-6 text-green-400" />
            <div>
              <div className="font-semibold text-white">Platform Analytics</div>
              <div className="text-sm text-gray-400">Detailed metrics</div>
            </div>
          </a>
          <button
            onClick={() => alert('Onboarding feature coming soon!')}
            className="flex items-center gap-3 p-4 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 rounded-lg transition-colors"
          >
            <Users className="w-6 h-6 text-amber-400" />
            <div>
              <div className="font-semibold text-white">Onboard New Garage</div>
              <div className="text-sm text-gray-400">Add customer</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  )
}
