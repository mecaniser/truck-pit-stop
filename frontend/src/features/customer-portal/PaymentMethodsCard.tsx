import { ControlButton } from '@/components/ui/Controls'
import { useState, useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { Spinner } from '@/components/ui'
import type { Stripe } from '@stripe/stripe-js'
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'
import { getStripeForAccount } from '../../lib/stripe'

interface PaymentMethod {
  id: string
  brand: string
  last4: string
  exp_month: number
  exp_year: number
  is_default: boolean
}

const CARD_BRANDS: Record<string, string> = {
  visa: '💳 Visa',
  mastercard: '💳 Mastercard',
  amex: '💳 Amex',
  discover: '💳 Discover',
  diners: '💳 Diners',
  jcb: '💳 JCB',
  unionpay: '💳 UnionPay',
}

function paymentError(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

function AddCardForm({ accountId, onSuccess, onCancel }: { accountId: string; onSuccess: () => void; onCancel: () => void }) {
  const stripe = useStripe()
  const elements = useElements()
  const [error, setError] = useState<string | null>(null)
  const [processing, setProcessing] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stripe || !elements) return

    setProcessing(true)
    setError(null)

    try {
      // Get setup intent from backend
      const { data } = await api.post('/payments/setup-intent')
      if (data.stripe_account_id !== accountId) {
        throw new Error('Payment account changed')
      }
      
      const cardElement = elements.getElement(CardElement)
      if (!cardElement) {
        throw new Error('Card element not found')
      }

      const { error: stripeError, setupIntent } = await stripe.confirmCardSetup(data.client_secret, {
        payment_method: { card: cardElement },
      })

      if (stripeError) {
        setError(stripeError.message || 'Failed to add card')
      } else if (setupIntent?.status === 'succeeded') {
        onSuccess()
      }
    } catch (err: unknown) {
      setError(paymentError(err, 'Unable to add your card. Refresh and try again.'))
    } finally {
      setProcessing(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="rounded-xl border border-[#30384b] bg-[#0d1118] p-4">
        <CardElement
          options={{
            style: {
              base: {
                fontSize: '16px',
                color: '#ffffff',
                '::placeholder': { color: '#9ca3af' },
              },
              invalid: { color: '#ef4444' },
            },
          }}
        />
      </div>
      
      {error && (
        <p role="alert" className="text-sm text-red-400">{error}</p>
      )}

      <div className="flex gap-3">
        <ControlButton
          type="submit"
          disabled={!stripe || processing}
          className="flex-1 rounded-xl bg-violet-600 px-4  font-medium text-white transition-colors hover:bg-violet-500 disabled:bg-gray-600"
        >
          {processing ? 'Adding...' : 'Add Card'}
        </ControlButton>
        <ControlButton
          type="button"
          onClick={onCancel}
          disabled={processing}
          className="px-4  bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
        >
          Cancel
        </ControlButton>
      </div>
    </form>
  )
}

function PaymentMethodsList({ scope }: { scope: string }) {
  const queryClient = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [stripePromise, setStripePromise] = useState<Promise<Stripe | null> | null>(null)

  const [stripeLoadError, setStripeLoadError] = useState(false)
  const [stripeReady, setStripeReady] = useState(false)
  const [stripeRetry, setStripeRetry] = useState(0)
  const methodsKey = ['payment-methods', scope]
  const config = useQuery<{ stripe_account_id: string }>({
    queryKey: ['payment-methods-config', scope],
    queryFn: async () => (await api.get('/payments/methods/config')).data,
    retry: false,
  })
  const accountId = config.data?.stripe_account_id

  useEffect(() => {
    let active = true
    setStripeReady(false)
    setStripeLoadError(false)
    setStripePromise(null)
    if (accountId) {
      const promise = getStripeForAccount(accountId).then((stripe) => {
        if (!stripe) throw new Error('Stripe is unavailable')
        if (active) setStripeReady(true)
        return stripe
      }).catch(() => {
        if (active) setStripeLoadError(true)
        return null
      })
      setStripePromise(promise)
    }
    return () => { active = false }
  }, [accountId, stripeRetry])

  const { data: methods, isLoading, isError, error: methodsError, refetch, isFetching } = useQuery<PaymentMethod[]>({
    queryKey: methodsKey,
    retry: false,
    queryFn: async () => {
      const response = await api.get('/payments/methods')
      return response.data
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/payments/methods/${id}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: methodsKey })
    },
  })

  const setDefaultMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/payments/methods/${id}/default`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: methodsKey })
    },
  })

  const handleAddSuccess = () => {
    setShowAddForm(false)
    queryClient.invalidateQueries({ queryKey: methodsKey })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner size="lg" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {isError ? (
        <div role="alert" className="space-y-2 text-sm text-red-400">
          <p>{paymentError(methodsError, 'Unable to load saved payment methods. Please try again.')}</p>
          <ControlButton type="button" onClick={() => { void refetch() }} disabled={isFetching} className="underline">
            {isFetching ? 'Retrying...' : 'Retry loading cards'}
          </ControlButton>
        </div>
      ) : methods && methods.length > 0 ? (
        <div className="space-y-3">
          {methods.map((method) => (
            <div
              key={method.id}
              className="flex items-center justify-between rounded-xl border border-[#232939] bg-[#0d1118] p-3"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">{CARD_BRANDS[method.brand] || '💳'}</span>
                <div>
                  <p className="text-white font-medium">
                    {method.brand.charAt(0).toUpperCase() + method.brand.slice(1)} •••• {method.last4}
                    {method.is_default && (
                      <span className="ml-2 rounded-full border border-violet-400/30 bg-violet-500/10 px-2 py-0.5 text-xs text-violet-200">
                        Default
                      </span>
                    )}
                  </p>
                  <p className="text-sm text-gray-400">
                    Expires {method.exp_month.toString().padStart(2, '0')}/{method.exp_year}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {!method.is_default && (
                  <ControlButton
                    onClick={() => setDefaultMutation.mutate(method.id)}
                    disabled={setDefaultMutation.isPending}
                    className="text-xs text-gray-400 hover:text-white transition-colors"
                  >
                    Set default
                  </ControlButton>
                )}
                <ControlButton controlKind="icon"
                  onClick={() => {
                    if (confirm('Remove this card?')) {
                      deleteMutation.mutate(method.id)
                    }
                  }}
                  disabled={deleteMutation.isPending}
                  className="p-1.5 text-gray-400 hover:text-red-400 transition-colors"
                  title="Remove card"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </ControlButton>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-gray-400 text-sm">No payment methods on file.</p>
      )}

      {(config.isError || stripeLoadError) && (
        <div role="alert" className="space-y-2 text-sm text-red-400">
          <p>{config.isError
            ? paymentError(config.error, 'Unable to load the secure card form. Please try again.')
            : 'Unable to load the secure card form. Please try again.'}</p>
          <ControlButton type="button" className="underline" onClick={() => {
            if (config.isError) void config.refetch()
            else setStripeRetry((value) => value + 1)
          }}>Retry card form</ControlButton>
        </div>
      )}
      {(deleteMutation.isError || setDefaultMutation.isError) && (
        <p role="alert" className="text-sm text-red-400">
          {paymentError(deleteMutation.error || setDefaultMutation.error, 'Unable to update your saved card. Please try again.')}
        </p>
      )}
      {showAddForm && stripePromise && stripeReady && accountId ? (
        <Elements stripe={stripePromise}>
          <AddCardForm accountId={accountId} onSuccess={handleAddSuccess} onCancel={() => setShowAddForm(false)} />
        </Elements>
      ) : (
        <ControlButton
          onClick={() => setShowAddForm(true)}
          disabled={!stripeReady || config.isError}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-[#30384b]  text-gray-400 transition-colors hover:border-violet-400/60 hover:text-violet-300"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Payment Method
        </ControlButton>
      )}
    </div>
  )
}

export default function PaymentMethodsCard() {
  const user = useAuthStore((state) => state.user)
  const scope = JSON.stringify([user?.id, user?.tenant_id, user?.customer_id])
  return (
    <div className="h-fit rounded-2xl border border-[#232939] bg-[#12161f] p-6">
      <div className="flex items-center gap-2 mb-4">
        <svg className="h-5 w-5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
        </svg>
        <h2 className="text-lg font-semibold text-white">Payment Methods</h2>
      </div>
      <p className="text-gray-400 text-sm mb-4">
        Saved cards can be used for quick checkout when paying for services.
      </p>
      <PaymentMethodsList key={scope} scope={scope} />
    </div>
  )
}
