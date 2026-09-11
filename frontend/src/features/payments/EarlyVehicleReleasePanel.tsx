import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown } from 'lucide-react'
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
  const [expanded, setExpanded] = useState(false)
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
      toast.success('Vehicle released. Payment is still due.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to record vehicle release.').message),
  })

  if (summary.allowed_actions?.authorize_early_release !== true) return null

  return (
    <div>
      <button id={`early-release-${invoiceId}`} type="button" aria-expanded={expanded} aria-controls={`early-release-form-${invoiceId}`} onClick={() => setExpanded(!expanded)}
        className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl px-3 text-left text-sm font-semibold text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700">
        Release vehicle before payment<ChevronDown className={`h-4 w-4 shrink-0 ${expanded ? 'rotate-180' : ''}`} />
      </button>
      {expanded && <div id={`early-release-form-${invoiceId}`}>
    <section className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-950" aria-labelledby={`early-release-${invoiceId}`}>
      <div className="flex items-center gap-2 text-sm">
        <AlertTriangle aria-hidden="true" className="h-4 w-4 shrink-0" />
        <p><span className="font-semibold">{formatMoney(summary.outstanding_balance)}</span> remains due.</p>
      </div>
      <label className="mt-3 block text-xs font-bold">Release reason
        <textarea
          value={reason}
          onChange={event => setReason(event.target.value)}
          rows={2}
          maxLength={1000}
          placeholder="Reason for early release"
          className="mt-1 w-full rounded-xl border border-amber-300 bg-white px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-amber-600"
        />
      </label>
      <button
        type="button"
        disabled={!reason.trim() || release.isPending}
        onClick={() => release.mutate()}
        className="mt-2 min-h-[44px] rounded-xl border border-amber-800 px-3 text-xs font-extrabold text-amber-950 disabled:opacity-50"
      >
        {release.isPending ? 'Releasing…' : 'Release vehicle'}
      </button>
    </section>
      </div>}
    </div>
  )
}

export { EarlyVehicleReleasePanel }
