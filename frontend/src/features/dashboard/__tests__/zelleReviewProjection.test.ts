import { describe, expect, it } from 'vitest'
import { withoutDuplicateZelle } from '../zelleReviewProjection'
import type { ZelleReviewRow } from '../useZelleReviewQueue'

const order = { id: 'ro-a', pending_zelle_confirmation: true, status: 'pending_review', quote_sent: true, hold_reason: 'Parts needed', promised_finish_at: '2026-11-05T18:00:00Z', is_overdue: true }
const request: ZelleReviewRow = { kind: 'legacy_zelle_submission', invoice_id: 'invoice-a', repair_order_id: 'ro-a', display_invoice_number: 'TPS-1687', customer_id: 'payer-a', customer_display_name: 'Billed customer', principal_amount: '168.44', attempt_id: null, settlement_id: 'settlement-a', settlement_version: 3, created_at: '2026-11-04T12:00:00Z', reported_at: '2026-11-04T12:00:00Z', report_status: 'legacy_report', review_mode: 'legacy_invoice', can_confirm: true }

describe('exact payment-review projection deduplication', () => {
  it('does not hide a projected payment when the successful queue is empty', () => {
    expect(withoutDuplicateZelle([order], [], true)).toEqual([order])
  })
  it.each(['foreign-ro', null])('preserves unmatched projected payments for queue order %s', repairOrderId => {
    // Even a coincidentally matching invoice ID cannot stand in for the RO identity.
    expect(withoutDuplicateZelle([order], [{ ...request, invoice_id: 'ro-a', repair_order_id: repairOrderId }], true)).toEqual([order])
  })
  it('preserves every projected row until the complete queue has loaded successfully', () => {
    expect(withoutDuplicateZelle([order], [request], false)).toEqual([order])
  })
  it('replaces only the exact matching legacy payment marker and preserves other work', () => {
    const unrelated = { ...order, id: 'ro-b', status: 'in_progress' }
    const result = withoutDuplicateZelle([order, unrelated], [request], true)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ ...order, pending_zelle_confirmation: false })
    expect(result[1]).toBe(unrelated)
    expect(order.pending_zelle_confirmation).toBe(true)
  })
  it('does not treat a canonical collection on the same RO as proof of the legacy invoice identity', () => {
    const canonical: ZelleReviewRow = { ...request, kind: 'canonical_zelle_attempt', review_mode: 'canonical_attempt', attempt_id: 'attempt-copy', report_status: 'explicit_report', invoice_id: 'different-native-copy' }
    expect(withoutDuplicateZelle([order], [canonical], true)).toEqual([order])
  })
  it('keeps invoice closeout work even when its payment marker has an exact review destination', () => {
    expect(withoutDuplicateZelle([{ ...order, status: 'invoiced' }], [request], true)).toEqual([{ ...order, status: 'invoiced', pending_zelle_confirmation: false }])
  })
  it('preserves the existing payment marker when the returned request has no available review action', () => {
    expect(withoutDuplicateZelle([order], [{ ...request, can_confirm: false }], true)).toEqual([order])
  })
})
