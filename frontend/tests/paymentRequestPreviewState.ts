import type { InvoiceSettlementSummary, PaymentAllocation } from '@/features/payments/types'
import type { AttemptResolutionCommand, AttemptResolutionResponse } from '@/features/payments/attemptResolutionTypes'

export type PreviewOutcome = 'cancelled' | 'review_required' | 'received'
export interface PreviewState { summary: InvoiceSettlementSummary; rows: PaymentAllocation[] }

/** Exact fictional fixture transitions. No API, storage, timers or provider calls. */
export function resolvePreview(state: PreviewState, id: string, command: AttemptResolutionCommand, outcome: PreviewOutcome): { state: PreviewState; response: AttemptResolutionResponse } {
  const row = state.rows.find(item => item.attempt_id === id)
  if (!row?.resolution || row.rail === 'cash' || !row.resolution.actions[command.action] || command.action !== 'cancel_unsent'
      || command.expected_attempt_version !== row.resolution.attempt_version || command.expected_settlement_version !== state.summary.version) throw new Error('Preview request changed. Reset the preview.')
  if (row.rail === 'zelle' && command.transfer_not_sent_confirmed !== true) throw new Error('Confirm that the transfer was not sent.')
  const summary: InvoiceSettlementSummary = { ...state.summary, version: state.summary.version + 1,
    ...(outcome === 'cancelled' ? { active_pending_principal: '100.00', allocatable_balance: '168.44' } : {}),
    ...(outcome === 'received' ? { confirmed_principal: '168.44', outstanding_balance: '100.00', active_pending_principal: '100.00', allocatable_balance: '0.00', state: 'partially_paid_pending' } : {}) }
  const resolution = { ...row.resolution, attempt_version: row.resolution.attempt_version + 1, settlement_version: summary.version,
    checkout_status: outcome, attempt_state: outcome === 'cancelled' ? 'failed' as const : outcome === 'received' ? 'confirmed' as const : 'pending' as const,
    reservation_amount: outcome === 'review_required' ? row.principal_amount : '0.00', can_retry: outcome === 'cancelled',
    actions: { cancel_unsent: false, check_provider_status: false, request_review: false, release_with_terminal_evidence: false, record_late_receipt: false },
    block_reason: outcome === 'review_required' ? { code: 'provider_review_required', message: 'The shop needs to check this payment before you try again.' } : null,
    review_status: outcome === 'review_required' ? 'requested' as const : 'resolved' as const,
    resolution_notice: outcome === 'cancelled' ? { kind: 'request_cancelled', message: 'Payment request canceled. No payment was recorded.', resolved_at: '2026-11-05T12:00:00Z' } : null }
  const updated: PaymentAllocation = { ...row, state: resolution.attempt_state, resolution, applied_principal_amount: outcome === 'received' ? row.principal_amount : '0.00' }
  const rows = state.rows.map(item => item.attempt_id === id ? updated : { ...item, resolution: item.resolution ? { ...item.resolution, settlement_version: summary.version } : undefined })
  const response: AttemptResolutionResponse = { attempt_id: id, invoice_id: summary.invoice_id, rail: row.rail, provider: row.provider,
    principal_amount: row.principal_amount, card_fee_amount: row.card_fee_amount, card_fee_tax_amount: row.card_fee_tax_amount, provider_charge_amount: row.provider_charge_amount,
    state: resolution.attempt_state, attempt_version: resolution.attempt_version, provider_configuration_version: 1, expires_at: null, resolution, settlement: summary }
  return { state: { summary, rows }, response }
}
