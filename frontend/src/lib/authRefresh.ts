import axios from 'axios'

export interface RefreshTokenResponse {
  access_token: string
  refresh_token: string
}

function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_URL || '/api/v1'
}

export async function requestTokenRefresh(refreshToken: string | null): Promise<RefreshTokenResponse> {
  if (!refreshToken) {
    throw new Error('Refresh token missing')
  }

  const response = await axios.post<RefreshTokenResponse>(
    `${getApiBaseUrl()}/auth/refresh`,
    { refresh_token: refreshToken },
    { withCredentials: true }
  )

  if (!response.data?.access_token || !response.data?.refresh_token) {
    throw new Error('Invalid refresh token response')
  }

  return response.data
}

export async function requestWorkOSSessionRefresh(): Promise<void> {
  await axios.post(
    `${getApiBaseUrl()}/auth/workos/session/refresh`,
    {},
    { withCredentials: true }
  )
}
