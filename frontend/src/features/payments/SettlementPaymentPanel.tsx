import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Banknote, Building2, Check, Clock3, Copy, CreditCard, Landmark, MoreHorizontal, Send, Truck } from 'lucide-react'
import toast from 'react-hot-toast'

import { Spinner } from '@/components/ui'
import QuickBooksPaymentPanel from '@/features/customer-portal/QuickBooksPaymentPanel'
import { getStripeForAccount } from '@/lib/stripe'

import { chargeQuickBooksPaymentAttempt, confirmPaymentAttempt, createIdempotencyKey, createPaymentAttempt, fetchPaymentQuote, paymentApiError } from './api'
import { centsToMoney, formatMoney, isPositiveMoney, isValidPrincipalAmount, moneyToCents, normalizeMoney } from './money'
import type { InlineCashTender } from './FullCashPaymentPanel'
import type { InlineInvoiceChargeControls } from './InvoiceChargeControls'
import type {
  InvoiceSettlementSummary,
  PaymentAttemptResponse,
  PaymentRail,
  FleetProvider,
  SettlementAccess,
} from './types'

const RAIL_META: Record<PaymentRail, { label: string; detail: string; icon: typeof CreditCard }> = {
  card: { label: 'Card', detail: 'Secure online payment', icon: CreditCard },
  zelle: { label: 'Zelle', detail: 'Confirmed by the shop', icon: Send },
  check: { label: 'Check', detail: 'Staff verified reference', icon: Building2 },
  ach: { label: 'ACH', detail: 'Account transfer / bank transfer', icon: Landmark },
  fleet_payment: { label: 'Fleet Check / Code', detail: 'EFS / MoneyCode, Comchek, T-Chek or other provider', icon: Truck },
}

function StripeAttemptForm({
  attempt,
  tone,
  onProviderSubmitted,
}: {
  attempt: PaymentAttemptResponse
  tone: 'dark' | 'light'
  onProviderSubmitted: () => void
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!stripe || !elements || busy) return
    setBusy(true)
    setError(null)
    const result = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.href },
      redirect: 'if_required',
    })
    if (result.error) {
      setError(result.error.message || 'The card payment was not accepted.')
      setBusy(false)
      return
    }
    if (result.paymentIntent?.id) {
      toast.success('Card accepted. Settlement is being reconciled.')
      onProviderSubmitted()
    }
    setBusy(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-label="Secure card payment">
      <PaymentElement />
      {error && <p role="alert" className={`rounded-xl border p-3 text-sm ${tone === 'dark' ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-red-200 bg-red-50 text-red-700'}`}>{error}</p>}
      <button type="submit" disabled={!stripe || busy} className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent-600,#b9472f)] px-4 text-sm font-extrabold text-white hover:brightness-110 disabled:opacity-50">
        {busy && <Spinner size="sm" />}
        {busy ? 'Confirming…' : `Pay ${formatMoney(attempt.provider_charge_amount)} with card`}
      </button>
      <p className={`text-xs ${tone === 'dark' ? 'text-[#99a4b7]' : 'text-slate-500'}`}>
        {formatMoney(attempt.principal_amount)} applies to the invoice
        {attempt.card_fee_amount !== '0.00' ? ` · ${formatMoney(attempt.card_fee_amount)} card fee` : ''}.
      </p>
    </form>
  )
}

function InvoicePaymentPanel({
  access,
  summary,
  audience,
  tone = 'dark',
  senderDefaults,
  zelleRecipient,
  onUpdated,
  cashTender,
  submissionBlockedReason,
  taxExemptionControl,
  chargeControls,
}: {
  access: SettlementAccess
  summary: InvoiceSettlementSummary
  audience: 'customer' | 'guest' | 'staff'
  tone?: 'dark' | 'light'
  senderDefaults?: { email?: string | null; phone?: string | null }
  zelleRecipient?: { display: string; memo: string } | null
  onUpdated: (next: InvoiceSettlementSummary) => void
  cashTender?: InlineCashTender
  submissionBlockedReason?: string
  taxExemptionControl?: ReactNode
  chargeControls?: InlineInvoiceChargeControls
}) {
  const queryClient = useQueryClient()
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const allowedRails = useMemo(() => summary.allowed_actions?.rails ?? [], [summary.allowed_actions?.rails])
  const [rail, setRail] = useState<PaymentRail | null>(allowedRails[0] ?? null)
  // Null follows the full balance. An explicit draft belongs to the operator,
  // not to a particular quote or invoice-charge version.
  const [amount, setAmount] = useState<string | null>(null)
  const [editingAmount, setEditingAmount] = useState(false)
  const [expandedTenders, setExpandedTenders] = useState(false)
  const [showTransferDetails, setShowTransferDetails] = useState(false)
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
  const [fleetProvider, setFleetProvider] = useState<FleetProvider>('EFS')
  const [fleetProviderName, setFleetProviderName] = useState('')
  const [authorization, setAuthorization] = useState('')
  const [senderEmail, setSenderEmail] = useState(senderDefaults?.email || '')
  const [senderPhone, setSenderPhone] = useState(senderDefaults?.phone || '')
  const [attempt, setAttempt] = useState<PaymentAttemptResponse | null>(null)
  const [receivedAmount, setReceivedAmount] = useState('')
  const [stripe, setStripe] = useState<Stripe | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [providerSubmitted, setProviderSubmitted] = useState(false)
  const railRefs = useRef<Array<HTMLButtonElement | null>>([])
  const dark = tone === 'dark'
  const panel = dark ? 'border-[#2a3245] bg-[#111722] text-[#edf0f6]' : 'border-slate-200 bg-white text-slate-950'
  const input = dark ? 'border-[#3a465e] bg-[#182234] text-white placeholder:text-[#738097]' : 'border-slate-300 bg-white text-slate-950 placeholder:text-slate-400'
  const quiet = dark ? 'text-[#99a4b7]' : 'text-slate-500'
  const cash = audience === 'staff' && access.kind === 'authenticated' ? cashTender : undefined
  const cashSelected = cash?.selected === true
  const noncashAvailable = allowedRails.length > 0 && summary.allowed_actions?.create_attempt !== false
  const secondarySelected = !cashSelected && (rail === 'check' || rail === 'ach' || rail === 'fleet_payment')
  const tenders: Array<PaymentRail | 'cash'> = audience === 'staff'
    ? ['card', 'zelle', ...(cash ? ['cash' as const] : []), ...(expandedTenders ? ['check' as const, 'ach' as const, 'fleet_payment' as const] : secondarySelected ? [rail] : [])]
    : allowedRails
  const tenderDisabled = (item: PaymentRail | 'cash') => Boolean(createMutation.isPending || cash?.pending || (item === 'cash' ? !cash?.allowed : !noncashAvailable || !allowedRails.includes(item)))
  const selectTender = (item: PaymentRail | 'cash') => {
    if (tenderDisabled(item)) return
    if (item !== (cashSelected ? 'cash' : rail)) {
      setReference('')
      setNote('')
      setAuthorization('')
      setFleetProvider('EFS')
      setFleetProviderName('')
    }
    cash?.select(item === 'cash')
    if (item !== 'cash') setRail(item)
    setAttempt(null)
  }

  useEffect(() => {
    if (rail && allowedRails.includes(rail)) return
    setRail(allowedRails[0] ?? null)
    setReference('')
    setNote('')
    setAuthorization('')
    setFleetProviderName('')
  }, [allowedRails, rail])

  const currentAmount = amount ?? summary.allocatable_balance
  const amountValid = isValidPrincipalAmount(currentAmount, summary.allocatable_balance)
  const selectedRail = cashSelected ? 'cash' : rail
  const quoteAmount = cashSelected ? summary.principal_total : normalizeMoney(currentAmount)
  const [pricedAmount, setPricedAmount] = useState(quoteAmount)
  useEffect(() => {
    const timer = window.setTimeout(() => setPricedAmount(quoteAmount), 180)
    return () => window.clearTimeout(timer)
  }, [quoteAmount])
  const quoteRequired = audience === 'staff' && access.kind === 'authenticated' && Boolean(summary.breakdown)
  const canQuote = quoteRequired && Boolean(selectedRail && quoteAmount && (cashSelected ? cash?.allowed : amountValid && noncashAvailable))
  const quoteEnabled = canQuote && pricedAmount === quoteAmount
  const quoteQuery = useQuery({
    queryKey: ['invoice-payment-quote', summary.invoice_id, summary.version, selectedRail, quoteAmount],
    queryFn: () => fetchPaymentQuote(summary.invoice_id, selectedRail!, quoteAmount!, summary.version),
    enabled: quoteEnabled,
    retry: false,
    staleTime: 0,
    // Display-only continuity. A previous version is never eligible for submission.
    placeholderData: (previous, previousQuery) => previousQuery?.queryKey[1] === summary.invoice_id
      && previousQuery.queryKey[3] === selectedRail ? previous : undefined,
  })
  const quote = canQuote ? quoteQuery.data : undefined
  const quoteReady = quoteEnabled && !quoteQuery.isFetching && !quoteQuery.error && quote?.settlement_version === summary.version
    && quote?.rail === selectedRail && quote?.principal_amount === quoteAmount
  const partialInvoicePayment = Boolean(quoteAmount && moneyToCents(quoteAmount) !== moneyToCents(summary.principal_total))
  const remainingAfterPayment = quoteAmount ? centsToMoney((moneyToCents(summary.outstanding_balance) ?? 0n) - (moneyToCents(quoteAmount) ?? 0n)) : '0.00'
  const submissionBlocked = Boolean(submissionBlockedReason || (quoteRequired && !quoteReady))
  const referenceRequired = audience === 'staff' && rail !== 'card'
  const canSubmit = Boolean(
    rail
    && amountValid
    && allowedRails.includes(rail)
    && (rail !== 'fleet_payment' || fleetProvider !== 'Other' || fleetProviderName.trim())
    && !submissionBlocked
    && summary.allowed_actions?.create_attempt !== false
    && (!referenceRequired || reference.trim()),
  )
  const providerLabel = summary.card_provider === 'stripe_connect'
    ? 'Stripe Connect'
    : summary.card_provider === 'quickbooks_payments'
      ? audience === 'staff' ? 'QBO Payments' : 'QuickBooks Payments'
      : 'Card'

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!rail) throw new Error('Select a payment method')
      if (rail === 'fleet_payment' && (!reference.trim() || (fleetProvider === 'Other' && !fleetProviderName.trim()))) throw new Error('Enter the Fleet provider and instrument reference.')
      const normalized = normalizeMoney(currentAmount)
      if (!normalized) throw new Error('Enter a valid amount')
      const created = await createPaymentAttempt(
        access,
        {
          amount: normalized,
          rail,
          expected_settlement_version: summary.version,
          sender_evidence: rail === 'zelle' || audience === 'staff'
            ? {
                sender_email: senderEmail.trim() || null,
                sender_phone: senderPhone.trim() || null,
                reference: reference.trim() || null,
                note: note.trim() || null,
                ...(rail === 'fleet_payment' ? {
                  fleet_provider: fleetProvider, fleet_provider_name: fleetProvider === 'Other' ? fleetProviderName.trim() : null,
                  authorization_number: authorization.trim() || null,
                } : {}),
              }
            : null,
        },
        createIdempotencyKey(),
      )
      return created
    },
    onSuccess: async created => {
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      if (!mounted.current) return
      setAmount(null)
      setEditingAmount(false)
      setAttempt(created)
      setReceivedAmount(created.principal_amount)
      onUpdated(created.settlement)
      if (created.provider_client_secret && created.provider === 'stripe_connect') {
        const instance = await getStripeForAccount(created.provider_account_id ?? null)
        if (mounted.current) setStripe(instance)
      } else if (created.state === 'confirmed') {
        setAttempt(null)
        toast.success(`${RAIL_META[rail!].label} payment recorded.`)
      } else if (rail === 'zelle') {
        toast.success('Zelle amount reserved for shop confirmation.')
      }
    },
    onError: error => {
      if (!mounted.current) return
      const parsed = paymentApiError(error)
      toast.error(parsed.message)
      if (typeof parsed.current_version === 'number') {
        queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      }
    },
  })

  const confirmMutation = useMutation({
    mutationFn: async () => {
      if (!attempt?.attempt_version) throw new Error('Payment confirmation version is unavailable. Refresh before confirming.')
      const normalizedReceived = normalizeMoney(receivedAmount)
      if (!normalizedReceived || !isPositiveMoney(normalizedReceived)) {
        throw new Error('Enter the amount actually received before confirming.')
      }
      return confirmPaymentAttempt(
        access,
        attempt.attempt_id,
        {
          expected_attempt_version: attempt.attempt_version,
          received_amount: normalizedReceived,
          reference: reference.trim(),
          note: note.trim() || undefined,
        },
        createIdempotencyKey(),
      )
    },
    onSuccess: confirmed => {
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      if (!mounted.current) return
      setAttempt(null)
      onUpdated(confirmed.settlement)
      toast.success(`${RAIL_META[confirmed.rail].label} payment confirmed.`)
    },
    onError: error => { if (mounted.current) toast.error(paymentApiError(error, 'Unable to confirm this payment.').message) },
  })

  const quickBooksMutation = useMutation({
    mutationFn: async (paymentToken: string) => {
      if (!attempt?.attempt_version) throw new Error('Payment attempt version is unavailable. Refresh before paying.')
      return chargeQuickBooksPaymentAttempt(
        access,
        attempt.attempt_id,
        paymentToken,
        attempt.attempt_version,
        createIdempotencyKey(),
      )
    },
    onSuccess: charged => {
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      if (!mounted.current) return
      setAttempt(charged.state === 'pending' ? charged : null)
      onUpdated(charged.settlement)
    },
  })

  const copy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(key)
      window.setTimeout(() => setCopied(null), 1500)
    } catch {
      toast.error('Unable to copy')
    }
  }

  const stripeOptions = useMemo(() => attempt?.provider_client_secret ? ({
    clientSecret: attempt.provider_client_secret,
    appearance: {
      theme: dark ? 'night' as const : 'stripe' as const,
      variables: {
        colorPrimary: '#b9472f',
        borderRadius: '12px',
      },
    },
  }) : null, [attempt?.provider_client_secret, dark])

  if (summary.state === 'paid' && !isPositiveMoney(summary.unapplied_credit) && !isPositiveMoney(summary.refund_pending)) return null

  if (providerSubmitted) {
    return (
      <div className={`rounded-2xl border p-4 text-sm ${panel}`} role="status">
        <p className="font-bold">Card submitted to Stripe Connect</p>
        <p className={`mt-1 ${quiet}`}>We are waiting for signed provider confirmation. Do not submit another payment while this attempt is reconciling.</p>
        <button
          type="button"
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
            queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
          }}
          className="mt-3 min-h-[44px] rounded-xl border border-current px-3 text-xs font-extrabold"
        >
          Refresh settlement
        </button>
      </div>
    )
  }

  if (attempt?.provider === 'quickbooks_payments' && attempt.provider_token_url) {
    return (
      <section className={`rounded-2xl border p-4 ${panel}`}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>QuickBooks Payments</p>
            <h2 className="mt-1 font-extrabold">Complete secure card payment</h2>
          </div>
          <button type="button" onClick={() => setAttempt(null)} className={`min-h-[44px] px-2 text-sm font-bold ${quiet}`}>Back</button>
        </div>
        <QuickBooksPaymentPanel
          tokenUrl={attempt.provider_token_url}
          submitLabel={`Pay ${formatMoney(attempt.provider_charge_amount)} with card`}
          tone={tone}
          onToken={token => quickBooksMutation.mutateAsync(token).then(() => undefined)}
          onSuccess={() => undefined}
        />
        <p className={`mt-3 text-xs ${quiet}`}>
          {formatMoney(attempt.principal_amount)} applies to the invoice
          {attempt.card_fee_amount !== '0.00' ? ` · ${formatMoney(attempt.card_fee_amount)} card fee` : ''}.
        </p>
      </section>
    )
  }

  if (attempt?.provider_client_secret && stripeOptions && stripe) {
    return (
      <section className={`rounded-2xl border p-4 ${panel}`}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>{providerLabel}</p>
            <h2 className="mt-1 font-extrabold">Complete secure card payment</h2>
          </div>
          <button type="button" onClick={() => { setAttempt(null); setStripe(null) }} className={`min-h-[44px] px-2 text-sm font-bold ${quiet}`}>Back</button>
        </div>
        <Elements stripe={stripe} options={stripeOptions}>
          <StripeAttemptForm
            attempt={attempt}
            tone={tone}
            onProviderSubmitted={() => {
              setProviderSubmitted(true)
              queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
              queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
            }}
          />
        </Elements>
      </section>
    )
  }

  if (attempt && audience === 'staff' && attempt.rail !== 'card' && attempt.state === 'pending') {
    const label = RAIL_META[attempt.rail].label
    const normalizedReceived = normalizeMoney(receivedAmount)
    const receivedAmountValid = Boolean(normalizedReceived && isPositiveMoney(normalizedReceived) && (attempt.rail !== 'fleet_payment' || normalizedReceived === attempt.principal_amount))
    return (
      <section className={`rounded-2xl border p-4 ${panel}`} aria-labelledby="manual-payment-confirmation-heading">
        <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>Staff confirmation required</p>
        <h2 id="manual-payment-confirmation-heading" className="mt-1 font-extrabold">Confirm {label} was received</h2>
        <dl className={`mt-4 divide-y rounded-xl border ${dark ? 'divide-[#2a3245] border-[#2a3245]' : 'divide-slate-200 border-slate-200'}`}>
          <div className="flex min-h-[48px] items-center justify-between gap-3 px-3"><dt className={quiet}>Reserved for invoice</dt><dd className="font-extrabold tabular-nums">{formatMoney(attempt.principal_amount)}</dd></div>
          <div className="flex min-h-[48px] items-center justify-between gap-3 px-3"><dt className={quiet}>Reference</dt><dd className="font-bold">{reference}</dd></div>
        </dl>
        <label className="mt-3 block">
          <span className={`mb-1.5 block text-xs font-bold ${quiet}`}>Amount actually received</span>
          <div className="relative">
            <span className={`pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-bold ${quiet}`}>$</span>
            <input
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={receivedAmount}
              disabled={confirmMutation.isPending}
              readOnly={attempt.rail === 'fleet_payment'}
              onChange={event => setReceivedAmount(event.target.value)}
              onBlur={() => { const normalized = normalizeMoney(receivedAmount); if (normalized) setReceivedAmount(normalized) }}
              aria-invalid={!receivedAmountValid}
              className={`h-11 w-full rounded-xl border pl-8 pr-3 text-sm font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-[var(--accent-500,#d25d43)] ${input}`}
            />
          </div>
        </label>
        <p className={`mt-2 text-xs ${quiet}`}>{attempt.rail === 'fleet_payment' ? 'Confirm the verified instrument amount. This records receipt; it does not redeem a code or confirm bank clearance.' : 'Confirm only after independently verifying the external payment. If the received amount is higher than the current balance, the excess stays unapplied and enters refund-first resolution.'}</p>
        {!attempt.attempt_version && <p role="alert" className="mt-3 text-sm text-red-500">Confirmation version is missing. Refresh this invoice before confirming.</p>}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button type="button" onClick={() => setAttempt(null)} disabled={confirmMutation.isPending} className={`min-h-[44px] px-3 text-sm font-bold ${quiet}`}>Back</button>
          <button type="button" onClick={() => confirmMutation.mutate()} disabled={!attempt.attempt_version || !receivedAmountValid || confirmMutation.isPending} className="min-h-[44px] rounded-xl bg-[var(--accent-600,#b9472f)] px-4 text-sm font-extrabold text-white disabled:opacity-50">
            {confirmMutation.isPending ? 'Confirming…' : `Confirm ${label} received`}
          </button>
        </div>
      </section>
    )
  }

  if (attempt && rail === 'zelle' && attempt.state === 'pending') {
    return (
      <section className={`rounded-2xl border p-4 ${panel}`} aria-labelledby="zelle-reservation-heading">
        <div className="flex items-start gap-3">
          <Clock3 className="mt-0.5 h-5 w-5 text-amber-500" />
          <div>
            <h2 id="zelle-reservation-heading" className="font-extrabold">Zelle amount reserved</h2>
            <p className={`mt-1 text-sm ${quiet}`}>
              Send the exact amount. The remaining invoice balance stays available for another payment.
            </p>
          </div>
        </div>
        <div className={`mt-4 divide-y rounded-xl border ${dark ? 'divide-[#2a3245] border-[#2a3245]' : 'divide-slate-200 border-slate-200'}`}>
          {[
            ['Amount', formatMoney(attempt.principal_amount), attempt.principal_amount],
            ...(zelleRecipient ? [['Recipient', zelleRecipient.display, zelleRecipient.display]] : []),
            ...(zelleRecipient ? [['Memo', zelleRecipient.memo, zelleRecipient.memo]] : []),
          ].map(([label, display, value]) => (
            <div key={label} className="flex min-h-[52px] items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0"><p className={`text-[11px] ${quiet}`}>{label}</p><p className="truncate font-bold tabular-nums">{display}</p></div>
              <button type="button" onClick={() => copy(value, label)} className="flex min-h-[44px] items-center gap-1 text-xs font-bold text-sky-500">
                {copied === label ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied === label ? 'Copied' : 'Copy'}
              </button>
            </div>
          ))}
        </div>
        <p className={`mt-3 text-xs ${quiet}`}>
          {attempt.expires_at ? `Reservation expires ${new Date(attempt.expires_at).toLocaleString()}. ` : ''}
          The invoice changes only after the shop confirms receipt.
        </p>
        {isPositiveMoney(summary.allocatable_balance) && (
          <button
            type="button"
            onClick={() => setAttempt(null)}
            className="mt-4 flex min-h-[48px] w-full items-center justify-center rounded-xl border border-current px-4 text-sm font-extrabold"
          >
            Make another payment · {formatMoney(summary.allocatable_balance)} available
          </button>
        )}
      </section>
    )
  }

  if (!noncashAvailable && !cash && audience !== 'staff') {
    return (
      <div className={`rounded-2xl border p-4 text-sm ${panel}`} role="status">
        <p className="font-bold">{summary.allowed_actions?.confirm_cash ? 'Other payment methods are unavailable.' : 'No new payment can be started right now.'}</p>
        <p className={`mt-1 ${quiet}`}>{summary.allowed_actions?.payment_unavailable_reason ?? 'Existing payments and pending reconciliation remain visible above. Contact the shop if this balance needs attention.'}</p>
      </div>
    )
  }

  const moreTenders = audience === 'staff' && <button type="button" onClick={() => setExpandedTenders(!expandedTenders)}
    aria-label="More payment methods" aria-expanded={expandedTenders} aria-controls={`payment-tenders-${summary.invoice_id}`}
    className={`flex min-h-11 items-center gap-2 rounded-lg px-2 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${quiet}`}>
    <MoreHorizontal className="h-4 w-4" />{expandedTenders ? 'Less' : 'More'}
  </button>

  return (
    <section className={`rounded-2xl border p-4 ${panel}`} aria-labelledby={`settlement-payment-${summary.invoice_id}`}>
      <fieldset disabled={createMutation.isPending || cash?.pending} className="m-0 min-w-0 border-0 p-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id={`settlement-payment-${summary.invoice_id}`} className="font-extrabold">{audience === 'staff' ? 'Payment method' : 'Choose an amount and tender'}</h2>
        </div>
        {audience !== 'staff' && <p className={`text-xs ${quiet}`}>Up to {formatMoney(summary.allocatable_balance)}</p>}
      </div>

      <div id={`payment-tenders-${summary.invoice_id}`} className="mt-3" role="radiogroup" aria-label="Payment tender">
        <div className={`grid gap-2 ${audience === 'staff' ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
          {tenders.map((item, index) => {
            const meta = item === 'cash' ? { label: 'Cash', detail: 'Full payment only', icon: Banknote } : RAIL_META[item]
            const Icon = meta.icon
            const selected = item === 'cash' ? cashSelected : !cashSelected && rail === item
            return (
              <button key={item} ref={node => { railRefs.current[index] = node }} type="button" role="radio"
                aria-checked={selected} disabled={tenderDisabled(item)}
                title={audience === 'staff' ? item === 'fleet_payment' ? `${meta.label} · ${meta.detail}` : meta.detail : undefined}
                aria-label={audience === 'staff' && item === 'fleet_payment' ? meta.label : undefined}
                aria-describedby={item === 'cash' && cash?.reason ? `cash-reason-${summary.invoice_id}` : undefined}
                tabIndex={selected || (!noncashAvailable && item === 'cash') ? 0 : -1}
                onClick={() => selectTender(item)}
                onKeyDown={event => {
                  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
                  event.preventDefault()
                  const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown'
                  for (let step = 1; step <= tenders.length; step++) {
                    const next = (index + (forward ? step : -step) + tenders.length) % tenders.length
                    if (tenderDisabled(tenders[next])) continue
                    selectTender(tenders[next])
                    railRefs.current[next]?.focus()
                    break
                  }
                }}
                className={`flex min-h-11 items-center gap-2 rounded-xl border px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-500,#d25d43)] disabled:cursor-not-allowed disabled:opacity-50 ${selected ? dark ? 'border-[#d25d43] bg-[#d25d43]/10' : 'border-emerald-700 bg-emerald-50' : input}`}>
                <Icon className="h-4 w-4 shrink-0" />
                <span className="min-w-0"><span className="block text-sm font-extrabold">{item === 'card' ? providerLabel : audience === 'staff' && item === 'fleet_payment' ? 'Fleet' : meta.label}</span>{audience !== 'staff' && <span className={`block text-[11px] ${quiet}`}>{meta.detail}</span>}</span>
              </button>
            )
          })}
        </div>
      </div>
      {audience === 'staff' && <div className={`mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-sm ${dark ? 'border-[#2a3245]' : 'border-slate-200'}`}>
        {moreTenders}
        {!cashSelected && noncashAvailable && <button type="button" disabled={createMutation.isPending} onClick={() => { setAmount(editingAmount ? null : currentAmount); setEditingAmount(!editingAmount) }} className="ml-auto min-h-11 rounded-lg px-2 font-semibold underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700">
          {editingAmount ? 'Pay full balance' : 'Pay partial amount'}
        </button>}
      </div>}
      {!cashSelected && noncashAvailable && (audience !== 'staff' || editingAmount) && <label className="mt-3 block">
        <span className={`mb-1.5 block text-xs font-bold ${quiet}`}>Amount applied to invoice</span>
        <div className="relative">
          <span className={`pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-bold ${quiet}`}>$</span>
          <input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={currentAmount}
            onChange={event => setAmount(event.target.value)}
            onBlur={() => { const normalized = normalizeMoney(currentAmount); if (normalized) setAmount(normalized) }}
            aria-invalid={currentAmount.length > 0 && !amountValid}
            aria-label="Amount applied to invoice"
            aria-describedby={`settlement-amount-help-${summary.invoice_id}`}
            className={`h-12 w-full rounded-xl border pl-8 pr-3 text-lg font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-[var(--accent-500,#d25d43)] ${input}`}
          />
        </div>
        <span id={`settlement-amount-help-${summary.invoice_id}`} className={`mt-1 block min-h-4 text-xs ${currentAmount.length > 0 && !amountValid ? 'text-red-500' : quiet}`}>
          {currentAmount.length > 0 && !amountValid ? `Enter at least $0.01 and no more than ${formatMoney(summary.allocatable_balance)}, the amount available to pay.` : 'Card fees are calculated only on the card-funded portion.'}
        </span>
      </label>}

      {cash?.reason && !cash.allowed && <p id={`cash-reason-${summary.invoice_id}`} className={`mt-2 text-xs ${quiet}`}>{cash.reason}</p>}
      {!noncashAvailable && <p role="status" className={`mt-3 text-sm ${quiet}`}>{summary.allowed_actions?.payment_unavailable_reason ?? 'Other payment methods are unavailable.'}</p>}
      {taxExemptionControl && <div className="mt-4">{taxExemptionControl}</div>}

      {!cashSelected && noncashAvailable && audience === 'staff' && rail === 'fleet_payment' && <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-xs font-bold">Fleet provider<select value={fleetProvider} onChange={event => {
          setFleetProvider(event.target.value as FleetProvider)
          setFleetProviderName('')
          setReference('')
          setAuthorization('')
          setNote('')
        }} className={`mt-1 h-11 w-full rounded-xl border px-3 text-sm ${input}`}><option value="EFS">EFS / MoneyCode</option><option value="Comchek">Comchek</option><option value="T-Chek">T-Chek</option><option value="Other">Other provider</option></select></label>
        {fleetProvider === 'Other' && <label className="block text-xs font-bold">Provider name<input maxLength={100} required value={fleetProviderName} onChange={event => setFleetProviderName(event.target.value)} className={`mt-1 h-11 w-full rounded-xl border px-3 text-sm ${input}`} /></label>}
        <label className="block text-xs font-bold">Approval reference (optional)<input maxLength={255} value={authorization} onChange={event => setAuthorization(event.target.value)} className={`mt-1 h-11 w-full rounded-xl border px-3 text-sm ${input}`} /></label>
      </div>}

      {!cashSelected && noncashAvailable && audience === 'staff' && rail && rail !== 'card' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>{rail === 'check' ? 'Check number' : rail === 'ach' ? 'Bank trace' : rail === 'fleet_payment' ? 'Instrument / code reference' : 'Zelle transaction reference'}</span><input maxLength={255} value={reference} onChange={event => setReference(event.target.value)} required className={`h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>Verification note <span className="font-normal">(optional)</span></span><input value={note} onChange={event => setNote(event.target.value)} className={`h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
        </div>
      )}

      {audience === 'staff' && summary.breakdown && <section aria-label="Payment breakdown" aria-busy={Boolean(submissionBlockedReason || (canQuote && !quoteReady))} className={`mt-4 border-t pt-4 ${dark ? 'border-[#2a3245]' : 'border-slate-200'}`}>
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-bold">Payment breakdown</h3>
          <span aria-hidden="true" className={`text-xs ${quiet} ${submissionBlockedReason || (canQuote && !quoteReady) ? '' : 'invisible'}`}>Updating…</span>
        </div>
        <dl className="mt-3 space-y-2 text-sm">
          {[
            ['subtotal', 'Services & parts', summary.breakdown.subtotal],
            ...(isPositiveMoney(summary.breakdown.discount_amount) ? [['discount', 'Discount', summary.breakdown.discount_amount]] : []),
            ['supplies', 'Shop supplies', summary.breakdown.shop_supplies_amount],
            ['tax', !chargeControls && summary.tax_exemption?.applied ? 'Sales tax · exempt' : 'Sales tax', summary.breakdown.sales_tax_amount],
            ...(partialInvoicePayment ? [['principal', 'Invoice total before card fees', summary.breakdown.principal_total]] : []),
          ].map(([key, label, value]) => <div key={key} className="flex items-center justify-between gap-2">
            <dt className={`flex min-w-0 flex-1 items-center ${quiet}`}>{label}{key === 'tax' && chargeControls?.referenceAction}</dt>
            <dd className="flex shrink-0 items-center gap-2 font-semibold tabular-nums">
              {key === 'supplies' ? chargeControls?.supplies : key === 'tax' ? chargeControls?.salesTax : null}
              <span className="min-w-[4rem] text-right">{label === 'Discount' ? '−' : ''}{formatMoney(value)}</span>
            </dd>
          </div>)}
        </dl>
        {selectedRail && <dl aria-live="polite" className={`mt-3 space-y-2 border-t pt-3 text-sm ${dark ? 'border-[#2a3245]' : 'border-slate-200'}`}>
          {partialInvoicePayment && <div className="flex justify-between gap-4"><dt className={quiet}>This payment toward invoice</dt><dd className="font-semibold tabular-nums">{quote ? formatMoney(quote.principal_amount) : '—'}</dd></div>}
          {selectedRail === 'card' && <div className="flex items-center justify-between gap-2"><dt className={`min-w-0 flex-1 ${quiet}`}>Card processing fee</dt><dd className="flex shrink-0 items-center gap-2 font-semibold tabular-nums">{chargeControls?.cardFee}<span className="min-w-[4rem] text-right">{quote ? formatMoney(quote.card_fee_amount) : '—'}</span></dd></div>}
          {selectedRail === 'card' && <div className="flex justify-between gap-4"><dt className={quiet}>Tax on card fee</dt><dd className="font-semibold tabular-nums">{quote ? formatMoney(quote.card_fee_tax_amount) : '—'}</dd></div>}
          <div className="flex items-baseline justify-between gap-4 pt-2"><dt className="font-bold">Amount to collect</dt><dd className="text-xl font-extrabold tabular-nums">{quote ? formatMoney(quote.total_amount) : '—'}</dd></div>
          {!cashSelected && isPositiveMoney(remainingAfterPayment) && <div className={`flex justify-between gap-4 text-xs ${quiet}`}><dt>Remaining after confirmation</dt><dd className="tabular-nums">{formatMoney(remainingAfterPayment)}</dd></div>}
        </dl>}
        {chargeControls?.details}
        <p role="status" className="sr-only">{canQuote && !quoteReady ? 'Calculating payment total…' : ''}</p>
        {quoteEnabled && quoteQuery.error && <div role="alert" className="mt-3 text-sm text-red-700"><p>{paymentApiError(quoteQuery.error, 'Payment total could not be verified. Retry before continuing.').message}</p><button type="button" onClick={() => { void quoteQuery.refetch(); void queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] }) }} className="min-h-11 font-semibold underline">Retry payment total</button></div>}
      </section>}
      {submissionBlockedReason && <p role="status" className="sr-only">{submissionBlockedReason}</p>}
      {cashSelected && <fieldset disabled={submissionBlocked} className="min-w-0 border-0 p-0">{cash?.confirmation}</fieldset>}

      {!cashSelected && rail === 'zelle' && audience !== 'staff' && (
        <div className="mt-3 grid gap-3">
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>Sender email or phone <span className="font-normal">(optional)</span></span><input value={senderEmail || senderPhone} onChange={event => { const value = event.target.value; value.includes('@') ? (setSenderEmail(value), setSenderPhone('')) : (setSenderPhone(value), setSenderEmail('')) }} className={`h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
          <button type="button" aria-expanded={showTransferDetails} onClick={() => setShowTransferDetails(!showTransferDetails)} className={`min-h-11 justify-self-start rounded-lg text-sm font-semibold underline underline-offset-4 focus-visible:ring-2 ${quiet}`}>{showTransferDetails ? 'Hide transfer details' : 'Add transfer details (optional)'}</button>
          {showTransferDetails && <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-bold">Zelle transaction reference (optional)<input maxLength={255} value={reference} onChange={event => setReference(event.target.value)} className={`mt-1 h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
            <label className="block text-xs font-bold">Note to shop (optional)<input maxLength={1000} value={note} onChange={event => setNote(event.target.value)} className={`mt-1 h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
          </div>}
        </div>
      )}

      {!cashSelected && noncashAvailable && <><button type="button" onClick={() => createMutation.mutate()} disabled={!canSubmit || createMutation.isPending} className="mt-4 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent-600,#b9472f)] px-4 text-sm font-extrabold text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
        {createMutation.isPending && <Spinner size="sm" />}
        {createMutation.isPending ? 'Preparing…' : rail === 'card' ? `Continue to ${providerLabel}` : audience === 'staff' ? `Record ${rail ? RAIL_META[rail].label : 'payment'}` : 'Reserve Zelle amount'}
      </button>
      <p className={`mt-2 text-center text-[11px] ${quiet}`}>Applied after {rail === 'card' ? 'provider' : 'shop'} confirmation.</p>
      </>}
      </fieldset>
    </section>
  )
}

export default function SettlementPaymentPanel(props: Parameters<typeof InvoicePaymentPanel>[0]) {
  // Draft amounts, evidence and provider attempts cannot follow a different
  // invoice, including customer/guest callers that do not key this component.
  return <InvoicePaymentPanel key={`${props.audience}:${props.summary.invoice_id}`} {...props} />
}

export { SettlementPaymentPanel }
