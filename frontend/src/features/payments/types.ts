export type SettlementState =
  | 'unpaid'
  | 'payment_pending'
  | 'partially_paid'
  | 'partially_paid_pending'
  | 'paid'
  | 'overpayment_resolution'

export type PaymentRail = 'card' | 'zelle' | 'check' | 'ach'
export type CardProvider = 'stripe_connect' | 'quickbooks_payments'
export type CardProviderStatus =
  | 'ready'
  | 'not_ready'
  | 'not_configured'
  | 'onboarding_incomplete'
  | 'accounting_mapping_incomplete'
  | 'accounting_unavailable'
  | 'unavailable_external_approval'
  | 'feature_disabled'

export type AccountingSyncStatus = 'not_started' | 'not_required' | 'not_applicable_local_cash' | 'pending' | 'synced' | 'failed' | 'dead_letter'
export type PaymentAttemptState = 'pending' | 'confirmed' | 'failed' | 'expired' | 'refunded' | 'reversed'

export interface SettlementAllowedActions {
  create_attempt?: boolean
  rails?: PaymentRail[]
  confirm_manual?: boolean
  resolve_overpayment?: boolean
  apply_customer_credit?: boolean
  authorize_early_release?: boolean
  retry_accounting?: boolean
  configure_provider?: boolean
  confirm_cash?: boolean
  cash_unavailable_reason?: string | null
  payment_unavailable_reason?: string | null
}

export interface InvoiceSettlementSummary {
  breakdown?: {
    subtotal: string
    shop_supplies_amount: string
    sales_tax_amount: string
    discount_amount: string
    principal_total: string
  }
  tax_exemption?: {
    applied: boolean
    can_apply: boolean
    unavailable_reason: string | null
    current_tax_amount: string
    removed_tax_amount: string
    exempt_principal_total: string
    reason: string | null
    support_reference: string | null
  }
  invoice_id: string
  currency: 'USD'
  principal_total: string
  confirmed_principal: string
  active_pending_principal: string
  outstanding_balance: string
  allocatable_balance: string
  unapplied_credit: string
  refund_pending: string
  state: SettlementState
  version: number
  card_provider: CardProvider | null
  card_provider_status: CardProviderStatus
  accounting_sync_status: AccountingSyncStatus
  feature_enabled?: boolean
  allowed_actions?: SettlementAllowedActions
}

export interface PaymentQuote {
  settlement_version: number
  rail: PaymentRail | 'cash'
  principal_amount: string
  card_fee_amount: string
  card_fee_tax_amount: string
  total_amount: string
}

export interface PaymentAttemptCreate {
  amount: string
  rail: PaymentRail
  expected_settlement_version: number
  sender_evidence?: {
    sender_email?: string | null
    sender_phone?: string | null
    reference?: string | null
    note?: string | null
  } | null
}

export interface PaymentAttemptResponse {
  attempt_id: string
  invoice_id: string
  principal_amount: string
  card_fee_amount: string
  card_fee_tax_amount: string
  provider_charge_amount: string
  rail: PaymentRail
  provider: CardProvider | 'manual'
  state: PaymentAttemptState
  expires_at: string | null
  provider_configuration_version: number
  attempt_version?: number
  provider_client_secret?: string | null
  provider_account_id?: string | null
  provider_token_url?: string | null
  settlement: InvoiceSettlementSummary
}

export interface PaymentAllocation {
  id: string
  attempt_id: string
  attempt_version?: number
  rail: PaymentRail | 'cash'
  provider: CardProvider | 'manual'
  principal_amount: string
  applied_principal_amount: string
  card_fee_amount: string
  card_fee_tax_amount: string
  provider_charge_amount: string
  received_amount?: string | null
  unapplied_amount: string
  state: PaymentAttemptState
  created_at: string
  confirmed_at?: string | null
  expires_at?: string | null
  actor_name?: string | null
  reference_number?: string | null
  accounting_sync_status?: AccountingSyncStatus
  overpayment_id?: string | null
  overpayment_state?: string | null
  refund_id?: string | null
  refund_state?: string | null
}

export interface PaymentAllocationPage {
  items: PaymentAllocation[]
  next_cursor: string | null
}

export type SettlementAccess =
  | { kind: 'authenticated'; invoiceId: string }
  | { kind: 'guest'; token: string; invoiceId?: string }

export interface CardProviderReadiness {
  feature_enabled: boolean
  selected_provider: CardProvider | null
  selected_provider_status: CardProviderStatus
  configuration_version: number | null
  stripe_connect: {
    approved: boolean
    tenant_ready: boolean
    status: CardProviderStatus
    message?: string | null
  }
  quickbooks_payments: {
    approved: boolean
    tenant_ready: boolean
    status: CardProviderStatus
    message?: string | null
  }
  accounting_ready: boolean
  accounting_message?: string | null
  writer_strategy?: 'dieselbridge' | 'intuit_native' | null
  mappings?: Record<string, string | null>
  allowed_actions?: SettlementAllowedActions
}

export interface CustomerCreditAgingItem {
  credit_id: string
  customer_id: string
  customer_name: string
  origin_amount: string
  remaining_amount: string
  issued_at: string
  age_days: number
  consent_channel?: string | null
  consent_note?: string | null
  disposition: string
}

export interface EligibleCustomerCredit {
  credit_id: string
  origin_overpayment_id?: string | null
  origin_amount: string
  remaining_amount: string
  issued_at: string
  consent_channel?: string | null
}

export interface AccountingReconciliationLink {
  id: string
  type: string
  state: string
  provider_object_id?: string | null
  error?: string | null
}

export interface AccountingReconciliation {
  invoice_id: string
  state: 'not_required' | 'pending' | 'synced' | 'failed'
  pending_operations: number
  failed_operations: number
  synced_operations: number
  links: AccountingReconciliationLink[]
}

export interface PaymentApiError {
  code: string
  message: string
  retryable: boolean
  current_version?: number | null
  status?: number
}
