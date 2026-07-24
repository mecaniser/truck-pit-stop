import { useEffect, useState } from 'react'
import { Spinner } from '@/components/ui'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { Camera, ChevronDown, ChevronUp, CreditCard, FileText, Download, Printer } from 'lucide-react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { AxiosError } from 'axios'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { getStripeForAccount } from '../../lib/stripe'
import type { InvoiceDetail, RepairOrderPhoto } from '../../types'
import { formatUSPhone } from '../../utils/phone'
import { usePlatformContact } from '../../hooks/usePlatformContact'
import { useAuthStore } from '../../stores/authStore'
import ZellePaymentPanel from './ZellePaymentPanel'
import QuickBooksPaymentPanel from './QuickBooksPaymentPanel'

const getErrorDetail = (error: unknown, fallback: string): string => {
  if (error instanceof AxiosError) {
    const detail = error.response?.data?.detail
    return typeof detail === 'string' ? detail : fallback
  }
  return fallback
}

const copyText = async (value: string | null | undefined, label: string) => {
  if (!value) {
    toast.error(`${label} is not available`)
    return
  }
  try {
    await navigator.clipboard.writeText(value)
    toast.success(`${label} copied`)
  } catch {
    toast.error(`Unable to copy ${label.toLowerCase()}`)
  }
}

function InvoicePaymentForm({
  invoiceId,
  onSuccess,
}: {
  invoiceId: string
  onSuccess: () => void
}) {
  const { supportEmail, supportPhoneDisplay, mailtoHref, telHref } = usePlatformContact()
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
        const response = await api.post('/payments/confirm-payment', {
          invoice_id: invoiceId,
          payment_intent_id: paymentIntent.id,
        })
        const paymentNote = response.data?.payment_note
        toast.success(paymentNote || 'Payment successful!')
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
      {error && (
        <div className="text-red-400 text-sm bg-red-500/10 p-3 rounded-lg space-y-1">
          <p>{error}</p>
          {(supportPhoneDisplay || supportEmail) && (
            <p className="text-red-300/90 text-xs">
              Support:{' '}
              {supportPhoneDisplay && telHref && (
                <>
                  <a className="underline font-medium hover:text-red-200" href={telHref}>
                    {supportPhoneDisplay}
                  </a>
                </>
              )}
              {supportPhoneDisplay && supportEmail && ' • '}
              {supportEmail && mailtoHref && (
                <a className="underline font-medium hover:text-red-200" href={mailtoHref}>
                  {supportEmail}
                </a>
              )}
            </p>
          )}
        </div>
      )}
      <button
        type="submit"
        disabled={!stripe || isProcessing}
        className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
      >
        {isProcessing ? (
          <>
            <Spinner size="sm" className="border-white/40 border-t-white" />
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

function InvoiceRepairPhotos({ photos }: { photos: RepairOrderPhoto[] }) {
  if (!photos.length) return null

  return (
    <div className="mt-4 border-t border-white/10 pt-4">
      <div className="mb-2 flex items-center gap-2">
        <Camera className="h-4 w-4 text-purple-300" />
        <h3 className="text-sm font-medium text-gray-300">Repair photos</h3>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {photos.map((photo) => (
          <a
            key={photo.id}
            href={photo.image_url}
            target="_blank"
            rel="noreferrer"
            className="group relative aspect-square overflow-hidden rounded-lg border border-white/10 bg-white/5"
          >
            <img src={photo.image_url} alt={photo.caption || 'Repair photo'} className="h-full w-full object-cover transition group-hover:scale-105" />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent p-2">
              <p className="line-clamp-2 text-[11px] font-semibold text-white">{photo.caption || 'Repair photo'}</p>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}

interface ZelleInfoResponse {
  zelle_email: string | null
  zelle_phone: string | null
  zelle_qr_image: string | null
  garage_name: string
  stripe_payments_available: boolean
}

interface QuickBooksPaymentAvailability {
  available: boolean
  token_url: string | null
  message: string | null
}

export default function CustomerInvoicePage() {
  const { invoiceId } = useParams<{ invoiceId: string }>()
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  const [stripeOptions, setStripeOptions] = useState<{ clientSecret: string; appearance: object } | null>(null)
  const [stripeInstance, setStripeInstance] = useState<Stripe | null>(null)
  const [showPayment, setShowPayment] = useState(false)
  const [showQuickBooksPayment, setShowQuickBooksPayment] = useState(false)
  const [zelleSenderEmail, setZelleSenderEmail] = useState('')
  const [zelleSenderPhone, setZelleSenderPhone] = useState('')
  const [zelleNotes, setZelleNotes] = useState('')
  const [isZelleSenderEditing, setIsZelleSenderEditing] = useState(false)
  const [showZelleDetails, setShowZelleDetails] = useState(false)

  const { data: invoice, isLoading, error } = useQuery<InvoiceDetail>({
    queryKey: ['invoice-detail', invoiceId],
    queryFn: async () => {
      const response = await api.get(`/invoices/${invoiceId}`)
      return response.data as InvoiceDetail
    },
    enabled: !!invoiceId,
  })

  const { data: zelleInfo } = useQuery<ZelleInfoResponse>({
    queryKey: ['customer-zelle-info', invoice?.id],
    queryFn: async () => {
      const response = await api.get(`/payments/zelle-info/${invoice!.id}`)
      return response.data as ZelleInfoResponse
    },
    enabled: !!invoice && invoice.status !== 'paid',
  })

  const { data: quickBooksPayment, isLoading: isQuickBooksPaymentLoading } = useQuery<QuickBooksPaymentAvailability>({
    queryKey: ['quickbooks-payment-availability', invoice?.id],
    queryFn: async () => (await api.get(`/quickbooks/payments/availability/${invoice!.id}`)).data,
    enabled: !!invoice && invoice.status !== 'paid',
  })

  const { data: repairPhotos = [] } = useQuery<RepairOrderPhoto[]>({
    queryKey: ['invoice-repair-photos', invoice?.repair_order_id],
    queryFn: async () => {
      const response = await api.get(`/repair-orders/${invoice!.repair_order_id}/photos`)
      return response.data
    },
    enabled: !!invoice?.repair_order_id,
  })

  const zelleAmount = invoice
    ? (parseFloat(invoice.total_amount) - parseFloat(invoice.service_fee_amount || '0')).toFixed(2)
    : '0.00'
  const zelleMemo = invoice ? `Invoice #${invoice.invoice_number}` : ''

  useEffect(() => {
    if (!user) return
    setZelleSenderEmail((current) => current || user.email || '')
    setZelleSenderPhone((current) => current || (user.phone ? formatUSPhone(user.phone) : ''))
  }, [user])

  useEffect(() => {
    if (!zelleMemo) return
    setZelleNotes(zelleMemo)
    setIsZelleSenderEditing(false)
  }, [invoice?.id, zelleMemo])

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
    setShowQuickBooksPayment(false)
  }

  const submitZelleMutation = useMutation({
    mutationFn: async () => {
      if (!invoice) throw new Error('Invoice not found')
      const response = await api.post('/payments/submit-zelle', {
        invoice_id: invoice.id,
        sender_email: zelleSenderEmail.trim() || null,
        sender_phone: zelleSenderPhone.trim() || null,
        notes: zelleNotes.trim() || null,
      })
      return response.data as { status: string; message: string }
    },
    onSuccess: (data) => {
      toast.success(data.message || 'Zelle payment submitted')
      queryClient.invalidateQueries({ queryKey: ['invoice-detail', invoiceId] })
      setZelleNotes('')
      setIsZelleSenderEditing(false)
    },
    onError: (e: unknown) => {
      toast.error(getErrorDetail(e, 'Unable to submit Zelle payment'))
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="xl" />
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
          <div className="flex gap-2 mt-3 print:hidden">
            <a
              href={`/api/v1/invoices/${invoiceId}/pdf`}
              download
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg hover:bg-amber-500/20"
            >
              <Download className="w-4 h-4" />
              Download PDF
            </a>
            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-300 bg-white/5 border border-white/10 rounded-lg hover:bg-white/10"
            >
              <Printer className="w-4 h-4" />
              Print
            </button>
          </div>
        </div>
        <Link to="/portal/repairs" className="text-sm text-amber-300 hover:text-amber-200 print:hidden">
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
          <div className="flex justify-between mb-2">
            <span className="text-gray-400">Shop Supplies</span>
            <span className="text-white">${parseFloat(invoice.shop_supplies_amount || '0').toFixed(2)}</span>
          </div>
          <div className="flex justify-between mb-2">
            <span className="text-gray-400">Card Processing Fee</span>
            <span className="text-white">${parseFloat(invoice.service_fee_amount || '0').toFixed(2)}</span>
          </div>
          <div className="flex justify-between mb-2">
            <span className="text-gray-400">Tax</span>
            <span className="text-white">${parseFloat(invoice.tax_amount || '0').toFixed(2)}</span>
          </div>
          {parseFloat(invoice.discount_amount || '0') > 0 && (
            <div className="flex justify-between mb-2">
              <span className="text-gray-400">Discount</span>
              <span className="text-green-400">-${parseFloat(invoice.discount_amount || '0').toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between pt-2 border-t border-white/10">
            <span className="font-semibold text-white">Total</span>
            <span className="font-bold text-xl text-white">${parseFloat(invoice.total_amount).toFixed(2)}</span>
          </div>
        </div>

        <InvoiceRepairPhotos photos={repairPhotos} />

        {isPaid ? (
          <div className="bg-green-500/15 border border-green-500/30 rounded-lg p-4 text-green-200">
            Thank you for your payment
            {invoice.paid_at ? ` on ${format(new Date(invoice.paid_at), 'MMM d, yyyy')}` : ''}.
          </div>
        ) : (
          <div className="mx-auto w-full max-w-2xl space-y-4">
            <ZellePaymentPanel
              garageName={zelleInfo?.garage_name}
              serviceFeeAmount={invoice.service_fee_amount}
              zelleAmount={zelleAmount}
              zelleMemo={zelleMemo}
              zelleEmail={zelleInfo?.zelle_email}
              zellePhone={zelleInfo?.zelle_phone}
              zelleQrImage={zelleInfo?.zelle_qr_image}
              pendingConfirmation={Boolean(invoice.pending_zelle_confirmation)}
              isOpen={showZelleDetails}
              isSenderEditing={isZelleSenderEditing}
              senderEmail={zelleSenderEmail}
              senderPhone={zelleSenderPhone}
              senderNotes={zelleNotes}
              isSubmitting={submitZelleMutation.isPending}
              onToggleOpen={() => setShowZelleDetails(prev => !prev)}
              onCopy={copyText}
              onToggleSenderEditing={() => setIsZelleSenderEditing(editing => !editing)}
              onSenderEmailChange={setZelleSenderEmail}
              onSenderPhoneChange={value => setZelleSenderPhone(formatUSPhone(value))}
              onSenderNotesChange={setZelleNotes}
              onSubmit={() => submitZelleMutation.mutate()}
            />

            {!invoice.pending_zelle_confirmation && zelleInfo?.stripe_payments_available && (
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-400 mb-2">Pay instantly by card</p>
              {!showPayment ? (
                <button
                  onClick={() => createIntentMutation.mutate(invoice.id)}
                  disabled={createIntentMutation.isPending}
                  className="w-full py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-semibold rounded-lg flex items-center justify-center gap-2"
                >
                  {createIntentMutation.isPending ? (
                    <>
                      <Spinner size="sm" className="border-white/40 border-t-white" />
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
                  <Spinner size="lg" />
                </div>
              )}
            </div>
            )}
            {!invoice.pending_zelle_confirmation
              && zelleInfo
              && !zelleInfo.stripe_payments_available
              && !isQuickBooksPaymentLoading
              && !(quickBooksPayment?.available && quickBooksPayment.token_url) && (
              <p className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-3 py-2 text-sm text-amber-200">
                Online card payment is currently unavailable for this shop.
              </p>
            )}
            {!invoice.pending_zelle_confirmation && isQuickBooksPaymentLoading && (
              <div
                role="status"
                aria-label="Checking QuickBooks payment availability"
                className="animate-pulse overflow-hidden rounded-xl border border-gray-700 bg-slate-950/40"
              >
                <div className="px-4 py-3">
                  <div className="h-4 w-40 rounded bg-gray-700/70" />
                  <div className="mt-2 h-3 w-28 rounded bg-gray-800" />
                </div>
                <span className="sr-only">Checking QuickBooks payment availability…</span>
              </div>
            )}
            {!invoice.pending_zelle_confirmation && quickBooksPayment?.available && quickBooksPayment.token_url && (
              <div className="overflow-hidden rounded-xl border border-emerald-500/40 bg-slate-950/40">
                <button
                  type="button"
                  aria-expanded={showQuickBooksPayment}
                  aria-controls="quickbooks-payment-panel"
                  onClick={() => setShowQuickBooksPayment(open => !open)}
                  className="flex w-full items-center justify-between gap-3 bg-emerald-500/10 px-4 py-3 text-left hover:bg-emerald-500/15"
                >
                  <span>
                    <span className="block text-sm font-semibold text-emerald-200">Pay securely by card</span>
                    <span className="mt-1 block text-xs text-gray-400">Powered by QuickBooks</span>
                  </span>
                  {showQuickBooksPayment
                    ? <ChevronUp className="h-4 w-4 shrink-0 text-emerald-200" />
                    : <ChevronDown className="h-4 w-4 shrink-0 text-emerald-200" />}
                </button>
                {showQuickBooksPayment && (
                  <div id="quickbooks-payment-panel" className="border-t border-emerald-500/30 px-4 py-4">
                  <QuickBooksPaymentPanel
                    invoiceId={invoice.id}
                    tokenUrl={quickBooksPayment.token_url}
                    onSuccess={handlePaymentSuccess}
                  />
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
