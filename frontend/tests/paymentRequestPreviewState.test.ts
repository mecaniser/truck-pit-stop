import { describe, expect, it } from 'vitest'
import { resolvePreview, type PreviewState } from './paymentRequestPreviewState'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { AttemptResolutionCommand } from '@/features/payments/attemptResolutionTypes'
const initial = (): PreviewState => ({
  summary: { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, invoice_id: 'preview', principal_total: '268.44', confirmed_principal: '0.00', outstanding_balance: '268.44', active_pending_principal: '268.44', allocatable_balance: '0.00', state: 'payment_pending', version: 1 },
  rows: [{ ...DB048_SETTLEMENT_FIXTURES.pendingZelle500.allocations[0], id: 'card', attempt_id: 'card', rail: 'card', principal_amount: '168.44', state: 'pending', resolution: { attempt_id: 'card', invoice_id: 'preview', rail: 'card', currency: 'USD', attempt_version: 1, settlement_version: 1, requested_principal: '168.44', reservation_amount: '168.44', attempt_state: 'pending', checkout_status: 'checkout_started', can_retry: false, review_status: 'none', block_reason: null, resolution_notice: null, actions: { cancel_unsent: true, check_provider_status: false, request_review: false, release_with_terminal_evidence: false, record_late_receipt: false } } }],
})
const command: AttemptResolutionCommand = { action: 'cancel_unsent', expected_attempt_version: 1, expected_settlement_version: 1, reason_code: 'payment_not_sent' }
describe('Network-free payment preview outcomes', () => {
  it('cancels only the attempt and restores available balance without recording money', () => {
    const before = initial(); const snapshot = JSON.stringify(before)
    const result = resolvePreview(before, 'card', command, 'cancelled')
    expect(result.state.summary).toMatchObject({ outstanding_balance: '268.44', confirmed_principal: '0.00', active_pending_principal: '100.00', allocatable_balance: '168.44' })
    expect(result.response.resolution.can_retry).toBe(true)
    expect(JSON.stringify(before)).toBe(snapshot)
  })
  it('retains reserved amounts when the outcome requires shop review', () => {
    const result = resolvePreview(initial(), 'card', command, 'review_required')
    expect(result.state.summary).toMatchObject({ confirmed_principal: '0.00', active_pending_principal: '268.44', allocatable_balance: '0.00' })
    expect(result.response.resolution).toMatchObject({ can_retry: false, checkout_status: 'review_required', review_status: 'requested' })
  })
  it('shows an already received payment rather than cancellation or retry', () => {
    const result = resolvePreview(initial(), 'card', command, 'received')
    expect(result.state.summary).toMatchObject({ confirmed_principal: '168.44', outstanding_balance: '100.00', active_pending_principal: '100.00', allocatable_balance: '0.00' })
    expect(result.response.resolution).toMatchObject({ can_retry: false, checkout_status: 'received', actions: { cancel_unsent: false } })
  })
  it('rejects stale versions, missing attempts and disallowed actions', () => {
    expect(() => resolvePreview(initial(), 'other', command, 'cancelled')).toThrow()
    expect(() => resolvePreview(initial(), 'card', { ...command, expected_settlement_version: 0 }, 'cancelled')).toThrow()
    expect(() => resolvePreview(initial(), 'card', { ...command, action: 'check_provider_status' }, 'cancelled')).toThrow()
  })
  it('retains the unsent-transfer assertion for Zelle', () => {
    const state = initial(); state.rows[0].rail = 'zelle'
    expect(() => resolvePreview(state, 'card', command, 'cancelled')).toThrow('Confirm that the transfer was not sent.')
  })
})
