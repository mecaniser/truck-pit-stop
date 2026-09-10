import { useMutation, useQuery } from '@tanstack/react-query'
import { Download, WalletCards } from 'lucide-react'
import toast from 'react-hot-toast'

import { Spinner } from '@/components/ui'

import {
  downloadCustomerCreditAging,
  fetchCustomerCreditAging,
  paymentApiError,
} from './api'
import { centsToMoney, formatMoney, moneyToCents } from './money'

export default function CustomerCreditAgingCard() {
  const credits = useQuery({
    queryKey: ['customer-credit-aging'],
    queryFn: fetchCustomerCreditAging,
    retry: false,
  })
  const exportMutation = useMutation({
    mutationFn: downloadCustomerCreditAging,
    onError: error => toast.error(paymentApiError(error, 'Unable to export customer credits.').message),
  })

  const parsedError = credits.error ? paymentApiError(credits.error) : null
  if (parsedError?.status === 404) return null

  if (credits.isLoading) {
    return <div className="flex min-h-24 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-950/40"><Spinner size="lg" /></div>
  }

  if (credits.error || !credits.data) {
    return (
      <section className="rounded-2xl border border-red-900/50 bg-red-950/20 p-4 text-sm text-red-200" role="alert">
        <p className="font-bold">Customer-credit aging is unavailable.</p>
        <p className="mt-1">{parsedError?.message || 'Refresh and try again. No credit balance was changed.'}</p>
      </section>
    )
  }

  const totalCents = credits.data.reduce((sum, item) => sum + (moneyToCents(item.remaining_amount) ?? 0n), 0n)
  const oldestAge = credits.data.reduce((oldest, item) => Math.max(oldest, item.age_days), 0)

  if (credits.data.length === 0) return (
    <section aria-label="Customer credits" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-800 p-4 text-sm">
      <h3 className="flex items-center gap-2 font-bold text-zinc-100"><WalletCards className="h-4 w-4" />Customer credits</h3>
      <p className="text-zinc-400"><span className="font-bold tabular-nums text-zinc-100">$0.00</span> · No open credits</p>
    </section>
  )

  return (
    <section className="overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950/40" aria-labelledby="customer-credit-aging-heading">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-800 p-4 sm:p-5">
        <div>
          <p className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-zinc-500">Unapplied customer money</p>
          <h3 id="customer-credit-aging-heading" className="mt-1 flex items-center gap-2 font-extrabold text-zinc-100"><WalletCards className="h-4 w-4" />Customer credits</h3>
          <p className="mt-1 max-w-2xl text-sm text-zinc-400">Only customer-consented credit remains here. It is not revenue and has no arbitrary expiration.</p>
        </div>
        <button
          type="button"
          disabled={exportMutation.isPending || credits.data.length === 0}
          onClick={() => exportMutation.mutate()}
          className="inline-flex min-h-[44px] items-center gap-2 rounded-xl border border-zinc-700 px-3 text-sm font-bold text-zinc-200 hover:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Download className="h-4 w-4" />
          {exportMutation.isPending ? 'Exporting…' : 'Export CSV'}
        </button>
      </header>

      <dl className="grid grid-cols-3 border-b border-zinc-800">
        <div className="border-r border-zinc-800 px-4 py-3"><dt className="text-xs text-zinc-500">Customers</dt><dd className="mt-1 font-extrabold tabular-nums text-zinc-100">{credits.data.length}</dd></div>
        <div className="border-r border-zinc-800 px-4 py-3"><dt className="text-xs text-zinc-500">Open credit</dt><dd className="mt-1 font-extrabold tabular-nums text-zinc-100">{formatMoney(centsToMoney(totalCents))}</dd></div>
        <div className="px-4 py-3"><dt className="text-xs text-zinc-500">Oldest</dt><dd className="mt-1 font-extrabold tabular-nums text-zinc-100">{credits.data.length ? `${oldestAge} days` : '—'}</dd></div>
      </dl>

      {credits.data.length === 0 ? (
        <p className="p-4 text-sm text-zinc-400">No retained customer credit requires aging or due-diligence review.</p>
      ) : (
        <ol className="divide-y divide-zinc-800">
          {credits.data.slice(0, 5).map(item => (
            <li key={item.credit_id} className="flex min-h-[56px] items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-bold text-zinc-100">{item.customer_name}</p>
                <p className="mt-0.5 text-xs text-zinc-500">{item.age_days} days old · consent recorded {new Date(item.issued_at).toLocaleDateString()}</p>
              </div>
              <span className="shrink-0 font-extrabold tabular-nums text-zinc-100">{formatMoney(item.remaining_amount)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export { CustomerCreditAgingCard }
