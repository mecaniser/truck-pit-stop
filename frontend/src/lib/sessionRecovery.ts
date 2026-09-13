import { create } from 'zustand'
import { useAuthStore } from '../stores/authStore'

export const useSessionRecovery = create<{ recovering: boolean }>(() => ({ recovering: false }))

export function setSessionRecovering(recovering: boolean): void {
  useSessionRecovery.setState({ recovering })
}

export function isSessionRejection(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  return status === 401 || status === 403
}

/** No logout HTTP call: a renewal rejection must not renew again recursively. */
export function endRejectedSession(error: unknown): void {
  const { user } = useAuthStore.getState()
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const code = typeof detail === 'object' && detail !== null && 'code' in detail ? detail.code : null
  const reason = code === 'session_expired' || detail === 'WorkOS session expired' ? 'session_expired' : 'session_ended'
  const query = new URLSearchParams({ reason })
  if (user?.tenant_id) query.set('tenant_id', user.tenant_id)
  if (user?.role !== 'driver') {
    query.set('return_to', `${window.location.pathname}${window.location.search}`)
  }
  const loginPath = user?.role === 'driver' ? '/driver/login' : '/login'
  setSessionRecovering(false)
  useAuthStore.getState().clearSession()
  window.location.href = `${loginPath}?${query}`
}

export function sessionEndMessage(reason: string | null): string | null {
  if (reason === 'session_expired' || reason === 'workos_session_expired') {
    return 'Your session expired. Sign in again to continue.'
  }
  if (reason === 'session_ended') return 'Your session ended. Sign in again to continue.'
  return null
}
