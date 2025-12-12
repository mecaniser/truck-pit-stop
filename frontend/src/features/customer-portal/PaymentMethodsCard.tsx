import { useState, useEffect } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../lib/api'

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
      <div className="p-4 bg-white/10 rounded-lg border border-white/20">
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
          className="flex-1 px-4 py-2.5 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white font-medium rounded-lg transition-colors"
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
  const [stripePromise, setStripePromise] = useState<ReturnType<typeof loadStripe> | null>(null)

  // Fetch Stripe config
  useEffect(() => {
    api.get('/payments/config').then(({ data }) => {
      if (data.publishable_key) {
        setStripePromise(loadStripe(data.publishable_key))
      }
    })
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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-500"></div>
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
              className="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/10"
            >
              <div className="flex items-center gap-3">
                <span className="text-lg">{CARD_BRANDS[method.brand] || '💳'}</span>
                <div>
                  <p className="text-white font-medium">
                    {method.brand.charAt(0).toUpperCase() + method.brand.slice(1)} •••• {method.last4}
                    {method.is_default && (
                      <span className="ml-2 text-xs bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full">
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
          className="w-full py-2.5 border border-dashed border-white/20 hover:border-amber-500/50 text-gray-400 hover:text-amber-400 rounded-lg transition-colors flex items-center justify-center gap-2"
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
    <div className="bg-white/5 rounded-xl p-6 border border-white/10 h-fit">
      <div className="flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
