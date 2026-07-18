import { useState } from 'react'
import { Spinner } from '@/components/ui'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { CheckCircle, XCircle, Truck, Wrench, AlertCircle } from 'lucide-react'
import { useAuthStore } from '../../stores/authStore'
import { getPasswordValidationError } from '../../lib/passwordPolicy'
import TenantBrandLogo from '../../components/brand/TenantBrandLogo'
import { usePlatformContact } from '../../hooks/usePlatformContact'

interface QuoteDetail {
  quote: {
    id: string
    quote_number: string
    total_amount: string
    is_approved: boolean
    is_declined: boolean
    decline_notes: string | null
    created_at: string
  }
  order_number: string
  order_description: string | null
  vehicle_year: number | null
  vehicle_make: string | null
  vehicle_model: string | null
  vehicle_vin: string | null
  customer_first_name: string
  services: Array<{ name: string; base_price: string; description?: string }>
  parts: Array<{ name: string; quantity: number; unit_price: string; total_price: string }>
  labor_total: string
  parts_total: string
  labor_discount_amount: string
  order_discount_amount: string
  shop_supplies_amount: string
  service_fee_amount: string
  tax_amount: string
  estimated_card_total: string
  estimated_zelle_total: string
  zelle_savings_amount: string
  shop_name: string | null
  shop_logo_url: string | null
  has_portal_account: boolean
  requires_password_setup: boolean
}

interface QuotePortalResolveResponse {
  has_portal_account: boolean
  requires_password_setup: boolean
  portal_enrollment_token: string
  portal_enrollment_expires_in: number
}

interface QuotePortalCreateResponse {
  access_token: string
  refresh_token: string
  token_type: string
  redirect_to: string
  user_exists: boolean
}

function QuotePageBrand({
  shopName,
  shopLogoUrl,
}: {
  shopName?: string | null
  shopLogoUrl?: string | null
}) {
  return (
    <div className="mb-2 flex justify-center">
      <TenantBrandLogo
        tenantLogoUrl={shopLogoUrl}
        tenantName={shopName}
        fallbackVariant="admin"
        className="h-12 sm:h-14 w-auto object-contain drop-shadow-[0_1px_2px_rgba(15,23,42,0.45)]"
      />
    </div>
  )
}

export default function QuoteApprovalPage() {
  const navigate = useNavigate()
  const { token } = useParams<{ token: string }>()
  const { login } = useAuthStore()
  const { supportEmail, supportPhoneDisplay, mailtoHref, telHref } = usePlatformContact()
  const [declineNotes, setDeclineNotes] = useState('')
  const [showDeclineForm, setShowDeclineForm] = useState(false)
  const [password, setPassword] = useState('')

  const getErrorDetail = (error: unknown, fallback: string): string => {
    if (error instanceof AxiosError) {
      const detail = error.response?.data?.detail
      return typeof detail === 'string' ? detail : fallback
    }
    return fallback
  }

  const { data, isLoading, error, refetch } = useQuery<QuoteDetail>({
    queryKey: ['quote-token', token],
    queryFn: async () => {
      const response = await api.get(`/quotes/token/${token}`)
      return response.data
    },
    enabled: !!token,
    retry: false,
  })

  const approveMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post(`/quotes/token/${token}/approve`)
      return response.data
    },
    onSuccess: () => {
      refetch()
    },
  })

  const declineMutation = useMutation({
    mutationFn: async (notes: string) => {
      const response = await api.post(`/quotes/token/${token}/decline`, { notes })
      return response.data
    },
    onSuccess: () => {
      refetch()
      setShowDeclineForm(false)
    },
  })

  const portalResolveMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post(`/quotes/token/${token}/portal-resolve`)
      return response.data as QuotePortalResolveResponse
    },
  })

  const createPortalMutation = useMutation({
    mutationFn: async (payload: { token: string; new_password?: string }) => {
      const response = await api.post('/quotes/portal/create', payload)
      return response.data as QuotePortalCreateResponse
    },
    onSuccess: async (data) => {
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
      const userResponse = await api.get('/auth/me')
      login(data.access_token, data.refresh_token, userResponse.data)
      navigate(data.redirect_to)
    },
  })

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <Spinner size="xl" />
          <p className="text-gray-400 mt-4">Loading quote...</p>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
        <div className="bg-white/5 rounded-2xl border border-white/10 p-8 max-w-md w-full text-center">
          <QuotePageBrand />
          <AlertCircle className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-white mb-2">Quote Not Found</h1>
          <p className="text-gray-400 mb-6">
            This link may have expired or the quote has already been processed.
          </p>
          <Link
            to="/login"
            className="inline-block px-6 py-3 bg-amber-500 hover:bg-amber-600 text-white font-medium rounded-lg transition-colors"
          >
            Go to Login
          </Link>
        </div>
      </div>
    )
  }

  const {
    quote,
    order_number,
    order_description,
    vehicle_year,
    vehicle_make,
    vehicle_model,
    vehicle_vin,
    customer_first_name,
    services,
    parts,
    labor_total,
    parts_total,
    labor_discount_amount,
    order_discount_amount,
    shop_supplies_amount,
    service_fee_amount,
    tax_amount,
    estimated_card_total,
    estimated_zelle_total,
    zelle_savings_amount,
  } = data
  const vehicleInfo = vehicle_year && vehicle_make && vehicle_model
    ? `${vehicle_year} ${vehicle_make} ${vehicle_model}`
    : null
  const passwordValidationError = password ? getPasswordValidationError(password) : null
  const portalActionPending = portalResolveMutation.isPending || createPortalMutation.isPending

  const openPortalFromApprovedState = async (newPassword?: string) => {
    if (!token) return

    if (typeof newPassword === 'string') {
      const validationError = getPasswordValidationError(newPassword)
      if (validationError) {
        toast.error(validationError)
        return
      }
    }

    try {
      const resolveData = await portalResolveMutation.mutateAsync()
      if (!resolveData.has_portal_account && !newPassword) {
        toast.error('Please set a password to create your portal account.')
        return
      }
      await createPortalMutation.mutateAsync(
        newPassword
          ? { token: resolveData.portal_enrollment_token, new_password: newPassword }
          : { token: resolveData.portal_enrollment_token }
      )
    } catch (err: unknown) {
      toast.error(getErrorDetail(err, 'Unable to open portal from this quote link.'))
    }
  }

  // Already approved
  if (quote.is_approved) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
        <div className="bg-white/5 rounded-2xl border border-white/10 p-8 max-w-md w-full text-center">
          <QuotePageBrand shopName={data.shop_name} shopLogoUrl={data.shop_logo_url} />
          <div className="w-20 h-20 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle className="w-10 h-10 text-green-400" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Quote Approved!</h1>
          <p className="text-gray-400 mb-2">
            Thank you, {customer_first_name}! Your quote <strong className="text-white">{quote.quote_number}</strong> has been approved.
          </p>
          <p className="text-gray-500 text-sm mb-6">
            We'll get started on your repair soon. You'll receive updates via text.
          </p>
          {data.has_portal_account ? (
            <div className="space-y-3">
              <button
                onClick={() => openPortalFromApprovedState()}
                disabled={portalActionPending}
                className="w-full px-6 py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors"
              >
                {portalActionPending ? 'Opening...' : 'Open My Portal'}
              </button>
              <button
                type="button"
                onClick={() => navigate('/')}
                className="w-full py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
              >
                Exit
              </button>
            </div>
          ) : (
            <div className="space-y-3 text-left">
              <label className="block text-sm text-gray-300">
                Create your portal password to track this repair and future invoices.
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={`w-full px-4 py-3 border rounded-lg bg-white text-gray-900 placeholder-gray-500 ${
                  passwordValidationError ? 'border-red-400' : 'border-gray-300'
                }`}
                placeholder="8+ chars, upper/lower/digit/special"
              />
              {passwordValidationError ? (
                <p className="text-xs text-red-400">{passwordValidationError}</p>
              ) : (
                <p className="text-xs text-gray-400">
                  Must include uppercase, lowercase, number, and special character.
                </p>
              )}
              <button
                onClick={() => openPortalFromApprovedState(password)}
                disabled={!password || !!passwordValidationError || portalActionPending}
                className="w-full px-6 py-3 bg-amber-500 hover:bg-amber-600 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors"
              >
                {portalActionPending ? 'Creating...' : 'Create Portal Account'}
              </button>
              <button
                type="button"
                onClick={() => navigate('/')}
                className="w-full py-2 text-sm text-gray-400 hover:text-gray-200 transition-colors text-center"
              >
                Exit
              </button>
            </div>
          )}
          {(supportPhoneDisplay || supportEmail) && (
            <p className="text-gray-500 text-xs mt-4">
              Need help?{' '}
              {supportPhoneDisplay && telHref && (
                <>
                  <a className="text-amber-300 hover:text-amber-200 font-medium underline" href={telHref}>
                    {supportPhoneDisplay}
                  </a>
                </>
              )}
              {supportPhoneDisplay && supportEmail && ' • '}
              {supportEmail && mailtoHref && (
                <a className="text-amber-300 hover:text-amber-200 font-medium underline" href={mailtoHref}>
                  {supportEmail}
                </a>
              )}
            </p>
          )}
        </div>
      </div>
    )
  }

  // Already declined
  if (quote.is_declined) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
        <div className="bg-white/5 rounded-2xl border border-white/10 p-8 max-w-lg w-full text-center">
          <QuotePageBrand shopName={data.shop_name} shopLogoUrl={data.shop_logo_url} />
          <div className="w-20 h-20 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
            <XCircle className="w-10 h-10 text-red-400" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">Quote Declined</h1>
          <p className="text-gray-400 mb-4">
            You've declined quote <strong className="text-white">{quote.quote_number}</strong>.
          </p>
          {quote.decline_notes && (
            <div className="bg-white/5 rounded-lg p-4 mb-4 text-left">
              <p className="text-sm text-gray-500 mb-1">Your notes:</p>
              <p className="text-gray-300">{quote.decline_notes}</p>
            </div>
          )}
          <p className="text-gray-500 text-sm mb-6">
            We'll review your feedback and may reach out with a revised quote.
          </p>
          <div className="flex flex-col gap-3">
            <button
              onClick={() => approveMutation.mutate()}
              disabled={approveMutation.isPending}
              className="px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors"
            >
              {approveMutation.isPending ? 'Processing...' : 'Changed my mind - Approve Quote'}
            </button>
            <Link
              to="/portal"
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors text-center"
            >
              Go to My Portal
            </Link>
          </div>
          {(supportPhoneDisplay || supportEmail) && (
            <p className="text-gray-500 text-xs mt-4">
              Need help?{' '}
              {supportPhoneDisplay && telHref && (
                <>
                  <a className="text-amber-300 hover:text-amber-200 font-medium underline" href={telHref}>
                    {supportPhoneDisplay}
                  </a>
                </>
              )}
              {supportPhoneDisplay && supportEmail && ' • '}
              {supportEmail && mailtoHref && (
                <a className="text-amber-300 hover:text-amber-200 font-medium underline" href={mailtoHref}>
                  {supportEmail}
                </a>
              )}
            </p>
          )}
        </div>
      </div>
    )
  }

  // Pending - show approval form
  return (
    <div className="min-h-screen bg-gray-900 py-8 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <QuotePageBrand shopName={data.shop_name} shopLogoUrl={data.shop_logo_url} />
          <p className="text-gray-400">Quote Approval</p>
        </div>

        {/* Quote Card */}
        <div className="bg-white/5 rounded-2xl border border-white/10 overflow-hidden">
          {/* Greeting */}
          <div className="p-6 border-b border-white/10">
            <h2 className="text-xl font-semibold text-white">
              Hi {customer_first_name}, your quote is ready!
            </h2>
            <p className="text-gray-400 mt-1">Please review the details below.</p>
          </div>

          {/* Quote Details */}
          <div className="p-6 space-y-4">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-sm text-gray-500">Quote Number</p>
                <p className="text-lg font-medium text-white">{quote.quote_number}</p>
              </div>
              <div className="text-right">
                <p className="text-sm text-gray-500">Order Number</p>
                <p className="text-lg font-medium text-white">{order_number}</p>
              </div>
            </div>

            {/* Vehicle */}
            {vehicleInfo && (
              <div className="bg-white/5 rounded-lg p-4 flex items-center gap-3">
                <div className="w-10 h-10 bg-cyan-500/20 rounded-lg flex items-center justify-center">
                  <Truck className="w-5 h-5 text-cyan-400" />
                </div>
                <div>
                  <p className="text-sm text-gray-500">Vehicle</p>
                  <p className="text-white font-medium">{vehicleInfo}</p>
                  {vehicle_vin && (
                    <p className="text-xs text-gray-500">VIN: ...{vehicle_vin.slice(-6)}</p>
                  )}
                </div>
              </div>
            )}

            {/* Description */}
            {order_description && (
              <div>
                <p className="text-sm text-gray-500 mb-1">Description</p>
                <p className="text-gray-300">{order_description}</p>
              </div>
            )}

            {/* Services */}
            {services.length > 0 && (
              <div>
                <p className="text-sm text-gray-500 mb-2">Services / Labor</p>
                <div className="space-y-2">
                  {services.map((svc, idx) => (
                    <div
                      key={idx}
                      className="bg-white/5 rounded-lg p-3 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <Wrench className="w-4 h-4 text-amber-400" />
                        <div>
                          <p className="text-white font-medium">{svc.name}</p>
                          {svc.description && (
                            <p className="text-xs text-gray-500">{svc.description}</p>
                          )}
                        </div>
                      </div>
                      <p className="text-white font-medium">
                        ${parseFloat(svc.base_price).toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Parts */}
            {parts.length > 0 && (
              <div>
                <p className="text-sm text-gray-500 mb-2">Parts</p>
                <div className="space-y-2">
                  {parts.map((part, idx) => (
                    <div
                      key={`${part.name}-${idx}`}
                      className="bg-white/5 rounded-lg p-3 flex items-center justify-between"
                    >
                      <div>
                        <p className="text-white font-medium">{part.name}</p>
                        <p className="text-xs text-gray-500">Qty {part.quantity} · ${parseFloat(part.unit_price).toFixed(2)} each</p>
                      </div>
                      <p className="text-white font-medium">
                        ${parseFloat(part.total_price).toFixed(2)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Breakdown */}
            <div className="bg-white/5 rounded-lg p-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Labor / Services</span>
                <span className="text-white">${parseFloat(labor_total || '0').toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm mt-1">
                <span className="text-gray-400">Parts</span>
                <span className="text-white">${parseFloat(parts_total || '0').toFixed(2)}</span>
              </div>
              {parseFloat(labor_discount_amount || '0') > 0 && (
                <div className="flex justify-between text-sm mt-1">
                  <span className="text-emerald-300">Labor discount</span>
                  <span className="text-emerald-300">-${parseFloat(labor_discount_amount || '0').toFixed(2)}</span>
                </div>
              )}
              {parseFloat(order_discount_amount || '0') > 0 && (
                <div className="flex justify-between text-sm mt-1">
                  <span className="text-emerald-300">Order discount</span>
                  <span className="text-emerald-300">-${parseFloat(order_discount_amount || '0').toFixed(2)}</span>
                </div>
              )}
            </div>

            {/* Total */}
            <div className="bg-amber-500/10 rounded-xl p-6 text-center border border-amber-500/30">
              <p className="text-sm text-amber-400 mb-1">Repair total</p>
              <p className="text-4xl font-bold text-white">
                ${parseFloat(quote.total_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div className="bg-white/5 rounded-xl p-4 border border-white/10">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-wide text-amber-300">Estimated checkout total</p>
                  <p className="text-xs text-gray-400">Includes estimated shop supplies, card processing fee, and tax.</p>
                </div>
              </div>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Repair total</span>
                  <span className="text-white">${parseFloat(quote.total_amount || '0').toFixed(2)}</span>
                </div>
                {parseFloat(shop_supplies_amount || '0') > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Shop supplies</span>
                    <span className="text-white">${parseFloat(shop_supplies_amount || '0').toFixed(2)}</span>
                  </div>
                )}
                {parseFloat(service_fee_amount || '0') > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Card processing fee</span>
                    <span className="text-white">${parseFloat(service_fee_amount || '0').toFixed(2)}</span>
                  </div>
                )}
                {parseFloat(tax_amount || '0') > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Estimated tax</span>
                    <span className="text-white">${parseFloat(tax_amount || '0').toFixed(2)}</span>
                  </div>
                )}
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Pay by card</p>
                  <p className="text-xl font-bold text-white">${parseFloat(estimated_card_total || quote.total_amount || '0').toFixed(2)}</p>
                </div>
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3">
                  <p className="text-xs uppercase tracking-wide text-emerald-300">Pay by Zelle</p>
                  <p className="text-xl font-bold text-emerald-200">${parseFloat(estimated_zelle_total || quote.total_amount || '0').toFixed(2)}</p>
                  {parseFloat(zelle_savings_amount || '0') > 0 && (
                    <p className="mt-1 text-xs font-semibold text-emerald-300">
                      Save ${parseFloat(zelle_savings_amount || '0').toFixed(2)}
                    </p>
                  )}
                </div>
              </div>
              <p className="mt-3 text-xs text-gray-500">Final payment total may vary if the invoice changes before checkout.</p>
            </div>
          </div>

          {/* Actions */}
          <div className="p-6 border-t border-white/10 bg-white/[0.02]">
            {showDeclineForm ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-2">
                    Please let us know why you're declining (optional)
                  </label>
                  <textarea
                    value={declineNotes}
                    onChange={(e) => setDeclineNotes(e.target.value)}
                    placeholder="e.g., Price too high, need different services, etc."
                    className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 resize-none"
                    rows={3}
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => setShowDeclineForm(false)}
                    className="flex-1 px-4 py-3 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => declineMutation.mutate(declineNotes)}
                    disabled={declineMutation.isPending}
                    className="flex-1 px-4 py-3 bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors"
                  >
                    {declineMutation.isPending ? 'Submitting...' : 'Confirm Decline'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-3">
                <button
                  onClick={() => setShowDeclineForm(true)}
                  className="flex-1 px-4 py-3 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  <XCircle className="w-5 h-5" />
                  Decline
                </button>
                <button
                  onClick={() => approveMutation.mutate()}
                  disabled={approveMutation.isPending}
                  className="flex-1 px-4 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {approveMutation.isPending ? (
                    <>
                      <Spinner size="sm" />
                      Approving...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-5 h-5" />
                      Approve Quote
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-gray-500 text-sm mt-6 space-y-1">
          <p>Questions? Contact platform support and reference quote {quote.quote_number}.</p>
          {(supportPhoneDisplay || supportEmail) && (
            <p className="text-gray-400">
              {supportPhoneDisplay && telHref && (
                <>
                  Phone:{' '}
                  <a className="text-amber-300 hover:text-amber-200 font-medium underline" href={telHref}>
                    {supportPhoneDisplay}
                  </a>
                </>
              )}
              {supportPhoneDisplay && supportEmail && ' • '}
              {supportEmail && mailtoHref && (
                <>
                  Email:{' '}
                  <a className="text-amber-300 hover:text-amber-200 font-medium underline" href={mailtoHref}>
                    {supportEmail}
                  </a>
                </>
              )}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
