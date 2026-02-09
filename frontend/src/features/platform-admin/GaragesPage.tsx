import { useEffect, useState } from 'react'
import { Building2, CheckCircle, XCircle, User, Phone, Mail, MapPin, Calendar } from 'lucide-react'
import api from '../../lib/api'
import { GlassNoirCard, GlassNoirButton, GlassNoirBadge } from '../../components/ui/GlassNoirCard'

interface Tenant {
  id: string
  name: string
  slug: string
  address: string | null
  phone: string | null
  email: string | null
  is_active: boolean
  owner_id: string | null
  owner_email: string | null
  owner_name: string | null
  owner_phone: string | null
  stripe_account_id: string | null
  stripe_onboarding_complete: boolean
  created_at: string
  updated_at: string
}

export default function GaragesPage() {
  const [garages, setGarages] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showActiveOnly, setShowActiveOnly] = useState(false)

  useEffect(() => {
    fetchGarages()
  }, [showActiveOnly])

  const fetchGarages = async () => {
    try {
      setLoading(true)
      const params = showActiveOnly ? { active_only: true } : {}
      const response = await api.get('/admin/tenants', { params })
      setGarages(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load garages')
      console.error(err)
    } finally {
      setLoading(false)
    }
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

  return (
    <div className="space-y-4">
      {/* Stats & Actions - Compact inline bar */}
      <div className="flex flex-wrap items-center gap-3 sm:gap-4 text-sm">
        <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
          <span className="text-gray-400">Total</span>
          <span className="font-bold text-white">{garages.length}</span>
        </div>
        <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
          <span className="text-gray-400">Active</span>
          <span className="font-bold text-green-400">{garages.filter(g => g.is_active).length}</span>
        </div>
        <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
          <span className="text-gray-400">Stripe</span>
          <span className="font-bold text-gold-400">{garages.filter(g => g.stripe_onboarding_complete).length}</span>
        </div>
        <label className="flex items-center gap-2 cursor-pointer bg-white/5 border border-white/10 rounded-lg px-3 py-2 hover:bg-white/10 transition-colors">
          <input
            type="checkbox"
            checked={showActiveOnly}
            onChange={(e) => setShowActiveOnly(e.target.checked)}
            className="w-4 h-4 rounded border-gold-500/50 bg-black/40 text-gold-500 focus:ring-gold-500 focus:ring-offset-0 cursor-pointer"
          />
          <span className="text-gray-300 whitespace-nowrap">Active only</span>
        </label>
        <GlassNoirButton onClick={() => alert('Create garage feature coming soon!')} className="ml-auto whitespace-nowrap" size="sm">
          + New Garage
        </GlassNoirButton>
      </div>

      {/* Garages List */}
      <div className="space-y-4">
        {garages.length === 0 ? (
          <GlassNoirCard className="text-center py-12">
            <Building2 className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">No garages found</p>
          </GlassNoirCard>
        ) : (
          garages.map((garage) => (
            <GlassNoirCard key={garage.id} hover>
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`p-2.5 sm:p-3 rounded-lg flex-shrink-0 ${garage.is_active ? 'bg-gold-500/10 border border-gold-500/20' : 'bg-gray-500/10 border border-gray-500/20'}`}>
                    <Building2 className={`w-5 h-5 sm:w-6 sm:h-6 ${garage.is_active ? 'text-gold-400' : 'text-gray-400'}`} />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-lg sm:text-xl font-semibold text-white truncate">{garage.name}</h3>
                    <p className="text-sm text-gray-400 truncate">/{garage.slug}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {garage.is_active ? (
                    <GlassNoirBadge variant="success">
                      <span className="flex items-center gap-1 whitespace-nowrap">
                        <CheckCircle className="w-3 h-3" />
                        Active
                      </span>
                    </GlassNoirBadge>
                  ) : (
                    <GlassNoirBadge variant="warning">
                      <span className="flex items-center gap-1 whitespace-nowrap">
                        <XCircle className="w-3 h-3" />
                        Inactive
                      </span>
                    </GlassNoirBadge>
                  )}
                  {garage.stripe_onboarding_complete && (
                    <GlassNoirBadge variant="gold">
                      <span className="whitespace-nowrap">Stripe ✓</span>
                    </GlassNoirBadge>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
                {/* Contact Info */}
                <div className="space-y-2 sm:space-y-3">
                  <h4 className="text-xs sm:text-sm font-semibold text-gold-400/80 uppercase tracking-wide">Contact</h4>
                  {garage.address && (
                    <div className="flex items-start gap-2 text-xs sm:text-sm">
                      <MapPin className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-300 break-words">{garage.address}</span>
                    </div>
                  )}
                  {garage.phone && (
                    <div className="flex items-center gap-2 text-xs sm:text-sm">
                      <Phone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{garage.phone}</span>
                    </div>
                  )}
                  {garage.email && (
                    <div className="flex items-center gap-2 text-xs sm:text-sm min-w-0">
                      <Mail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={`mailto:${garage.email}`} className="text-gold-400 hover:text-gold-300 truncate">
                        {garage.email}
                      </a>
                    </div>
                  )}
                </div>

                {/* Owner Info */}
                <div className="space-y-2 sm:space-y-3">
                  <h4 className="text-xs sm:text-sm font-semibold text-gold-400/80 uppercase tracking-wide">Owner</h4>
                  {garage.owner_name && (
                    <div className="flex items-center gap-2 text-xs sm:text-sm">
                      <User className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{garage.owner_name}</span>
                    </div>
                  )}
                  {garage.owner_email && (
                    <div className="flex items-center gap-2 text-xs sm:text-sm min-w-0">
                      <Mail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={`mailto:${garage.owner_email}`} className="text-gold-400 hover:text-gold-300 truncate">
                        {garage.owner_email}
                      </a>
                    </div>
                  )}
                  {garage.owner_phone && (
                    <div className="flex items-center gap-2 text-xs sm:text-sm">
                      <Phone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{garage.owner_phone}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2 text-xs sm:text-sm">
                    <Calendar className="w-4 h-4 text-gray-500 flex-shrink-0" />
                    <span className="text-gray-400 whitespace-nowrap">Joined {formatDate(garage.created_at)}</span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="mt-4 sm:mt-6 pt-4 border-t border-gold-500/10 flex flex-wrap gap-2">
                <GlassNoirButton
                  variant="ghost"
                  size="sm"
                  onClick={() => alert(`View details for ${garage.name} - Coming soon!`)}
                >
                  View Details
                </GlassNoirButton>
                <a
                  href={`/dashboard/garages/${garage.id}/analytics`}
                  className="px-3 sm:px-4 py-2 bg-gold-500 hover:bg-gold-400 text-black rounded-lg text-xs sm:text-sm font-semibold transition-colors whitespace-nowrap"
                >
                  View Analytics
                </a>
                {!garage.is_active && (
                  <GlassNoirButton
                    variant="secondary"
                    size="sm"
                    className="sm:ml-auto"
                    onClick={() => alert(`Activate ${garage.name} - Coming soon!`)}
                  >
                    Activate
                  </GlassNoirButton>
                )}
              </div>
            </GlassNoirCard>
          ))
        )}
      </div>
    </div>
  )
}
