import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { CreditCard, FileText } from 'lucide-react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { getStripeForAccount } from '../../lib/stripe'
import type { InvoiceDetail } from '../../types'

const getErrorDetail = (error: unknown, fallback: string): string => {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    return typeof detail === 'string' ? detail : fallback
  }
  return fallback
}

function InvoicePaymentForm({
  invoiceId,
  onSuccess,
}: {
  invoiceId: string
  onSuccess: () => void
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
        await api.post('/payments/confirm-payment', {
          invoice_id: invoiceId,
          payment_intent_id: paymentIntent.id,
        })
        toast.success('Payment successful!')
        onSuccess()
      } catch {
        setError('Payment confirmed but failed to update records. Please contact support.')
      }
    }

    setIsProcessing(false)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <PaymentElement />
      {error && <div className="text-red-400 text-sm bg-red-500/10 p-3 rounded-lg">{error}</div>}
      <button
        type="submit"
        disabled={!stripe || isProcessing}
        className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
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

export default function CustomerInvoicePage() {
  const { invoiceId } = useParams<{ invoiceId: string }>()
  const queryClient = useQueryClient()
  const [stripeOptions, setStripeOptions] = useState<{ clientSecret: string; appearance: object } | null>(null)
  const [stripeInstance, setStripeInstance] = useState<Stripe | null>(null)
  const [showPayment, setShowPayment] = useState(false)

  const { data: invoice, isLoading, error } = useQuery<InvoiceDetail>({
    queryKey: ['invoice-detail', invoiceId],
    queryFn: async () => {
      const response = await api.get(`/invoices/${invoiceId}`)
      return response.data as InvoiceDetail
    },
    enabled: !!invoiceId,
  })

  const createIntentMutation = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post('/payments/create-payment-intent', { invoice_id: id })
      return data as { client_secret: string; stripe_account_id: string | null }
    },
    onSuccess: async (data) => {
      const stripe = await getStripeForAccount(data.stripe_account_id)
      setStripeInstance(stripe)
      setStripeOptions({
        clientSecret: data.client_secret,
        appearance: {
          theme: 'night',
          variables: {
            colorPrimary: '#16a34a',
            colorBackground: '#0f172a',
            colorText: '#f8fafc',
            colorDanger: '#ef4444',
            borderRadius: '8px',
          },
        },
      })
      setShowPayment(true)
    },
    onError: (e: unknown) => {
      toast.error(getErrorDetail(e, 'Failed to initialize payment'))
    },
  })

  const handlePaymentSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ['invoice-detail', invoiceId] })
    setShowPayment(false)
    setStripeOptions(null)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-amber-500"></div>
      </div>
    )
  }

  if (!invoice || error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-6">
        <p className="text-red-300 font-medium">Unable to load this invoice.</p>
        <Link to="/portal/repairs" className="inline-block mt-3 text-sm text-amber-300 hover:text-amber-200">
          Back to repair history
        </Link>
      </div>
    )
  }

  const isPaid = invoice.status === 'paid'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white">Invoice {invoice.invoice_number}</h1>
          <p className="text-gray-400 mt-1">
            Order {invoice.order_number}
            {invoice.due_date ? ` • Due ${format(new Date(invoice.due_date), 'MMM d, yyyy')}` : ''}
          </p>
        </div>
        <Link to="/portal/repairs" className="text-sm text-amber-300 hover:text-amber-200">
          Back to history
        </Link>
      </div>

      <div className="bg-purple-500/10 rounded-xl border border-purple-500/30 p-4 sm:p-6">
        <div className="flex items-center gap-3 mb-4">
          <FileText className="w-6 h-6 text-purple-400" />
          <div>
            <h3 className="font-semibold text-white">Invoice Details</h3>
            <p className="text-sm text-gray-400">{invoice.vehicle_info}</p>
          </div>
        </div>

        <div className="bg-white/5 rounded-lg p-4 mb-4">
          <div className="flex justify-between mb-2">
            <span className="text-gray-400">Subtotal</span>
            <span className="text-white">${parseFloat(invoice.subtotal).toFixed(2)}</span>
          </div>
          {parseFloat(invoice.shop_supplies_amount || '0') > 0 && (
            <div className="flex justify-between mb-2">
              <span className="text-gray-400">Shop Supplies</span>
              <span className="text-white">${parseFloat(invoice.shop_supplies_amount).toFixed(2)}</span>
            </div>
          )}
          {parseFloat(invoice.service_fee_amount || '0') > 0 && (
            <div className="flex justify-between mb-2">
              <span className="text-gray-400">Service Fee</span>
              <span className="text-white">${parseFloat(invoice.service_fee_amount).toFixed(2)}</span>
            </div>
          )}
          {parseFloat(invoice.tax_amount || '0') > 0 && (
            <div className="flex justify-between mb-2">
              <span className="text-gray-400">Tax</span>
              <span className="text-white">${parseFloat(invoice.tax_amount).toFixed(2)}</span>
            </div>
          )}
          {parseFloat(invoice.discount_amount || '0') > 0 && (
            <div className="flex justify-between mb-2">
              <span className="text-gray-400">Discount</span>
              <span className="text-green-400">-${parseFloat(invoice.discount_amount).toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between pt-2 border-t border-white/10">
            <span className="font-semibold text-white">Total</span>
            <span className="font-bold text-xl text-white">${parseFloat(invoice.total_amount).toFixed(2)}</span>
          </div>
        </div>

        {isPaid ? (
          <div className="bg-green-500/15 border border-green-500/30 rounded-lg p-4 text-green-200">
            Thank you for your payment
            {invoice.paid_at ? ` on ${format(new Date(invoice.paid_at), 'MMM d, yyyy')}` : ''}.
          </div>
        ) : !showPayment ? (
          <button
            onClick={() => createIntentMutation.mutate(invoice.id)}
            disabled={createIntentMutation.isPending}
            className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
          >
            {createIntentMutation.isPending ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                Preparing checkout...
              </>
            ) : (
              <>
                <CreditCard className="w-5 h-5" />
                Pay Now
              </>
            )}
          </button>
        ) : stripeOptions && stripeInstance ? (
          <Elements stripe={stripeInstance} options={stripeOptions}>
            <InvoicePaymentForm invoiceId={invoice.id} onSuccess={handlePaymentSuccess} />
          </Elements>
        ) : (
          <div className="flex items-center justify-center py-4">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500"></div>
          </div>
        )}
      </div>
    </div>
  )
}
