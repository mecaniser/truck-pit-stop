import { ImportedBillingSourceLink } from './ImportedBillingSourceLink'
import { importedBillingWarnings } from './importedBillingWarnings'
import { ImportedBillingTooltip } from './ImportedBillingTooltip'
import { CircleCheck, TriangleAlert } from 'lucide-react'
import './importedBilling.css'
import { importedMoney, importedPaymentLabel, importedBillingSeverity, type ImportedBilling } from './importedBilling'

export function ImportedBillingDetails({ billing, failed = false }: { billing?: ImportedBilling | null; failed?: boolean }) {
  const verifiedStatus = !failed && billing ? billing.payment_status : 'unverified'
  const observedAt = billing?.observed_at && !Number.isNaN(Date.parse(billing.observed_at)) ? billing.observed_at : null
  const label = importedPaymentLabel(verifiedStatus)
  const severity = importedBillingSeverity(billing, failed)
  const { remaining } = severity
  const statusLabel = { paid: 'Paid in full', partially_paid: 'Partially paid', unpaid: 'Unpaid', unverified: label }[verifiedStatus]
  const hasBalanceDue = remaining !== 'Unavailable' && /[1-9]/.test(billing?.recorded_remaining_amount ?? '')
  const StatusIcon = severity.tone === 'warning' ? TriangleAlert : CircleCheck
  const warnings = importedBillingWarnings(billing, failed)
  return <div className="mt-1 text-xs text-slate-600" aria-label="Imported ETS billing">
    <div className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1">
      {verifiedStatus !== 'unverified' && <span className="font-semibold text-slate-900">{statusLabel}</span>}
      {hasBalanceDue && <span>Balance due <strong className="font-semibold">{remaining}</strong></span>}
      <ImportedBillingTooltip description={severity.description} tone={severity.tone} icon={<StatusIcon className="h-4 w-4" aria-hidden="true" />}>
        <p className="db-imported-billing-severity flex items-center gap-2 font-semibold" data-severity={severity.tone}><StatusIcon className="h-4 w-4 shrink-0" aria-hidden="true" />{severity.heading}</p>
        {verifiedStatus === 'unverified' && severity.heading !== label && <p className="mt-1">{label}</p>}
        {warnings.length > 0 && <ul className="mt-1 list-disc space-y-1 pl-4">{warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>}
        <p className="mt-2 font-semibold text-slate-900">{billing?.invoice_id && !failed ? 'ETS invoice on file' : 'ETS invoice unavailable'} · no new invoice</p>
        <p className="mt-2">Payment status from Easy Truck Shop (ETS), separate from this operation’s work status.</p>
        <dl className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          <div><dt className="inline">Invoice total </dt><dd className="inline font-semibold">{importedMoney(failed ? null : billing?.total_amount)}</dd></div>
          <div><dt className="inline">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Source paid ' : 'Imported payments '}</dt><dd className="inline font-semibold">{importedMoney(failed || verifiedStatus === 'unverified' ? null : billing?.recorded_completed_amount)}</dd></div>
          <div><dt className="inline">Remaining </dt><dd className="inline font-semibold">{importedMoney(failed || verifiedStatus === 'unverified' ? null : billing?.recorded_remaining_amount)}</dd></div>
        </dl>
        {billing?.shared_invoice && !failed && <p className="mt-1">Shared invoice for the whole job, including related operations. {billing.invoice_repair_order_number ? `Invoice belongs to ${billing.invoice_repair_order_number}; amounts are counted once.` : 'Amounts are counted once.'}</p>}
        <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'ETS source snapshot' : 'Imported ETS records'} · QuickBooks not checked</p>
        {observedAt && !failed && <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Observed ' : 'Record updated '}<time dateTime={observedAt}>{new Date(observedAt).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</time></p>}
      </ImportedBillingTooltip>
      {severity.tone === 'warning' && !failed && <ImportedBillingSourceLink url={billing?.source_invoice_url} />}
    </div>
    {failed && <p role="alert">Billing unavailable. Reopen this order to retry.</p>}
  </div>
}
