import { importedMoney, type ImportedBilling } from './importedBilling'

export function ImportedBillingDetails({ billing, failed = false }: { billing?: ImportedBilling | null; failed?: boolean }) {
  const verifiedStatus = !failed && billing ? billing.payment_status : 'unverified'
  const observedAt = billing?.observed_at && !Number.isNaN(Date.parse(billing.observed_at)) ? billing.observed_at : null
  const label = { paid: 'Paid in ETS', partially_paid: 'Partially paid in ETS', unpaid: 'Unpaid in ETS', unverified: 'Payment unverified' }[verifiedStatus]
  return <div className="mt-1 text-xs text-slate-600" aria-label="Imported ETS billing">
    <p className="font-semibold text-slate-900">{label}</p>
    <dl className="mt-1 flex flex-wrap justify-end gap-x-3 gap-y-1">
      <div><dt className="inline">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Source paid ' : 'Imported payments '}</dt><dd className="inline font-semibold">{importedMoney(failed ? null : billing?.recorded_completed_amount)}</dd></div>
      <div><dt className="inline">Remaining </dt><dd className="inline font-semibold">{importedMoney(failed ? null : billing?.recorded_remaining_amount)}</dd></div>
    </dl>
    <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'ETS source snapshot' : 'Imported ETS records'} · QuickBooks not checked</p>
    {observedAt && !failed && <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Observed ' : 'Record updated '}<time dateTime={observedAt}>{new Date(observedAt).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</time></p>}
    {billing?.review_required && !failed && <p className="mt-1 font-medium">Review needed</p>}
    {failed && <p role="alert">Billing unavailable. Reopen this order to retry.</p>}
  </div>
}
