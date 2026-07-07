import { useEffect, useState } from 'react'
import { Building2, Users, TrendingUp, Crown, DollarSign, Wrench, UserCog, ChevronRight, Gauge } from 'lucide-react'
import api from '../../lib/api'
import { GlassNoirCard, GlassNoirHeader } from '../../components/ui/GlassNoirCard'
import { StatScrollRow, CollapsibleStats, InlineStats } from '../../components/ui/MobileStats'

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
  users: {
    owners: number
    admins: number
    mechanics: number
    total: number
  }
  customers: number
}

export default function PlatformDashboard() {
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
        api.get('/admin/tenants/summary'),
      ])
      setStats(statsRes.data)
      setTenants(tenantsRes.data)
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
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gold-500"></div>
      </div>
    )
  }

  if (error) {
    return (
      <GlassNoirCard className="border-red-500/30">
        <p className="text-red-400">{error}</p>
      </GlassNoirCard>
    )
  }

  if (!stats) return null

  const formatCurrency = (amount: number) => {
    if (amount >= 1000000) return `$${(amount / 1000000).toFixed(1)}M`
    if (amount >= 1000) return `$${(amount / 1000).toFixed(1)}k`
    return `$${amount}`
  }

  return (
    <div className="space-y-6">
      <GlassNoirHeader 
        title="Platform Overview"
        subtitle="Monitor your SaaS platform"
        icon={<Crown className="w-6 h-6 text-gold-400" />}
      />

      {/* Platform-Level Stats Only */}
      <StatScrollRow
        stats={[
          { label: 'Shops', value: stats.tenants.total, icon: <Building2 className="w-4 h-4" />, sublabel: `${stats.tenants.active} active`, color: 'gold' },
          { label: 'Revenue', value: formatCurrency(stats.revenue.total), icon: <DollarSign className="w-4 h-4" />, sublabel: 'All shops', color: 'green' },
        ]}
      />

      {/* Shops with Per-Shop User Breakdown */}
      <CollapsibleStats
        title="Shops"
        summary={
          <InlineStats items={[
            { label: 'Total', value: stats.tenants.total },
            { label: 'Active', value: stats.tenants.active, color: 'text-green-400' },
          ]} />
        }
        defaultExpanded={true}
      >
        <div className="space-y-2">
          {tenants.map((tenant) => (
            <a
              key={tenant.id}
              href={`/dashboard/garages/${tenant.id}/analytics`}
              className="flex items-center justify-between p-3 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-gold-500/30 rounded-lg transition-all group"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={`p-2 rounded-lg ${tenant.is_active ? 'bg-gold-500/10' : 'bg-gray-500/10'}`}>
                  <Building2 className={`w-4 h-4 ${tenant.is_active ? 'text-gold-400' : 'text-gray-500'}`} />
                </div>
                <div className="min-w-0">
                  <div className="text-white font-medium truncate group-hover:text-gold-400 transition-colors">
                    {tenant.name}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
                    <span className="flex items-center gap-1">
                      <Wrench className="w-3 h-3" />
                      {tenant.users.mechanics}
                    </span>
                    <span className="flex items-center gap-1">
                      <UserCog className="w-3 h-3" />
                      {tenant.users.admins + tenant.users.owners}
                    </span>
                    <span className="flex items-center gap-1">
                      <Users className="w-3 h-3" />
                      {tenant.customers}
                    </span>
                  </div>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-500 group-hover:text-gold-400 flex-shrink-0" />
            </a>
          ))}
          {tenants.length === 0 && (
            <div className="text-center py-4 text-gray-500 text-sm">No shops yet</div>
          )}
        </div>
      </CollapsibleStats>

      {/* Quick Actions */}
      <GlassNoirCard>
        <h2 className="text-lg font-bold text-white mb-3">Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <a
            href="/dashboard/garages"
            className="flex items-center gap-3 p-3 bg-gold-500/10 hover:bg-gold-500/20 border border-gold-500/30 rounded-lg transition-all"
          >
            <Building2 className="w-5 h-5 text-gold-400 flex-shrink-0" />
            <div className="min-w-0">
              <div className="font-medium text-white text-sm">All Shops</div>
            </div>
          </a>
          <a
            href="/dashboard/analytics"
            className="flex items-center gap-3 p-3 bg-gold-500/10 hover:bg-gold-500/20 border border-gold-500/30 rounded-lg transition-all"
          >
            <TrendingUp className="w-5 h-5 text-gold-400 flex-shrink-0" />
            <div className="min-w-0">
              <div className="font-medium text-white text-sm">Analytics</div>
            </div>
          </a>
          <a
            href="/dashboard/analytics?tab=performance"
            className="flex items-center gap-3 p-3 bg-gold-500/10 hover:bg-gold-500/20 border border-gold-500/30 rounded-lg transition-all"
          >
            <Gauge className="w-5 h-5 text-gold-400 flex-shrink-0" />
            <div className="min-w-0">
              <div className="font-medium text-white text-sm">Performance</div>
            </div>
          </a>
          <a
            href="/dashboard/pending-enrollments"
            className="flex items-center gap-3 p-3 bg-gold-500/10 hover:bg-gold-500/20 border border-gold-500/30 rounded-lg transition-all"
          >
            <Users className="w-5 h-5 text-gold-400 flex-shrink-0" />
            <div className="min-w-0">
              <div className="font-medium text-white text-sm">Enrollments</div>
            </div>
          </a>
        </div>
      </GlassNoirCard>
    </div>
  )
}
