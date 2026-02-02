import { useEffect, useState } from 'react'
import { Building2, CheckCircle, XCircle, User, Phone, Mail, MapPin, Calendar } from 'lucide-react'
import api from '../../lib/api'

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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white mb-2">Garages</h1>
          <p className="text-gray-400">Manage your garage customers</p>
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={showActiveOnly}
              onChange={(e) => setShowActiveOnly(e.target.checked)}
              className="rounded border-gray-600 bg-gray-700 text-amber-500 focus:ring-amber-500"
            />
            Active only
          </label>
          <button
            onClick={() => alert('Create garage feature coming soon!')}
            className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg font-medium transition-colors"
          >
            + New Garage
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
          <div className="text-gray-400 text-sm">Total Garages</div>
          <div className="text-2xl font-bold text-white mt-1">{garages.length}</div>
        </div>
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
          <div className="text-gray-400 text-sm">Active</div>
          <div className="text-2xl font-bold text-green-400 mt-1">
            {garages.filter(g => g.is_active).length}
          </div>
        </div>
        <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
          <div className="text-gray-400 text-sm">Stripe Connected</div>
          <div className="text-2xl font-bold text-blue-400 mt-1">
            {garages.filter(g => g.stripe_onboarding_complete).length}
          </div>
        </div>
      </div>

      {/* Garages List */}
      <div className="space-y-4">
        {garages.length === 0 ? (
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-12 text-center">
            <Building2 className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">No garages found</p>
          </div>
        ) : (
          garages.map((garage) => (
            <div
              key={garage.id}
              className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6 hover:border-gray-600/50 transition-colors"
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`p-3 rounded-lg ${garage.is_active ? 'bg-green-500/10' : 'bg-gray-500/10'}`}>
                    <Building2 className={`w-6 h-6 ${garage.is_active ? 'text-green-400' : 'text-gray-400'}`} />
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold text-white">{garage.name}</h3>
                    <p className="text-sm text-gray-400">/{garage.slug}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {garage.is_active ? (
                    <span className="flex items-center gap-1 px-3 py-1 bg-green-500/10 text-green-400 rounded-full text-sm">
                      <CheckCircle className="w-4 h-4" />
                      Active
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 px-3 py-1 bg-gray-500/10 text-gray-400 rounded-full text-sm">
                      <XCircle className="w-4 h-4" />
                      Inactive
                    </span>
                  )}
                  {garage.stripe_onboarding_complete && (
                    <span className="px-3 py-1 bg-blue-500/10 text-blue-400 rounded-full text-sm">
                      Stripe ✓
                    </span>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Contact Info */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Contact</h4>
                  {garage.address && (
                    <div className="flex items-start gap-2 text-sm">
                      <MapPin className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-300">{garage.address}</span>
                    </div>
                  )}
                  {garage.phone && (
                    <div className="flex items-center gap-2 text-sm">
                      <Phone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{garage.phone}</span>
                    </div>
                  )}
                  {garage.email && (
                    <div className="flex items-center gap-2 text-sm">
                      <Mail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={`mailto:${garage.email}`} className="text-blue-400 hover:text-blue-300">
                        {garage.email}
                      </a>
                    </div>
                  )}
                </div>

                {/* Owner Info */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">Owner</h4>
                  {garage.owner_name && (
                    <div className="flex items-center gap-2 text-sm">
                      <User className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{garage.owner_name}</span>
                    </div>
                  )}
                  {garage.owner_email && (
                    <div className="flex items-center gap-2 text-sm">
                      <Mail className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <a href={`mailto:${garage.owner_email}`} className="text-blue-400 hover:text-blue-300">
                        {garage.owner_email}
                      </a>
                    </div>
                  )}
                  {garage.owner_phone && (
                    <div className="flex items-center gap-2 text-sm">
                      <Phone className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      <span className="text-gray-300">{garage.owner_phone}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2 text-sm">
                    <Calendar className="w-4 h-4 text-gray-500 flex-shrink-0" />
                    <span className="text-gray-400">Joined {formatDate(garage.created_at)}</span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="mt-6 pt-4 border-t border-gray-700/50 flex gap-2">
                <button
                  onClick={() => alert(`View details for ${garage.name} - Coming soon!`)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm transition-colors"
                >
                  View Details
                </button>
                <a
                  href={`/dashboard/garages/${garage.id}/analytics`}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm transition-colors"
                >
                  View Analytics
                </a>
                {!garage.is_active && (
                  <button
                    onClick={() => alert(`Activate ${garage.name} - Coming soon!`)}
                    className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm transition-colors ml-auto"
                  >
                    Activate
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
