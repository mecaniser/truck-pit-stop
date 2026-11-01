import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { CircleCheck, TriangleAlert } from 'lucide-react'
import './importedBilling.css'
import { importedMoney, importedPaymentLabel, importedBillingSeverity, type ImportedBilling } from './importedBilling'

export function ImportedBillingDetails({ billing, failed = false }: { billing?: ImportedBilling | null; failed?: boolean }) {
  const verifiedStatus = !failed && billing ? billing.payment_status : 'unverified'
  const observedAt = billing?.observed_at && !Number.isNaN(Date.parse(billing.observed_at)) ? billing.observed_at : null
  const label = importedPaymentLabel(verifiedStatus)
  const severity = importedBillingSeverity(billing, failed)
  const { remaining } = severity
  const StatusIcon = severity.tone === 'warning' ? TriangleAlert : CircleCheck
  const reviewCopy: Record<string, string> = {
    shared_job_identity_conflict: 'Related operations have different customer or vehicle identities. Shared billing needs review.',
    invoice_customer_identity_mismatch: 'The invoice customer does not match this repair order.',
    shared_job_source_conflict: 'Related operations have conflicting source records.',
    missing_or_ambiguous_invoice: 'A single ETS invoice could not be verified.',
    stale_source_observation: 'ETS payment evidence is out of date.',
    source_payment_coverage_unconfirmed: 'Current ETS payment evidence is unavailable.',
    imported_financial_rows_differ: 'ETS source amounts differ from the imported financial records.',
  }
  const reviewExplanation = billing?.review_reasons.map(reason => reviewCopy[reason]).find(Boolean)
  return <div className="mt-1 text-xs text-slate-600" aria-label="Imported ETS billing">
    <Popover className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1">
      {verifiedStatus !== 'unverified' && <span className="font-semibold text-slate-900">{label}</span>}
      {remaining !== 'Unavailable' && <span>Remaining <strong className="font-semibold">{remaining}</strong></span>}
      <PopoverButton aria-label="ETS billing details" aria-description={severity.description} title={severity.description} data-severity={severity.tone} className="db-imported-billing-indicator inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-orange-600">
        <StatusIcon className="h-4 w-4" aria-hidden="true" />
      </PopoverButton>
      <PopoverPanel anchor="top end" focus aria-label="ETS billing details" className="z-[100] w-72 max-w-[calc(100vw-2rem)] rounded-xl bg-white p-4 text-left text-xs text-slate-600 shadow-lg ring-1 ring-slate-200 [--anchor-gap:8px] [--anchor-padding:16px]">
        <p className="db-imported-billing-severity flex items-center gap-2 font-semibold" data-severity={severity.tone}><StatusIcon className="h-4 w-4 shrink-0" aria-hidden="true" />{severity.heading}</p>
        {verifiedStatus === 'unverified' && severity.heading !== label && <p className="mt-1">{label}</p>}
        {reviewExplanation && !failed && <p className="mt-1">{reviewExplanation}</p>}
        <p className="mt-2 font-semibold text-slate-900">{billing?.invoice_id && !failed ? 'ETS invoice on file' : 'ETS invoice unavailable'} · no new invoice</p>
        <dl className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          <div><dt className="inline">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Source paid ' : 'Imported payments '}</dt><dd className="inline font-semibold">{importedMoney(failed || verifiedStatus === 'unverified' ? null : billing?.recorded_completed_amount)}</dd></div>
          <div><dt className="inline">Remaining </dt><dd className="inline font-semibold">{importedMoney(failed || verifiedStatus === 'unverified' ? null : billing?.recorded_remaining_amount)}</dd></div>
        </dl>
        {billing?.shared_invoice && billing.invoice_repair_order_number && !failed && <p className="mt-1">Invoice belongs to {billing.invoice_repair_order_number}; shown across related operations, counted once.</p>}
        <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'ETS source snapshot' : 'Imported ETS records'} · QuickBooks not checked</p>
        {observedAt && !failed && <p className="mt-1">{billing?.evidence_basis === 'ets_source_snapshot' ? 'Observed ' : 'Record updated '}<time dateTime={observedAt}>{new Date(observedAt).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}</time></p>}
      </PopoverPanel>
    </Popover>
    {billing?.shared_invoice && !failed && <p className="text-right">Shared ETS invoice · whole-job balance</p>}
    {failed && <p role="alert">Billing unavailable. Reopen this order to retry.</p>}
  </div>
}
