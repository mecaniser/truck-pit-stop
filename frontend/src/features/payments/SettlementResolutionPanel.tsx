import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'

import {
  confirmManualRefund,
  createIdempotencyKey,
  fetchSettlement,
  paymentApiError,
  recordOverpaymentCreditConsent,
  retryPaymentRefund,
} from './api'
import { formatMoney, isPositiveMoney } from './money'
import type { InvoiceSettlementSummary, PaymentAllocation, SettlementAccess } from './types'

function SettlementResolutionItem({
  access,
  summary,
  resolution,
  audience,
  tone = 'light',
  onUpdated,
}: {
  access: SettlementAccess
  summary: InvoiceSettlementSummary
  resolution: PaymentAllocation
  audience: 'customer' | 'guest' | 'staff'
  tone?: 'dark' | 'light'
  onUpdated: (next: InvoiceSettlementSummary) => void
}) {
  const queryClient = useQueryClient()
  const [consentNote, setConsentNote] = useState('')
  const [consentChannel, setConsentChannel] = useState<'in_person' | 'phone'>('in_person')
  const [refundReference, setRefundReference] = useState('')
  const canManage = audience === 'staff' && summary.allowed_actions?.resolve_overpayment === true
  const canConsent = audience !== 'staff' || canManage

  const refresh = async () => {
    const next = await fetchSettlement(access)
    onUpdated(next)
    queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
    queryClient.invalidateQueries({ queryKey: ['invoice-eligible-customer-credits'] })
  }
  const consentMutation = useMutation({
    mutationFn: () => recordOverpaymentCreditConsent(
      access,
      resolution!.overpayment_id!,
      access.kind === 'guest' ? 'guest_token' : audience === 'staff' ? consentChannel : 'customer_portal',
      consentNote.trim(),
      createIdempotencyKey(),
    ),
    onSuccess: async () => {
      await refresh()
      toast.success('Customer consent recorded. The excess is now customer credit.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to record customer-credit consent.').message),
  })
  const refundMutation = useMutation({
    mutationFn: () => confirmManualRefund(resolution!.refund_id!, refundReference.trim(), createIdempotencyKey()),
    onSuccess: async () => {
      await refresh()
      toast.success('Manual refund confirmed and removed from unapplied customer money.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to confirm the manual refund.').message),
  })
  const retryRefundMutation = useMutation({
    mutationFn: () => retryPaymentRefund(resolution!.refund_id!, createIdempotencyKey()),
    onSuccess: async () => {
      await refresh()
      toast.success('Card refund retry queued. The excess remains unapplied until the provider confirms it.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to retry the card refund.').message),
  })

  const dark = tone === 'dark'
  if (resolution.overpayment_state === 'credited') {
    return <div className={`flex gap-2 rounded-xl border p-3 text-sm ${dark ? 'border-emerald-700/40 bg-emerald-950/20 text-emerald-200' : 'border-emerald-200 bg-emerald-50 text-emerald-900'}`}><CheckCircle2 className="h-4 w-4 shrink-0" />Customer consent is recorded and this excess is retained as customer credit.</div>
  }
  const automaticPending = resolution.rail === 'card' && ['pending', 'processing'].includes(resolution.refund_state || '')
  const automaticFailed = resolution.rail === 'card' && resolution.refund_id && resolution.refund_state === 'failed'
  const manualRefundRequired = resolution.refund_id && resolution.refund_state === 'manual_action_required'

  return (
    <section className={`rounded-xl border p-3 ${dark ? 'border-amber-700/40 bg-amber-950/20 text-amber-100' : 'border-amber-300 bg-amber-50 text-amber-950'}`} aria-labelledby={`overpayment-resolution-${resolution.id}`}>
      <div className="flex gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <h3 id={`overpayment-resolution-${resolution.id}`} className="text-sm font-extrabold">Resolve {formatMoney(resolution.unapplied_amount)} customer overpayment</h3>
          <p className={`mt-0.5 text-xs ${dark ? 'text-amber-300' : 'text-amber-800'}`}>
            {automaticPending
              ? 'A refund to the original card is pending. The excess is not revenue.'
              : automaticFailed
                ? 'The automatic card refund failed. The excess remains unapplied and can be retried safely.'
              : manualRefundRequired
                ? 'Refund is the default. Confirm the external refund reference after returning the money, or record explicit customer consent for store credit.'
                : 'The excess remains unapplied and requires a verified resolution.'}
          </p>
        </div>
      </div>

      {automaticFailed && canManage && (
        <button
          type="button"
          disabled={retryRefundMutation.isPending}
          onClick={() => retryRefundMutation.mutate()}
          className="mt-3 min-h-[44px] rounded-xl bg-amber-900 px-3 text-xs font-extrabold text-white disabled:opacity-50"
        >
          {retryRefundMutation.isPending ? 'Retrying…' : 'Retry card refund'}
        </button>
      )}

      {manualRefundRequired && canManage && (
        <div className={`mt-3 rounded-xl border p-3 ${dark ? 'border-amber-800/60 bg-black/20' : 'border-amber-200 bg-white/70'}`}>
          <label className={`block text-xs font-bold ${dark ? 'text-amber-100' : 'text-amber-950'}`}>Refund transaction or check reference
            <input value={refundReference} onChange={event => setRefundReference(event.target.value)} className={`mt-1 h-11 w-full rounded-xl border px-3 text-sm outline-none focus:ring-2 focus:ring-amber-600 ${dark ? 'border-amber-800 bg-[#161b27] text-white' : 'border-amber-300 bg-white'}`} />
          </label>
          <button type="button" disabled={!refundReference.trim() || refundMutation.isPending} onClick={() => refundMutation.mutate()} className="mt-2 min-h-[44px] rounded-xl bg-amber-900 px-3 text-xs font-extrabold text-white disabled:opacity-50">
            {refundMutation.isPending ? 'Confirming…' : 'Confirm refund completed'}
          </button>
        </div>
      )}

      {canConsent && resolution.refund_state !== 'succeeded' && (
        <div className={`mt-3 rounded-xl border p-3 ${dark ? 'border-amber-800/60 bg-black/20' : 'border-amber-200 bg-white/70'}`}>
          {audience === 'staff' && (
            <label className={`block text-xs font-bold ${dark ? 'text-amber-100' : 'text-amber-950'}`}>Consent channel
              <select value={consentChannel} onChange={event => setConsentChannel(event.target.value as 'in_person' | 'phone')} className={`mt-1 h-11 w-full rounded-xl border px-3 text-sm ${dark ? 'border-amber-800 bg-[#161b27] text-white' : 'border-amber-300 bg-white'}`}>
                <option value="in_person">In person</option>
                <option value="phone">Phone</option>
              </select>
            </label>
          )}
          <label className={`${audience === 'staff' ? 'mt-2 ' : ''}block text-xs font-bold ${dark ? 'text-amber-100' : 'text-amber-950'}`}>Customer consent note
            <textarea value={consentNote} onChange={event => setConsentNote(event.target.value)} rows={2} placeholder="Record the customer's explicit request to keep this amount as shop credit." className={`mt-1 w-full rounded-xl border px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-amber-600 ${dark ? 'border-amber-800 bg-[#161b27] text-white placeholder:text-amber-200/40' : 'border-amber-300 bg-white'}`} />
          </label>
          <button type="button" disabled={!consentNote.trim() || consentMutation.isPending} onClick={() => consentMutation.mutate()} className={`mt-2 min-h-[44px] rounded-xl border px-3 text-xs font-extrabold disabled:opacity-50 ${dark ? 'border-amber-600 text-amber-100' : 'border-amber-800 text-amber-950'}`}>
            {consentMutation.isPending ? 'Recording…' : 'Keep as customer credit'}
          </button>
        </div>
      )}
    </section>
  )
}

export default function SettlementResolutionPanel({
  access,
  summary,
  allocations,
  audience,
  tone = 'light',
  onUpdated,
}: {
  access: SettlementAccess
  summary: InvoiceSettlementSummary
  allocations: PaymentAllocation[]
  audience: 'customer' | 'guest' | 'staff'
  tone?: 'dark' | 'light'
  onUpdated: (next: InvoiceSettlementSummary) => void
}) {
  const resolutions = allocations.filter(item => item.overpayment_id && isPositiveMoney(item.unapplied_amount))
  if (resolutions.length === 0) return null
  return (
    <div className="space-y-3">
      {resolutions.map(resolution => (
        <SettlementResolutionItem
          key={resolution.id}
          access={access}
          summary={summary}
          resolution={resolution}
          audience={audience}
          tone={tone}
          onUpdated={onUpdated}
        />
      ))}
    </div>
  )
}

export { SettlementResolutionPanel }
