import type { CardProvider, InvoiceSettlementSummary, PaymentAttemptResponse, PaymentAttemptState, PaymentRail } from './types'

export type ResolutionAction = 'cancel_unsent' | 'check_provider_status' | 'request_review' | 'release_with_terminal_evidence'
export type CheckoutStatus = 'checkout_started' | 'transfer_reported' | 'verification_pending' | 'review_required' | 'received' | 'cancelled' | 'failed'

export const CHECKOUT_LABELS: Record<CheckoutStatus, string> = {
  checkout_started: 'Checkout started', transfer_reported: 'Transfer reported',
  verification_pending: 'Payment being checked', review_required: 'Needs shop review',
  received: 'Payment received', cancelled: 'Request canceled', failed: 'Payment not completed',
}

export interface ResolutionProjection {
  attempt_id: string
  invoice_id: string
  attempt_version: number
  settlement_version: number
  rail: PaymentRail | 'cash'
  requested_principal: string
  currency: 'USD'
  attempt_state: PaymentAttemptState
  checkout_status: CheckoutStatus
  reservation_amount: string
  can_retry: boolean
  actions: Record<ResolutionAction | 'record_late_receipt', boolean>
  block_reason: { code: string; message: string } | null
  resolution_notice: { kind: string; message: string; resolved_at: string } | null
  review_status: 'none' | 'requested' | 'evidence_required' | 'resolved'
}

export interface ResolutionBinding {
  provider: CardProvider | 'manual'
  provider_account_id: string | null
  environment: 'sandbox' | 'production' | null
  configuration_version: number | null
  provider_request_id: string | null
  provider_reference: string | null
  attempted_at: string
  requested_principal: string
  provider_charge_amount: string
  currency: 'USD'
  evidence_context_sha256: string
}

export interface AttemptResolutionDetail {
  resolution: ResolutionProjection
  binding: ResolutionBinding
  evidence_requirements: {
    can_submit_terminal_evidence: boolean
    requires_provider_case: boolean
    requires_document: boolean
    allowed_kinds: Array<'provider_terminal_no_charge' | 'provider_cancelled'>
    missing_binding_fields: string[]
    message: string
  }
  history: Array<{ event_id: string; action: string; occurred_at: string; actor_display: string; reason: string; proof_kind: string; evidence_reference?: string | null; provider_case_reference?: string | null }>
}

export interface TerminalEvidence extends Pick<ResolutionBinding, 'provider' | 'provider_account_id' | 'environment' | 'configuration_version' | 'provider_request_id' | 'provider_reference' | 'attempted_at' | 'evidence_context_sha256'> {
  kind: 'provider_terminal_no_charge' | 'provider_cancelled'
  review_window_start: string
  review_window_end: string
  provider_case_reference: string
  evidence_reference: string
  evidence_sha256?: string | null
  terminal_outcome: 'no_charge' | 'cancelled'
  reviewer_statement: string
}

export interface AttemptResolutionCommand {
  action: ResolutionAction
  expected_attempt_version: number
  expected_settlement_version: number
  reason_code: string
  reason?: string
  transfer_not_sent_confirmed?: boolean
  evidence?: TerminalEvidence
}

export type AttemptResolutionResponse = PaymentAttemptResponse & { resolution: ResolutionProjection; settlement: InvoiceSettlementSummary }
