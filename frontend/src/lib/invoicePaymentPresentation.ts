import type { InvoicePaymentPresentation } from '@/types'
import type { InvoiceSettlementSummary } from '@/features/payments/types'

export function currentInvoicePaymentSummary(saved: InvoicePaymentPresentation | null | undefined, settlement: InvoiceSettlementSummary | null | undefined): InvoicePaymentPresentation | null | undefined {
  if (!settlement || settlement.feature_enabled === false || saved?.state === 'cancelled' || saved?.state === 'unknown' || saved?.basis === 'cash_receipt') return saved
  const pending = Number(settlement.active_pending_principal) > 0
  const balance = Number(settlement.outstanding_balance)
  if (!Number.isFinite(balance)) return saved
  const applied = Number(settlement.confirmed_principal)
  const state = balance === 0 ? 'paid' : applied > 0 ? pending ? 'partially_paid_pending' : 'partially_paid' : pending ? 'payment_pending' : saved?.state === 'overdue' ? 'overdue' : 'unpaid'
  const notes = (saved?.note || '').split(/(?<=\.)\s+/).filter(note => note && !note.startsWith('Pending payment') && !note.startsWith('A refund is pending') && !note.startsWith('Unapplied funds'))
  if (pending) notes.push('Pending payment is awaiting confirmation and has not reduced the balance.')
  if (Number(settlement.refund_pending) > 0) notes.push('A refund is pending; contact the shop for its status.')
  if (Number(settlement.unapplied_credit) > 0) notes.push('Unapplied funds are held separately from this invoice balance.')
  return { state, applied_amount: saved?.applied_amount === null && (saved.basis === 'settlement' || saved.basis === 'status_only') ? null : settlement.confirmed_principal, balance_due: settlement.outstanding_balance, pending_amount: pending ? settlement.active_pending_principal : null, basis: 'settlement', note: [...new Set(notes)].join(' ') || null }
}
