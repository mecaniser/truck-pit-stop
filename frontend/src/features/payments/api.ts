import { AxiosError } from 'axios'

import api from '@/lib/api'

import type {
  AccountingReconciliation,
  CardProvider,
  CardProviderReadiness,
  CustomerCreditAgingItem,
  EligibleCustomerCredit,
  InvoiceSettlementSummary,
  PaymentAllocationPage,
  PaymentApiError,
  PaymentAttemptCreate,
  PaymentAttemptResponse,
  SettlementAccess,
} from './types'

interface CardProviderConfigurationWire {
  selected_provider?: CardProvider | null
  readiness_state?: string
  version?: number | null
  writer_strategy?: 'dieselbridge' | 'intuit_native' | null
  mappings?: Record<string, string | null>
}

interface CardProviderReadinessWire {
  provider?: CardProvider | null
  status?: string
  split_payment_global_gate?: boolean
  split_payment_tenant_gate?: boolean
  provider_global_gate?: boolean
  provider_onboarding_ready?: boolean
  qbo_accounting_ready?: boolean
  mappings_ready?: boolean
  reasons?: string[]
  allowed_actions?: CardProviderReadiness['allowed_actions']
}

const idempotencyHeaders = (key: string) => ({ headers: { 'Idempotency-Key': key } })

export function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `db048-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function paymentApiError(error: unknown, fallback = 'Unable to update this payment.'): PaymentApiError {
  if (error instanceof AxiosError) {
    const envelope = error.response?.data?.error
    if (envelope && typeof envelope === 'object') {
      return {
        code: typeof envelope.code === 'string' ? envelope.code : 'payment_request_failed',
        message: typeof envelope.message === 'string' ? envelope.message : fallback,
        retryable: Boolean(envelope.retryable),
        current_version: typeof envelope.current_version === 'number' ? envelope.current_version : null,
        status: error.response?.status,
      }
    }
    const detail = error.response?.data?.detail
    return {
      code: 'payment_request_failed',
      message: typeof detail === 'string' ? detail : fallback,
      retryable: (error.response?.status ?? 500) >= 500,
      status: error.response?.status,
    }
  }
  return { code: 'payment_request_failed', message: fallback, retryable: false }
}

export function isSettlementUnavailable(error: unknown): boolean {
  const parsed = paymentApiError(error)
  const routeMissing = parsed.status === 404
    && parsed.code === 'payment_request_failed'
    && parsed.message.toLowerCase() === 'not found'
  return routeMissing
    || (parsed.status === 409 && ['feature_disabled', 'invoice_split_payments_disabled', 'split_payments_disabled'].includes(parsed.code))
}

export async function fetchSettlement(access: SettlementAccess): Promise<InvoiceSettlementSummary> {
  if (access.kind === 'guest') {
    const { data } = await api.post('/invoice-access/settlement', { token: access.token })
    return (data.settlement ?? data) as InvoiceSettlementSummary
  }
  const { data } = await api.get(`/payments/invoices/${access.invoiceId}/settlement`)
  return (data.settlement ?? data) as InvoiceSettlementSummary
}

export async function fetchAllocations(
  access: SettlementAccess,
  cursor?: string | null,
  limit = 20,
): Promise<PaymentAllocationPage> {
  if (access.kind === 'guest') {
    const { data } = await api.post('/invoice-access/allocations', {
      token: access.token,
      cursor: cursor || null,
      limit,
    })
    return normalizeAllocationPage(data)
  }
  const { data } = await api.get(`/payments/invoices/${access.invoiceId}/allocations`, {
    params: { cursor: cursor || undefined, limit },
  })
  return normalizeAllocationPage(data)
}

function normalizeAllocationPage(data: PaymentAllocationPage | { items?: Array<Record<string, unknown>>; next_cursor?: string | null }): PaymentAllocationPage {
  return {
    items: (data.items ?? []).map(item => {
      const raw = item as Record<string, unknown>
      const attemptId = String(raw.attempt_id ?? raw.id ?? '')
      return {
        id: String(raw.id ?? attemptId),
        attempt_id: attemptId,
        attempt_version: typeof raw.attempt_version === 'number' ? raw.attempt_version : undefined,
        rail: raw.rail as PaymentAllocationPage['items'][number]['rail'],
        provider: raw.provider as PaymentAllocationPage['items'][number]['provider'],
        principal_amount: String(raw.principal_amount ?? '0.00'),
        applied_principal_amount: String(raw.applied_principal_amount ?? raw.principal_amount ?? '0.00'),
        card_fee_amount: String(raw.card_fee_amount ?? '0.00'),
        card_fee_tax_amount: String(raw.card_fee_tax_amount ?? '0.00'),
        provider_charge_amount: String(raw.provider_charge_amount ?? raw.principal_amount ?? '0.00'),
        received_amount: raw.received_amount == null ? null : String(raw.received_amount),
        unapplied_amount: String(raw.unapplied_amount ?? '0.00'),
        state: raw.state as PaymentAllocationPage['items'][number]['state'],
        created_at: String(raw.created_at),
        confirmed_at: raw.confirmed_at == null ? null : String(raw.confirmed_at),
        expires_at: raw.expires_at == null ? null : String(raw.expires_at),
        actor_name: raw.actor_name == null ? null : String(raw.actor_name),
        reference_number: raw.reference_number == null && raw.reference == null
          ? null
          : String(raw.reference_number ?? raw.reference),
        accounting_sync_status: raw.accounting_sync_status as PaymentAllocationPage['items'][number]['accounting_sync_status'],
        overpayment_id: raw.overpayment_id == null ? null : String(raw.overpayment_id),
        overpayment_state: raw.overpayment_state == null ? null : String(raw.overpayment_state),
        refund_id: raw.refund_id == null ? null : String(raw.refund_id),
        refund_state: raw.refund_state == null ? null : String(raw.refund_state),
      }
    }),
    next_cursor: data.next_cursor ?? null,
  }
}

export async function createPaymentAttempt(
  access: SettlementAccess,
  payload: PaymentAttemptCreate,
  idempotencyKey: string,
): Promise<PaymentAttemptResponse> {
  if (access.kind === 'guest') {
    const { data } = await api.post(
      '/invoice-access/attempts',
      { token: access.token, ...payload },
      idempotencyHeaders(idempotencyKey),
    )
    return data as PaymentAttemptResponse
  }
  const { data } = await api.post(
    `/payments/invoices/${access.invoiceId}/attempts`,
    payload,
    idempotencyHeaders(idempotencyKey),
  )
  return data as PaymentAttemptResponse
}

export async function chargeQuickBooksPaymentAttempt(
  access: SettlementAccess,
  attemptId: string,
  paymentToken: string,
  expectedAttemptVersion: number,
  idempotencyKey: string,
): Promise<PaymentAttemptResponse> {
  const path = access.kind === 'guest'
    ? `/invoice-access/attempts/${attemptId}/quickbooks-charge`
    : `/payments/attempts/${attemptId}/quickbooks-charge`
  const body = access.kind === 'guest'
    ? { token: access.token, payment_token: paymentToken, expected_attempt_version: expectedAttemptVersion }
    : { token: paymentToken, expected_attempt_version: expectedAttemptVersion }
  const { data } = await api.post(path, body, idempotencyHeaders(idempotencyKey))
  return data as PaymentAttemptResponse
}

export async function confirmPaymentAttempt(
  access: SettlementAccess,
  attemptId: string,
  payload: { expected_attempt_version: number; received_amount?: string; reference?: string; note?: string },
  idempotencyKey: string,
): Promise<PaymentAttemptResponse> {
  const path = access.kind === 'guest'
    ? `/invoice-access/attempts/${attemptId}/confirm`
    : `/payments/attempts/${attemptId}/confirm`
  const body = access.kind === 'guest' ? { token: access.token, ...payload } : payload
  const { data } = await api.post(path, body, idempotencyHeaders(idempotencyKey))
  return data as PaymentAttemptResponse
}

export async function fetchCardProviderReadiness(): Promise<CardProviderReadiness> {
  const [{ data: readinessData }, { data: configurationData }] = await Promise.all([
    api.get<CardProviderReadiness | CardProviderReadinessWire>('/payments/settings/card-provider/readiness'),
    api.get<CardProviderConfigurationWire>('/payments/settings/card-provider'),
  ])
  if ('selected_provider' in readinessData && 'stripe_connect' in readinessData) {
    return readinessData as CardProviderReadiness
  }
  const readiness = readinessData as CardProviderReadinessWire
  const configuration = configurationData ?? {}
  const selectedProvider = configuration.selected_provider ?? readiness.provider ?? null
  const featureEnabled = Boolean(readiness.split_payment_global_gate && readiness.split_payment_tenant_gate)
  const accountingReady = Boolean(readiness.qbo_accounting_ready && readiness.mappings_ready)
  const status = (readiness.status || configuration.readiness_state || 'not_configured') as CardProviderReadiness['selected_provider_status']
  return {
    feature_enabled: featureEnabled,
    selected_provider: selectedProvider,
    selected_provider_status: status,
    configuration_version: configuration.version ?? null,
    stripe_connect: {
      approved: Boolean(readiness.provider_global_gate),
      tenant_ready: Boolean(readiness.provider_onboarding_ready),
      status: selectedProvider === 'stripe_connect' ? status : 'not_configured',
      message: readiness.reasons?.join(' ') || null,
    },
    quickbooks_payments: {
      approved: Boolean(readiness.provider === 'quickbooks_payments' && readiness.provider_global_gate),
      tenant_ready: Boolean(readiness.provider === 'quickbooks_payments' && readiness.provider_onboarding_ready),
      status: readiness.provider === 'quickbooks_payments' ? status : 'not_configured',
      message: readiness.reasons?.join(' ') || null,
    },
    accounting_ready: accountingReady,
    accounting_message: accountingReady ? null : readiness.reasons?.join(' ') || 'QuickBooks Accounting mappings are not ready.',
    writer_strategy: configuration.writer_strategy ?? null,
    mappings: configuration.mappings ?? {},
    allowed_actions: readiness.allowed_actions,
  }
}

export async function updateCardProvider(
  provider: CardProvider,
  current: CardProviderReadiness,
  idempotencyKey: string,
): Promise<CardProviderReadiness> {
  const mappings = current.mappings ?? {}
  await api.put(
    '/payments/settings/card-provider',
    {
      selected_provider: provider,
      expected_version: current.configuration_version,
      writer_strategy: current.writer_strategy ?? 'dieselbridge',
      stripe_clearing_account: mappings.stripe_clearing_account ?? null,
      qbp_clearing_account: mappings.qbp_clearing_account ?? null,
      check_deposit_account: mappings.check_deposit_account ?? '',
      zelle_ach_account: mappings.zelle_ach_account ?? '',
      card_fee_income_account: mappings.card_fee_income_account ?? '',
      processor_fee_expense_account: mappings.processor_fee_expense_account ?? '',
      sales_tax_liability_account: mappings.sales_tax_liability_account ?? '',
      checking_account: mappings.checking_account ?? '',
    },
    idempotencyHeaders(idempotencyKey),
  )
  return fetchCardProviderReadiness()
}

export async function fetchCustomerCreditAging(): Promise<CustomerCreditAgingItem[]> {
  const { data } = await api.get<CustomerCreditAgingItem[]>('/payments/customer-credits/aging')
  if (!Array.isArray(data)) {
    throw new Error('Customer-credit aging returned an invalid response.')
  }
  return data
}

export async function downloadCustomerCreditAging(): Promise<void> {
  const { data } = await api.get<Blob>('/payments/customer-credits/aging/export.csv', {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'customer-credit-aging.csv'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function fetchAccountingReconciliation(invoiceId: string): Promise<AccountingReconciliation> {
  const { data } = await api.get<AccountingReconciliation>(`/payments/invoices/${invoiceId}/accounting-reconciliation`)
  return data
}

export async function retryAccountingOperation(operationId: string, idempotencyKey: string): Promise<{ operation_id: string; state: string }> {
  const { data } = await api.post(
    `/payments/accounting-operations/${operationId}/retry`,
    {},
    idempotencyHeaders(idempotencyKey),
  )
  return data
}

export async function fetchEligibleCustomerCredits(
  access: Extract<SettlementAccess, { kind: 'authenticated' }>,
): Promise<EligibleCustomerCredit[]> {
  const { data } = await api.get<EligibleCustomerCredit[]>(`/payments/invoices/${access.invoiceId}/eligible-credits`)
  return data
}

export async function applyEligibleCustomerCredit(
  access: Extract<SettlementAccess, { kind: 'authenticated' }>,
  creditId: string,
  amount: string,
  expectedSettlementVersion: number,
  idempotencyKey: string,
): Promise<{ application_id: string; settlement: InvoiceSettlementSummary }> {
  const invoiceId = access.invoiceId
  if (!invoiceId) throw new Error('Invoice identity is required to apply customer credit.')
  const { data } = await api.post(
    `/payments/customer-credits/${creditId}/applications`,
    { invoice_id: invoiceId, amount, expected_settlement_version: expectedSettlementVersion },
    idempotencyHeaders(idempotencyKey),
  )
  return data
}

export async function recordOverpaymentCreditConsent(
  access: SettlementAccess,
  overpaymentId: string,
  channel: 'customer_portal' | 'guest_token' | 'in_person' | 'phone',
  note: string,
  idempotencyKey: string,
): Promise<{ credit_id: string; state: string; amount: string }> {
  if (access.kind === 'guest') {
    const { data } = await api.post(
      `/invoice-access/overpayments/${overpaymentId}/credit-consent`,
      { token: access.token, channel: 'guest_token', note },
      idempotencyHeaders(idempotencyKey),
    )
    return data
  }
  const { data } = await api.post(
    `/payments/overpayments/${overpaymentId}/credit-consent`,
    { channel, note },
    idempotencyHeaders(idempotencyKey),
  )
  return data
}

export async function confirmManualRefund(
  refundId: string,
  reference: string,
  idempotencyKey: string,
): Promise<{ refund_id: string; state: string }> {
  const { data } = await api.post(
    `/payments/refunds/${refundId}/confirm-manual`,
    { reference },
    idempotencyHeaders(idempotencyKey),
  )
  return data
}

export async function retryPaymentRefund(
  refundId: string,
  idempotencyKey: string,
): Promise<{ refund_id: string; state: string }> {
  const { data } = await api.post(
    `/payments/refunds/${refundId}/retry`,
    {},
    idempotencyHeaders(idempotencyKey),
  )
  return data
}

export async function authorizeEarlyVehicleRelease(
  invoiceId: string,
  expectedSettlementVersion: number,
  reason: string,
  idempotencyKey: string,
): Promise<InvoiceSettlementSummary> {
  const { data } = await api.post(
    `/payments/invoices/${invoiceId}/early-release`,
    {
      invoice_id: invoiceId,
      expected_settlement_version: expectedSettlementVersion,
      reason,
    },
    idempotencyHeaders(idempotencyKey),
  )
  return (data.settlement ?? data) as InvoiceSettlementSummary
}
