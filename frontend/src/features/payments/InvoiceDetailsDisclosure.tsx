import { useId, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { formatMoney, isPositiveMoney } from './money'
import type { InvoiceSettlementSummary } from './types'

export default function InvoiceDetailsDisclosure({ summary }: { summary: InvoiceSettlementSummary }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const breakdown = summary.breakdown
  const hasSnapshot = breakdown?.labor_total != null && breakdown?.parts_total != null
  const rows = [
    ...(hasSnapshot ? [
      ['Labor · before labor discounts', breakdown.labor_total!],
      ['Parts', breakdown.parts_total!],
    ] : []),
    ...(breakdown ? [
      ...(isPositiveMoney(breakdown.discount_amount) ? [['Discounts', `-${breakdown.discount_amount}`]] : []),
    ] : []),
  ]
  return <div className="border-t border-slate-200">
    <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}
      className="flex w-full items-center justify-between gap-3 rounded-2xl px-4 py-3 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-500">
      {open ? 'Hide details' : 'View details'}
      <ChevronDown aria-hidden="true" className={`h-4 w-4 shrink-0 ${open ? 'rotate-180' : ''}`} />
    </button>
    {open && <div id={id} className="border-t border-slate-200 p-4">
      {!hasSnapshot && <p className="text-xs text-slate-500">Labor/parts breakdown wasn’t saved.</p>}
      <dl className="space-y-2 text-sm">
        {rows.map(([label, value]) => <div key={label} className="flex justify-between gap-4">
          <dt className="text-slate-500">{label}</dt><dd className="shrink-0 font-semibold tabular-nums">{formatMoney(value)}</dd>
        </div>)}
      </dl>
      {hasSnapshot && <p className="mt-3 text-xs leading-relaxed text-slate-500">Shop supplies apply to labor after labor discounts, not parts. Original rate unavailable.</p>}
    </div>}
  </div>
}
