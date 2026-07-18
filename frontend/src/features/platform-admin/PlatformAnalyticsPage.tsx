import { useEffect, useState } from 'react'
import { Spinner } from '@/components/ui'
import { useSearchParams } from 'react-router-dom'
import { 
  Building2, Users, DollarSign,
  TrendingUp, CheckCircle, XCircle,
  BarChart3, Gauge, AlertTriangle
} from 'lucide-react'
import api from '../../lib/api'
import PerformanceTab from './PerformanceTab'
import ErrorsTab from './ErrorsTab'
import { GlassNoirCard, GlassNoirHeader, GlassNoirBadge } from '../../components/ui/GlassNoirCard'
import { SegmentedControl, StatScrollRow, CollapsibleStats, InlineStats } from '../../components/ui/MobileStats'

type TabType = 'business' | 'performance' | 'errors'

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

function isTabType(value: string | null): value is TabType {
  return value === 'business' || value === 'performance' || value === 'errors'
}

export default function PlatformAnalyticsPage() {
  const [searchParams] = useSearchParams()
  const initialTab = searchParams.get('tab')
  const [activeTab, setActiveTab] = useState<TabType>(isTabType(initialTab) ? initialTab : 'business')
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
        <Spinner size="xl" />
      </div>
    )
  }

  if (error || !stats) {
    return (
      <GlassNoirCard className="border-red-500/30">
        <p className="text-red-400">{error || 'No data available'}</p>
      </GlassNoirCard>
    )
  }

  const activeRate = stats.tenants.total > 0 
    ? (stats.tenants.active / stats.tenants.total * 100).toFixed(1)
    : '0.0'

  const avgRevenuePerGarage = stats.tenants.active > 0
    ? stats.revenue.total / stats.tenants.active
    : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <GlassNoirHeader
        title="Platform Analytics"
        subtitle="Overview of your entire platform"
        icon={<BarChart3 className="w-6 h-6 text-gold-400" />}
      />

      {/* Tab Navigation - Segmented Control */}
      <SegmentedControl
        value={activeTab}
        onChange={(v) => setActiveTab(v as TabType)}
        options={[
          { id: 'business', label: 'Business', shortLabel: 'Biz', icon: <BarChart3 className="w-4 h-4" />, color: 'gold' },
          { id: 'performance', label: 'Performance', shortLabel: 'Perf', icon: <Gauge className="w-4 h-4" />, color: 'blue' },
          { id: 'errors', label: 'Errors', shortLabel: 'Err', icon: <AlertTriangle className="w-4 h-4" />, color: 'red' },
        ]}
      />

      {/* Performance Tab Content */}
      {activeTab === 'performance' && <PerformanceTab />}

      {/* Errors Tab Content */}
      {activeTab === 'errors' && <ErrorsTab />}

      {/* Business Tab Content */}
      {activeTab === 'business' && (
        <>
          {/* Platform-Level Stats Only */}
          <StatScrollRow
            stats={[
              { label: 'Shops', value: stats.tenants.total, icon: <Building2 className="w-4 h-4" />, sublabel: `${activeRate}% active`, color: 'gold' },
              { label: 'Users', value: stats.users.total, icon: <Users className="w-4 h-4" />, sublabel: `${stats.users.by_role.garage_owner || 0} owners` },
              { label: 'Revenue', value: formatCurrency(stats.revenue.total), icon: <DollarSign className="w-4 h-4" />, sublabel: 'All shops', color: 'green' },
            ]}
          />

          {/* User Distribution */}
          <GlassNoirCard>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">User Distribution</h2>
              <Users className="w-5 h-5 text-gold-400" />
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
                      <div className="w-full bg-noir-700 rounded-full h-2">
                        <div 
                          className="bg-gradient-to-r from-gold-600 to-gold-400 h-2 rounded-full transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
            </div>
            <div className="mt-4 pt-4 border-t border-gold-500/10">
              <div className="text-sm text-gray-400">
                Total Users: <span className="text-white font-semibold">{stats.users.total}</span>
              </div>
            </div>
          </GlassNoirCard>

          {/* Shop List - Links to per-shop analytics */}
          <GlassNoirCard>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Shops</h2>
              <div className="text-sm text-gray-400">
                {stats.tenants.active} active of {stats.tenants.total} total
              </div>
            </div>
            
            <div className="space-y-2">
              {tenants.map((tenant) => (
                <a
                  key={tenant.id}
                  href={`/dashboard/garages/${tenant.id}/analytics`}
                  className="flex items-center justify-between p-3 sm:p-4 bg-gold-500/5 hover:bg-gold-500/10 border border-gold-500/10 hover:border-gold-500/20 rounded-lg transition-all group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`p-2 rounded-lg border flex-shrink-0 ${tenant.is_active ? 'bg-gold-500/10 border-gold-500/20' : 'bg-gray-500/10 border-gray-500/20'}`}>
                      <Building2 className={`w-4 h-4 sm:w-5 sm:h-5 ${tenant.is_active ? 'text-gold-400' : 'text-gray-400'}`} />
                    </div>
                    <div className="min-w-0">
                      <div className="text-white font-medium group-hover:text-gold-400 transition-colors truncate">
                        {tenant.name}
                      </div>
                      <div className="text-xs text-gray-400 truncate">
                        {tenant.owner_email} • {formatDate(tenant.created_at)}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                    {tenant.is_active ? (
                      <GlassNoirBadge variant="success">
                        <span className="flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" />
                          <span className="hidden sm:inline">Active</span>
                        </span>
                      </GlassNoirBadge>
                    ) : (
                      <GlassNoirBadge variant="warning">
                        <span className="flex items-center gap-1">
                          <XCircle className="w-3 h-3" />
                          <span className="hidden sm:inline">Inactive</span>
                        </span>
                      </GlassNoirBadge>
                    )}
                    <TrendingUp className="w-4 h-4 text-gray-400 group-hover:text-gold-400 transition-colors" />
                  </div>
                </a>
              ))}
            </div>

            {tenants.length === 0 && (
              <div className="text-center py-8 text-gray-400">
                No shops yet.
              </div>
            )}
          </GlassNoirCard>

          {/* Platform Health */}
          <CollapsibleStats
            title="Health"
            summary={
              <InlineStats items={[
                { label: 'Active', value: `${activeRate}%`, color: parseFloat(activeRate) >= 80 ? 'text-green-400' : 'text-yellow-400' },
                { label: 'Avg Rev', value: formatCurrency(avgRevenuePerGarage) },
              ]} />
            }
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-gray-400 mb-1">Active Rate</div>
                <div className="text-xl font-bold text-white">{activeRate}%</div>
                <div className={`text-xs ${parseFloat(activeRate) >= 80 ? 'text-green-400' : 'text-yellow-400'}`}>
                  {parseFloat(activeRate) >= 80 ? 'Healthy' : 'Needs attention'}
                </div>
              </div>
              <div className="bg-white/5 rounded-lg p-3">
                <div className="text-gray-400 mb-1">Avg Revenue/Shop</div>
                <div className="text-xl font-bold text-white">{formatCurrency(avgRevenuePerGarage)}</div>
              </div>
            </div>
          </CollapsibleStats>
        </>
      )}
    </div>
  )
}
