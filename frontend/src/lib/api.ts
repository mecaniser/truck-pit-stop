import axios from 'axios'
import { useAuthStore } from '../stores/authStore'
import { requestTokenRefresh, requestWorkOSSessionRefresh } from './authRefresh'

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
    const token = useAuthStore.getState().token
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
    const authProvider = useAuthStore.getState().authProvider
    const mayRefresh = authProvider === 'workos' ? !isWorkOSSessionEndpoint : !isAuthEndpoint

    if (error.response?.status === 401 && mayRefresh && !originalRequest._retry) {
      if (isRefreshing) {
        // Queue requests while refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
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

      try {
        if (authProvider === 'workos') {
          await requestWorkOSSessionRefresh()
          delete originalRequest.headers?.Authorization
          processQueue(null, null)
        } else {
          const refreshToken = useAuthStore.getState().refreshToken
          const { access_token, refresh_token: newRefreshToken } = await requestTokenRefresh(refreshToken)
          useAuthStore.getState().setTokens(access_token, newRefreshToken)
          originalRequest.headers.Authorization = `Bearer ${access_token}`
          processQueue(null, access_token)
        }
        return api(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        if (authProvider === 'workos') {
          useAuthStore.getState().clearSession()
        } else {
          void useAuthStore.getState().logout()
        }
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default api
