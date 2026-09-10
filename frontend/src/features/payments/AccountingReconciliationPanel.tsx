import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Clock3, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'

import {
  createIdempotencyKey,
  fetchAccountingReconciliation,
  paymentApiError,
  retryAccountingOperation,
} from './api'

export default function AccountingReconciliationPanel({
  invoiceId,
  canRetry,
}: {
  invoiceId: string
  canRetry: boolean
}) {
  const queryClient = useQueryClient()
  const reconciliation = useQuery({
    queryKey: ['invoice-accounting-reconciliation', invoiceId],
    queryFn: () => fetchAccountingReconciliation(invoiceId),
    retry: false,
  })
  const retryMutation = useMutation({
    mutationFn: (operationId: string) => retryAccountingOperation(operationId, createIdempotencyKey()),
    onSuccess: () => {
      toast.success('QuickBooks reconciliation retry queued.')
      queryClient.invalidateQueries({ queryKey: ['invoice-accounting-reconciliation', invoiceId] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement', 'authenticated', invoiceId] })
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to retry QuickBooks reconciliation.').message),
  })

  if (reconciliation.isLoading) return <p className="px-1 text-xs text-slate-500">Loading QuickBooks reconciliation…</p>
  if (reconciliation.error || !reconciliation.data) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
        {paymentApiError(reconciliation.error, 'QuickBooks reconciliation status is unavailable.').message}
      </div>
    )
  }
  const data = reconciliation.data
  if (data.state === 'not_required' && data.links.length === 0) return null
  const failed = data.links.filter(link => ['failed', 'dead'].includes(link.state))
  const Icon = data.state === 'synced' ? CheckCircle2 : data.state === 'failed' ? AlertTriangle : Clock3

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white" aria-labelledby={`accounting-reconciliation-${invoiceId}`}>
      <header className="flex items-start gap-3 px-3 py-3">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${data.state === 'synced' ? 'text-emerald-600' : data.state === 'failed' ? 'text-red-600' : 'text-amber-600'}`} />
        <div className="min-w-0 flex-1">
          <h3 id={`accounting-reconciliation-${invoiceId}`} className="text-sm font-extrabold text-slate-950">QuickBooks reconciliation</h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {data.state === 'synced'
              ? `${data.synced_operations} accounting operation${data.synced_operations === 1 ? '' : 's'} synced.`
              : data.state === 'failed'
                ? `${data.failed_operations} operation${data.failed_operations === 1 ? '' : 's'} needs attention. The DieselBridge payment remains recorded.`
                : `${data.pending_operations} accounting operation${data.pending_operations === 1 ? '' : 's'} queued. Do not record the payment again.`}
          </p>
        </div>
      </header>
      {failed.length > 0 && (
        <ol className="divide-y divide-slate-200 border-t border-slate-200">
          {failed.map(link => (
            <li key={link.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5">
              <div className="min-w-0">
                <p className="text-xs font-bold capitalize text-slate-800">{link.type.replace(/_/g, ' ')}</p>
                {link.error && <p className="mt-0.5 truncate text-xs text-red-700">{link.error}</p>}
              </div>
              {canRetry && (
                <button
                  type="button"
                  disabled={retryMutation.isPending}
                  onClick={() => retryMutation.mutate(link.id)}
                  className="inline-flex min-h-[44px] items-center gap-1.5 rounded-xl border border-slate-300 px-3 text-xs font-extrabold text-slate-800 hover:bg-slate-50 disabled:opacity-50"
                >
                  <RefreshCw className="h-3.5 w-3.5" />Retry sync
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export { AccountingReconciliationPanel }
