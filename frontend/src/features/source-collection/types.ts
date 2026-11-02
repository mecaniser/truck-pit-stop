export interface SourceCollectionSummary {
  is_source_history?: boolean
  restricted_history?: boolean
  source_invoice_id?: string
  source_customer_id?: string
  target_customer_id?: string | null
  bill_to_authorization_mode?: 'same_customer' | 'owner_same_legal_entity'
  bill_to_reviewed_at?: string
  id: string
  state: 'prepared' | 'active' | 'source_conflict' | 'closed'
  version: number
  source_invoice_number: string
  source_service_number: string
  original_issued_total: string
  original_invoice_date?: string | null
  source_prior_allocated: string
  opening_principal: string
  native_invoice_id: string | null
  balance_due: string | null
  native_confirmed_principal: string | null
  native_pending_principal: string | null
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
  bill_to_review?: {
    required: boolean
    source_customer_id: string
    source_ets_customer_id: string
    target_customer_id: string
    source_legal_name: string
    target_legal_name: string
    authorization_mode: 'same_customer' | 'owner_same_legal_entity' | null
  }
  existing_handoff?: SourceCollectionSummary | null
  eligibility: 'ready' | 'held'
  hold_reasons: string[]
  proposal: SourceCollectionProposal | null
}

export interface BillToReview {
  mode: 'owner_same_legal_entity'
  source_customer_id: string
  target_customer_id: string
  attested_same_legal_entity: true
  confirmation_reference: string
  reason: string
}
