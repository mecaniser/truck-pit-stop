import type { InvoicePaymentPresentation } from '@/types'

export const invoicePaymentLabels: Record<InvoicePaymentPresentation['state'], string> = {
  paid: 'Paid', unpaid: 'Unpaid', partially_paid: 'Partially paid',
  payment_pending: 'Payment awaiting confirmation', partially_paid_pending: 'Partially paid · Payment awaiting confirmation',
  overdue: 'Overdue', cancelled: 'Cancelled', unknown: 'Payment status unavailable',
}
