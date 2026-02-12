import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { CreditCard, Lock, FileText, UserPlus } from 'lucide-react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { getStripeForAccount } from '../../lib/stripe'
import { getPasswordValidationError } from '../../lib/passwordPolicy'
import { useAuthStore } from '../../stores/authStore'

interface InvoiceAccessResolve {
  invoice_id: string
  invoice_number: string
  order_number: string
  customer_name: string
  vehicle_info: string
  amount_due: string
  subtotal: string
  shop_supplies_amount: string
  service_fee_amount: string
  tax_amount: string
  discount_amount: string
  total_amount: string
  status: string
  due_date: string | null
  paid_at: string | null
  is_paid: boolean
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
}

interface CreatePortalResponse {
  access_token: string
  refresh_token: string
  token_type: string
  redirect_to: string
  user_exists: boolean
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
        toast.success('Payment successful!')
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
  const navigate = useNavigate()
  const { login } = useAuthStore()
  const [password, setPassword] = useState('')
  const [stripeOptions, setStripeOptions] = useState<{ clientSecret: string; appearance: object } | null>(null)
  const [stripeInstance, setStripeInstance] = useState<Stripe | null>(null)
  const [showPayment, setShowPayment] = useState(false)
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
          <h1 className="text-2xl font-bold text-gray-900 mb-3">{title}</h1>
          <p className="text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">{detail}</p>
          <p className="text-sm text-gray-600 mt-4">
            Please contact the shop and ask them to resend your invoice link.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-amber-50 to-yellow-100 py-8 px-4">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900">Invoice {invoice.invoice_number}</h1>
          <p className="text-gray-600 mt-1">
            Order {invoice.order_number}
            {invoice.due_date ? ` • Due ${format(new Date(invoice.due_date), 'MMM d, yyyy')}` : ''}
          </p>
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
              {parseFloat(invoice.shop_supplies_amount) > 0 && (
                <div className="flex items-center justify-between text-gray-700">
                  <span>Shop Supplies</span>
                  <span>{formatMoney(invoice.shop_supplies_amount)}</span>
                </div>
              )}
              {parseFloat(invoice.service_fee_amount) > 0 && (
                <div className="flex items-center justify-between text-gray-700">
                  <span>Service Fee</span>
                  <span>{formatMoney(invoice.service_fee_amount)}</span>
                </div>
              )}
              {parseFloat(invoice.tax_amount) > 0 && (
                <div className="flex items-center justify-between text-gray-700">
                  <span>Tax</span>
                  <span>{formatMoney(invoice.tax_amount)}</span>
                </div>
              )}
              {parseFloat(invoice.discount_amount) > 0 && (
                <div className="flex items-center justify-between text-green-700">
                  <span>Discount</span>
                  <span>-{formatMoney(invoice.discount_amount)}</span>
                </div>
              )}
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

        <div className="text-center text-sm text-gray-600">
          Need help with this invoice? Contact the shop directly.
          <Link to="/login" className="ml-2 text-amber-700 hover:text-amber-800 font-medium">
            Staff login
          </Link>
        </div>
      </div>
    </div>
  )
}
