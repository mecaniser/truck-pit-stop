import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Clock3 } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'

import { confirmPaymentAttempt, createIdempotencyKey, paymentApiError } from './api'
import { formatMoney, isPositiveMoney, normalizeMoney } from './money'
import type { InvoiceSettlementSummary, PaymentAllocation } from './types'

const RAIL_LABEL: Record<'zelle' | 'check' | 'ach' | 'fleet_payment', string> = {
  zelle: 'Zelle',
  check: 'check',
  ach: 'ACH',
  fleet_payment: 'Fleet Check / Code',
}

function PendingManualPaymentItem({
  allocation,
  invoiceId,
  tone,
  onUpdated,
}: {
  allocation: PaymentAllocation
  invoiceId: string
  tone: 'dark' | 'light'
  onUpdated: (next: InvoiceSettlementSummary) => void
}) {
  const queryClient = useQueryClient()
  const submitted = allocation.sender_evidence
  const [reference, setReference] = useState(allocation.reference_number || submitted?.reference || submitted?.reference_number || '')
  const [receivedAmount, setReceivedAmount] = useState(allocation.principal_amount)
  const [note, setNote] = useState(submitted?.note ?? '')
  const sender = [submitted?.sender_name, submitted?.sender_email, submitted?.sender_phone].filter(Boolean).join(' · ')
  const normalizedReceived = normalizeMoney(receivedAmount)
  const receivedValid = Boolean(normalizedReceived && isPositiveMoney(normalizedReceived) && (allocation.rail !== 'fleet_payment' || normalizedReceived === allocation.principal_amount))
  const dark = tone === 'dark'
  const input = dark ? 'border-[#3a465e] bg-[#182234] text-white' : 'border-slate-300 bg-white text-slate-950'
  const quiet = dark ? 'text-[#99a4b7]' : 'text-slate-500'
  const label = RAIL_LABEL[allocation.rail as keyof typeof RAIL_LABEL]

  const confirm = useMutation({
    mutationFn: async () => {
      if (!allocation.attempt_version) throw new Error('Payment confirmation version is unavailable.')
      if (!normalizedReceived || !receivedValid || !reference.trim()) throw new Error('Verified amount and transaction reference are required.')
      return confirmPaymentAttempt(
        { kind: 'authenticated', invoiceId },
        allocation.attempt_id,
        {
          expected_attempt_version: allocation.attempt_version,
          received_amount: normalizedReceived,
          reference: reference.trim(),
          note: note.trim() || undefined,
        },
        createIdempotencyKey(),
      )
    },
    onSuccess: result => {
      onUpdated(result.settlement)
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      toast.success(`${label} payment confirmed.`)
    },
    onError: error => toast.error(paymentApiError(error, `Unable to confirm this ${label} payment.`).message),
  })

  return (
    <li className={`rounded-xl border p-3 ${dark ? 'border-amber-700/40 bg-amber-950/20' : 'border-amber-200 bg-amber-50'}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-extrabold">Confirm pending {label}</p>
          <p className={`mt-0.5 text-xs ${quiet}`}>{formatMoney(allocation.principal_amount)} is reserved until confirmation or expiry.</p>
        </div>
        {allocation.expires_at && <p className={`text-xs ${quiet}`}>Expires {new Date(allocation.expires_at).toLocaleString()}</p>}
      </div>
      {sender && <p className={`mt-2 break-words text-xs ${quiet}`}>Submitted sender: {sender}</p>}
      {allocation.fleet_provider && <p className={`mt-2 break-words text-xs ${quiet}`}>Provider: {allocation.fleet_provider === 'Other' ? allocation.fleet_provider_name : allocation.fleet_provider}{allocation.authorization_number ? ` · Approval: ${allocation.authorization_number}` : ''}</p>}
      {submitted?.note && <p className={`mt-1 break-words text-xs ${quiet}`}>Submitted note: {submitted.note}</p>}
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block text-xs font-bold">Amount actually received
          <div className="relative mt-1">
            <span className={`pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 ${quiet}`}>$</span>
            <input
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={receivedAmount}
              readOnly={allocation.rail === 'fleet_payment'}
              onChange={event => setReceivedAmount(event.target.value.replace(/[^\d.]/g, ''))}
              onBlur={() => { const normalized = normalizeMoney(receivedAmount); if (normalized) setReceivedAmount(normalized) }}
              aria-invalid={!receivedValid}
              className={`h-11 w-full rounded-xl border pl-8 pr-3 font-bold tabular-nums outline-none focus:ring-2 focus:ring-amber-600 ${input}`}
            />
          </div>
        </label>
        <label className="block text-xs font-bold">Transaction reference
          <input value={reference} readOnly={allocation.rail === 'fleet_payment'} onChange={event => setReference(event.target.value)} className={`mt-1 h-11 w-full rounded-xl border px-3 outline-none focus:ring-2 focus:ring-amber-600 ${input}`} />
        </label>
      </div>
      <label className="mt-3 block text-xs font-bold">Verification note <span className="font-normal">(optional)</span>
        <input value={note} onChange={event => setNote(event.target.value)} className={`mt-1 h-11 w-full rounded-xl border px-3 outline-none focus:ring-2 focus:ring-amber-600 ${input}`} />
      </label>
      {!allocation.attempt_version && <p role="alert" className="mt-2 text-xs text-red-500">Refresh this invoice before confirming; its optimistic version is unavailable.</p>}
      <button
        type="button"
        disabled={!allocation.attempt_version || !receivedValid || !reference.trim() || confirm.isPending}
        onClick={() => confirm.mutate()}
        className="mt-3 min-h-[44px] rounded-xl bg-amber-900 px-3 text-xs font-extrabold text-white disabled:opacity-50"
      >
        {confirm.isPending ? 'Confirming…' : `Confirm ${label} received`}
      </button>
    </li>
  )
}

export default function PendingManualPaymentPanel({
  invoiceId,
  summary,
  allocations,
  tone = 'light',
  onUpdated,
}: {
  invoiceId: string
  summary: InvoiceSettlementSummary
  allocations: PaymentAllocation[]
  tone?: 'dark' | 'light'
  onUpdated: (next: InvoiceSettlementSummary) => void
}) {
  if (summary.allowed_actions?.confirm_manual !== true) return null
  const pending = allocations.filter(allocation => allocation.state === 'pending' && allocation.rail !== 'card')
  if (pending.length === 0) return null
  return (
    <section aria-labelledby={`pending-manual-${invoiceId}`}>
      <div className="mb-2 flex items-center gap-2">
        <Clock3 className="h-4 w-4 text-amber-500" />
        <h3 id={`pending-manual-${invoiceId}`} className="text-sm font-extrabold">Payments awaiting shop confirmation</h3>
      </div>
      <ol className="space-y-3">
        {pending.map(allocation => (
          <PendingManualPaymentItem
            key={allocation.attempt_id}
            allocation={allocation}
            invoiceId={invoiceId}
            tone={tone}
            onUpdated={onUpdated}
          />
        ))}
      </ol>
    </section>
  )
}

export { PendingManualPaymentPanel }
