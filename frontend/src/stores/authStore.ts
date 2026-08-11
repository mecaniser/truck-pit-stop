import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import api from '../lib/api'
import { isTokenExpired } from '../lib/authTokens'

interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string | null
  role: 'super_admin' | 'garage_owner' | 'garage_admin' | 'mechanic' | 'receptionist' | 'fleet_manager' | 'driver' | 'customer'
  is_active: boolean
  can_access_messaging?: boolean
  // Shop-wide switch for the Messages feature; defaults on when absent.
  messaging_enabled?: boolean
  tenant_id: string | null
  tenant_name?: string | null
  tenant_slug?: string | null
  tenant_logo_url?: string | null
  customer_id: string | null
}

interface AuthState {
  user: User | null
  token: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  authProvider: 'legacy' | 'workos' | null
  authSessionEpoch: number
  logoutInProgress: boolean
  webSocketRecoverySessionKey: string | null
  login: (token: string, refreshToken: string, user: User) => void
  establishCookieSession: (user: User) => void
  logout: () => Promise<void>
  clearSession: () => void
  setUser: (user: User) => void
  setTokens: (token: string, refreshToken: string) => void
  claimWebSocketAuthRecovery: () => boolean
}

export function getAuthenticatedSessionIdentity(
  state: Pick<
    AuthState,
    'isAuthenticated' | 'logoutInProgress' | 'authSessionEpoch' | 'authProvider' | 'user'
  >
): string | null {
  if (!state.isAuthenticated || state.logoutInProgress || !state.user) return null
  return JSON.stringify([
    state.authSessionEpoch,
    state.authProvider,
    state.user.id,
    state.user.tenant_id,
  ])
}

function sanitizePersistedAuthState(state: Partial<AuthState>): Partial<AuthState> {
  const sanitized = {
    ...state,
    // These fields coordinate live resources and must never resume from disk.
    authSessionEpoch: 0,
    logoutInProgress: false,
    webSocketRecoverySessionKey: null,
  }
  if (sanitized.authProvider === 'workos') {
    // The HttpOnly WorkOS session is revalidated by /auth/me on page load.
    // Never trust a persisted browser flag after the short provider session expires.
    return { ...sanitized, user: null, token: null, refreshToken: null, isAuthenticated: false }
  }
  if (!sanitized.token) {
    return sanitized
  }
  if (!isTokenExpired(sanitized.token)) {
    return sanitized
  }
  const hasValidRefreshToken = Boolean(
    sanitized.refreshToken && !isTokenExpired(sanitized.refreshToken)
  )
  if (hasValidRefreshToken) {
    // Access token is short-lived; keep a valid refresh token so the app can
    // recover session via /auth/refresh on the next protected API call.
    return {
      ...sanitized,
      token: null,
      isAuthenticated: true,
    }
  }
  return {
    ...sanitized,
    user: null,
    token: null,
    refreshToken: null,
    isAuthenticated: false,
  }
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      authProvider: null,
      authSessionEpoch: 0,
      logoutInProgress: false,
      webSocketRecoverySessionKey: null,
      login: (token, refreshToken, user) =>
        set((state) => ({
          token,
          refreshToken,
          user,
          isAuthenticated: true,
          authProvider: 'legacy',
          authSessionEpoch: state.authSessionEpoch + 1,
          logoutInProgress: false,
          webSocketRecoverySessionKey: null,
        })),
      establishCookieSession: (user) =>
        set((state) => ({
          user,
          token: null,
          refreshToken: null,
          isAuthenticated: true,
          authProvider: 'workos',
          authSessionEpoch: state.authSessionEpoch + 1,
          logoutInProgress: false,
          webSocketRecoverySessionKey: null,
        })),
      logout: async () => {
        const session = get()
        if (session.logoutInProgress) return

        const logoutEpoch = session.authSessionEpoch + 1
        const endpoint = session.isAuthenticated
          ? (session.authProvider === 'workos' ? '/auth/workos/logout' : '/auth/logout')
          : null

        // Publish logout intent before waiting on the network so live resources
        // cannot remain attached to the session during a slow provider logout.
        set({ authSessionEpoch: logoutEpoch, logoutInProgress: true })

        // Call backend to blacklist token and clear cookies
        try {
          if (endpoint) {
            await api.post(endpoint)
          }
        } catch {
          // Ignore errors - we're logging out anyway
        }

        set((current) => {
          // A new session may have started while the logout request was slow.
          if (current.authSessionEpoch !== logoutEpoch || !current.logoutInProgress) return {}
          return {
            user: null,
            token: null,
            refreshToken: null,
            isAuthenticated: false,
            authProvider: null,
            logoutInProgress: false,
            webSocketRecoverySessionKey: null,
          }
        })
      },
      clearSession: () => set((state) => ({
        user: null,
        token: null,
        refreshToken: null,
        isAuthenticated: false,
        authProvider: null,
        authSessionEpoch: state.authSessionEpoch + 1,
        logoutInProgress: false,
        webSocketRecoverySessionKey: null,
      })),
      setUser: (user) => set((state) => {
        const identityChanged = state.user?.id !== user.id
          || state.user?.tenant_id !== user.tenant_id
        return {
          user,
          authSessionEpoch: identityChanged
            ? state.authSessionEpoch + 1
            : state.authSessionEpoch,
          webSocketRecoverySessionKey: identityChanged
            ? null
            : state.webSocketRecoverySessionKey,
        }
      }),
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
      claimWebSocketAuthRecovery: () => {
        let claimed = false
        set((state) => {
          const sessionKey = getAuthenticatedSessionIdentity(state)
          if (
            !sessionKey
            || state.webSocketRecoverySessionKey === sessionKey
          ) return {}
          claimed = true
          return { webSocketRecoverySessionKey: sessionKey }
        })
        return claimed
      },
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
      merge: (persistedState, currentState) => {
        const sanitized = sanitizePersistedAuthState((persistedState as Partial<AuthState>) ?? {})
        return {
          ...currentState,
          ...sanitized,
        }
      },
    }
  )
)
