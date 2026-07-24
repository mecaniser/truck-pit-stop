import { useState, useEffect } from 'react'
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

function AddCardForm({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
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
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add card')
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
        <p className="text-sm text-red-400">{error}</p>
      )}

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={!stripe || processing}
          className="flex-1 rounded-xl bg-violet-600 px-4 py-2.5 font-medium text-white transition-colors hover:bg-violet-500 disabled:bg-gray-600"
        >
          {processing ? 'Adding...' : 'Add Card'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={processing}
          className="px-4 py-2.5 bg-white/10 hover:bg-white/20 text-white font-medium rounded-lg transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

function PaymentMethodsList() {
  const queryClient = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [stripePromise, setStripePromise] = useState<Promise<Stripe | null> | null>(null)

  useEffect(() => {
    setStripePromise(getStripeForAccount().catch(() => null))
  }, [])

  const { data: methods, isLoading } = useQuery<PaymentMethod[]>({
    queryKey: ['payment-methods'],
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
      queryClient.invalidateQueries({ queryKey: ['payment-methods'] })
    },
  })

  const setDefaultMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/payments/methods/${id}/default`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payment-methods'] })
    },
  })

  const handleAddSuccess = () => {
    setShowAddForm(false)
    queryClient.invalidateQueries({ queryKey: ['payment-methods'] })
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
      {methods && methods.length > 0 ? (
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
                  <button
                    onClick={() => setDefaultMutation.mutate(method.id)}
                    disabled={setDefaultMutation.isPending}
                    className="text-xs text-gray-400 hover:text-white transition-colors"
                  >
                    Set default
                  </button>
                )}
                <button
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
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-gray-400 text-sm">No payment methods on file.</p>
      )}

      {showAddForm && stripePromise ? (
        <Elements stripe={stripePromise}>
          <AddCardForm onSuccess={handleAddSuccess} onCancel={() => setShowAddForm(false)} />
        </Elements>
      ) : (
        <button
          onClick={() => setShowAddForm(true)}
          disabled={!stripePromise}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-[#30384b] py-2.5 text-gray-400 transition-colors hover:border-violet-400/60 hover:text-violet-300"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Payment Method
        </button>
      )}
    </div>
  )
}

export default function PaymentMethodsCard() {
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
      <PaymentMethodsList />
    </div>
  )
}
