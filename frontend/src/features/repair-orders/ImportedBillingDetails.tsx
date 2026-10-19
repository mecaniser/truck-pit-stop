import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { Info } from 'lucide-react'
import { importedMoney, type ImportedBilling } from './importedBilling'

export function ImportedBillingDetails({ billing, failed = false }: { billing?: ImportedBilling | null; failed?: boolean }) {
  const verifiedStatus = !failed && billing ? billing.payment_status : 'unverified'
  const observedAt = billing?.observed_at && !Number.isNaN(Date.parse(billing.observed_at)) ? billing.observed_at : null
  const label = { paid: 'Paid in ETS', partially_paid: 'Partially paid in ETS', unpaid: 'Unpaid in ETS', unverified: 'Payment unverified' }[verifiedStatus]
  return <div className="mt-1 text-xs text-slate-600" aria-label="Imported ETS billing">
    <Popover className="flex items-center justify-end gap-1">
      <span className="font-semibold text-slate-900">{label}</span>
      <PopoverButton aria-label="ETS billing details" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600">
        <Info className="h-4 w-4" aria-hidden="true" />
      </PopoverButton>
      <PopoverPanel anchor="top end" focus aria-label="ETS billing details" className="z-[100] w-72 max-w-[calc(100vw-2rem)] rounded-xl bg-white p-4 text-left text-xs text-slate-600 shadow-lg ring-1 ring-slate-200 [--anchor-gap:8px] [--anchor-padding:16px]">
        <p className="font-semibold text-slate-900">{billing?.invoice_id && !failed ? 'ETS invoice on file' : 'ETS invoice unavailable'} · no new invoice</p>
        <dl className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          <div><dt className="inline">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Source paid ' : 'Imported payments '}</dt><dd className="inline font-semibold">{importedMoney(failed ? null : billing?.recorded_completed_amount)}</dd></div>
          <div><dt className="inline">Remaining </dt><dd className="inline font-semibold">{importedMoney(failed ? null : billing?.recorded_remaining_amount)}</dd></div>
        </dl>
        <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'ETS source snapshot' : 'Imported ETS records'} · QuickBooks not checked</p>
        {observedAt && !failed && <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Observed ' : 'Record updated '}<time dateTime={observedAt}>{new Date(observedAt).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</time></p>}
        {billing?.review_required && !failed && <p className="mt-1 font-medium">Review needed</p>}
      </PopoverPanel>
    </Popover>
    {failed && <p role="alert">Billing unavailable. Reopen this order to retry.</p>}
  </div>
}
