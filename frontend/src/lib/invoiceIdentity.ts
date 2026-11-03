import type { SourceCollectionSummary } from '@/features/source-collection/types'

type InvoiceIdentity = { invoice_number: string; source?: string | null; source_collection?: SourceCollectionSummary | null }

export function customerInvoiceNumber(invoice: InvoiceIdentity): string {
  if (invoice.source === 'ets_collection_handoff' || invoice.source_collection != null || invoice.invoice_number?.startsWith('DBN-COL-')) {
    return invoice.source_collection?.display_invoice_number || ''
  }
  return invoice.invoice_number
}

export function customerInvoiceLabel(invoice: InvoiceIdentity): string {
  const number = customerInvoiceNumber(invoice)
  return number ? `Invoice ${number}` : 'Invoice'
}

export function customerInvoiceMemo(invoice: InvoiceIdentity, ordinaryMemo: string): string {
  const number = customerInvoiceNumber(invoice)
  return number === invoice.invoice_number ? ordinaryMemo : number || 'Invoice'
}
