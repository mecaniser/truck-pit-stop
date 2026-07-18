import { useEffect, useRef, useState } from 'react'
import { Spinner } from '@/components/ui'
import { Building2, CheckCircle, XCircle, User, Phone, Mail, MapPin, Calendar, MessageSquare, X } from 'lucide-react'
import api from '../../lib/api'
import toast from 'react-hot-toast'
import { GlassNoirCard, GlassNoirButton, GlassNoirBadge } from '../../components/ui/GlassNoirCard'
import { formatUSPhone } from '../../utils/phone'
import GarageTeamModal from './components/GarageTeamModal'

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
  sms_phone_number: string | null
  sms_phone_sid: string | null
  sms_enabled: boolean
  created_at: string
  updated_at: string
}

type SMSModalMode = 'provision' | 'attach'

export default function GaragesPage() {
  const [garages, setGarages] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showActiveOnly, setShowActiveOnly] = useState(false)
  const [smsDetailsOpenByGarageId, setSmsDetailsOpenByGarageId] = useState<Record<string, boolean>>({})
  const [smsModalGarage, setSmsModalGarage] = useState<Tenant | null>(null)
  const [smsModalMode, setSmsModalMode] = useState<SMSModalMode>('provision')
  const [smsAreaCode, setSmsAreaCode] = useState('')
  const [attachPhoneSid, setAttachPhoneSid] = useState('')
  const [attachEnableSMS, setAttachEnableSMS] = useState(true)
  const [attachConfigureWebhooks, setAttachConfigureWebhooks] = useState(true)
  const [replaceConfirmation, setReplaceConfirmation] = useState(false)
  const [smsProvisioning, setSmsProvisioning] = useState(false)
  const [smsProvisionError, setSmsProvisionError] = useState<string | null>(null)
  const [smsStateUpdatingGarageId, setSmsStateUpdatingGarageId] = useState<string | null>(null)
  const [teamModalGarage, setTeamModalGarage] = useState<Tenant | null>(null)
  const isFirstLoadRef = useRef(true)
  const smsModalRef = useRef<HTMLDivElement | null>(null)
  const areaCodeInputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    fetchGarages(isFirstLoadRef.current ? 'initial' : 'refresh')
    isFirstLoadRef.current = false
  }, [showActiveOnly])

  useEffect(() => {
    if (!smsModalGarage) return
    areaCodeInputRef.current?.focus()
  }, [smsModalGarage])

  const fetchGarages = async (mode: 'initial' | 'refresh' = 'initial') => {
    try {
      if (mode === 'initial') {
        setLoading(true)
      } else {
        setRefreshing(true)
      }
      setError(null)
      const params = showActiveOnly ? { active_only: true } : {}
      const response = await api.get('/admin/tenants', { params })
      setGarages(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load shops')
      console.error(err)
    } finally {
      if (mode === 'initial') {
        setLoading(false)
      } else {
        setRefreshing(false)
      }
    }
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  }

  const hasProvisionedSMSNumber = (garage: Tenant) => Boolean(garage.sms_phone_number || garage.sms_phone_sid)

  const formatSMSPhoneNumber = (phone: string | null) => {
    if (!phone) return null
    const digits = phone.replace(/\D/g, '')
    if (digits.length === 11 && digits.startsWith('1')) {
      return `+1 ${formatUSPhone(digits.slice(1))}`
    }
    if (digits.length === 10) {
      return formatUSPhone(digits)
    }
    return phone
  }

  const openSMSProvisionModal = (garage: Tenant) => {
    setSmsModalGarage(garage)
    setSmsModalMode('provision')
    setSmsAreaCode('')
    setAttachPhoneSid('')
    setAttachEnableSMS(true)
    setAttachConfigureWebhooks(true)
    setReplaceConfirmation(false)
    setSmsProvisionError(null)
  }

  const closeSMSProvisionModal = (force = false) => {
    if (smsProvisioning && !force) return
    setSmsModalGarage(null)
    setSmsModalMode('provision')
    setSmsAreaCode('')
    setAttachPhoneSid('')
    setAttachEnableSMS(true)
    setAttachConfigureWebhooks(true)
    setReplaceConfirmation(false)
    setSmsProvisionError(null)
  }

  const handleSMSModalKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      closeSMSProvisionModal()
      return
    }

    if (e.key !== 'Tab' || !smsModalRef.current) return

    const focusable = smsModalRef.current.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )

    if (!focusable.length) return

    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    const active = document.activeElement

    if (e.shiftKey && active === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  const handleSetSMSEnabled = async (garage: Tenant, enabled: boolean) => {
    if (smsStateUpdatingGarageId) return

    if (!enabled) {
      const confirmed = window.confirm(`Disable SMS for ${garage.name}? You can enable it again later.`)
      if (!confirmed) return
    }

    try {
      setSmsStateUpdatingGarageId(garage.id)
      await api.put(`/admin/tenants/${garage.id}`, { sms_enabled: enabled })
      toast.success(enabled ? `Enabled SMS for ${garage.name}` : `Disabled SMS for ${garage.name}`)
      await fetchGarages('refresh')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || `Failed to ${enabled ? 'enable' : 'disable'} SMS`)
      console.error(err)
    } finally {
      setSmsStateUpdatingGarageId(null)
    }
  }

  const handleProvisionSMSNumber = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!smsModalGarage) return

    const replacingExistingNumber = Boolean(smsModalGarage.sms_phone_sid)
    if (replacingExistingNumber && !replaceConfirmation) {
      setSmsProvisionError('Please confirm that you want to replace the existing SMS number.')
      return
    }

    try {
      setSmsProvisioning(true)
      setSmsProvisionError(null)

      if (smsModalMode === 'provision') {
        const trimmedAreaCode = smsAreaCode.trim()
        let areaCode: number | undefined
        if (trimmedAreaCode) {
          if (!/^\d{3}$/.test(trimmedAreaCode)) {
            setSmsProvisionError('Area code must be exactly 3 digits (US only).')
            return
          }
          areaCode = Number.parseInt(trimmedAreaCode, 10)
        }

        const payload: { area_code?: number; replace_existing: boolean; country_code: string } = {
          replace_existing: replacingExistingNumber,
          country_code: 'US',
        }
        if (areaCode) {
          payload.area_code = areaCode
        }

        await api.post(`/admin/tenants/${smsModalGarage.id}/provision-sms-number`, payload)

        toast.success(
          replacingExistingNumber
            ? `Replaced SMS number for ${smsModalGarage.name}`
            : `Provisioned SMS number for ${smsModalGarage.name}`
        )
      } else {
        const sid = attachPhoneSid.trim()
        if (!sid) {
          setSmsProvisionError('Twilio Phone SID is required.')
          return
        }

        await api.post(`/admin/tenants/${smsModalGarage.id}/attach-sms-number`, {
          phone_sid: sid,
          enable_sms: attachEnableSMS,
          configure_webhooks: attachConfigureWebhooks,
          replace_existing: replacingExistingNumber,
        })

        toast.success(
          replacingExistingNumber
            ? `Attached and replaced SMS number for ${smsModalGarage.name}`
            : `Attached existing SMS number for ${smsModalGarage.name}`
        )
      }

      closeSMSProvisionModal(true)
      await fetchGarages('refresh')
    } catch (err: any) {
      setSmsProvisionError(err.response?.data?.detail || 'Failed to provision SMS number')
      console.error(err)
    } finally {
      setSmsProvisioning(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="xl" />
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
        <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
          <span className="text-gray-400">SMS</span>
          <span className="font-bold text-blue-400">{garages.filter(g => g.sms_enabled).length}</span>
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
        <div className="ml-auto flex items-center gap-2">
          {refreshing && (
            <span className="inline-flex items-center gap-2 text-xs text-gold-300 bg-gold-500/10 border border-gold-500/20 rounded-lg px-3 py-2">
              <Spinner size="xs" />
              Refreshing...
            </span>
          )}
          <GlassNoirButton onClick={() => alert('Create shop feature coming soon!')} className="whitespace-nowrap" size="sm">
            + New Shop
          </GlassNoirButton>
        </div>
      </div>

      {/* Shops List */}
      <div className="space-y-4">
        {garages.length === 0 ? (
          <GlassNoirCard className="text-center py-12">
            <Building2 className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">No shops found</p>
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
                  {garage.sms_enabled && (
                    <GlassNoirBadge variant="info">
                      <span className="whitespace-nowrap">SMS ✓</span>
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
                  <div className="flex items-start gap-2 text-xs sm:text-sm">
                    <MessageSquare className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                    <div className="min-w-0">
                      <div className={garage.sms_enabled ? 'text-green-400' : hasProvisionedSMSNumber(garage) ? 'text-amber-400' : 'text-gray-400'}>
                        SMS {garage.sms_enabled ? 'Enabled' : hasProvisionedSMSNumber(garage) ? 'Disabled' : 'Not provisioned'}
                      </div>
                      {garage.sms_phone_number && (
                        <div className="text-gray-300">{formatSMSPhoneNumber(garage.sms_phone_number)}</div>
                      )}
                      {garage.sms_phone_sid && (
                        <button
                          type="button"
                          onClick={() => setSmsDetailsOpenByGarageId(prev => ({ ...prev, [garage.id]: !prev[garage.id] }))}
                          className="mt-1 text-[11px] text-gold-400 hover:text-gold-300"
                        >
                          {smsDetailsOpenByGarageId[garage.id] ? 'Hide details' : 'Show details'}
                        </button>
                      )}
                      {garage.sms_phone_sid && smsDetailsOpenByGarageId[garage.id] && (
                        <div className="text-[11px] text-gray-500 font-mono break-all mt-1">
                          Twilio SID: {garage.sms_phone_sid}
                        </div>
                      )}
                    </div>
                  </div>
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
                  onClick={() => setTeamModalGarage(garage)}
                >
                  Manage Team
                </GlassNoirButton>
                <a
                  href={`/dashboard/garages/${garage.id}/analytics`}
                  className="px-3 sm:px-4 py-2 bg-gold-500 hover:bg-gold-400 text-black rounded-lg text-xs sm:text-sm font-semibold transition-colors whitespace-nowrap"
                >
                  View Analytics
                </a>
                <GlassNoirButton
                  variant={hasProvisionedSMSNumber(garage) ? 'ghost' : 'secondary'}
                  size="sm"
                  disabled={Boolean(smsStateUpdatingGarageId)}
                  onClick={() => openSMSProvisionModal(garage)}
                >
                  {hasProvisionedSMSNumber(garage) ? 'Manage SMS Number' : 'Set Up SMS Number'}
                </GlassNoirButton>
                {hasProvisionedSMSNumber(garage) && !garage.sms_enabled && (
                  <GlassNoirButton
                    variant="secondary"
                    size="sm"
                    disabled={Boolean(smsStateUpdatingGarageId)}
                    onClick={() => handleSetSMSEnabled(garage, true)}
                  >
                    <span className="inline-flex items-center gap-2">
                      {smsStateUpdatingGarageId === garage.id ? <Spinner size="xs" /> : null}
                      Enable SMS
                    </span>
                  </GlassNoirButton>
                )}
                {garage.sms_enabled && (
                  <GlassNoirButton
                    variant="ghost"
                    size="sm"
                    className="text-red-400 hover:bg-red-500/10"
                    disabled={Boolean(smsStateUpdatingGarageId)}
                    onClick={() => handleSetSMSEnabled(garage, false)}
                  >
                    <span className="inline-flex items-center gap-2">
                      {smsStateUpdatingGarageId === garage.id ? <Spinner size="xs" /> : null}
                      Disable SMS
                    </span>
                  </GlassNoirButton>
                )}
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

      {teamModalGarage && (
        <GarageTeamModal
          garageId={teamModalGarage.id}
          garageName={teamModalGarage.name}
          onClose={() => setTeamModalGarage(null)}
        />
      )}

      {smsModalGarage && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onKeyDown={handleSMSModalKeyDown}
          role="dialog"
          aria-modal="true"
          aria-labelledby="sms-modal-title"
          tabIndex={-1}
        >
          <div ref={smsModalRef} className="bg-noir-800 rounded-xl border border-gold-500/20 w-full max-w-lg shadow-2xl shadow-gold-500/10">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gold-500/20">
              <div>
                <h2 id="sms-modal-title" className="text-lg font-semibold text-white">
                  {smsModalMode === 'attach'
                    ? smsModalGarage.sms_phone_sid
                      ? 'Attach / Replace Existing SMS Number'
                      : 'Attach Existing SMS Number'
                    : smsModalGarage.sms_phone_sid
                      ? 'Replace SMS Number'
                      : 'Provision SMS Number'}
                </h2>
                <p className="text-sm text-gray-400">{smsModalGarage.name}</p>
              </div>
              <button
                type="button"
                onClick={() => closeSMSProvisionModal()}
                disabled={smsProvisioning}
                className="p-2 rounded-lg hover:bg-gold-500/10 text-gray-400 hover:text-gold-400 transition-colors disabled:opacity-50"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleProvisionSMSNumber} className="px-6 py-5 space-y-4">
              <div className="flex items-center gap-2 rounded-lg border border-gold-500/20 bg-black/30 p-2">
                <button
                  type="button"
                  onClick={() => {
                    setSmsModalMode('provision')
                    setSmsProvisionError(null)
                  }}
                  className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                    smsModalMode === 'provision' ? 'bg-gold-500 text-black font-semibold' : 'text-gray-300 hover:bg-white/10'
                  }`}
                >
                  Provision New
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSmsModalMode('attach')
                    setSmsProvisionError(null)
                  }}
                  className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                    smsModalMode === 'attach' ? 'bg-gold-500 text-black font-semibold' : 'text-gray-300 hover:bg-white/10'
                  }`}
                >
                  Attach Existing
                </button>
              </div>

              {smsModalGarage.sms_phone_number && (
                <div className="rounded-lg border border-gold-500/20 bg-black/30 p-3">
                  <p className="text-xs text-gold-400/80 uppercase tracking-wide">Current Number</p>
                  <p className="text-sm text-white mt-1">{formatSMSPhoneNumber(smsModalGarage.sms_phone_number)}</p>
                </div>
              )}

              {smsModalMode === 'provision' ? (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                  <p className="text-sm text-amber-200">
                    This will purchase a new phone number from Twilio. Standard Twilio rates apply.
                  </p>
                </div>
              ) : (
                <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-3">
                  <p className="text-sm text-blue-200">
                    Attach an already-purchased Twilio number by SID. The system will validate it and can configure webhooks automatically.
                  </p>
                </div>
              )}

              {smsModalGarage.sms_phone_sid && (
                <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                  <p className="text-xs text-red-300">
                    {smsModalMode === 'attach'
                      ? 'Replacing SMS will switch this shop to the attached Twilio number.'
                      : 'Replacing SMS will purchase another number and keep the old one unless it is released separately.'}
                  </p>
                </div>
              )}

              {smsModalMode === 'provision' ? (
                <div>
                  <label htmlFor="areaCode" className="block text-sm text-gray-300 mb-1">
                    Area Code (optional)
                  </label>
                  <input
                    ref={areaCodeInputRef}
                    id="areaCode"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{3}"
                    maxLength={3}
                    value={smsAreaCode}
                    onChange={(e) => {
                      setSmsAreaCode(e.target.value.replace(/\D/g, '').slice(0, 3))
                      if (smsProvisionError) setSmsProvisionError(null)
                    }}
                    placeholder="e.g. 305"
                    className="w-full px-3 py-2 bg-black/40 border border-gold-500/20 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-gold-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">Applies to US numbers only. Leave blank for any available US number.</p>
                </div>
              ) : (
                <>
                  <div>
                    <label htmlFor="attachPhoneSid" className="block text-sm text-gray-300 mb-1">
                      Twilio Phone SID
                    </label>
                    <input
                      id="attachPhoneSid"
                      type="text"
                      value={attachPhoneSid}
                      onChange={(e) => {
                        setAttachPhoneSid(e.target.value)
                        if (smsProvisionError) setSmsProvisionError(null)
                      }}
                      placeholder="PNxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                      className="w-full px-3 py-2 bg-black/40 border border-gold-500/20 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-gold-500 font-mono text-xs"
                    />
                  </div>
                  <label className="flex items-start gap-2 text-sm text-gray-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={attachConfigureWebhooks}
                      onChange={(e) => setAttachConfigureWebhooks(e.target.checked)}
                      className="mt-0.5 w-4 h-4 rounded border-gold-500/50 bg-black/40 text-gold-500 focus:ring-gold-500 focus:ring-offset-0"
                    />
                    <span>Configure inbound/status webhook URLs on this Twilio number</span>
                  </label>
                  <label className="flex items-start gap-2 text-sm text-gray-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={attachEnableSMS}
                      onChange={(e) => setAttachEnableSMS(e.target.checked)}
                      className="mt-0.5 w-4 h-4 rounded border-gold-500/50 bg-black/40 text-gold-500 focus:ring-gold-500 focus:ring-offset-0"
                    />
                    <span>Enable SMS immediately after attach</span>
                  </label>
                </>
              )}

              {smsModalGarage.sms_phone_sid && (
                <label className="flex items-start gap-2 text-sm text-gray-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={replaceConfirmation}
                    onChange={(e) => {
                      setReplaceConfirmation(e.target.checked)
                      if (smsProvisionError) setSmsProvisionError(null)
                    }}
                    className="mt-0.5 w-4 h-4 rounded border-gold-500/50 bg-black/40 text-gold-500 focus:ring-gold-500 focus:ring-offset-0"
                  />
                  <span>
                    I confirm this will replace the current SMS number for this shop.
                  </span>
                </label>
              )}

              {smsProvisionError && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                  {smsProvisionError}
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <GlassNoirButton
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => closeSMSProvisionModal()}
                  disabled={smsProvisioning}
                >
                  Cancel
                </GlassNoirButton>
                <GlassNoirButton type="submit" size="sm" disabled={smsProvisioning}>
                  <span className="inline-flex items-center gap-2">
                    {smsProvisioning ? (
                      <>
                        <Spinner size="xs" />
                        {smsModalMode === 'attach' ? 'Attaching...' : 'Provisioning...'}
                      </>
                    ) : smsModalMode === 'attach' ? (
                      smsModalGarage.sms_phone_sid ? 'Attach & Replace' : 'Attach Existing Number'
                    ) : smsModalGarage.sms_phone_sid ? (
                      'Replace SMS Number'
                    ) : (
                      'Provision SMS Number'
                    )}
                  </span>
                </GlassNoirButton>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
