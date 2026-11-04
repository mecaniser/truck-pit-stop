import { AxiosError } from 'axios'
import api from '@/lib/api'
import { paymentStepUpHeaders } from '@/lib/paymentStepUp'
import type { PaymentAttemptResponse, SettlementAccess } from './types'

export interface EfsSubmissionSummary {
  provider: 'EFS'
  code_last4: string
  status: 'awaiting_verification' | 'received' | 'rejected' | 'cancelled' | 'review_required'
  can_cancel: boolean
  can_reveal: boolean
  can_verify: boolean
  can_reject: boolean
  can_resolve_received_difference: boolean
  difference_review: { observation_id: string; requested_amount: string; actual_received_amount: string; currency: 'USD'; authorization_reference: string } | null
}
export type EfsAttemptResponse = PaymentAttemptResponse & { efs: EfsSubmissionSummary }
export interface EfsSubmissionCommand {
  code: string
  amount: string
  expected_settlement_version: number
  submitted_for_verification: true
}
export interface EfsVerificationCommand {
  action: 'confirm_received' | 'reject' | 'resolve_received_difference'
  expected_attempt_version: number
  expected_settlement_version: number
  reason: string
  observation_id?: string
  merchant_authorized?: true
  authorization_reference?: string
  received_amount?: string
}
export const EFS_STATUS_LABELS: Record<EfsSubmissionSummary['status'], string> = {
  awaiting_verification: 'Awaiting shop verification', received: 'Payment received',
  rejected: 'Request rejected', cancelled: 'Request canceled', review_required: 'Needs shop review',
}

export function normalizeEfsSummary(value: unknown): EfsSubmissionSummary | null {
  if (value == null) return null
  if (typeof value !== 'object') throw new Error('EFS details are unavailable.')
  const row = value as Record<string, unknown>
  const keys = ['can_cancel', 'can_reveal', 'can_verify', 'can_reject', 'can_resolve_received_difference'] as const
  if (row.provider !== 'EFS' || typeof row.code_last4 !== 'string' || !/^[0-9]{4}$/.test(row.code_last4)
      || typeof row.status !== 'string' || !Object.prototype.hasOwnProperty.call(EFS_STATUS_LABELS, row.status) || keys.some(key => typeof row[key] !== 'boolean')) throw new Error('EFS details are unavailable.')
  const difference = row.difference_review as Record<string, unknown> | null
  if (difference !== null && (typeof difference !== 'object' || !difference || typeof difference.observation_id !== 'string' || typeof difference.requested_amount !== 'string' || typeof difference.actual_received_amount !== 'string' || difference.currency !== 'USD' || typeof difference.authorization_reference !== 'string')) throw new Error('EFS details are unavailable.')
  return {
    provider: 'EFS', code_last4: row.code_last4, status: row.status as EfsSubmissionSummary['status'],
    can_cancel: row.can_cancel as boolean, can_reveal: row.can_reveal as boolean,
    can_verify: row.can_verify as boolean, can_reject: row.can_reject as boolean,
    can_resolve_received_difference: row.can_resolve_received_difference as boolean,
    difference_review: difference ? { observation_id: difference.observation_id as string, requested_amount: difference.requested_amount as string, actual_received_amount: difference.actual_received_amount as string, currency: 'USD', authorization_reference: difference.authorization_reference as string } : null,
  }
}

export async function submitEfsCode(access: SettlementAccess, command: EfsSubmissionCommand, key: string): Promise<EfsAttemptResponse> {
  const path = access.kind === 'guest' ? '/invoice-access/efs-submissions' : `/payments/invoices/${access.invoiceId}/efs-submissions`
  return (await api.post<EfsAttemptResponse>(path, access.kind === 'guest' ? { token: access.token, ...command } : command, { headers: { 'Idempotency-Key': key } })).data
}

export async function revealEfsCode(attemptId: string, version: number): Promise<{ code: string; last4: string }> {
  // This sensitive read is deliberately outside the query/mutation cache.
  return (await api.post<{ code: string; last4: string }>(`/payments/attempts/${attemptId}/efs-code/reveal`, {
    expected_attempt_version: version, reason: 'Verify the submitted EFS MoneyCode.',
  })).data
}

export async function verifyEfsCode(attemptId: string, command: EfsVerificationCommand, key: string, grant?: string): Promise<EfsAttemptResponse> {
  return (await api.post<EfsAttemptResponse>(`/payments/attempts/${attemptId}/efs-verification`, command, { headers: { 'Idempotency-Key': key, ...(grant ? paymentStepUpHeaders(grant) : {}) } })).data
}

export function efsError(error: unknown) {
  const response = error instanceof AxiosError ? error.response : undefined
  const detail = response?.data?.detail ?? response?.data?.error
  const code = typeof detail === 'object' && detail ? detail.code : undefined
  const messages: Record<string, string> = {
    STEP_UP_METHOD_UNAVAILABLE: 'This account cannot use password verification. Use an authorized account that supports it.',
    efs_code_requires_review: 'This code was already submitted. Contact the shop about it, or use a different code.',
    efs_unavailable: 'EFS is unavailable right now. Choose another method or contact the shop.',
    stale_attempt_version: 'This request changed. Refresh before continuing.',
    stale_settlement_version: 'Your balance changed. Refresh before continuing.',
    invoice_not_found: 'This invoice is no longer available to this account.',
  }
  return {
    message: typeof code === 'string' && messages[code] ? messages[code] : response?.status === 422
      ? 'Check the code, amount and verification details.'
      : 'Couldn’t verify the result. Check payment activity before trying again.',
    uncertain: !response || response.status >= 500,
    stepUpUnavailable: code === 'STEP_UP_METHOD_UNAVAILABLE',
    stale: response?.status === 409,
  }
}
