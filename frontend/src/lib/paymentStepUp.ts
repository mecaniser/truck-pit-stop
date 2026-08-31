import api from './api'

export type PaymentStepUpScope =
  | 'payment_sources.manage'
  | 'payment_sources.zelle.disable'
  | 'payment_sources.zelle.qr.remove'
  | 'payment_sources.stripe.disconnect'
  | 'payment_sources.quickbooks.disconnect'
  | 'platform.payment_sources.stripe.reset'
  | 'platform.payment_sources.quickbooks.reset'

export interface PaymentStepUpGrant {
  grant_token: string
  scope: PaymentStepUpScope
  expires_at: string
  one_time: boolean
}

export async function createPaymentStepUpGrant(
  password: string,
  scope: PaymentStepUpScope,
  targetTenantId?: string,
): Promise<PaymentStepUpGrant> {
  const response = await api.post('/auth/step-up-grants', {
    password,
    scope,
    target_tenant_id: targetTenantId ?? null,
  })
  return response.data as PaymentStepUpGrant
}

export function paymentStepUpHeaders(grantToken: string) {
  return { 'X-Step-Up-Authorization': grantToken }
}

export function paymentStepUpError(error: unknown, fallback: string): string {
  if (!error || typeof error !== 'object') return fallback
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    return detail.message
  }
  return fallback
}

export function isPaymentStepUpRequired(error: unknown): boolean {
  return Boolean(
    error
    && typeof error === 'object'
    && (error as { response?: { status?: number } }).response?.status === 428,
  )
}

export function paymentStepUpRequiredScope(error: unknown): string | null {
  if (!isPaymentStepUpRequired(error)) return null
  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
  if (!detail || typeof detail !== 'object' || !('required_scope' in detail)) return null
  return typeof detail.required_scope === 'string' ? detail.required_scope : null
}
