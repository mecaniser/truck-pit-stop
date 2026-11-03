import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import api from '../lib/api'
import { setSessionRecovering } from '../lib/sessionRecovery'
import { isTokenExpired } from '../lib/authTokens'
import { startSessionKeepAlive, stopSessionKeepAlive } from '../lib/sessionKeepAlive'
import type { PresentationBootstrap } from '../types/presentation'

interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string | null
  role: 'super_admin' | 'garage_owner' | 'garage_admin' | 'mechanic' | 'receptionist' | 'fleet_manager' | 'driver' | 'customer'
  is_active: boolean
  can_access_messaging?: boolean
  permissions?: Record<string, boolean>
  // Shop-wide switch for the Messages feature; defaults on when absent.
  messaging_enabled?: boolean
  tenant_id: string | null
  tenant_name?: string | null
  tenant_slug?: string | null
  tenant_logo_url?: string | null
  customer_id: string | null
  presentation?: PresentationBootstrap
}

interface AuthState {
  user: User | null
  token: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  authProvider: 'legacy' | 'workos' | null
  authSessionEpoch: number
  browserSessionId: string | null
  explicitlySignedOut: boolean
  logoutInProgress: boolean
  webSocketRecoverySessionKey: string | null
  login: (token: string, refreshToken: string, user: User) => void
  establishCookieSession: (user: User) => void
  logout: () => Promise<void>
  clearSession: () => void
  setUser: (user: User, expectedEpoch?: number) => void
  setTokens: (token: string, refreshToken: string) => void
  claimWebSocketAuthRecovery: () => boolean
}

export function getAuthenticatedSessionIdentity(
  state: Pick<
    AuthState,
    'isAuthenticated' | 'logoutInProgress' | 'authSessionEpoch' | 'authProvider' | 'user'
  >
): string | null {
  if (
    !state.isAuthenticated
    || state.logoutInProgress
    || !state.user
    || !state.user.is_active
  ) return null
  return JSON.stringify([
    state.authSessionEpoch,
    state.authProvider,
    state.user.id,
    state.user.tenant_id,
    state.user.role,
    state.user.customer_id,
  ])
}

const signedOutSession = { user: null, token: null, refreshToken: null, authProvider: null, isAuthenticated: false }
const storageKey = 'auth-storage'

// Store only a comparison key in memory. Credentials can rotate without changing
// the session. Older persisted sessions have no browserSessionId, so also compare
// the principal and access fields.
function boundaryKey(state?: Partial<AuthState>) {
  return JSON.stringify([state?.browserSessionId, state?.explicitlySignedOut === true, state?.isAuthenticated,
    state?.authProvider, state?.user?.id, state?.user?.tenant_id, state?.user?.role, state?.user?.customer_id,
    state?.user?.is_active, state?.user?.permissions?.payments])
}
let observedBoundary = boundaryKey()

function sanitizePersistedAuthState(state: Partial<AuthState>): Partial<AuthState> {
  const sanitized = {
    ...state,
    explicitlySignedOut: state.explicitlySignedOut === true,
    browserSessionId: state.browserSessionId ?? null,
    // These fields coordinate live resources and must never resume from disk.
    authSessionEpoch: 0,
    logoutInProgress: false,
    webSocketRecoverySessionKey: null,
  }
  if (state.logoutInProgress || state.explicitlySignedOut) {
    return { ...sanitized, ...signedOutSession, explicitlySignedOut: true }
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
      browserSessionId: null,
      explicitlySignedOut: false,
      logoutInProgress: false,
      webSocketRecoverySessionKey: null,
      login: (token, refreshToken, user) => {
        setSessionRecovering(false)
        set((state) => ({
          token,
          refreshToken,
          user,
          isAuthenticated: true,
          explicitlySignedOut: false,
          authProvider: 'legacy',
          browserSessionId: crypto.randomUUID(),
          authSessionEpoch: state.authSessionEpoch + 1,
          logoutInProgress: false,
          webSocketRecoverySessionKey: null,
        }))
        // Keep the short-lived access token renewed ahead of expiry so an
        // all-day session never rides a stale credential into a forced logout.
        startSessionKeepAlive()
      },
      establishCookieSession: (user) => {
        setSessionRecovering(false)
        set((state) => ({
          user,
          token: null,
          refreshToken: null,
          isAuthenticated: true,
          explicitlySignedOut: false,
          authProvider: 'workos',
          // Cookie bootstrap also runs on reload. Keep the same browser session
          // unless this establishes a different actor or follows explicit logout.
          browserSessionId: !state.explicitlySignedOut && (!state.user || state.user.id === user.id && state.user.tenant_id === user.tenant_id)
            ? state.browserSessionId ?? crypto.randomUUID() : crypto.randomUUID(),
          authSessionEpoch: state.authSessionEpoch + 1,
          logoutInProgress: false,
          webSocketRecoverySessionKey: null,
        }))
        startSessionKeepAlive()
      },
      logout: async () => {
        if (syncStoredSession()) return
        const session = get()
        if (session.logoutInProgress) return

        const logoutEpoch = session.authSessionEpoch + 1
        const endpoint = session.isAuthenticated
          ? (session.authProvider === 'workos' ? '/auth/workos/logout' : '/auth/logout')
          : null

        // Publish logout intent before waiting on the network so live resources
        // cannot remain attached to the session during a slow provider logout.
        setSessionRecovering(false)
        stopSessionKeepAlive()
        set({ authSessionEpoch: logoutEpoch, browserSessionId: crypto.randomUUID(), logoutInProgress: true, explicitlySignedOut: true })

        // Call backend to blacklist token and clear cookies
        try {
          if (endpoint) {
            await api.post(endpoint)
          }
        } catch {
          // Ignore errors - we're logging out anyway
        }

        // An intervening login, including one in another tab, owns the new session.
        syncStoredSession()
        if (get().authSessionEpoch !== logoutEpoch || !get().logoutInProgress) return
        set({ ...signedOutSession, logoutInProgress: false, webSocketRecoverySessionKey: null })
      },
      clearSession: () => {
        if (syncStoredSession()) return
        setSessionRecovering(false)
        stopSessionKeepAlive()
        set((state) => ({
          ...signedOutSession,
          browserSessionId: crypto.randomUUID(),
          authSessionEpoch: state.authSessionEpoch + 1,
          logoutInProgress: false,
          webSocketRecoverySessionKey: null,
        }))
      },
      setUser: (user, expectedEpoch) => {
        if (syncStoredSession()) return
        const current = get()
        if (!current.isAuthenticated || current.logoutInProgress || !current.user) return
        // Async profile saves belong to their original session. Explicit identity
        // transitions still replace the principal and reopen the socket.
        if (expectedEpoch !== undefined && (expectedEpoch !== current.authSessionEpoch ||
            current.user.id !== user.id || current.user.tenant_id !== user.tenant_id)) return
        const changed = current.user.id !== user.id || current.user.tenant_id !== user.tenant_id ||
          current.user.role !== user.role || current.user.customer_id !== user.customer_id ||
          current.user.is_active !== user.is_active
        set({
          user,
          authSessionEpoch: current.authSessionEpoch + (changed ? 1 : 0),
          webSocketRecoverySessionKey: changed ? null : current.webSocketRecoverySessionKey,
        })
      },
      setTokens: (token, refreshToken) => {
        if (!syncStoredSession() && getAuthenticatedSessionIdentity(get())) set({ token, refreshToken })
      },
      claimWebSocketAuthRecovery: () => {
        if (syncStoredSession()) return false
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
      name: storageKey,
      // The initiating tab keeps its credential only in memory to revoke it.
      // Peers and reloads see a signed-out projection before the HTTP response.
      partialize: state => {
        const projection = state.logoutInProgress ? { ...state, ...signedOutSession, logoutInProgress: false } : state
        observedBoundary = boundaryKey(projection)
        return projection
      },
      storage: createJSONStorage(() => localStorage),
      merge: (persistedState, currentState) => {
        const saved = persistedState as Partial<AuthState> | undefined
        observedBoundary = boundaryKey(saved)
        const sanitized = sanitizePersistedAuthState(saved ?? { ...signedOutSession, explicitlySignedOut: false, browserSessionId: null })
        return {
          ...currentState,
          ...sanitized,
          authSessionEpoch: currentState.authSessionEpoch + 1,
        }
      },
      onRehydrateStorage: () => (state) => {
        // A legacy session resumed straight from localStorage never calls
        // login(); start the keep-alive here so a reloaded all-day tab still
        // renews its access token ahead of expiry. The WorkOS path rehydrates
        // as unauthenticated and starts the scheduler from establishCookieSession.
        if (state?.isAuthenticated && state.authProvider === 'legacy') {
          startSessionKeepAlive()
        }
      },
    }
  )
)

/** React only to session boundaries. Ordinary token rotations and writes by the
 * same user must not reset the workspace. Read current storage so queued events
 * cannot restore an older identity or overwrite a subsequent login. */
export function syncStoredSession() {
  let saved: Partial<AuthState> | undefined
  try {
    saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null')?.state
  } catch { return false }
  if (boundaryKey(saved) === observedBoundary) return false
  stopSessionKeepAlive()
  setSessionRecovering(false)
  void useAuthStore.persist.rehydrate()
  return true
}

export function watchSessionBoundary() {
  window.addEventListener('storage', event => {
    if (event.storageArea === localStorage && (event.key === storageKey || event.key === null)) syncStoredSession()
  })
  window.addEventListener('pageshow', syncStoredSession)
}
