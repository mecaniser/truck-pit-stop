import { useMutation } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { useState } from 'react'
import toast from 'react-hot-toast'

import {
  authorizeEarlyVehicleRelease,
  createIdempotencyKey,
  paymentApiError,
} from './api'
import { formatMoney } from './money'
import type { InvoiceSettlementSummary } from './types'

export default function EarlyVehicleReleasePanel({
  invoiceId,
  summary,
  onUpdated,
}: {
  invoiceId: string
  summary: InvoiceSettlementSummary
  onUpdated: (next: InvoiceSettlementSummary) => void
}) {
  const [reason, setReason] = useState('')
  const release = useMutation({
    mutationFn: () => authorizeEarlyVehicleRelease(
      invoiceId,
      summary.version,
      reason.trim(),
      createIdempotencyKey(),
    ),
    onSuccess: next => {
      onUpdated(next)
      setReason('')
      toast.success('Vehicle release recorded with the outstanding balance preserved.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to record vehicle release.').message),
  })

  if (summary.allowed_actions?.authorize_early_release !== true) return null

  return (
    <section className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-950" aria-labelledby={`early-release-${invoiceId}`}>
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <h3 id={`early-release-${invoiceId}`} className="text-sm font-extrabold">Release vehicle before payment is complete</h3>
          <p className="mt-0.5 text-xs text-amber-800">
            {formatMoney(summary.outstanding_balance)} remains due. This records an owner/admin exception; it does not close the invoice or reduce QuickBooks A/R.
          </p>
        </div>
      </div>
      <label className="mt-3 block text-xs font-bold">Release reason
        <textarea
          value={reason}
          onChange={event => setReason(event.target.value)}
          rows={2}
          maxLength={1000}
          placeholder="Explain why the vehicle may leave before the invoice is paid in full."
          className="mt-1 w-full rounded-xl border border-amber-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-amber-600"
        />
      </label>
      <button
        type="button"
        disabled={!reason.trim() || release.isPending}
        onClick={() => release.mutate()}
        className="mt-2 min-h-[44px] rounded-xl border border-amber-800 px-3 text-xs font-extrabold text-amber-950 disabled:opacity-50"
      >
        {release.isPending ? 'Recording release…' : 'Authorize vehicle release'}
      </button>
    </section>
  )
}

export { EarlyVehicleReleasePanel }
