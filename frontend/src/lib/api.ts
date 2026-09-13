import axios from 'axios'
import { useAuthStore } from '../stores/authStore'
import { requestTokenRefresh, requestWorkOSSessionRefresh } from './authRefresh'
import { endRejectedSession, isSessionRejection, setSessionRecovering } from './sessionRecovery'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Send cookies with every request
  timeout: 30000, // 30 second timeout
})

// Request interceptor to add auth token (fallback for non-cookie scenarios)
api.interceptors.request.use(
  (config) => {
    const state = useAuthStore.getState()
    ;(config as typeof config & { authSessionEpoch?: number }).authSessionEpoch = state.authSessionEpoch
    const token = state.token
    const hasAuthHeader = Boolean(config.headers?.Authorization || config.headers?.authorization)
    // Only add Authorization header if we have a token and cookies might not be set yet
    if (token && !hasAuthHeader) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor to handle auth errors with token refresh
let isRefreshing = false
let refreshingEpoch: number | null = null
let failedQueue: Array<{
  resolve: (token: string | null) => void
  reject: (error: unknown) => void
}> = []

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error)
    } else {
      prom.resolve(token)
    }
  })
  failedQueue = []
}

// A single failed renewal used to force a logout. In an all-day workspace a
// transient failure (network blip, provider 5xx, rate limit, a cross-tab
// rotation race) must not eject the user — retry a few times first, and only
// log out when the refresh endpoint itself says the session is gone.
const REFRESH_RETRY_BACKOFF_MS = [250, 1000, 3000]

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function refreshErrorStatus(error: unknown): number | undefined {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    return (error as { response?: { status?: number } }).response?.status
  }
  return undefined
}

async function runRefreshWithRetry(
  attempt: () => Promise<{ accessToken: string | null }>
): Promise<{ accessToken: string | null }> {
  let lastError: unknown
  for (let i = 0; i <= REFRESH_RETRY_BACKOFF_MS.length; i += 1) {
    try {
      return await attempt()
    } catch (error) {
      lastError = error
      if (axios.isCancel(error)) throw error
      const status = refreshErrorStatus(error)
      // A definitive "session is gone" answer is not retryable.
      if (status === 401 || status === 403) {
        throw error
      }
      if (i < REFRESH_RETRY_BACKOFF_MS.length) {
        await sleep(REFRESH_RETRY_BACKOFF_MS[i])
      }
    }
  }
  throw lastError
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    // React Query uses AbortSignal to cancel stale navigation requests. An
    // aborted request must not enter the 401 refresh/logout flow: it is not an
    // authentication failure and retrying it would recreate the request we
    // intentionally stopped.
    if (axios.isCancel(error)) {
      return Promise.reject(error)
    }

    const originalRequest = error.config
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/')
    const isWorkOSSessionEndpoint = originalRequest?.url?.includes('/auth/workos/session/refresh')
    const session = useAuthStore.getState()
    const authProvider = session.authProvider
    const sessionEpoch = session.authSessionEpoch
    const isCurrentSession = () => useAuthStore.getState().authSessionEpoch === sessionEpoch
      && !useAuthStore.getState().logoutInProgress
    if (originalRequest?.authSessionEpoch !== undefined && originalRequest.authSessionEpoch !== sessionEpoch) {
      return Promise.reject(error)
    }
    const mayRefresh = authProvider === 'workos' ? !isWorkOSSessionEndpoint : !isAuthEndpoint

    if (error.response?.status === 401 && mayRefresh && !session.logoutInProgress && !originalRequest._retry) {
      if (isRefreshing) {
        if (refreshingEpoch !== sessionEpoch) return Promise.reject(new axios.CanceledError('Session changed'))
        // Queue requests while refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          if (!isCurrentSession()) throw new axios.CanceledError('Session changed')
          // Mark as retried to prevent infinite refresh loops
          originalRequest._retry = true
          if (token) {
            originalRequest.headers.Authorization = `Bearer ${token}`
          }
          return api(originalRequest)
        })
      }

      originalRequest._retry = true
      isRefreshing = true
      refreshingEpoch = sessionEpoch

      try {
        const { accessToken } = await runRefreshWithRetry(async () => {
          if (!isCurrentSession()) throw new axios.CanceledError('Session changed')
          if (authProvider === 'workos') {
            await requestWorkOSSessionRefresh()
            return { accessToken: null }
          }
          const refreshToken = useAuthStore.getState().refreshToken
          const { access_token, refresh_token: newRefreshToken } = await requestTokenRefresh(refreshToken)
          if (!isCurrentSession()) throw new axios.CanceledError('Session changed')
          useAuthStore.getState().setTokens(access_token, newRefreshToken)
          return { accessToken: access_token }
        })

        if (!isCurrentSession()) throw new axios.CanceledError('Session changed')
        setSessionRecovering(false)
        if (accessToken) {
          originalRequest.headers.Authorization = `Bearer ${accessToken}`
        } else {
          delete originalRequest.headers?.Authorization
        }
        processQueue(null, accessToken)
        return api(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        if (isCurrentSession() && !axios.isCancel(refreshError)) {
          if (isSessionRejection(refreshError)) endRejectedSession(refreshError)
          else setSessionRecovering(true)
        }
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
        refreshingEpoch = null
      }
    }

    return Promise.reject(error)
  }
)

export default api
