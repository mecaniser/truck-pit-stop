import type { Invoice } from '@/types'
import { moneyToCents } from '@/features/payments/money'

export function portalInvoiceBalance(invoice: Invoice): bigint | null {
  if (!invoice.payment_summary || invoice.payment_summary.state === 'unknown') return null
  const amount = moneyToCents(invoice.payment_summary.balance_due)
  return amount !== null && amount >= 0n ? amount : null
}
export function canPayPortalInvoice(invoice: Invoice): boolean {
  const balance = portalInvoiceBalance(invoice)
  const pending = moneyToCents(invoice.payment_summary?.pending_amount ?? '0.00')
  return balance !== null && balance > 0n && pending !== null && pending >= 0n && pending < balance &&
    (invoice.source !== 'ets_collection_handoff' || (invoice.source_collection?.collection_enabled !== false && invoice.source_collection?.state === 'active'))
}
export function currentPortalInvoices(invoices: Invoice[]) {
  return invoices.filter(invoice => invoice.source !== 'easy_truck_shop_import' && invoice.status !== 'cancelled' && invoice.payment_summary?.state !== 'cancelled')
}
