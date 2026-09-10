import { useEffect, useMemo, useRef, useState } from 'react'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, Check, Clock3, Copy, CreditCard, Landmark, Send } from 'lucide-react'
import toast from 'react-hot-toast'

import { Spinner } from '@/components/ui'
import QuickBooksPaymentPanel from '@/features/customer-portal/QuickBooksPaymentPanel'
import { getStripeForAccount } from '@/lib/stripe'

import { chargeQuickBooksPaymentAttempt, confirmPaymentAttempt, createIdempotencyKey, createPaymentAttempt, paymentApiError } from './api'
import { formatMoney, isPositiveMoney, isValidPrincipalAmount, normalizeMoney } from './money'
import type {
  InvoiceSettlementSummary,
  PaymentAttemptResponse,
  PaymentRail,
  SettlementAccess,
} from './types'

const RAIL_META: Record<PaymentRail, { label: string; detail: string; icon: typeof CreditCard }> = {
  card: { label: 'Card', detail: 'Secure online payment', icon: CreditCard },
  zelle: { label: 'Zelle', detail: 'Confirmed by the shop', icon: Send },
  check: { label: 'Check', detail: 'Staff verified reference', icon: Building2 },
  ach: { label: 'ACH', detail: 'Staff verified bank trace', icon: Landmark },
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

export default function SettlementPaymentPanel({
  access,
  summary,
  audience,
  tone = 'dark',
  senderDefaults,
  zelleRecipient,
  onUpdated,
}: {
  access: SettlementAccess
  summary: InvoiceSettlementSummary
  audience: 'customer' | 'guest' | 'staff'
  tone?: 'dark' | 'light'
  senderDefaults?: { email?: string | null; phone?: string | null }
  zelleRecipient?: { display: string; memo: string } | null
  onUpdated: (next: InvoiceSettlementSummary) => void
}) {
  const queryClient = useQueryClient()
  const allowedRails = useMemo(() => summary.allowed_actions?.rails ?? [], [summary.allowed_actions?.rails])
  const [rail, setRail] = useState<PaymentRail | null>(allowedRails[0] ?? null)
  const [amount, setAmount] = useState(summary.allocatable_balance)
  const [reference, setReference] = useState('')
  const [note, setNote] = useState('')
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

  useEffect(() => {
    setAmount(summary.allocatable_balance)
  }, [summary.allocatable_balance, summary.version])

  useEffect(() => {
    if (rail && allowedRails.includes(rail)) return
    setRail(allowedRails[0] ?? null)
  }, [allowedRails, rail])

  const amountValid = isValidPrincipalAmount(amount, summary.allocatable_balance)
  const referenceRequired = audience === 'staff' && rail !== 'card'
  const canSubmit = Boolean(
    rail
    && amountValid
    && summary.allowed_actions?.create_attempt !== false
    && (!referenceRequired || reference.trim()),
  )
  const providerLabel = summary.card_provider === 'stripe_connect'
    ? 'Stripe Connect'
    : summary.card_provider === 'quickbooks_payments'
      ? 'QuickBooks Payments'
      : 'Card'

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!rail) throw new Error('Select a payment method')
      const normalized = normalizeMoney(amount)
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
              }
            : null,
        },
        createIdempotencyKey(),
      )
      return created
    },
    onSuccess: async created => {
      setAttempt(created)
      setReceivedAmount(created.principal_amount)
      onUpdated(created.settlement)
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      if (created.provider_client_secret && created.provider === 'stripe_connect') {
        setStripe(await getStripeForAccount(created.provider_account_id ?? null))
      } else if (created.state === 'confirmed') {
        setAttempt(null)
        toast.success(`${RAIL_META[rail!].label} payment recorded.`)
      } else if (rail === 'zelle') {
        toast.success('Zelle amount reserved for shop confirmation.')
      }
    },
    onError: error => {
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
      setAttempt(null)
      onUpdated(confirmed.settlement)
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      toast.success(`${RAIL_META[confirmed.rail].label} payment confirmed.`)
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to confirm this payment.').message),
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
      setAttempt(charged.state === 'pending' ? charged : null)
      onUpdated(charged.settlement)
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
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
    const receivedAmountValid = Boolean(normalizedReceived && isPositiveMoney(normalizedReceived))
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
              onChange={event => setReceivedAmount(event.target.value.replace(/[^\d.]/g, ''))}
              onBlur={() => { const normalized = normalizeMoney(receivedAmount); if (normalized) setReceivedAmount(normalized) }}
              aria-invalid={!receivedAmountValid}
              className={`h-11 w-full rounded-xl border pl-8 pr-3 text-sm font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-[var(--accent-500,#d25d43)] ${input}`}
            />
          </div>
        </label>
        <p className={`mt-2 text-xs ${quiet}`}>Confirm only after independently verifying the external payment. If the received amount is higher than the current balance, the excess stays unapplied and enters refund-first resolution.</p>
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

  if (allowedRails.length === 0 || summary.allowed_actions?.create_attempt === false) {
    return (
      <div className={`rounded-2xl border p-4 text-sm ${panel}`} role="status">
        <p className="font-bold">No new payment can be started right now.</p>
        <p className={`mt-1 ${quiet}`}>Existing payments and pending reconciliation remain visible above. Contact the shop if this balance needs attention.</p>
      </div>
    )
  }

  return (
    <section className={`rounded-2xl border p-4 ${panel}`} aria-labelledby={`settlement-payment-${summary.invoice_id}`}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className={`text-[11px] font-extrabold uppercase tracking-[0.12em] ${quiet}`}>New payment</p>
          <h2 id={`settlement-payment-${summary.invoice_id}`} className="mt-1 font-extrabold">Choose an amount and tender</h2>
        </div>
        <p className={`text-xs ${quiet}`}>Up to {formatMoney(summary.allocatable_balance)}</p>
      </div>

      <label className="mt-4 block">
        <span className={`mb-1.5 block text-xs font-bold ${quiet}`}>Amount applied to invoice</span>
        <div className="relative">
          <span className={`pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-bold ${quiet}`}>$</span>
          <input
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={amount}
            onChange={event => setAmount(event.target.value.replace(/[^\d.]/g, ''))}
            onBlur={() => { const normalized = normalizeMoney(amount); if (normalized) setAmount(normalized) }}
            aria-invalid={amount.length > 0 && !amountValid}
            aria-describedby={`settlement-amount-help-${summary.invoice_id}`}
            className={`h-12 w-full rounded-xl border pl-8 pr-3 text-lg font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-[var(--accent-500,#d25d43)] ${input}`}
          />
        </div>
        <span id={`settlement-amount-help-${summary.invoice_id}`} className={`mt-1 block min-h-4 text-xs ${amount.length > 0 && !amountValid ? 'text-red-500' : quiet}`}>
          {amount.length > 0 && !amountValid ? `Enter $0.01–${formatMoney(summary.allocatable_balance)}.` : 'Card fees are calculated only on the card-funded portion.'}
        </span>
      </label>

      <div className="mt-3" role="radiogroup" aria-label="Payment tender">
        <p className={`mb-1.5 text-xs font-bold ${quiet}`}>Tender</p>
        <div className={`grid gap-2 ${allowedRails.length > 2 ? 'sm:grid-cols-2' : 'grid-cols-2'}`}>
          {allowedRails.map((item, index) => {
            const Icon = RAIL_META[item].icon
            const selected = rail === item
            return (
              <button
                key={item}
                ref={node => { railRefs.current[index] = node }}
                type="button"
                role="radio"
                aria-checked={selected}
                tabIndex={selected ? 0 : -1}
                onClick={() => { setRail(item); setAttempt(null) }}
                onKeyDown={event => {
                  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
                  event.preventDefault()
                  const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown'
                  const next = (index + (forward ? 1 : -1) + allowedRails.length) % allowedRails.length
                  setRail(allowedRails[next])
                  railRefs.current[next]?.focus()
                }}
                className={`flex min-h-[52px] items-center gap-2 rounded-xl border px-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-500,#d25d43)] ${selected ? dark ? 'border-[#d25d43] bg-[#d25d43]/10' : 'border-[#b9472f] bg-orange-50' : input}`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="min-w-0"><span className="block text-sm font-extrabold">{item === 'card' ? providerLabel : RAIL_META[item].label}</span><span className={`block truncate text-[11px] ${quiet}`}>{RAIL_META[item].detail}</span></span>
              </button>
            )
          })}
        </div>
      </div>

      {rail === 'zelle' && audience !== 'staff' && (
        <div className="mt-3 grid gap-3">
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>Sender email or phone <span className="font-normal">(optional)</span></span><input value={senderEmail || senderPhone} onChange={event => { const value = event.target.value; value.includes('@') ? (setSenderEmail(value), setSenderPhone('')) : (setSenderPhone(value), setSenderEmail('')) }} className={`h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
        </div>
      )}

      {audience === 'staff' && rail && rail !== 'card' && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>{rail === 'check' ? 'Check number' : rail === 'ach' ? 'Bank trace' : 'Zelle transaction reference'}</span><input value={reference} onChange={event => setReference(event.target.value)} required className={`h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
          <label className="block"><span className={`mb-1 block text-xs font-bold ${quiet}`}>Verification note <span className="font-normal">(optional)</span></span><input value={note} onChange={event => setNote(event.target.value)} className={`h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 ${input}`} /></label>
        </div>
      )}

      <button type="button" onClick={() => createMutation.mutate()} disabled={!canSubmit || createMutation.isPending} className="mt-4 flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl bg-[var(--accent-600,#b9472f)] px-4 text-sm font-extrabold text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
        {createMutation.isPending && <Spinner size="sm" />}
        {createMutation.isPending ? 'Preparing…' : rail === 'card' ? `Continue to ${providerLabel}` : audience === 'staff' ? `Record ${rail ? RAIL_META[rail].label : 'payment'}` : 'Reserve Zelle amount'}
      </button>
      <p className={`mt-2 text-center text-[11px] ${quiet}`}>Payments are applied only after provider or staff confirmation. This screen never marks an invoice paid optimistically.</p>
    </section>
  )
}

export { SettlementPaymentPanel }
