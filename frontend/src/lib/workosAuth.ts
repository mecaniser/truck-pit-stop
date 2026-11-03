import { beginSignedOutLogin } from './workosLoginReturn'
import api from './api'
import { syncStoredSession, useAuthStore } from '../stores/authStore'

export type DriverInvitationCapabilityReason =
  | 'available'
  | 'workos_auth_disabled'
  | 'organization_not_provisioned'
  | 'manager_not_provisioned'
  | 'workos_reauthentication_required'
  | 'missing_permission'

export interface WorkOSCapabilities {
  session_provider: 'legacy' | 'workos'
  workos_auth_enabled: boolean
  organization_provisioned: boolean
  driver_invitation_management: {
    available: boolean
    reason: DriverInvitationCapabilityReason
    required_permission: 'members:manage'
    reauth_path: string | null
  }
}

function safeReturnPath(value: string): string {
  return value.startsWith('/') && !value.startsWith('//') ? value : '/'
}

function apiBaseUrl(): string {
  return String(import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '')
}

export function buildWorkOSLoginUrl(returnTo: string, tenantId?: string | null): string {
  const params = new URLSearchParams({ return_to: safeReturnPath(returnTo) })
  if (tenantId) params.set('tenant_id', tenantId)
  return `${apiBaseUrl()}/auth/workos/login?${params.toString()}`
}

export async function getWorkOSCapabilities(returnTo: string): Promise<WorkOSCapabilities> {
  const response = await api.get<WorkOSCapabilities>('/auth/workos/capabilities', {
    params: { return_to: safeReturnPath(returnTo) },
  })
  return response.data
}

export function startWorkOSLogin(returnTo: string, reauthPath?: string | null, tenantId?: string | null): void {
  syncStoredSession()
  const session = useAuthStore.getState()
  const target = reauthPath ? `${apiBaseUrl()}${reauthPath}` : buildWorkOSLoginUrl(returnTo, tenantId)
  if (session.explicitlySignedOut) {
    window.location.assign(beginSignedOutLogin(target, session.browserSessionId))
    return
  }
  // Do not send legacy Authorization credentials after AuthKit returns.
  session.clearSession()
  delete api.defaults.headers.common.Authorization
  window.location.assign(target)
}
