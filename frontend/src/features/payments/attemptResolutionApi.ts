import { AxiosError } from 'axios'
import api from '@/lib/api'
import { paymentStepUpHeaders } from '@/lib/paymentStepUp'
import type { SettlementAccess } from './types'
import type { AttemptResolutionCommand, AttemptResolutionDetail, AttemptResolutionResponse } from './attemptResolutionTypes'

export async function fetchAttemptResolutionDetail(attemptId: string): Promise<AttemptResolutionDetail> {
  return (await api.get<AttemptResolutionDetail>(`/payments/attempts/${attemptId}/resolution/read`)).data
}

export async function resolvePaymentAttempt(access: SettlementAccess, attemptId: string, command: AttemptResolutionCommand, key: string, grant?: string): Promise<AttemptResolutionResponse> {
  const path = access.kind === 'guest' ? `/invoice-access/attempts/${attemptId}/resolution` : `/payments/attempts/${attemptId}/resolution`
  return (await api.post<AttemptResolutionResponse>(path, access.kind === 'guest' ? { token: access.token, ...command } : command, {
    headers: { 'Idempotency-Key': key, ...(grant ? paymentStepUpHeaders(grant) : {}) },
  })).data
}

export function resolutionError(error: unknown): { message: string; uncertain: boolean; stale: boolean } {
  const response = error instanceof AxiosError ? error.response : undefined
  const detail = response?.data?.detail ?? response?.data?.error
  const code = typeof detail === 'object' && detail ? detail.code : undefined
  const message = typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message : undefined
  // Public controls never echo provider diagnostics, request IDs, or source policy names.
  const safe = message && !/\b(DBN|ETS|idempotency|configuration|traceback)\b|source_|handoff_|bill_to_/i.test(message)
  return {
    message: safe ? message : 'Couldn’t update this request. Refresh its status before trying again.',
    uncertain: !response || response.status >= 500,
    stale: response?.status === 409 || typeof code === 'string' && code.includes('stale'),
  }
}
