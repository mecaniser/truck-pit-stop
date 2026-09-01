import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { WalletCards } from 'lucide-react'
import toast from 'react-hot-toast'

import {
  applyEligibleCustomerCredit,
  createIdempotencyKey,
  fetchEligibleCustomerCredits,
  paymentApiError,
} from './api'
import { centsToMoney, formatMoney, moneyToCents } from './money'
import type { InvoiceSettlementSummary, SettlementAccess } from './types'

type AuthenticatedSettlementAccess = Extract<SettlementAccess, { kind: 'authenticated' }>

const payableFromCredit = (remaining: string, allocatable: string): string => {
  const credit = moneyToCents(remaining) ?? 0n
  const available = moneyToCents(allocatable) ?? 0n
  return centsToMoney(credit < available ? credit : available)
}

export default function SettlementCreditPanel({
  access,
  summary,
  tone = 'light',
  onUpdated,
}: {
  access: AuthenticatedSettlementAccess
  summary: InvoiceSettlementSummary
  tone?: 'dark' | 'light'
  onUpdated: (next: InvoiceSettlementSummary) => void
}) {
  const queryClient = useQueryClient()
  const canApply = summary.allowed_actions?.apply_customer_credit === true
  const credits = useQuery({
    queryKey: ['invoice-eligible-customer-credits', access.kind, access.invoiceId],
    queryFn: () => fetchEligibleCustomerCredits(access),
    enabled: canApply && (moneyToCents(summary.allocatable_balance) ?? 0n) > 0n,
    retry: false,
  })
  const applyMutation = useMutation({
    mutationFn: ({ creditId, amount }: { creditId: string; amount: string }) => applyEligibleCustomerCredit(
      access,
      creditId,
      amount,
      summary.version,
      createIdempotencyKey(),
    ),
    onSuccess: result => {
      onUpdated(result.settlement)
      queryClient.invalidateQueries({ queryKey: ['invoice-eligible-customer-credits'] })
      queryClient.invalidateQueries({ queryKey: ['invoice-settlement-allocations'] })
      toast.success('Customer credit applied to this invoice.')
    },
    onError: error => toast.error(paymentApiError(error, 'Unable to apply customer credit.').message),
  })

  if (!canApply) return null
  const dark = tone === 'dark'
  const panel = dark ? 'border-emerald-700/40 bg-emerald-950/20' : 'border-emerald-200 bg-emerald-50'
  const primary = dark ? 'text-emerald-100' : 'text-emerald-950'
  const secondary = dark ? 'text-emerald-300' : 'text-emerald-800'
  const divider = dark ? 'divide-emerald-800/60 border-emerald-800/60' : 'divide-emerald-200 border-emerald-200'

  if (credits.isError) {
    return (
      <section role="alert" className={`rounded-xl border p-3 text-sm ${dark ? 'border-red-800/60 bg-red-950/30 text-red-200' : 'border-red-200 bg-red-50 text-red-800'}`}>
        <p className="font-extrabold">Customer credit could not be verified.</p>
        <p className="mt-1 text-xs">No credit was applied. Refresh before accepting another payment.</p>
      </section>
    )
  }

  if (credits.isLoading) {
    return <p className={`px-1 text-xs ${secondary}`}>Checking eligible customer credit…</p>
  }

  if (!credits.data?.length) return null

  return (
    <section className={`overflow-hidden rounded-xl border ${panel}`} aria-labelledby={`eligible-credit-${summary.invoice_id}`}>
      <header className={`flex items-start gap-2 px-3 py-3 ${primary}`}>
        <WalletCards className="mt-0.5 h-4 w-4 shrink-0" />
        <div>
          <h3 id={`eligible-credit-${summary.invoice_id}`} className="text-sm font-extrabold">Available customer credit</h3>
          <p className={`mt-0.5 text-xs ${secondary}`}>Credit is applied explicitly and only within this customer and shop.</p>
        </div>
      </header>
      <ol className={`divide-y border-t ${divider}`}>
        {credits.data.map(credit => {
          const amount = payableFromCredit(credit.remaining_amount, summary.allocatable_balance)
          return (
            <li key={credit.credit_id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5">
              <div>
                <p className={`text-sm font-bold ${primary}`}>{formatMoney(credit.remaining_amount)} available</p>
                <p className={`text-xs ${secondary}`}>Consent recorded {new Date(credit.issued_at).toLocaleDateString()}</p>
              </div>
              <button
                type="button"
                disabled={applyMutation.isPending || (moneyToCents(amount) ?? 0n) === 0n}
                onClick={() => applyMutation.mutate({ creditId: credit.credit_id, amount })}
                className="min-h-[44px] rounded-xl bg-emerald-800 px-3 text-xs font-extrabold text-white hover:bg-emerald-900 disabled:opacity-50"
              >
                {applyMutation.isPending ? 'Applying…' : `Apply ${formatMoney(amount)}`}
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

export { SettlementCreditPanel }
