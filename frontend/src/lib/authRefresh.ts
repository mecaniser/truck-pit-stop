import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

export interface RefreshTokenResponse {
  access_token: string
  refresh_token: string
}

function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_URL || '/api/v1'
}

async function refreshTokenRequest(
  refreshToken: string | null,
  signal?: AbortSignal
): Promise<RefreshTokenResponse> {
  if (!refreshToken) {
    throw new Error('Refresh token missing')
  }

  const response = await axios.post<RefreshTokenResponse>(
    `${getApiBaseUrl()}/auth/refresh`,
    { refresh_token: refreshToken },
    { withCredentials: true, signal, timeout: 15_000 }
  )

  if (!response.data?.access_token || !response.data?.refresh_token) {
    throw new Error('Invalid refresh token response')
  }

  return response.data
}

async function refreshWorkOSRequest(signal?: AbortSignal): Promise<void> {
  await axios.post(
    `${getApiBaseUrl()}/auth/workos/session/refresh`,
    {},
    { withCredentials: true, signal, timeout: 15_000 }
  )
}

// Timer and reactive recovery share one request per browser session.
// Explicit cancellation signals retain their own lifecycle.
let legacyFlight: { epoch: number; promise: Promise<RefreshTokenResponse> } | null = null
let workOSFlight: { epoch: number; promise: Promise<void> } | null = null

export function requestTokenRefresh(token: string | null, signal?: AbortSignal): Promise<RefreshTokenResponse> {
  if (signal) return refreshTokenRequest(token, signal)
  const epoch = useAuthStore.getState().authSessionEpoch
  if (legacyFlight?.epoch === epoch) return legacyFlight.promise
  const promise = refreshTokenRequest(token).finally(() => {
    if (legacyFlight?.promise === promise) legacyFlight = null
  })
  legacyFlight = { epoch, promise }
  return promise
}

export function requestWorkOSSessionRefresh(signal?: AbortSignal): Promise<void> {
  if (signal) return refreshWorkOSRequest(signal)
  const epoch = useAuthStore.getState().authSessionEpoch
  if (workOSFlight?.epoch === epoch) return workOSFlight.promise
  const promise = refreshWorkOSRequest().finally(() => {
    if (workOSFlight?.promise === promise) workOSFlight = null
  })
  workOSFlight = { epoch, promise }
  return promise
}
