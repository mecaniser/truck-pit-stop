import type { InvoicePaymentPresentation } from '@/types'

import { invoicePaymentLabels } from '@/lib/invoicePaymentLabels'

const money = (value: string) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))

export default function InvoicePaymentSummary({ summary, dark = false }: { summary?: InvoicePaymentPresentation | null; dark?: boolean }) {
  if (!summary) return null
  return <section aria-label="Invoice payment summary" className={`my-4 rounded-xl border p-4 text-sm ${dark ? 'border-[#30394b] bg-[#161a26] text-[#eceef4]' : 'border-gray-200 bg-gray-50 text-gray-900'}`}>
    <h2 className="mb-3 font-bold">{invoicePaymentLabels[summary.state]}</h2>
    <dl className="space-y-2">
      {summary.applied_amount !== null && <div className="flex justify-between gap-4"><dt>{summary.basis === 'cash_receipt' ? 'Cash received' : 'Payments / credits applied'}</dt><dd className="shrink-0 font-semibold">{money(summary.applied_amount)}</dd></div>}
      {summary.pending_amount !== null && Number(summary.pending_amount) > 0 && <div className="flex justify-between gap-4"><dt>Awaiting confirmation</dt><dd className="shrink-0">{money(summary.pending_amount)}</dd></div>}
      {summary.state !== 'cancelled' && <div className="flex justify-between gap-4 border-t border-current/15 pt-2 font-bold"><dt>Balance due</dt><dd className="shrink-0">{summary.balance_due === null ? 'Unavailable' : money(summary.balance_due)}</dd></div>}
    </dl>
    {summary.note && <p className={`mt-3 text-xs ${dark ? 'text-[#aab1c1]' : 'text-gray-600'}`}>{summary.note}</p>}
  </section>
}
