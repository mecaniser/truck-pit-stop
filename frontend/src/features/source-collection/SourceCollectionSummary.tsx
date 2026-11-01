import type { SourceCollectionSummary as Summary } from './types'

const money = (value: string) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))

export default function SourceCollectionSummary({ summary, dark = false }: { summary: Summary; dark?: boolean }) {
  const held = summary.state === 'source_conflict' || summary.source_sync_state === 'source_conflict'
    || summary.source_sync_state === 'source_unavailable' || summary.collection_enabled === false
  return <section aria-label="Original invoice and collection balance" className={`mt-4 rounded-xl border p-4 text-sm ${dark ? 'border-[#232939] bg-[#161a26] text-[#c9cdd8]' : 'border-slate-200 bg-slate-50 text-slate-700'}`}>
    <h2 className="font-semibold">Collection copy of ETS invoice {summary.source_invoice_number}</h2>
    <dl className="mt-3 space-y-1">
      {([
        ['Original invoice', summary.original_issued_total],
        ['Paid before transfer', summary.source_prior_allocated],
        ['Balance transferred to DBN', summary.opening_principal],
      ] as const).map(([label, amount]) => <div className="flex justify-between gap-4" key={label}><dt>{label}</dt><dd className="shrink-0 tabular-nums">{money(amount)}</dd></div>)}
    </dl>
    {held && <p role="status" className="mt-3 font-semibold">Payments are on hold while the shop reconciles this invoice.</p>}
    {summary.source_sync_state === 'ets_update_pending' && <p role="status" className="mt-3">Payment recorded in DBN · ETS update pending. Your DBN balance already includes the confirmed payment.</p>}
    {summary.source_sync_state === 'current' && !held && !summary.is_source_history && summary.state === 'active' && Number(summary.balance_due) > 0 && <p className="mt-3">Pay the remaining balance through DBN. This copy tracks the same original invoice.</p>}
  </section>
}
