import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { CreditCard, Lock, FileText, UserPlus, Download, Printer, Copy, Check } from 'lucide-react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { getStripeForAccount } from '../../lib/stripe'
import { getPasswordValidationError } from '../../lib/passwordPolicy'
import { useAuthStore } from '../../stores/authStore'
import TenantBrandLogo from '@/components/brand/TenantBrandLogo'

interface InvoiceAccessResolve {
  invoice_id: string
  invoice_number: string
  order_number: string
  customer_name: string
  vehicle_info: string
  shop_name: string | null
  shop_logo_url: string | null
  amount_due: string
  subtotal: string
  shop_supplies_amount: string
  service_fee_amount: string
  tax_amount: string
  discount_amount: string
  total_amount: string
  zelle_amount: string
  status: string
  due_date: string | null
  paid_at: string | null
  is_paid: boolean
  pending_zelle_confirmation: boolean
  zelle_email: string | null
  zelle_phone: string | null
  zelle_qr_image: string | null
  has_portal_account: boolean
  requires_password_setup: boolean
}

interface PaymentIntentResponse {
  client_secret: string
  stripe_account_id: string | null
}

interface ConfirmGuestPaymentResponse {
  status: string
  message: string
  invoice_id: string
  paid_at: string | null
  portal_enrollment_token: string | null
  portal_enrollment_expires_in: number | null
  payment_note?: string | null
}

interface CreatePortalResponse {
  access_token: string
  refresh_token: string
  token_type: string
  redirect_to: string
  user_exists: boolean
}

interface SubmitGuestZellePaymentResponse {
  status: string
  message: string
  pending_zelle_confirmation: boolean
}

const getErrorDetail = (error: unknown, fallback: string): string => {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    return typeof detail === 'string' ? detail : fallback
  }
  return fallback
}

const formatMoney = (value: string) => `$${parseFloat(value).toFixed(2)}`

function GuestPaymentForm({
  token,
  onSuccess,
}: {
  token: string
  onSuccess: (result: ConfirmGuestPaymentResponse) => void
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return

    setIsProcessing(true)
    setError(null)

    const { error: submitError, paymentIntent } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.href },
      redirect: 'if_required',
    })

    if (submitError) {
      setError(submitError.message || 'Payment failed')
      setIsProcessing(false)
      return
    }

    if (paymentIntent && paymentIntent.status === 'succeeded') {
      try {
        const response = await api.post('/invoice-access/confirm-payment', {
          token,
          payment_intent_id: paymentIntent.id,
        })
        const result = response.data as ConfirmGuestPaymentResponse
        toast.success(result.payment_note || 'Payment successful!')
        onSuccess(result)
      } catch (err: unknown) {
        setError(getErrorDetail(err, 'Payment confirmed but update failed. Please contact the shop.'))
      }
    }

    setIsProcessing(false)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <PaymentElement />
      {error && <div className="text-red-600 text-sm bg-red-50 p-3 rounded-lg border border-red-200">{error}</div>}
      <button
        type="submit"
        disabled={!stripe || isProcessing}
        className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
      >
        {isProcessing ? (
          <>
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
            Processing...
          </>
        ) : (
          <>
            <CreditCard className="w-5 h-5" />
            Pay Now
          </>
        )}
      </button>
    </form>
  )
}

function PortalEnrollmentSection({
  hasPortalAccount,
  isPending,
  canUsePortalToken,
  password,
  passwordValidationError,
  onPasswordChange,
  onOpenPortal,
  onCreatePortal,
  showTokenWarning = false,
}: {
  hasPortalAccount: boolean
  isPending: boolean
  canUsePortalToken: boolean
  password: string
  passwordValidationError: string | null
  onPasswordChange: (value: string) => void
  onOpenPortal: () => void
  onCreatePortal: () => void
  showTokenWarning?: boolean
}) {
  return (
    <section className="border-t pt-6">
      <h3 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
        <UserPlus className="w-5 h-5 text-amber-600" />
        Create or Open Portal (Optional)
      </h3>
      <p className="text-sm text-gray-600 mb-3">
        Track service history, manage profile, and pay future invoices faster.
      </p>

      {hasPortalAccount ? (
        <button
          onClick={onOpenPortal}
          disabled={isPending || !canUsePortalToken}
          className="w-full py-3 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-400 text-white font-semibold rounded-lg"
        >
          {isPending ? 'Opening portal...' : 'Open My Portal'}
        </button>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Set Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-3.5" />
              <input
                type="password"
                value={password}
                onChange={(e) => onPasswordChange(e.target.value)}
                className={`w-full pl-9 pr-3 py-2.5 border rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-amber-500 ${
                  passwordValidationError ? 'border-red-300 bg-red-50/30' : 'border-gray-300'
                }`}
                placeholder="8+ chars, upper/lower/digit/special"
              />
            </div>
            {passwordValidationError ? (
              <p className="text-xs text-red-600 mt-1">{passwordValidationError}</p>
            ) : (
              <p className="text-xs text-gray-500 mt-1">
                Must include uppercase, lowercase, number, and special character.
              </p>
            )}
          </div>
          <button
            onClick={onCreatePortal}
            disabled={!password || !!passwordValidationError || isPending || !canUsePortalToken}
            className="w-full py-3 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-400 text-white font-semibold rounded-lg"
          >
            {isPending ? 'Creating account...' : 'Create Portal Account'}
          </button>
        </div>
      )}

      {showTokenWarning && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3 mt-3">
          Payment was recorded, but portal enrollment token could not be issued. Contact the shop for a new portal link.
        </p>
      )}
    </section>
  )
}

export default function InvoiceAccessPage() {
  const { token } = useParams<{ token: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { login } = useAuthStore()
  const [password, setPassword] = useState('')
  const [stripeOptions, setStripeOptions] = useState<{ clientSecret: string; appearance: object } | null>(null)
  const [stripeInstance, setStripeInstance] = useState<Stripe | null>(null)
  const [showPayment, setShowPayment] = useState(false)
  const [zelleNotes, setZelleNotes] = useState('')
  const [showZelleNote, setShowZelleNote] = useState(false)
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [paymentResult, setPaymentResult] = useState<{
    paidAt: string | null
    portalEnrollmentToken: string | null
  } | null>(null)

  const {
    data: invoice,
    isLoading,
    error,
  } = useQuery<InvoiceAccessResolve>({
    queryKey: ['invoice-access', token],
    queryFn: async () => {
      const response = await api.post('/invoice-access/resolve', { token })
      return response.data as InvoiceAccessResolve
    },
    enabled: !!token,
    retry: false,
  })

  const paidInThisSession = paymentResult !== null
  const isPaid = !!invoice && (invoice.is_paid || paidInThisSession)
  const paidAt = paymentResult?.paidAt ?? invoice?.paid_at ?? null
  const portalTokenForCreate = paidInThisSession
    ? paymentResult?.portalEnrollmentToken ?? null
    : token
  const passwordValidationError = password ? getPasswordValidationError(password) : null
  const shopContact = (() => {
    const params = new URLSearchParams(location.search)
    const shopName = params.get('shop_name')?.trim() || null
    const shopEmailRaw = params.get('shop_email')?.trim() || null
    const shopPhoneRaw = params.get('shop_phone')?.trim() || null
    const shopLogoUrl = params.get('shop_logo_url')?.trim() || null
    const shopEmail =
      shopEmailRaw && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(shopEmailRaw) ? shopEmailRaw : null
    const normalizedPhone = shopPhoneRaw ? shopPhoneRaw.replace(/[^\d+]/g, '') : null
    const shopPhone =
      normalizedPhone && normalizedPhone.replace(/\D/g, '').length >= 10 ? shopPhoneRaw : null
    const telHref = shopPhone && normalizedPhone ? `tel:${normalizedPhone}` : null
    return { shopName, shopEmail, shopPhone, shopLogoUrl, telHref }
  })()
  const pageBrandName = invoice?.shop_name || shopContact.shopName || 'Diesel Bridge Network'
  const pageBrandLogoUrl = invoice?.shop_logo_url || shopContact.shopLogoUrl || null

  const createIntentMutation = useMutation({
    mutationFn: async (tokenValue: string) => {
      const response = await api.post('/invoice-access/create-payment-intent', { token: tokenValue })
      return response.data as PaymentIntentResponse
    },
    onSuccess: async (data) => {
      const stripe = await getStripeForAccount(data.stripe_account_id)
      setStripeInstance(stripe)
      setStripeOptions({
        clientSecret: data.client_secret,
        appearance: {
          theme: 'stripe',
          variables: {
            colorPrimary: '#16a34a',
            borderRadius: '8px',
          },
        },
      })
      setShowPayment(true)
    },
    onError: (err: unknown) => {
      toast.error(getErrorDetail(err, 'Unable to start checkout'))
    },
  })

  const createPortalMutation = useMutation({
    mutationFn: async (payload: { token: string; new_password?: string }) => {
      const response = await api.post('/invoice-access/create-portal', payload)
      return response.data as CreatePortalResponse
    },
    onSuccess: async (data) => {
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
      const userResponse = await api.get('/auth/me')
      login(data.access_token, data.refresh_token, userResponse.data)
      navigate(data.redirect_to)
    },
    onError: (err: unknown) => {
      toast.error(getErrorDetail(err, 'Unable to open portal'))
    },
  })

  const submitZelleMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/invoice-access/submit-zelle', {
        token,
        notes: zelleNotes.trim() || null,
      })
      return response.data as SubmitGuestZellePaymentResponse
    },
    onSuccess: (data) => {
      toast.success(data.message || 'Zelle payment submitted')
      queryClient.invalidateQueries({ queryKey: ['invoice-access', token] })
      setZelleNotes('')
      setShowZelleNote(false)
    },
    onError: (err: unknown) => {
      toast.error(getErrorDetail(err, 'Unable to submit Zelle payment'))
    },
  })

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(key)
      setTimeout(() => setCopiedKey(null), 2000)
    })
  }

  const openPortalFromCurrentFlow = (newPassword?: string) => {
    if (!portalTokenForCreate) {
      toast.error('Portal enrollment is not available for this link. Please contact the shop.')
      return
    }
    if (typeof newPassword === 'string') {
      const validationError = getPasswordValidationError(newPassword)
      if (validationError) {
        toast.error(validationError)
        return
      }
    }
    createPortalMutation.mutate(
      newPassword
        ? { token: portalTokenForCreate, new_password: newPassword }
        : { token: portalTokenForCreate }
    )
  }

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-md text-center bg-white p-8 rounded-xl shadow-md border">
          <p className="text-red-600 font-medium">Invalid invoice link.</p>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  if (error || !invoice) {
    let title = 'Invoice Link Unavailable'
    let detail = getErrorDetail(error, 'This link may be expired or invalid. Please request a fresh invoice link.')
    if (error instanceof AxiosError) {
      if (error.response?.status === 410) {
        title = 'Invoice Link Already Used'
        detail = 'This link has already been used. Please contact the shop for a fresh invoice link.'
      } else if (error.response?.status === 400) {
        title = 'Invoice Link Expired'
        detail = 'This link is expired or invalid. Please contact the shop to resend your invoice.'
      }
    }

    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-amber-50 to-yellow-100 flex items-center justify-center px-4">
        <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl border border-red-200 p-8">
          <div className="mb-6 flex justify-center">
            <TenantBrandLogo
              tenantLogoUrl={pageBrandLogoUrl}
              tenantName={pageBrandName}
              fallbackVariant="admin"
              className="h-12 w-auto object-contain drop-shadow-[0_1px_2px_rgba(15,23,42,0.35)]"
            />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-3">{title}</h1>
          <p className="text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">{detail}</p>
          <div className="mt-4 space-y-2">
            <p className="text-sm text-gray-600">
              Please contact {shopContact.shopName || 'the shop'} and ask them to resend your invoice link.
            </p>
            {shopContact.shopPhone || shopContact.shopEmail ? (
              <div className="text-sm text-gray-700 bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
                <p className="font-medium text-amber-900">Shop contact</p>
                {shopContact.shopPhone && shopContact.telHref && (
                  <p>
                    Phone:{' '}
                    <a className="text-amber-800 font-medium underline" href={shopContact.telHref}>
                      {shopContact.shopPhone}
                    </a>
                  </p>
                )}
                {shopContact.shopEmail && (
                  <p>
                    Email:{' '}
                    <a className="text-amber-800 font-medium underline" href={`mailto:${shopContact.shopEmail}`}>
                      {shopContact.shopEmail}
                    </a>
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs text-gray-500">
                If contact details are not shown here, reply to the original invoice email or SMS from the shop.
              </p>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-amber-50 to-yellow-100 py-8 px-4">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="text-center">
          <div className="mb-4 flex justify-center">
            <TenantBrandLogo
              tenantLogoUrl={pageBrandLogoUrl}
              tenantName={pageBrandName}
              fallbackVariant="admin"
              className="h-12 sm:h-14 w-auto object-contain drop-shadow-[0_1px_2px_rgba(15,23,42,0.35)]"
            />
          </div>
          <h1 className="text-3xl font-bold text-gray-900">Invoice {invoice.invoice_number}</h1>
          <p className="text-gray-600 mt-1">
            Order {invoice.order_number}
            {invoice.due_date ? ` • Due ${format(new Date(invoice.due_date), 'MMM d, yyyy')}` : ''}
          </p>
          <div className="flex gap-2 mt-3 print:hidden">
            <a
              href={`/api/v1/invoice-access/pdf/${token}`}
              download
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100"
            >
              <Download className="w-4 h-4" />
              Download PDF
            </a>
            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100"
            >
              <Printer className="w-4 h-4" />
              Print
            </button>
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-xl border border-amber-100 p-6">
          <div className="flex items-center gap-3 mb-4">
            <FileText className="w-6 h-6 text-amber-600" />
            <div>
              <h2 className="text-xl font-semibold text-gray-900">{invoice.customer_name}</h2>
              <p className="text-sm text-gray-600">{invoice.vehicle_info}</p>
            </div>
          </div>

          <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between">
              <span className="text-gray-700 font-medium">Amount Due</span>
              <span className="text-3xl font-bold text-gray-900">{formatMoney(invoice.amount_due)}</span>
            </div>
            <p className="text-xs text-gray-500 mt-2">Status: {invoice.status.replace('_', ' ')}</p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Invoice Breakdown</h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between text-gray-700">
                <span>Subtotal</span>
                <span>{formatMoney(invoice.subtotal)}</span>
              </div>
              <div className="flex items-center justify-between text-gray-700">
                <span>Shop Supplies</span>
                <span>{formatMoney(invoice.shop_supplies_amount)}</span>
              </div>
              <div className="flex items-center justify-between text-gray-700">
                <span>Service Fee</span>
                <span>{formatMoney(invoice.service_fee_amount)}</span>
              </div>
              <div className="flex items-center justify-between text-gray-700">
                <span>Tax</span>
                <span>{formatMoney(invoice.tax_amount)}</span>
              </div>
              <div className="flex items-center justify-between text-green-700">
                <span>Discount</span>
                <span>-{formatMoney(invoice.discount_amount)}</span>
              </div>
              <div className="pt-2 border-t border-gray-200 flex items-center justify-between text-gray-900 font-semibold">
                <span>Total</span>
                <span>{formatMoney(invoice.total_amount)}</span>
              </div>
            </div>
          </div>

          {isPaid ? (
            <section className="space-y-6">
              <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-green-800">
                <p className="font-semibold">Payment received.</p>
                <p className="text-sm mt-1">
                  This invoice is already paid
                  {paidAt ? ` on ${format(new Date(paidAt), 'MMM d, yyyy')}` : ''}.
                </p>
              </div>
              <PortalEnrollmentSection
                hasPortalAccount={invoice.has_portal_account}
                isPending={createPortalMutation.isPending}
                canUsePortalToken={!!portalTokenForCreate}
                password={password}
                passwordValidationError={passwordValidationError}
                onPasswordChange={setPassword}
                onOpenPortal={() => openPortalFromCurrentFlow()}
                onCreatePortal={() => openPortalFromCurrentFlow(password)}
                showTokenWarning={paidInThisSession && !portalTokenForCreate}
              />
            </section>
          ) : (
            <div className="space-y-6">
              <section className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                <h3 className="font-semibold text-blue-900 mb-1">Pay with Zelle</h3>
                {parseFloat(invoice.service_fee_amount) > 0 && (
                  <p className="text-xs text-blue-700 font-medium mb-3">
                    Save ${parseFloat(invoice.service_fee_amount).toFixed(2)} — no processing fee
                  </p>
                )}

                {/* Copyable amount */}
                <div className="mb-3">
                  <p className="text-xs text-blue-700 mb-1 font-medium">Send exact amount</p>
                  <div className="flex items-center gap-2 bg-white border border-blue-200 rounded-lg px-3 py-2">
                    <span className="font-bold text-gray-900 flex-1 text-lg">{formatMoney(invoice.zelle_amount)}</span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(parseFloat(invoice.zelle_amount).toFixed(2), 'amount')}
                      className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium"
                    >
                      {copiedKey === 'amount' ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                      {copiedKey === 'amount' ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </div>

                {/* Zelle contact details block */}
                {(invoice.zelle_email || invoice.zelle_phone) && (
                  <div className="mb-3 bg-white border border-blue-200 rounded-lg divide-y divide-blue-100">
                    {invoice.zelle_email && (
                      <div className="flex items-center gap-2 px-3 py-2">
                        <span className="text-sm text-gray-700 flex-1 truncate">{invoice.zelle_email}</span>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(invoice.zelle_email!, 'email')}
                          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium shrink-0"
                        >
                          {copiedKey === 'email' ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                          {copiedKey === 'email' ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                    )}
                    {invoice.zelle_phone && (
                      <div className="flex items-center gap-2 px-3 py-2">
                        <span className="text-sm text-gray-700 flex-1">{invoice.zelle_phone}</span>
                        <button
                          type="button"
                          onClick={() => copyToClipboard(invoice.zelle_phone!, 'phone')}
                          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium shrink-0"
                        >
                          {copiedKey === 'phone' ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                          {copiedKey === 'phone' ? 'Copied' : 'Copy'}
                        </button>
                      </div>
                    )}
                  </div>
                )}

                <p className="text-xs text-blue-700 mb-3">
                  Include <strong>#{invoice.invoice_number}</strong> in the Zelle memo.
                </p>

                {invoice.zelle_qr_image && (
                  <div className="bg-white border border-blue-100 rounded-lg p-3 mb-3 flex justify-center">
                    <img src={invoice.zelle_qr_image} alt="Zelle QR" className="w-44 h-44 object-contain" />
                  </div>
                )}

                {invoice.pending_zelle_confirmation ? (
                  <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-yellow-900 text-sm">
                    Payment is marked as submitted via Zelle and is pending staff confirmation.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {!showZelleNote ? (
                      <button
                        type="button"
                        onClick={() => setShowZelleNote(true)}
                        className="text-xs text-blue-600 underline underline-offset-2"
                      >
                        Add a note for garage staff (optional)
                      </button>
                    ) : (
                      <textarea
                        value={zelleNotes}
                        onChange={(e) => setZelleNotes(e.target.value)}
                        rows={2}
                        placeholder="Optional note for garage staff"
                        className="w-full px-3 py-2 border border-blue-200 rounded-lg text-sm resize-none"
                      />
                    )}
                    <button
                      onClick={() => submitZelleMutation.mutate()}
                      disabled={submitZelleMutation.isPending}
                      className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold rounded-lg"
                    >
                      {submitZelleMutation.isPending ? 'Submitting...' : 'I Sent Payment via Zelle'}
                    </button>
                    <p className="text-xs text-blue-700">
                      Staff will confirm receipt. If unconfirmed, they receive reminders at 24h and 48h.
                    </p>
                  </div>
                )}
              </section>

              {invoice.has_portal_account ? (
                <>
                  <section className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                    <h3 className="font-semibold text-amber-900 mb-1">Portal Payment Required</h3>
                    <p className="text-sm text-amber-800">
                      This invoice is linked to your customer portal account. Open your portal to review and pay securely.
                    </p>
                  </section>
                  <PortalEnrollmentSection
                    hasPortalAccount={invoice.has_portal_account}
                    isPending={createPortalMutation.isPending}
                    canUsePortalToken={!!portalTokenForCreate}
                    password={password}
                    passwordValidationError={passwordValidationError}
                    onPasswordChange={setPassword}
                    onOpenPortal={() => openPortalFromCurrentFlow()}
                    onCreatePortal={() => openPortalFromCurrentFlow(password)}
                  />
                </>
              ) : (
                <>
                  <section>
                    <h3 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                      <CreditCard className="w-5 h-5 text-green-600" />
                      Pay Online Now
                    </h3>
                    {!showPayment ? (
                      <button
                        onClick={() => createIntentMutation.mutate(token)}
                        disabled={createIntentMutation.isPending}
                        className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold rounded-lg"
                      >
                        {createIntentMutation.isPending ? 'Preparing checkout...' : 'Continue to Secure Payment'}
                      </button>
                    ) : stripeOptions && stripeInstance ? (
                      <Elements stripe={stripeInstance} options={stripeOptions}>
                        <GuestPaymentForm
                          token={token}
                          onSuccess={(result) => {
                            setShowPayment(false)
                            setStripeOptions(null)
                            setPaymentResult({
                              paidAt: result.paid_at,
                              portalEnrollmentToken: result.portal_enrollment_token,
                            })
                          }}
                        />
                      </Elements>
                    ) : (
                      <div className="flex items-center justify-center py-4">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500"></div>
                      </div>
                    )}
                  </section>

                  <PortalEnrollmentSection
                    hasPortalAccount={invoice.has_portal_account}
                    isPending={createPortalMutation.isPending}
                    canUsePortalToken={!!portalTokenForCreate}
                    password={password}
                    passwordValidationError={passwordValidationError}
                    onPasswordChange={setPassword}
                    onOpenPortal={() => openPortalFromCurrentFlow()}
                    onCreatePortal={() => openPortalFromCurrentFlow(password)}
                  />
                </>
              )}
            </div>
          )}
        </div>

        <div className="text-center text-sm text-gray-600 space-y-1">
          <p>Need help with this invoice? Contact {shopContact.shopName || 'the shop'} directly.</p>
          {shopContact.shopPhone || shopContact.shopEmail ? (
            <p className="text-gray-700">
              {shopContact.shopPhone && shopContact.telHref && (
                <>
                  Phone:{' '}
                  <a className="text-amber-700 hover:text-amber-800 font-medium underline" href={shopContact.telHref}>
                    {shopContact.shopPhone}
                  </a>
                </>
              )}
              {shopContact.shopPhone && shopContact.shopEmail && ' • '}
              {shopContact.shopEmail && (
                <>
                  Email:{' '}
                  <a
                    className="text-amber-700 hover:text-amber-800 font-medium underline"
                    href={`mailto:${shopContact.shopEmail}`}
                  >
                    {shopContact.shopEmail}
                  </a>
                </>
              )}
            </p>
          ) : null}
          <p>
            <Link to="/login" className="text-amber-700 hover:text-amber-800 font-medium">
              Staff login
            </Link>
          </p>
          <p className="text-xs text-gray-400 mt-4">
            Powered by{' '}
            <a href="/" className="hover:text-gray-500 transition-colors">
              DieselBridge Network
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}
