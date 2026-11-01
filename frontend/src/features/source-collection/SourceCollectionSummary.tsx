import type { SourceCollectionSummary as Summary } from './types'

const money = (value: string) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))

export default function SourceCollectionSummary({ summary, dark = false, originalInvoiceHref, showCurrentBalance = false }: { summary: Summary; dark?: boolean; originalInvoiceHref?: string; showCurrentBalance?: boolean }) {
  if (summary.restricted_history) return <section aria-label="Original invoice history" className={`mt-4 rounded-xl border p-4 text-sm ${dark ? 'border-[#232939] bg-[#161a26] text-[#c9cdd8]' : 'border-slate-200 bg-slate-50 text-slate-700'}`}>
    <h2 className="font-semibold">ETS invoice {summary.source_invoice_number} · historical record</h2>
    <p className="mt-2">Collection of this invoice has been transferred. This historical copy is not a separate payment request. Contact the shop for current payment details.</p>
  </section>
  const held = summary.state === 'source_conflict' || summary.source_sync_state === 'source_conflict'
    || summary.source_sync_state === 'source_unavailable' || summary.collection_enabled === false
  return <section aria-label="Original invoice and collection balance" className={`mt-4 rounded-xl border p-4 text-sm ${dark ? 'border-[#232939] bg-[#161a26] text-[#c9cdd8]' : 'border-slate-200 bg-slate-50 text-slate-700'}`}>
    <h2 className="font-semibold">{summary.is_source_history ? 'DBN collection for ETS invoice ' : 'Collection copy of ETS invoice '}{summary.source_invoice_number}</h2>
    {summary.original_invoice_date && Number.isFinite(Date.parse(summary.original_invoice_date)) && <p className="mt-1 text-xs">Original invoice date: <time dateTime={summary.original_invoice_date}>{new Date(summary.original_invoice_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })}</time></p>}
    <dl className="mt-3 space-y-1">
      {([
        ['Original invoice', summary.original_issued_total],
        ['Paid before transfer', summary.source_prior_allocated],
        ['Balance transferred to DBN', summary.opening_principal],
      ] as const).map(([label, amount]) => <div className="flex justify-between gap-4" key={label}><dt>{label}</dt><dd className="shrink-0 tabular-nums">{money(amount)}</dd></div>)}
    </dl>
    {(summary.is_source_history || showCurrentBalance) && <div className="mt-3 flex justify-between gap-4 border-t border-slate-400/20 pt-3 font-semibold"><span>Current DBN balance</span><span className="shrink-0 tabular-nums">{summary.balance_due == null ? 'Unavailable' : money(summary.balance_due)}</span></div>}
    <p className="mt-3 text-xs">The transferred balance includes the original charges and tax.</p>
    {!summary.is_source_history && originalInvoiceHref && <a href={originalInvoiceHref} className={`mt-2 inline-flex min-h-11 items-center font-semibold ${dark ? 'text-[#c4b1ff]' : 'text-indigo-700'}`}>View original ETS invoice</a>}
    {held && <p role="status" className="mt-3 font-semibold">Payments are on hold while the shop reconciles this invoice.</p>}
    {summary.source_sync_state === 'ets_update_pending' && <p role="status" className="mt-3">Payment recorded in DBN · ETS update pending. Your DBN balance already includes the confirmed payment.</p>}
    {summary.source_sync_state === 'current' && !held && !summary.is_source_history && summary.state === 'active' && Number(summary.balance_due) > 0 && <p className="mt-3">Pay the remaining balance through DBN. This copy tracks the same original invoice.</p>}
  </section>
}
