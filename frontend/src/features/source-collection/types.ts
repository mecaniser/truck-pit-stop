export interface SourceCollectionSummary {
  is_source_history?: boolean
  id: string
  state: 'prepared' | 'active' | 'source_conflict' | 'closed'
  version: number
  source_invoice_number: string
  source_service_number: string
  original_issued_total: string
  source_prior_allocated: string
  opening_principal: string
  native_invoice_id: string | null
  balance_due: string | null
  native_confirmed_principal: string
  native_pending_principal: string
  source_observed_at: string
  source_sync_state: 'current' | 'ets_update_pending' | 'source_conflict' | 'source_unavailable'
  accounting_state: 'external_reconciliation_pending' | 'verified_external'
  hold_reasons: string[]
  collection_enabled?: boolean
  payment_hold_reasons?: string[]
  source_capture_sha256?: string
  source_revision?: string
}

export interface EtsReceiptTask {
  id: string
  handoff_id: string
  invoice_id: string
  payment_id: string
  attempt_id: string | null
  principal_amount: string
  received_amount: string
  fee_amount: string
  unapplied_amount: string
  currency: string
  effective_at: string
  state: 'pending_manual' | 'claimed' | 'awaiting_verification' | 'verified' | 'conflict'
  version: number
  expected_source_revision: string
  claim_expires_at: string | null
}

export interface SourceCollectionProposal {
  source_invoice_id: string
  source_repair_order_id: string
  source_shop_id: string
  source_service_number: string
  source_invoice_number: string
  source_internal_invoice_id: string
  source_observed_at: string
  source_capture_sha256: string
  source_revision: string
  currency: string
  original_issued_total: string
  source_prior_allocated: string
  opening_principal: string
  target_customer_id: string
  original_invoice_date: string
}

export interface SourceCollectionPreview {
  existing_handoff?: SourceCollectionSummary | null
  eligibility: 'ready' | 'held'
  hold_reasons: string[]
  proposal: SourceCollectionProposal | null
}
