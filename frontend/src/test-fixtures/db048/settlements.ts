import type {
  CardProviderReadiness,
  InvoiceSettlementSummary,
  PaymentAllocation,
} from '@/features/payments'

const base: InvoiceSettlementSummary = {
  invoice_id: 'invoice-834',
  currency: 'USD',
  principal_total: '834.00',
  confirmed_principal: '0.00',
  active_pending_principal: '0.00',
  outstanding_balance: '834.00',
  allocatable_balance: '834.00',
  unapplied_credit: '0.00',
  refund_pending: '0.00',
  state: 'unpaid',
  version: 1,
  card_provider: 'stripe_connect',
  card_provider_status: 'ready',
  accounting_sync_status: 'not_started',
  feature_enabled: true,
  allowed_actions: { create_attempt: true, rails: ['card', 'zelle'] },
}

const allocation = (overrides: Partial<PaymentAllocation>): PaymentAllocation => ({
  id: overrides.id || 'allocation-1',
  attempt_id: overrides.attempt_id || 'attempt-1',
  rail: overrides.rail || 'zelle',
  provider: overrides.provider || 'manual',
  principal_amount: overrides.principal_amount || '500.00',
  applied_principal_amount: overrides.applied_principal_amount || overrides.principal_amount || '500.00',
  card_fee_amount: overrides.card_fee_amount || '0.00',
  card_fee_tax_amount: overrides.card_fee_tax_amount || '0.00',
  provider_charge_amount: overrides.provider_charge_amount || overrides.principal_amount || '500.00',
  received_amount: overrides.received_amount ?? overrides.provider_charge_amount ?? overrides.principal_amount ?? '500.00',
  unapplied_amount: overrides.unapplied_amount || '0.00',
  state: overrides.state || 'confirmed',
  created_at: overrides.created_at || '2026-08-30T12:00:00Z',
  confirmed_at: overrides.confirmed_at ?? '2026-08-30T12:05:00Z',
  expires_at: overrides.expires_at ?? null,
  actor_name: overrides.actor_name ?? 'Alex Manager',
  reference_number: overrides.reference_number ?? null,
  accounting_sync_status: overrides.accounting_sync_status ?? 'synced',
  overpayment_id: overrides.overpayment_id ?? null,
  overpayment_state: overrides.overpayment_state ?? null,
  refund_id: overrides.refund_id ?? null,
  refund_state: overrides.refund_state ?? null,
})

export const DB048_SETTLEMENT_FIXTURES = {
  unpaid: { summary: base, allocations: [] },
  pendingZelle500: {
    summary: {
      ...base,
      active_pending_principal: '500.00',
      allocatable_balance: '334.00',
      state: 'payment_pending' as const,
      version: 2,
    },
    allocations: [allocation({ state: 'pending', confirmed_at: null, expires_at: '2026-08-31T12:00:00Z' })],
  },
  zelle500PlusCard334: {
    summary: { ...base, confirmed_principal: '834.00', outstanding_balance: '0.00', allocatable_balance: '0.00', state: 'paid' as const, version: 4, accounting_sync_status: 'synced' as const },
    allocations: [
      allocation({ id: 'zelle-500', principal_amount: '500.00' }),
      allocation({ id: 'card-334', rail: 'card', provider: 'stripe_connect', principal_amount: '334.00', provider_charge_amount: '344.02' }),
    ],
  },
  threeTendersClosed: {
    summary: { ...base, confirmed_principal: '834.00', outstanding_balance: '0.00', allocatable_balance: '0.00', state: 'paid' as const, version: 6, accounting_sync_status: 'synced' as const },
    allocations: [
      allocation({ id: 'check-200', rail: 'check', principal_amount: '200.00', reference_number: '1008' }),
      allocation({ id: 'zelle-300', principal_amount: '300.00', reference_number: 'ZELLE-882' }),
      allocation({ id: 'card-334', rail: 'card', provider: 'stripe_connect', principal_amount: '334.00' }),
    ],
  },
  failedCardReleased: {
    summary: { ...base, version: 3 },
    allocations: [allocation({ rail: 'card', provider: 'stripe_connect', state: 'failed', confirmed_at: null, principal_amount: '334.00' })],
  },
  accountingSyncPending: {
    summary: { ...base, confirmed_principal: '500.00', outstanding_balance: '334.00', allocatable_balance: '334.00', state: 'partially_paid' as const, version: 3, accounting_sync_status: 'pending' as const },
    allocations: [allocation({ accounting_sync_status: 'pending' })],
  },
  automaticRefundPending: {
    summary: { ...base, confirmed_principal: '834.00', outstanding_balance: '0.00', allocatable_balance: '0.00', refund_pending: '75.00', state: 'overpayment_resolution' as const, version: 5, accounting_sync_status: 'pending' as const },
    allocations: [allocation({ rail: 'card', provider: 'stripe_connect', principal_amount: '834.00', provider_charge_amount: '909.00', unapplied_amount: '75.00', overpayment_id: 'overpayment-card-75', overpayment_state: 'refund_required', refund_id: 'refund-card-75', refund_state: 'pending' })],
  },
  manualOverpaymentDecision: {
    summary: { ...base, confirmed_principal: '834.00', outstanding_balance: '0.00', allocatable_balance: '0.00', unapplied_credit: '50.00', state: 'overpayment_resolution' as const, version: 5, allowed_actions: { resolve_overpayment: true, rails: [] } },
    allocations: [allocation({ rail: 'ach', principal_amount: '834.00', provider_charge_amount: '884.00', received_amount: '884.00', unapplied_amount: '50.00', reference_number: 'ACH-9921', overpayment_id: 'overpayment-ach-50', overpayment_state: 'refund_required', refund_id: 'refund-ach-50', refund_state: 'manual_action_required' })],
  },
  futureCreditApplied: {
    summary: { ...base, confirmed_principal: '100.00', outstanding_balance: '734.00', allocatable_balance: '734.00', state: 'partially_paid' as const, version: 2 },
    allocations: [allocation({ rail: 'ach', principal_amount: '100.00', reference_number: 'Customer credit' })],
  },
}

export const DB048_PROVIDER_READINESS: CardProviderReadiness = {
  feature_enabled: true,
  selected_provider: 'stripe_connect',
  selected_provider_status: 'ready',
  configuration_version: 2,
  stripe_connect: { approved: true, tenant_ready: true, status: 'ready' },
  quickbooks_payments: {
    approved: false,
    tenant_ready: false,
    status: 'unavailable_external_approval',
    message: 'Intuit production acceptance is pending.',
  },
  accounting_ready: true,
  allowed_actions: { configure_provider: true },
}

export const DB048_BOUNDARY_FIXTURES = {
  disabled: { status: 409, error: { code: 'invoice_split_payments_disabled' } },
  unauthorized: { status: 404, error: { code: 'invoice_not_found' } },
  foreignInvoice: { status: 404, error: { code: 'invoice_not_found' } },
}
