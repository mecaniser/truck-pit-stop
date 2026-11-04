import type { ZelleReviewRow } from './useZelleReviewQueue'

/** Replace only a matched payment marker; the repair order may still need other work. */
export function withoutDuplicateZelle<T extends { id: string; pending_zelle_confirmation?: boolean }>(rows: T[], queue: ZelleReviewRow[], complete: boolean): T[] {
  if (!complete) return rows
  // Canonical collection invoices can share this RO with a different original
  // invoice. An RO-only projection cannot prove that their money is the same.
  const reviewedOrders = new Set(queue.filter(row => row.can_confirm && row.repair_order_id && row.kind === 'legacy_zelle_submission' && row.review_mode === 'legacy_invoice').map(row => row.repair_order_id))
  return rows.map(row => row.pending_zelle_confirmation && reviewedOrders.has(row.id) ? { ...row, pending_zelle_confirmation: false } : row)
}
