import { ControlButton, ControlInput } from '@/components/ui/Controls'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Label, Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Banknote, Building2, Check, ChevronDown, Copy, CreditCard, Landmark, MoreHorizontal, Send, Truck } from 'lucide-react'
import toast from 'react-hot-toast'

import { Spinner } from '@/components/ui'
import QuickBooksPaymentPanel from '@/features/customer-portal/QuickBooksPaymentPanel'
import PaymentStatusRefresh from './PaymentStatusRefresh'
import EfsSubmissionForm from './EfsSubmissionForm'
import { getStripeForAccount } from '@/lib/stripe'

import { chargeQuickBooksPaymentAttempt, confirmPaymentAttempt, createIdempotencyKey, createPaymentAttempt, fetchPaymentQuote, paymentApiError } from './api'
import { centsToMoney, formatMoney, isPositiveMoney, isValidPrincipalAmount, moneyToCents, normalizeMoney } from './money'
import type { InlineCashTender } from './FullCashPaymentPanel'
import type { InlineInvoiceChargeControls } from './InvoiceChargeControls'
import type {
  InvoiceSettlementSummary,
  PaymentAttemptResponse,
  PaymentAttemptCreate,
  PaymentRail,
  FleetProvider,
  PaymentAllocation,
  SettlementAccess,
} from './types'

const RAIL_META: Record<PaymentRail, { label: string; detail: string; icon: typeof CreditCard }> = {
  card: { label: 'Card', detail: 'Secure online payment', icon: CreditCard },
  zelle: { label: 'Zelle', detail: 'Confirmed by the shop', icon: Send },
  check: { label: 'Check', detail: 'Staff verified reference', icon: Building2 },
  ach: { label: 'ACH', detail: 'Account transfer / bank transfer', icon: Landmark },
  fleet_payment: { label: 'Fleet Check / Code', detail: 'EFS / MoneyCode, Comchek, T-Chek or other provider', icon: Truck },
}

function combinedCardProcessingFee(cardFeeAmount: string, cardFeeTaxAmount: string): string {
  return centsToMoney((moneyToCents(cardFeeAmount) ?? 0n) + (moneyToCents(cardFeeTaxAmount) ?? 0n))
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
      toast.success('Your payment is being confirmed.')
      onProviderSubmitted()
    }
    setBusy(false)
  }

  return (
    <form onSubmit={submit} className="space-y-4" aria-label="Secure card payment">
      <PaymentElement />
      {error && <p role="alert" className={`rounded-xl border p-3 text-sm ${tone === 'dark' ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-red-200 bg-red-50 text-red-700'}`}>{error}</p>}
      <ControlButton type="submit" disabled={!stripe || busy} className="flex  w-full items-center justify-center gap-2 rounded-xl bg-[color-mix(in_srgb,var(--accent-600,#b9472f)_75%,#000)] px-4 text-sm font-extrabold text-white hover:brightness-110 disabled:opacity-50">
        {busy && <Spinner size="sm" />}
        {busy ? 'Confirming…' : `Pay ${formatMoney(attempt.provider_charge_amount)} with card`}
      </ControlButton>
      <p className={`text-xs ${tone === 'dark' ? 'text-[#99a4b7]' : 'text-slate-500'}`}>
        {formatMoney(attempt.principal_amount)} applies to the invoice
        {attempt.card_fee_amount !== '0.00' ? ` · ${formatMoney(combinedCardProcessingFee(attempt.card_fee_amount, attempt.card_fee_tax_amount))} card fee` : ''}.
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
  allocations = [],
  hideVerificationNotice = false,
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
  allocations?: PaymentAllocation[]
  hideVerificationNotice?: boolean
}) {
  const queryClient = useQueryClient()
  const latestSummary = useRef(summary)
  useEffect(() => { latestSummary.current = summary }, [summary])
  const accepts = (next: InvoiceSettlementSummary) => mounted.current && next.invoice_id === latestSummary.current.invoice_id && next.version >= latestSummary.current.version && !(latestSummary.current.payment_verification_required && !next.payment_verification_required && next.version <= latestSummary.current.version)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const allowedRails = useMemo(() => [...(summary.allowed_actions?.rails ?? []).filter(item => audience === 'staff' || item === 'card' || item === 'zelle'), ...(audience !== 'staff' && summary.allowed_actions?.submit_efs === true ? ['fleet_payment' as const] : [])], [summary.allowed_actions?.rails, summary.allowed_actions?.submit_efs, audience])
  const [rail, setRail] = useState<PaymentRail | null>(allowedRails[0] ?? null)
  // Null follows the full balance. An explicit draft belongs to the operator,
  // not to a particular quote or invoice-charge version.
  const [amount, setAmount] = useState<string | null>(null)
  const [editingAmount, setEditingAmount] = useState(false)
  const amountInput = useRef<HTMLInputElement>(null)
  const [expandedTenders, setExpandedTenders] = useState(false)
  const [otherMethodsOpen, setOtherMethodsOpen] = useState(false)
  const [efsBusy, setEfsBusy] = useState(false)
  const [showTransferDetails, setShowTransferDetails] = useState(false)
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
  const [fleetProvider, setFleetProvider] = useState<FleetProvider>('EFS')
  const [fleetProviderName, setFleetProviderName] = useState('')
  const [authorization, setAuthorization] = useState('')
  const [senderEmail, setSenderEmail] = useState(senderDefaults?.email || '')
  const [senderPhone, setSenderPhone] = useState(senderDefaults?.phone || '')
  const [attempt, setAttempt] = useState<PaymentAttemptResponse | null>(null)
  const [zelleDraft, setZelleDraft] = useState<{ amount: string; version: number; recipient: string; memo: string; key: string } | null>(null)
  const reportRequest = useRef<{ key: string; body: PaymentAttemptCreate } | null>(null)
  const [reportStarted, setReportStarted] = useState(false)
  const zelleHeading = useRef<HTMLHeadingElement>(null)
  const instructionTrigger = useRef<HTMLButtonElement>(null)
  const draftWasOpen = useRef(false)
  useEffect(() => {
    if (zelleDraft) zelleHeading.current?.focus()
    else if (draftWasOpen.current) instructionTrigger.current?.focus()
    draftWasOpen.current = Boolean(zelleDraft)
  }, [zelleDraft])
  const [receivedAmount, setReceivedAmount] = useState('')
  const [stripe, setStripe] = useState<Stripe | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [providerSubmitted, setProviderSubmitted] = useState(false)
  useEffect(() => {
    if (!attempt) return
    const current = allocations.find(row => row.attempt_id === attempt.attempt_id)
    if (current && current.state !== 'pending') { setAttempt(null); setStripe(null); setProviderSubmitted(false) }
  }, [allocations, attempt])
  const railRefs = useRef<Array<HTMLButtonElement | null>>([])
  const dark = tone === 'dark'
  const panel = dark ? 'border-[#2a3245] bg-[#111722] text-[#edf0f6]' : 'border-slate-200 bg-white text-slate-950'
  const input = dark ? 'border-[#3a465e] bg-[#182234] text-white placeholder:text-[#738097]' : 'border-slate-300 bg-white text-slate-950 placeholder:text-slate-400'
  const quiet = dark ? 'text-[#99a4b7]' : 'text-slate-500'
  const selectedFeeNote = rail === 'fleet_payment' ? 'No card fee. EFS account fees may apply.'
    : rail === 'zelle' ? 'No card processing fee.' : 'Any processing fee is shown before payment.'


  const cash = audience === 'staff' && access.kind === 'authenticated' ? cashTender : undefined
  const cashSelected = cash?.selected === true
  const genericAvailable = (summary.allowed_actions?.rails?.length ?? 0) > 0 && summary.allowed_actions?.create_attempt !== false
  const efsAvailable = audience !== 'staff' && summary.allowed_actions?.submit_efs === true
  const noncashAvailable = genericAvailable || efsAvailable
  const secondarySelected = !cashSelected && (rail === 'check' || rail === 'ach' || rail === 'fleet_payment')
  const tenders: Array<PaymentRail | 'cash'> = audience === 'staff'
    ? ['card', 'zelle', ...(cash ? ['cash' as const] : []), ...(expandedTenders ? ['check' as const, 'ach' as const, 'fleet_payment' as const] : [])]
    : allowedRails
  const tenderDisabled = (item: PaymentRail | 'cash') => Boolean(efsBusy || createMutation.isPending || cash?.pending || (item === 'cash' ? !cash?.allowed : !(item === 'fleet_payment' && audience !== 'staff' ? efsAvailable : genericAvailable) || !allowedRails.includes(item)))
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
  const canQuote = !summary.payment_verification_required && quoteRequired && Boolean(selectedRail && quoteAmount && (cashSelected ? cash?.allowed : amountValid && noncashAvailable))
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
  const displayedCardProcessingFee = quote != null
    ? combinedCardProcessingFee(quote.card_fee_amount, quote.card_fee_tax_amount)
    : undefined
  const quoteReady = quoteEnabled && !quoteQuery.isFetching && !quoteQuery.error && quote?.settlement_version === summary.version
    && quote?.rail === selectedRail && quote?.principal_amount === quoteAmount
  const partialInvoicePayment = Boolean(quoteAmount && moneyToCents(quoteAmount) !== moneyToCents(summary.principal_total))
  const remainingAfterPayment = quoteAmount ? centsToMoney((moneyToCents(summary.outstanding_balance) ?? 0n) - (moneyToCents(quoteAmount) ?? 0n)) : '0.00'
  const submissionBlocked = Boolean(submissionBlockedReason || (quoteRequired && !quoteReady))
  const referenceRequired = audience === 'staff' && rail !== 'card'
  const canSubmit = Boolean(
    rail
    && !(audience !== 'staff' && rail === 'fleet_payment')
    && !summary.payment_verification_required
    && amountValid
    && allowedRails.includes(rail)
    && (rail !== 'fleet_payment' || fleetProvider !== 'Other' || fleetProviderName.trim())
    && !submissionBlocked
    && summary.allowed_actions?.create_attempt !== false
    && (!referenceRequired || reference.trim()),
  )
  const providerLabel = audience !== 'staff' ? 'Card' : summary.card_provider === 'stripe_connect'
    ? 'Stripe Connect'
    : summary.card_provider === 'quickbooks_payments'
      ? 'QBO Payments'
      : 'Card'

  const createMutation = useMutation({
    mutationFn: async () => {
      if (latestSummary.current.payment_verification_required) throw new Error('Payment status needs review before another payment.')
      if (!rail) throw new Error('Select a payment method')
      if (rail === 'fleet_payment' && (!reference.trim() || (fleetProvider === 'Other' && !fleetProviderName.trim()))) throw new Error('Enter the Fleet provider and instrument reference.')
      const normalized = normalizeMoney(currentAmount)
      if (!normalized) throw new Error('Enter a valid amount')
      const reportingZelle = rail === 'zelle' && audience !== 'staff'
      if (reportingZelle && (!zelleDraft || zelleDraft.version !== summary.version || zelleDraft.recipient !== zelleRecipient?.display || zelleDraft.memo !== zelleRecipient?.memo || normalized !== zelleDraft.amount)) throw new Error('These payment details changed. Review the invoice before reporting your transfer.')
      const body: PaymentAttemptCreate = {
          amount: normalized,
          rail,
          expected_settlement_version: summary.version,
          ...(reportingZelle ? { transfer_sent_confirmed: true } : {}),
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
        }
      if (reportingZelle && !reportRequest.current) reportRequest.current = { key: zelleDraft!.key, body }
      const request = reportingZelle ? reportRequest.current! : { key: createIdempotencyKey(), body }
      if (reportingZelle) setReportStarted(true)
      return createPaymentAttempt(access, request.body, request.key)
    },
    onSuccess: async created => {
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      if (!accepts(created.settlement)) return
      latestSummary.current = created.settlement
      setAmount(null)
      setEditingAmount(false)
      setAttempt(created.rail === 'zelle' && audience !== 'staff' ? null : created)
      setZelleDraft(null)
      setReportStarted(false)
      reportRequest.current = null
      setReceivedAmount(created.principal_amount)
      onUpdated(created.settlement)
      if (created.provider_client_secret && created.provider === 'stripe_connect') {
        const instance = await getStripeForAccount(created.provider_account_id ?? null)
        if (accepts(created.settlement)) setStripe(instance)
      } else if (created.state === 'confirmed') {
        setAttempt(null)
        toast.success(`${RAIL_META[rail!].label} payment recorded.`)
      } else if (rail === 'zelle') {
        toast.success('Transfer reported. The shop will verify receipt.')
      }
    },
    onError: error => {
      if (!mounted.current) return
      const parsed = paymentApiError(error)
      if (typeof parsed.status === 'number' && parsed.status < 500) { setReportStarted(false); reportRequest.current = null }
      const publicMessage = /source_|handoff_|bill_to_|configuration/.test(parsed.code) || /\b(DBN|ETS|idempotency|mapping|reconciling)\b/i.test(parsed.message)
        ? 'Please refresh this invoice or contact the shop before paying.' : parsed.message
      toast.error(audience === 'staff' ? parsed.message : publicMessage)
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
      if (!accepts(confirmed.settlement)) return
      latestSummary.current = confirmed.settlement
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
      if (!accepts(charged.settlement)) return
      latestSummary.current = charged.settlement
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

  // Composed invoice screens give the shared summary ownership of this notice.
  if (summary.payment_verification_required) return hideVerificationNotice ? null : (
    <div className={`rounded-2xl border p-4 text-sm ${panel}`} role="status">
      <p className="font-bold">Payment status needs review</p>
      <p className={`mt-1 ${quiet}`}>Contact the shop before making another payment.</p>
    </div>
  )

  if (summary.state === 'paid' && !isPositiveMoney(summary.unapplied_credit) && !isPositiveMoney(summary.refund_pending)) return null

  if (providerSubmitted) {
    return (
      <div className={`rounded-2xl border p-4 text-sm ${panel}`} role="status">
        <p className="font-bold">{audience === 'staff' ? 'Card submitted to Stripe Connect' : 'Payment being confirmed'}</p>
        <p className={`mt-1 ${quiet}`}>{audience === 'staff' ? 'We are waiting for signed provider confirmation. Do not submit another payment while this attempt is reconciling.' : "Your payment is being confirmed. Please don't pay again yet."}</p>
        <ControlButton
          type="button"
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
            queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
          }}
          className="mt-3  rounded-xl border border-current px-3 text-xs font-extrabold"
        >
          Refresh settlement
        </ControlButton>
      </div>
    )
  }

  if (attempt?.provider === 'quickbooks_payments' && attempt.provider_token_url) {
    return (
      <section className={`rounded-2xl border p-4 ${panel}`}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            {audience === 'staff' && <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>QuickBooks Payments</p>}
            <h2 className="mt-1 font-extrabold">Complete secure card payment</h2>
          </div>
          <ControlButton type="button" onClick={() => setAttempt(null)} className={` px-2 text-sm font-bold ${quiet}`}>Back</ControlButton>
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
          {attempt.card_fee_amount !== '0.00' ? ` · ${formatMoney(combinedCardProcessingFee(attempt.card_fee_amount, attempt.card_fee_tax_amount))} card fee` : ''}.
        </p>
      </section>
    )
  }

  if (attempt?.provider_client_secret && stripeOptions && stripe) {
    return (
      <section className={`rounded-2xl border p-4 ${panel}`}>
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            {audience === 'staff' && <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>{providerLabel}</p>}
            <h2 className="mt-1 font-extrabold">Complete secure card payment</h2>
          </div>
          <ControlButton type="button" onClick={() => { setAttempt(null); setStripe(null) }} className={` px-2 text-sm font-bold ${quiet}`}>Back</ControlButton>
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
            <ControlInput
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={receivedAmount}
              disabled={confirmMutation.isPending}
              readOnly={attempt.rail === 'fleet_payment'}
              onChange={event => setReceivedAmount(event.target.value)}
              onBlur={() => { const normalized = normalizeMoney(receivedAmount); if (normalized) setReceivedAmount(normalized) }}
              aria-invalid={!receivedAmountValid}
              className={` w-full rounded-xl border pl-8 pr-3 text-sm font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-[var(--accent-500,#d25d43)] ${input}`}
            />
          </div>
        </label>
        <p className={`mt-2 text-xs ${quiet}`}>{attempt.rail === 'fleet_payment' ? 'Confirm the verified instrument amount. This records receipt; it does not redeem a code or confirm bank clearance.' : 'Confirm only after independently verifying the external payment. If the received amount is higher than the current balance, the excess stays unapplied and enters refund-first resolution.'}</p>
        {!attempt.attempt_version && <p role="alert" className="mt-3 text-sm text-red-500">Confirmation version is missing. Refresh this invoice before confirming.</p>}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <ControlButton type="button" onClick={() => setAttempt(null)} disabled={confirmMutation.isPending} className={` px-3 text-sm font-bold ${quiet}`}>Back</ControlButton>
          <ControlButton type="button" onClick={() => confirmMutation.mutate()} disabled={!attempt.attempt_version || !receivedAmountValid || confirmMutation.isPending} className=" rounded-xl bg-[color-mix(in_srgb,var(--accent-600,#b9472f)_75%,#000)] px-4 text-sm font-extrabold text-white disabled:opacity-50">
            {confirmMutation.isPending ? 'Confirming…' : `Confirm ${label} received`}
          </ControlButton>
        </div>
      </section>
    )
  }

  if (zelleDraft && audience !== 'staff') {
    const errorStatus = createMutation.isError ? paymentApiError(createMutation.error).status : undefined
    const knownRejection = typeof errorStatus === 'number' && errorStatus < 500
    const unchanged = zelleDraft.version === summary.version && zelleDraft.recipient === zelleRecipient?.display
      && zelleDraft.memo === zelleRecipient?.memo && isValidPrincipalAmount(zelleDraft.amount, summary.allocatable_balance)
    return <section className={`rounded-2xl border p-4 ${panel}`} aria-labelledby="zelle-instructions-heading">
      <h2 ref={zelleHeading} id="zelle-instructions-heading" tabIndex={-1} className="font-extrabold">Pay with Zelle</h2>
      <p className={`mt-2 text-sm ${quiet}`}>Send this transfer in your banking app, then tell the shop below.</p>
      <dl className={`mt-4 divide-y border-y ${dark ? 'divide-[#2a3245] border-[#2a3245]' : 'divide-slate-200 border-slate-200'}`}>
        {[
          ['Amount', formatMoney(zelleDraft.amount), zelleDraft.amount],
          ['Recipient', zelleDraft.recipient, zelleDraft.recipient],
          ['Memo', zelleDraft.memo, zelleDraft.memo],
        ].map(([label, display, value]) => <div key={label} className="flex min-h-[60px] items-center justify-between gap-3 py-3">
          <div className="min-w-0"><dt className={`text-xs ${quiet}`}>{label}</dt><dd className="break-words font-bold tabular-nums">{display}</dd></div>
          <ControlButton type="button" aria-label={`Copy ${label.toLowerCase()}`} onClick={() => { void copy(value, label) }} className="inline-flex shrink-0 items-center gap-1 px-2 text-xs font-bold">
            {copied === label ? <Check size={15} /> : <Copy size={15} />}{copied === label ? 'Copied' : 'Copy'}
          </ControlButton>
        </div>)}
      </dl>
      <div className="mt-4 space-y-3">
        <label className="block text-xs font-bold">Sender email or phone (optional)<ControlInput disabled={reportStarted} value={senderEmail || senderPhone} onChange={event => { const value = event.target.value; if (value.includes('@')) { setSenderEmail(value); setSenderPhone('') } else { setSenderPhone(value); setSenderEmail('') } }} className={`mt-1 w-full rounded-xl border px-3 text-sm ${input}`} /></label>
        <ControlButton type="button" aria-expanded={showTransferDetails} onClick={() => setShowTransferDetails(!showTransferDetails)} className={`text-sm font-semibold underline underline-offset-4 ${quiet}`}>{showTransferDetails ? 'Hide transfer details' : 'Add transfer details (optional)'}</ControlButton>
        {showTransferDetails && <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-bold">Zelle transaction reference (optional)<ControlInput disabled={reportStarted} maxLength={255} value={reference} onChange={event => setReference(event.target.value)} className={`mt-1 w-full rounded-xl border px-3 ${input}`} /></label>
          <label className="text-xs font-bold">Note to shop (optional)<ControlInput disabled={reportStarted} maxLength={1000} value={note} onChange={event => setNote(event.target.value)} className={`mt-1 w-full rounded-xl border px-3 ${input}`} /></label>
        </div>}
      </div>
      <p className={`mt-4 text-xs ${quiet}`}>Report only after sending. The shop will verify receipt before marking the invoice paid.</p>
      {!unchanged && <p role="alert" className="mt-3 text-sm">The invoice or payment details changed. Return to the invoice to review them.</p>}
      {createMutation.isError && <div className="mt-3 space-y-3"><p role="alert" className="text-sm">{knownRejection ? 'Your transfer report wasn’t saved. Review the details and try again.' : 'We couldn’t confirm your report was saved. Check the status or retry this report.'}</p><PaymentStatusRefresh access={access} summary={summary} tone={tone} onUpdated={onUpdated} /></div>}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:flex sm:flex-nowrap sm:justify-end">
        <ControlButton type="button" disabled={createMutation.isPending || (reportStarted && unchanged)} onClick={() => { setZelleDraft(null); reportRequest.current = null; setReportStarted(false); createMutation.reset() }} className={`min-h-11 w-full whitespace-nowrap rounded-xl border px-3 text-sm font-semibold sm:w-auto ${dark ? 'border-[#3a465e]' : 'border-slate-300'}`}>Back to invoice</ControlButton>
        <ControlButton type="button" disabled={!unchanged || !canSubmit || createMutation.isPending} onClick={() => createMutation.mutate()} className="inline-flex min-h-11 w-full items-center justify-center gap-2 whitespace-nowrap rounded-xl bg-[color-mix(in_srgb,var(--accent-600,#b9472f)_75%,#000)] px-4 text-sm font-extrabold text-white disabled:opacity-50 sm:w-auto">
          {createMutation.isPending && <Spinner size="sm" />}{createMutation.isPending ? 'Reporting…' : createMutation.isError ? 'Retry report' : "I’ve sent the payment"}
        </ControlButton>
      </div>
    </section>
  }

  if (!noncashAvailable && (!cash || (!cash.allowed && !cashSelected))) {
    const resolving = isPositiveMoney(summary.unapplied_credit) || isPositiveMoney(summary.refund_pending)
    const pending = isPositiveMoney(summary.active_pending_principal)
    const quietPending = pending && !resolving
    const settled = !isPositiveMoney(summary.outstanding_balance)
    const title = resolving ? 'Payment review needed' : pending ? 'Payment awaiting confirmation' : settled ? 'Invoice paid in full' : !cash && summary.allowed_actions?.confirm_cash ? 'Other payment methods are unavailable.' : 'Payment unavailable'
    const explanation = resolving
      ? audience === 'staff' ? 'Review the excess payment shown above before collecting any additional money.' : 'Contact the shop for help with this payment.'
      : pending ? audience === 'staff' ? `${formatMoney(summary.active_pending_principal)} is awaiting confirmation. It is reserved against this invoice to prevent a duplicate payment.` : `${formatMoney(summary.active_pending_principal)} is awaiting confirmation. Please don’t send this amount again.`
      : settled ? 'There is no remaining balance to collect.'
      : audience === 'staff' ? summary.allowed_actions?.payment_unavailable_reason ?? cash?.reason ?? 'Payment collection is unavailable. Review the invoice’s accounting status.' : 'Online payment is currently unavailable. Contact the shop for help.'
    return (
      <div className={quietPending ? 'px-1 text-sm' : `rounded-2xl border p-4 text-sm ${panel}`}>
        {!quietPending && <><p className="font-bold">{title}</p><p className={`mt-1 ${quiet}`}>{explanation}</p></>}
        <div className="mt-3"><PaymentStatusRefresh access={access} summary={summary} tone={tone} onUpdated={onUpdated} /></div>
      </div>
    )
  }

  const moreTenders = audience === 'staff' && <ControlButton controlKind="action" type="button" onClick={() => setExpandedTenders(!expandedTenders)}
    aria-label="More payment methods" aria-expanded={expandedTenders} aria-controls={`payment-tenders-${summary.invoice_id}`}
    className={`flex  items-center gap-2 rounded-lg px-2 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 ${quiet}`}>
    <MoreHorizontal className="h-4 w-4" />{expandedTenders ? 'Less' : 'More'}
  </ControlButton>

  return (
    <section className={`rounded-2xl border p-4 ${panel}`} aria-labelledby={`settlement-payment-${summary.invoice_id}`}>
      <fieldset disabled={createMutation.isPending || cash?.pending} className="m-0 min-w-0 border-0 p-0">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id={`settlement-payment-${summary.invoice_id}`} tabIndex={-1} className="font-extrabold">Payment method</h2>
        </div>
      </div>

      <div id={`payment-tenders-${summary.invoice_id}`} className="mt-3" role="radiogroup" aria-label="Payment tender">
        <div className={`grid gap-2 ${audience === 'staff' ? 'sm:grid-cols-3' : tenders.length === 3 ? 'grid-cols-3' : tenders.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
          {tenders.map((item, index) => {
            const meta = item === 'cash' ? { label: 'Cash', detail: 'Full payment only', icon: Banknote } : RAIL_META[item]
            const Icon = meta.icon
            const selected = item === 'cash' ? cashSelected : !cashSelected && rail === item
            return (
              <ControlButton controlKind="content" key={item} ref={node => { railRefs.current[index] = node }} type="button" role="radio"
                aria-checked={selected} disabled={tenderDisabled(item)}
                title={audience === 'staff' ? item === 'fleet_payment' ? `${meta.label} · ${meta.detail}` : meta.detail : undefined}
                aria-label={audience === 'staff' && item === 'fleet_payment' ? meta.label : undefined}
                aria-describedby={item === 'cash' && cash?.reason ? `cash-reason-${summary.invoice_id}` : undefined}
                tabIndex={selected || (index === 0 && secondarySelected && !expandedTenders) || (!noncashAvailable && item === 'cash') ? 0 : -1}
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
                className={`flex min-h-11 min-w-0 items-center ${audience === 'staff' ? 'text-left' : 'justify-center text-center'} ${audience !== 'staff' && tenders.length === 3 ? 'gap-1.5 px-2' : 'gap-2 px-3'} rounded-xl border py-2 outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-500,#d25d43)] disabled:cursor-not-allowed disabled:opacity-50 ${selected ? dark ? 'border-[#d25d43] bg-[#d25d43]/10' : 'border-emerald-700 bg-emerald-50' : input}`}>
                <Icon className="h-4 w-4 shrink-0" />
                <span className="min-w-0"><span className="block text-sm font-extrabold">{item === 'card' ? providerLabel : item === 'fleet_payment' ? audience === 'staff' ? 'EFS codes' : 'EFS' : meta.label}</span>{audience !== 'staff' && tenders.length !== 3 && <span className={`block text-[11px] ${quiet}`}>{item === 'card' ? 'Credit or debit' : item === 'zelle' ? 'No card fee' : item === 'fleet_payment' ? '10-digit code' : meta.detail}</span>}</span>
              </ControlButton>
            )
          })}
        </div>
      </div>
      {audience === 'staff' && <div className={`mt-3 flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-sm ${dark ? 'border-[#2a3245]' : 'border-slate-200'}`}>
        {moreTenders}
        {!cashSelected && noncashAvailable && <ControlButton type="button" disabled={createMutation.isPending} onClick={() => { setAmount(editingAmount ? null : currentAmount); setEditingAmount(!editingAmount) }} className="ml-auto  rounded-lg px-2 font-semibold underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700">
          {editingAmount ? 'Pay full balance' : 'Pay partial amount'}
        </ControlButton>}
      </div>}

      {!cashSelected && noncashAvailable && (audience !== 'staff' || editingAmount) && <div className="mt-3">
        <div className="mb-1.5 flex items-center justify-between gap-3">
          <label htmlFor={`settlement-amount-${summary.invoice_id}`} className={`text-xs font-bold ${quiet}`}>{audience === 'staff' ? 'Amount applied to invoice' : 'Payment amount'}</label>
          {audience !== 'staff' && <ControlButton type="button" disabled={efsBusy} onClick={() => {
            if (editingAmount) { setAmount(null); setEditingAmount(false) }
            else { setEditingAmount(true); setAmount('') }
            amountInput.current?.focus()
          }} className={`min-h-11 whitespace-nowrap px-1 text-sm font-semibold underline underline-offset-4 ${quiet}`}>
            {editingAmount ? isPositiveMoney(summary.active_pending_principal) ? 'Use available' : 'Pay full balance' : 'Partial payment'}
          </ControlButton>}
        </div>
        <div className="relative">
          <span className={`pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-bold ${quiet}`}>$</span>
          <ControlInput
            ref={amountInput}
            id={`settlement-amount-${summary.invoice_id}`}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={currentAmount}
            onChange={event => {
              const next = event.target.value
              if (audience !== 'staff' && !/^\d*(?:\.\d{0,2})?$/.test(next)) return
              setAmount(next)
              if (audience !== 'staff') setEditingAmount(true)
            }}
            onBlur={() => { const normalized = normalizeMoney(currentAmount); if (normalized) setAmount(normalized) }}
            aria-invalid={currentAmount.length > 0 && !amountValid}
            disabled={efsBusy}
            aria-label={audience === 'staff' ? 'Amount applied to invoice' : 'Payment amount'}
            aria-describedby={`settlement-amount-help-${summary.invoice_id}`}
            className={` w-full rounded-xl border pl-8 pr-3 text-lg font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-[var(--accent-500,#d25d43)] ${input}`}
          />
        </div>
        <span id={`settlement-amount-help-${summary.invoice_id}`} className={`mt-1 block min-h-4 text-xs ${currentAmount.length > 0 && !amountValid ? 'text-red-500' : quiet}`}>
          {currentAmount.length > 0 && !amountValid ? `Enter at least $0.01 and no more than ${formatMoney(summary.allocatable_balance)}, the amount available to pay.` : audience === 'staff' ? rail === 'card' ? 'Card fees are calculated only on the card-funded portion.' : '' : selectedFeeNote}
        </span>
      </div>}
      {audience !== 'staff' && amountValid && (moneyToCents(currentAmount) ?? 0n) < (moneyToCents(summary.allocatable_balance) ?? 0n) && <p className={`mt-2 text-sm ${quiet}`} role="status">
        Remaining after confirmation: <strong className="tabular-nums">{formatMoney(centsToMoney((moneyToCents(summary.outstanding_balance) ?? 0n) - (moneyToCents(currentAmount) ?? 0n)))}</strong>
      </p>}


      {cash?.reason && !cash.allowed && <p id={`cash-reason-${summary.invoice_id}`} className={`mt-2 text-xs ${quiet}`}>{cash.reason}</p>}
      {!noncashAvailable && <p role="status" className={`mt-3 text-sm ${quiet}`}>{summary.allowed_actions?.payment_unavailable_reason ?? 'Other payment methods are unavailable.'}</p>}
      {taxExemptionControl && <div className="mt-4">{taxExemptionControl}</div>}

      {!cashSelected && noncashAvailable && audience === 'staff' && rail === 'fleet_payment' && <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="text-xs font-bold"><Listbox value={fleetProvider} disabled={createMutation.isPending || cash?.pending} onChange={(provider: FleetProvider) => {
          setFleetProvider(provider)
          setFleetProviderName('')
          setReference('')
          setAuthorization('')
          setNote('')
        }}>
          <Label>Fleet provider</Label>
          <ListboxButton data-db-control="select" className={`mt-1 flex h-11 w-full items-center justify-between gap-2 rounded-xl border px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-500,#0891b2)] disabled:cursor-not-allowed disabled:opacity-50 ${input}`}>
            <span>{fleetProvider === 'EFS' ? 'EFS / MoneyCode' : fleetProvider === 'Other' ? 'Other provider' : fleetProvider}</span><ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0" />
          </ListboxButton>
          <ListboxOptions anchor="bottom start" modal={false} className={`z-[10010] w-[var(--button-width)] max-w-[calc(100vw-2rem)] rounded-xl border p-1 shadow-lg outline-none [--anchor-gap:4px] [--anchor-padding:16px] ${dark ? 'border-[#2a3245] bg-[#161d2b] text-slate-100' : 'border-slate-200 bg-white text-slate-900'}`}>
            {(['EFS', 'Comchek', 'T-Chek', 'Other'] as const).map(provider => <ListboxOption key={provider} value={provider} className={`flex min-h-10 cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm ${dark ? 'data-[focus]:bg-white/10 data-[selected]:bg-emerald-950' : 'data-[focus]:bg-slate-100 data-[selected]:bg-emerald-50'}`}>
              {({ selected }) => <><span>{provider === 'EFS' ? 'EFS / MoneyCode' : provider === 'Other' ? 'Other provider' : provider}</span><Check aria-hidden="true" className={`h-4 w-4 text-emerald-600 ${selected ? '' : 'invisible'}`} /></>}
            </ListboxOption>)}
          </ListboxOptions>
        </Listbox></div>
        {fleetProvider === 'Other' && <label className="block text-xs font-bold">Provider name<ControlInput maxLength={100} required value={fleetProviderName} onChange={event => setFleetProviderName(event.target.value)} className={`mt-1  w-full rounded-xl border px-3 text-sm ${input}`} /></label>}
        <label className="block text-xs font-bold">Approval reference (optional)<ControlInput maxLength={255} value={authorization} onChange={event => setAuthorization(event.target.value)} className={`mt-1  w-full rounded-xl border px-3 text-sm ${input}`} /></label>
      </div>}

      {!cashSelected && noncashAvailable && audience === 'staff' && rail && rail !== 'card' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>{rail === 'check' ? 'Check number' : rail === 'ach' ? 'Bank trace' : rail === 'fleet_payment' ? 'Instrument / code reference' : 'Zelle transaction reference'}</span><ControlInput maxLength={255} value={reference} onChange={event => setReference(event.target.value)} required className={` w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>Verification note <span className="font-normal">(optional)</span></span><ControlInput value={note} onChange={event => setNote(event.target.value)} className={` w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
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
          {selectedRail === 'card' && <div className="flex items-center justify-between gap-2"><dt className={`min-w-0 flex-1 ${quiet}`}>Card processing fee</dt><dd className="flex shrink-0 items-center gap-2 font-semibold tabular-nums">{chargeControls?.cardFee}<span className="min-w-[4rem] text-right">{displayedCardProcessingFee ? formatMoney(displayedCardProcessingFee) : '—'}</span></dd></div>}
          <div className="flex items-baseline justify-between gap-4 pt-2"><dt className="font-bold">Amount to collect</dt><dd className="text-xl font-extrabold tabular-nums">{quote ? formatMoney(quote.total_amount) : '—'}</dd></div>
          {!cashSelected && isPositiveMoney(remainingAfterPayment) && <div className={`flex justify-between gap-4 text-xs ${quiet}`}><dt>Remaining after confirmation</dt><dd className="tabular-nums">{formatMoney(remainingAfterPayment)}</dd></div>}
        </dl>}
        {chargeControls?.details}
        <p role="status" className="sr-only">{canQuote && !quoteReady ? 'Calculating payment total…' : ''}</p>
        {quoteEnabled && quoteQuery.error && <div role="alert" className="mt-3 text-sm text-red-700"><p>{paymentApiError(quoteQuery.error, 'Payment total could not be verified. Retry before continuing.').message}</p><ControlButton type="button" onClick={() => { void quoteQuery.refetch(); void queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] }) }} className=" font-semibold underline">Retry payment total</ControlButton></div>}
      </section>}
      {submissionBlockedReason && <p role="status" className="sr-only">{submissionBlockedReason}</p>}
      {cashSelected && <fieldset disabled={submissionBlocked} className="min-w-0 border-0 p-0">{cash?.confirmation}</fieldset>}

      {!cashSelected && rail === 'zelle' && audience !== 'staff' && !zelleRecipient?.display && <p role="status" className={`mt-3 text-sm ${quiet}`}>Zelle instructions are unavailable. Contact the shop.</p>}
      {!cashSelected && noncashAvailable && <>{audience !== 'staff' && rail === 'fleet_payment' ? <EfsSubmissionForm access={access} summary={summary} amount={currentAmount} tone={tone} onUpdated={onUpdated} onBusyChange={setEfsBusy} /> : <ControlButton ref={instructionTrigger} type="button" onClick={() => {
        if (rail === 'zelle' && audience !== 'staff') {
          const normalized = normalizeMoney(currentAmount)
          if (!normalized || !canSubmit || !zelleRecipient?.display) return
          setAmount(normalized); reportRequest.current = null; setReportStarted(false); createMutation.reset()
          setZelleDraft({ amount: normalized, version: summary.version, recipient: zelleRecipient.display, memo: zelleRecipient.memo, key: createIdempotencyKey() })
          return
        }
        createMutation.mutate()
      }} disabled={!canSubmit || createMutation.isPending || (rail === 'zelle' && audience !== 'staff' && !zelleRecipient?.display)} className="mt-4 flex  w-full items-center justify-center gap-2 rounded-xl bg-[color-mix(in_srgb,var(--accent-600,#b9472f)_75%,#000)] px-4 text-sm font-extrabold text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
        {createMutation.isPending && <Spinner size="sm" />}
        {createMutation.isPending ? 'Preparing…' : rail === 'card' ? audience === 'staff' ? `Continue to ${providerLabel}` : 'Continue with card' : audience === 'staff' ? `Record ${rail ? RAIL_META[rail].label : 'payment'}` : 'View Zelle instructions'}
      </ControlButton>}
      {audience === 'staff' && <p className={`mt-2 text-center text-[11px] ${quiet}`}>Applied after {rail === 'card' ? 'provider' : 'shop'} confirmation.</p>}
      </>}
      {audience !== 'staff' && noncashAvailable && !allowedRails.includes('ach') && <div className="mt-2">
        <ControlButton type="button" aria-expanded={otherMethodsOpen} aria-controls={`other-payment-methods-${summary.invoice_id}`} onClick={() => setOtherMethodsOpen(value => !value)} className={`flex min-h-11 items-center gap-2 rounded-lg px-1 text-xs font-semibold ${quiet}`}>
          Other payment methods<ChevronDown aria-hidden="true" className={`h-4 w-4 ${otherMethodsOpen ? 'rotate-180' : ''}`} />
        </ControlButton>
        {otherMethodsOpen && <p id={`other-payment-methods-${summary.invoice_id}`} className={`mt-1 text-sm ${quiet}`}>Contact the shop about bank transfers or other fleet checks/codes.</p>}
      </div>}
      </fieldset>
    </section>
  )
}

export default function SettlementPaymentPanel(props: Parameters<typeof InvoicePaymentPanel>[0]) {
  // Draft amounts, evidence and provider attempts cannot follow a different
  // invoice, including customer/guest callers that do not key this component.
  return <InvoicePaymentPanel key={`${props.audience}:${props.summary.invoice_id}:${props.access.kind === 'guest' ? props.access.token : props.access.invoiceId}`} {...props} />
}

export { SettlementPaymentPanel }
