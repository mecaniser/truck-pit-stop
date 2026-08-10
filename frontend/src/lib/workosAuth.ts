import api from './api'
import { useAuthStore } from '../stores/authStore'

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

export function buildWorkOSLoginUrl(returnTo: string): string {
  return `${apiBaseUrl()}/auth/workos/login?return_to=${encodeURIComponent(safeReturnPath(returnTo))}`
}

export async function getWorkOSCapabilities(returnTo: string): Promise<WorkOSCapabilities> {
  const response = await api.get<WorkOSCapabilities>('/auth/workos/capabilities', {
    params: { return_to: safeReturnPath(returnTo) },
  })
  return response.data
}

export function startWorkOSLogin(returnTo: string, reauthPath?: string | null): void {
  // A legacy Authorization header takes precedence over the new HttpOnly
  // WorkOS cookie. Clear the browser projection before leaving for AuthKit.
  useAuthStore.getState().clearSession()
  delete api.defaults.headers.common.Authorization
  const target = reauthPath ? `${apiBaseUrl()}${reauthPath}` : buildWorkOSLoginUrl(returnTo)
  window.location.assign(target)
}
