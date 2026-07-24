import { useEffect, useMemo, useRef, useState } from 'react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { format } from 'date-fns'
import { Check, Copy, Download, Lock, QrCode } from 'lucide-react'
import { useLocation, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'

import BackPill from '@/components/navigation/BackPill'
import { Spinner } from '@/components/ui'
import api from '@/lib/api'
import { getStripeForAccount } from '@/lib/stripe'
import { useAuthStore } from '@/stores/authStore'
import type { InvoiceDetail, RepairOrderDetail } from '@/types'
import { formatUSPhone } from '@/utils/phone'

import QuickBooksPaymentPanel from './QuickBooksPaymentPanel'

type PaymentMethod = 'zelle' | 'card'

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

const money = (value: string | number | null | undefined) =>
  `$${Number(value || 0).toFixed(2)}`

const errorDetail = (error: unknown, fallback: string) => {
  if (error instanceof AxiosError && typeof error.response?.data?.detail === 'string') {
    return error.response.data.detail
  }
  return fallback
}

function StripePaymentForm({
  invoiceId,
  amount,
  onSuccess,
}: {
  invoiceId: string
  amount: number
  onSuccess: () => void
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!stripe || !elements || isProcessing) return
    setIsProcessing(true)
    setError(null)

    const result = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.href },
      redirect: 'if_required',
    })

    if (result.error) {
      setError(result.error.message || 'Payment could not be completed. Please try again.')
      setIsProcessing(false)
      return
    }

    if (result.paymentIntent?.status === 'succeeded') {
      try {
        await api.post('/payments/confirm-payment', {
          invoice_id: invoiceId,
          payment_intent_id: result.paymentIntent.id,
        })
        toast.success('Payment successful')
        onSuccess()
      } catch {
        setError('Your card was charged, but the invoice could not be updated. Please contact the shop.')
      }
    }
    setIsProcessing(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-[14px] border border-[#232939] bg-[#12161f] p-4">
      <PaymentElement />
      {error && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={!stripe || isProcessing}
        className="flex h-[50px] w-full items-center justify-center gap-2 rounded-xl bg-[#8b7cf7] text-sm font-extrabold text-[#0e1118] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isProcessing && <Spinner size="sm" className="border-black/30 border-t-black" />}
        {isProcessing ? 'Processing payment…' : `Pay ${money(amount)} by card`}
      </button>
    </form>
  )
}

function LoadingPaymentPage() {
  return (
    <div className="mx-auto w-full max-w-[640px] animate-pulse px-4 pb-8 pt-6 sm:px-0">
      <div className="mb-8 h-9 w-28 rounded-full bg-[#191d2a]" />
      <div className="mx-auto h-4 w-72 max-w-full rounded bg-[#232939]" />
      <div className="mx-auto mt-5 h-12 w-48 rounded bg-[#232939]" />
      <div className="mx-auto mt-3 h-4 w-56 rounded bg-[#1e2432]" />
      <div className="mt-6 grid grid-cols-2 gap-2.5">
        <div className="h-14 rounded-xl bg-[#191d2a]" />
        <div className="h-14 rounded-xl bg-[#191d2a]" />
      </div>
      <div className="mt-4 h-[54px] rounded-[13px] bg-[#312d56]" />
      <div className="mt-4 h-56 rounded-[14px] bg-[#161a26]" />
    </div>
  )
}

export default function CustomerInvoicePage() {
  const { invoiceId } = useParams<{ invoiceId: string }>()
  const location = useLocation()
  const queryClient = useQueryClient()
  const user = useAuthStore(state => state.user)
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod>('zelle')
  const [showZelleDetails, setShowZelleDetails] = useState(false)
  const [showCardDetails, setShowCardDetails] = useState(false)
  const [stripeOptions, setStripeOptions] = useState<{ clientSecret: string; appearance: object } | null>(null)
  const [stripeInstance, setStripeInstance] = useState<Stripe | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const methodRefs = useRef<Array<HTMLButtonElement | null>>([])

  const { data: invoice, isLoading, error } = useQuery<InvoiceDetail>({
    queryKey: ['invoice-detail', invoiceId],
    queryFn: async () => (await api.get(`/invoices/${invoiceId}`)).data,
    enabled: Boolean(invoiceId),
  })

  const { data: repairOrder } = useQuery<RepairOrderDetail>({
    queryKey: ['repair-order-payment-detail', invoice?.repair_order_id],
    queryFn: async () => (await api.get(`/repair-orders/${invoice!.repair_order_id}/detail`)).data,
    enabled: Boolean(invoice?.repair_order_id),
  })

  const { data: zelleInfo, isLoading: isZelleLoading } = useQuery<ZelleInfoResponse>({
    queryKey: ['customer-zelle-info', invoice?.id],
    queryFn: async () => (await api.get(`/payments/zelle-info/${invoice!.id}`)).data,
    enabled: Boolean(invoice && invoice.status !== 'paid'),
  })

  const { data: quickBooksPayment, isLoading: isQuickBooksLoading } = useQuery<QuickBooksPaymentAvailability>({
    queryKey: ['quickbooks-payment-availability', invoice?.id],
    queryFn: async () => (await api.get(`/quickbooks/payments/availability/${invoice!.id}`)).data,
    enabled: Boolean(invoice && invoice.status !== 'paid'),
  })

  const createIntentMutation = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post('/payments/create-payment-intent', { invoice_id: id })
      return data as { client_secret: string; stripe_account_id: string | null }
    },
    onSuccess: async data => {
      const stripe = await getStripeForAccount(data.stripe_account_id)
      setStripeInstance(stripe)
      setStripeOptions({
        clientSecret: data.client_secret,
        appearance: {
          theme: 'night',
          variables: {
            colorPrimary: '#8b7cf7',
            colorBackground: '#12161f',
            colorText: '#eceef4',
            colorDanger: '#f87171',
            borderRadius: '10px',
          },
        },
      })
      setShowCardDetails(true)
    },
    onError: error => toast.error(errorDetail(error, 'Unable to prepare card checkout')),
  })

  const submitZelleMutation = useMutation({
    mutationFn: async () => {
      if (!invoice) throw new Error('Invoice not found')
      return api.post('/payments/submit-zelle', {
        invoice_id: invoice.id,
        sender_email: user?.email || null,
        sender_phone: user?.phone ? formatUSPhone(user.phone) : null,
        notes: `Invoice #${invoice.invoice_number}`,
      })
    },
    onSuccess: () => {
      toast.success('Zelle payment sent for shop confirmation')
      queryClient.invalidateQueries({ queryKey: ['invoice-detail', invoiceId] })
    },
    onError: error => toast.error(errorDetail(error, 'Unable to submit Zelle payment')),
  })

  const handlePaymentSuccess = () => {
    queryClient.invalidateQueries({ queryKey: ['invoice-detail', invoiceId] })
    setShowCardDetails(false)
    setStripeOptions(null)
  }

  const zelleEnabled = Boolean(
    zelleInfo && (zelleInfo.zelle_email || zelleInfo.zelle_phone || zelleInfo.zelle_qr_image),
  )
  const cardEnabled = Boolean(
    (quickBooksPayment?.available && quickBooksPayment.token_url) || zelleInfo?.stripe_payments_available,
  )

  useEffect(() => {
    if (isZelleLoading || isQuickBooksLoading) return
    if (!zelleEnabled && cardEnabled) setSelectedMethod('card')
    if (zelleEnabled && !cardEnabled) setSelectedMethod('zelle')
  }, [cardEnabled, isQuickBooksLoading, isZelleLoading, zelleEnabled])

  const pricing = useMemo(() => {
    const cardTotal = Number(invoice?.total_amount || 0)
    const cardFee = Number(invoice?.service_fee_amount || 0)
    const zelleTotal = Math.max(0, cardTotal - cardFee)
    return {
      cardFee,
      cardTotal,
      zelleTotal,
      selectedTotal: selectedMethod === 'zelle' ? zelleTotal : cardTotal,
    }
  }, [invoice, selectedMethod])

  const copy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(key)
      window.setTimeout(() => setCopied(null), 1800)
    } catch {
      toast.error('Unable to copy')
    }
  }

  if (isLoading) return <LoadingPaymentPage />

  if (error || !invoice) {
    return (
      <div className="mx-auto mt-16 max-w-md rounded-[14px] border border-red-500/30 bg-red-500/10 p-6 text-center">
        <p className="font-bold text-red-200">Unable to load this invoice.</p>
        <div className="mt-5"><BackPill destination="History" /></div>
      </div>
    )
  }

  const state = location.state as { paymentOrigin?: 'History' | 'Dashboard' } | null
  const backDestination = state?.paymentOrigin || 'History'
  const isPaid = invoice.status === 'paid'
  const isPending = Boolean(invoice.pending_zelle_confirmation)
  const concern = repairOrder?.description?.trim() || 'Service / Repair'
  const labor = Number(repairOrder?.total_labor_cost || invoice.subtotal)
  const parts = Number(repairOrder?.total_parts_cost || 0)
  const recipient = zelleInfo?.zelle_phone || zelleInfo?.zelle_email || ''
  const methodCount = Number(zelleEnabled) + Number(cardEnabled)

  const chooseMethod = (method: PaymentMethod) => {
    setSelectedMethod(method)
    setShowCardDetails(false)
    setShowZelleDetails(false)
  }

  const handleMethodKeyDown = (event: React.KeyboardEvent, index: number) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
    event.preventDefault()
    const next = event.key === 'ArrowRight' || event.key === 'ArrowDown'
      ? (index + 1) % methodCount
      : (index - 1 + methodCount) % methodCount
    methodRefs.current[next]?.focus()
    const methods = [zelleEnabled ? 'zelle' : null, cardEnabled ? 'card' : null].filter(Boolean) as PaymentMethod[]
    chooseMethod(methods[next])
  }

  const startPayment = () => {
    if (selectedMethod === 'zelle') {
      setShowZelleDetails(true)
      return
    }
    if (quickBooksPayment?.available && quickBooksPayment.token_url) {
      setShowCardDetails(true)
      return
    }
    if (!createIntentMutation.isPending) createIntentMutation.mutate(invoice.id)
  }

  return (
    <div className="min-h-full bg-[#10131c] px-4 pb-8 text-[#eceef4] sm:px-6">
      <div className="mx-auto w-full max-w-[640px] pb-6 pt-4">
        <div className="mb-2">
          <BackPill destination={backDestination} />
        </div>

        <section className="py-2 text-center" aria-labelledby="payment-total">
          <p className="flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 text-[13px] text-[#8b92a5]">
            <span>{invoice.order_number}</span>
            <span aria-hidden="true">·</span>
            <span className="text-[#d9a521]">{invoice.vehicle_info}</span>
            <span className="rounded-full border border-violet-400/35 bg-violet-400/10 px-2.5 py-0.5 text-[11px] font-bold text-[#a78bfa]">
              {isPaid ? 'paid' : 'invoiced'}
            </span>
          </p>
          <h1 id="payment-total" className="mt-2.5 whitespace-nowrap text-[38px] font-extrabold leading-none tracking-[-0.02em] tabular-nums sm:text-[46px]">
            {money(pricing.selectedTotal)}
          </h1>
          <p className={`mt-1 min-h-5 text-[13px] font-bold ${selectedMethod === 'zelle' ? 'text-[#2dd4bf]' : 'text-[#8b92a5]'}`}>
            {selectedMethod === 'zelle'
              ? pricing.cardFee > 0 && `No card fee with Zelle — you save ${money(pricing.cardFee)}`
              : `Includes ${money(pricing.cardFee)} card processing fee`}
          </p>
        </section>

        {isPaid ? (
          <section className="mt-4 rounded-[14px] border border-[#2dd4bf]/35 bg-[#2dd4bf]/10 p-5 text-center">
            <p className="text-lg font-extrabold text-[#5eead4]">Paid</p>
            <p className="mt-1 text-sm text-[#c9cdd8]">
              {money(invoice.payment?.amount || invoice.total_amount)}
              {invoice.paid_at ? ` · ${format(new Date(invoice.paid_at), 'MMM d, yyyy')}` : ''}
              {invoice.payment?.method ? ` · ${invoice.payment.method}` : ''}
            </p>
            <a
              href={`/api/v1/invoices/${invoice.id}/pdf`}
              download
              className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-[#c4b1ff] hover:text-white"
            >
              <Download className="h-4 w-4" />
              Receipt
            </a>
          </section>
        ) : (
          <>
            {isPending && (
              <div className="mt-4 rounded-xl border border-amber-400/35 bg-amber-400/10 px-4 py-3 text-center text-sm font-bold text-amber-200">
                Awaiting confirmation from the shop
              </div>
            )}

            {!isPending && methodCount > 1 && (
              <div role="radiogroup" aria-label="Payment method" className="mt-4 grid grid-cols-2 gap-2.5">
                {zelleEnabled && (
                  <button
                    ref={element => { methodRefs.current[0] = element }}
                    type="button"
                    role="radio"
                    aria-checked={selectedMethod === 'zelle'}
                    tabIndex={selectedMethod === 'zelle' ? 0 : -1}
                    onClick={() => chooseMethod('zelle')}
                    onKeyDown={event => handleMethodKeyDown(event, 0)}
                    className={`flex h-14 min-w-0 flex-col items-center justify-center gap-0.5 rounded-xl border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8b7cf7] ${
                      selectedMethod === 'zelle'
                        ? 'border-[#8b7cf7] bg-[#8b7cf7]/10 text-[#c9bfff]'
                        : 'border-[#272d3d] bg-[#161a26] text-[#8b92a5]'
                    }`}
                  >
                    <span className="whitespace-nowrap text-sm font-extrabold">Zelle · {money(pricing.zelleTotal)}</span>
                    <span className="text-[10px] font-bold text-[#2dd4bf]">NO FEE</span>
                  </button>
                )}
                {cardEnabled && (
                  <button
                    ref={element => { methodRefs.current[zelleEnabled ? 1 : 0] = element }}
                    type="button"
                    role="radio"
                    aria-checked={selectedMethod === 'card'}
                    tabIndex={selectedMethod === 'card' ? 0 : -1}
                    onClick={() => chooseMethod('card')}
                    onKeyDown={event => handleMethodKeyDown(event, zelleEnabled ? 1 : 0)}
                    className={`flex h-14 min-w-0 flex-col items-center justify-center gap-0.5 rounded-xl border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#8b7cf7] ${
                      selectedMethod === 'card'
                        ? 'border-[#8b7cf7] bg-[#8b7cf7]/10 text-[#c9bfff]'
                        : 'border-[#272d3d] bg-[#161a26] text-[#8b92a5]'
                    }`}
                  >
                    <span className="whitespace-nowrap text-sm font-extrabold">Card · {money(pricing.cardTotal)}</span>
                    <span className="text-[10px] font-bold opacity-70">QUICKBOOKS</span>
                  </button>
                )}
              </div>
            )}

            <div className="sticky bottom-2 z-20 mt-4 sm:static">
              <button
                type="button"
                onClick={isPending ? () => setShowZelleDetails(true) : startPayment}
                disabled={createIntentMutation.isPending || submitZelleMutation.isPending || methodCount === 0}
                className="flex h-[54px] w-full items-center justify-center gap-2 rounded-[13px] bg-[#8b7cf7] px-4 text-[15px] font-extrabold text-[#0e1118] shadow-[0_8px_30px_rgba(16,19,28,0.65)] hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60 sm:shadow-none"
              >
                {(createIntentMutation.isPending || submitZelleMutation.isPending) && (
                  <Spinner size="sm" className="border-black/30 border-t-black" />
                )}
                {isPending
                  ? 'View Zelle details'
                  : selectedMethod === 'zelle'
                    ? `Get Zelle details — ${money(pricing.zelleTotal)}`
                    : `Pay ${money(pricing.cardTotal)} by card`}
              </button>
            </div>

            {showZelleDetails && selectedMethod === 'zelle' && (
              <section className="mt-4 overflow-hidden rounded-[14px] border border-[#2dd4bf]/35 bg-[#12161f]" aria-label="Zelle payment details">
                <div className="flex items-start gap-3 border-b border-[#1e2432] p-4">
                  <div className="rounded-lg bg-[#2dd4bf]/10 p-2 text-[#2dd4bf]"><QrCode className="h-5 w-5" /></div>
                  <div>
                    <h2 className="font-extrabold">Send with Zelle</h2>
                    <p className="mt-0.5 text-xs text-[#8b92a5]">Use the exact amount and memo so the shop can match your payment.</p>
                  </div>
                </div>
                <div className="divide-y divide-[#1e2432] px-4">
                  {[
                    ['Amount', money(pricing.zelleTotal), pricing.zelleTotal.toFixed(2)],
                    ['Recipient', recipient || zelleInfo?.garage_name || 'Contact the shop', recipient],
                    ['Memo', invoice.order_number, invoice.order_number],
                  ].map(([label, display, value]) => (
                    <div key={label} className="flex items-center gap-3 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#8b92a5]">{label}</p>
                        <p className="mt-0.5 truncate text-sm font-bold tabular-nums">{display}</p>
                      </div>
                      {value && (
                        <button type="button" onClick={() => copy(value, label)} className="inline-flex items-center gap-1 text-xs font-bold text-[#a78bfa] hover:text-[#c4b1ff]">
                          {copied === label ? <Check className="h-4 w-4 text-[#2dd4bf]" /> : <Copy className="h-4 w-4" />}
                          {copied === label ? 'Copied' : 'Copy'}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                {zelleInfo?.zelle_qr_image && (
                  <div className="border-t border-[#1e2432] p-4 text-center">
                    <img src={zelleInfo.zelle_qr_image} alt="Zelle QR code" className="mx-auto h-40 w-40 rounded-lg bg-white object-contain p-2" />
                  </div>
                )}
                {!isPending && (
                  <div className="border-t border-[#1e2432] p-4">
                    <button
                      type="button"
                      onClick={() => submitZelleMutation.mutate()}
                      disabled={submitZelleMutation.isPending}
                      className="h-11 w-full rounded-xl border border-[#2dd4bf]/35 bg-[#2dd4bf]/10 text-sm font-extrabold text-[#5eead4] hover:bg-[#2dd4bf]/15 disabled:opacity-60"
                    >
                      {submitZelleMutation.isPending ? 'Submitting…' : "I've sent it"}
                    </button>
                  </div>
                )}
              </section>
            )}

            {showCardDetails && selectedMethod === 'card' && quickBooksPayment?.available && quickBooksPayment.token_url && (
              <section className="mt-4 rounded-[14px] border border-[#232939] bg-[#12161f] p-4">
                <h2 className="mb-3 text-sm font-extrabold">Secure card payment</h2>
                <QuickBooksPaymentPanel invoiceId={invoice.id} tokenUrl={quickBooksPayment.token_url} onSuccess={handlePaymentSuccess} />
              </section>
            )}

            {showCardDetails && selectedMethod === 'card' && stripeOptions && stripeInstance && (
              <div className="mt-4">
                <Elements stripe={stripeInstance} options={stripeOptions}>
                  <StripePaymentForm invoiceId={invoice.id} amount={pricing.cardTotal} onSuccess={handlePaymentSuccess} />
                </Elements>
              </div>
            )}

            {methodCount === 0 && !isZelleLoading && !isQuickBooksLoading && (
              <p className="mt-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-center text-sm text-amber-200">
                Online payment is unavailable for this shop. Please contact the shop for help.
              </p>
            )}
          </>
        )}

        <section className="mt-4 rounded-[14px] border border-[#232939] bg-[#161a26] px-5 py-4" aria-labelledby="charge-breakdown">
          <div className="flex items-center justify-between gap-4 pb-2">
            <h2 id="charge-breakdown" className="min-w-0 truncate text-[11px] font-extrabold uppercase tracking-[0.1em] text-[#8b92a5]">
              {concern} · Charges
            </h2>
            <a
              href={`/api/v1/invoices/${invoice.id}/pdf`}
              download
              className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs font-bold text-[#a78bfa] hover:text-[#c4b1ff]"
            >
              <Download className="h-3.5 w-3.5" />
              Invoice PDF
            </a>
          </div>
          <div>
            {[
              ['Labor / Services', labor],
              ['Parts', parts],
              ['Shop Supplies', Number(invoice.shop_supplies_amount || 0)],
              ['Tax', Number(invoice.tax_amount || 0)],
              ...(Number(invoice.discount_amount || 0) > 0
                ? [['Discount', -Number(invoice.discount_amount)] as [string, number]]
                : []),
              ...(selectedMethod === 'card' && pricing.cardFee > 0
                ? [['Card Processing Fee', pricing.cardFee] as [string, number]]
                : []),
            ].map(([label, amount], index, rows) => (
              <div key={label} className={`flex items-center justify-between py-[9px] text-[13px] ${index < rows.length - 1 ? 'border-b border-[#1e2432]' : ''}`}>
                <span className="text-[#9aa1b3]">{label}</span>
                <span className="whitespace-nowrap font-semibold text-[#eceef4] tabular-nums">{money(amount)}</span>
              </div>
            ))}
          </div>
        </section>

        <p className="mt-4 flex items-center justify-center gap-1.5 text-center text-[11px] text-[#5c6375]">
          <Lock className="h-3 w-3" />
          Secure payment · Receipt emailed instantly
        </p>
      </div>
    </div>
  )
}
