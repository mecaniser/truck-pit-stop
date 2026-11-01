import { importedBillingSeverity, importedMoney, type ImportedBilling } from './importedBilling'

const explanations: Record<string, string> = {
  shared_job_identity_conflict: 'Related operations have different customer or vehicle identities. Shared billing needs review.',
  invoice_customer_identity_mismatch: 'The invoice customer does not match this repair order.',
  shared_job_source_conflict: 'Related operations have conflicting source records.',
  missing_or_ambiguous_invoice: 'A single ETS invoice could not be verified.',
  stale_source_observation: 'ETS payment evidence is out of date.',
  source_observation_expired: 'ETS payment evidence is out of date.',
  source_payment_coverage_unconfirmed: 'Current ETS payment evidence is unavailable.',
  imported_financial_rows_differ: 'ETS source amounts differ from the imported financial records.',
  payment_identity_mismatch: 'A payment is linked to a different invoice or shop.',
  mixed_payment_source: 'The invoice includes payment records from another source.',
  deleted_payment_evidence: 'The payment evidence includes a deleted payment.',
  noncompleted_payment_evidence: 'The payment evidence includes a payment that is not completed.',
  refund_evidence: 'The payment evidence includes a refund that needs review.',
  invalid_payment_amount: 'A recorded payment amount is invalid.',
  nonpositive_invoice_total: 'The invoice total is zero or negative.',
  overpayment_evidence: 'Recorded payments exceed the invoice total.',
  invoice_payment_status_mismatch: 'The invoice payment status does not match its recorded payments.',
  invalid_source_evidence: 'The ETS source evidence could not be validated.',
  source_identity_unavailable: 'The ETS customer or vehicle identity is unavailable.',
  shared_job_capacity_exceeded: 'There are too many related operations to verify shared billing safely.',
  source_identity_mismatch: 'The ETS source identity does not match the imported record.',
  source_order_mismatch: 'The ETS evidence belongs to a different repair order.',
  source_invoice_manifest_unverified: 'The complete set of ETS invoices could not be verified.',
  source_evidence_unavailable: 'ETS source evidence is unavailable.',
  observation_time_unavailable: 'The time of the ETS source observation is unavailable.',
  invoice_total_unavailable: 'The ETS invoice total is unavailable.',
  unsupported_invoice_status: 'The ETS invoice status is not supported for payment verification.',
  allocation_evidence_incomplete: 'ETS payment allocation evidence is incomplete.',
  allocation_balance_mismatch: 'ETS payment allocations do not match the remaining balance.',
  payment_overallocated: 'An ETS payment is allocated for more than its total amount.',
  duplicate_payment_identity: 'The ETS evidence contains a duplicate payment.',
  unsupported_payment_state: 'An ETS payment has a status that cannot be verified.',
}

/** Explain the existing severity decision; never calculate or change billing state. */
export function importedBillingWarnings(billing?: ImportedBilling | null, failed = false): string[] {
  const severity = importedBillingSeverity(billing, failed)
  if (failed) return ['Billing details could not be loaded. Reopen this order to retry.']
  if (severity.tone !== 'warning') return []
  const reasons = [...new Set(billing?.review_reasons ?? [])].map(reason => explanations[reason]
    ?? `ETS reported a billing review reason: ${reason.replace(/_/g, ' ')}.`)
  if (billing?.review_required && reasons.length === 0) reasons.push('ETS flagged this invoice for review without providing a reason.')
  if (!billing || billing.payment_status === 'unverified') reasons.push('The payment status could not be verified from ETS records.')
  if (severity.remaining === 'Unavailable') reasons.push('The remaining balance is unavailable.')
  else if (/[1-9]/.test(billing?.recorded_remaining_amount ?? '')) reasons.push(`This invoice has an unpaid balance of ${severity.remaining}.`)
  if (importedMoney(billing?.total_amount) === 'Unavailable') reasons.push('The invoice total is unavailable.')
  if (billing?.payment_status !== 'unverified' && importedMoney(billing?.recorded_completed_amount) === 'Unavailable') reasons.push('The recorded payment amount is unavailable.')
  if (reasons.length === 0) reasons.push('The payment status and recorded balance require review.')
  return reasons
}
