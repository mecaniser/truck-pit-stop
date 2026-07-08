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
  role: 'super_admin' | 'garage_owner' | 'garage_admin' | 'mechanic' | 'receptionist' | 'fleet_manager' | 'customer'
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
  login: (token: string, refreshToken: string, user: User) => void
  logout: () => void
  setUser: (user: User) => void
  setTokens: (token: string, refreshToken: string) => void
}

function sanitizePersistedAuthState(state: Partial<AuthState>): Partial<AuthState> {
  if (!state.token) {
    return state
  }
  if (!isTokenExpired(state.token)) {
    return state
  }
  const hasValidRefreshToken = Boolean(
    state.refreshToken && !isTokenExpired(state.refreshToken)
  )
  if (hasValidRefreshToken) {
    // Access token is short-lived; keep a valid refresh token so the app can
    // recover session via /auth/refresh on the next protected API call.
    return {
      ...state,
      token: null,
      isAuthenticated: true,
    }
  }
  return {
    ...state,
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
      login: (token, refreshToken, user) =>
        set({
          token,
          refreshToken,
          user,
          isAuthenticated: true,
        }),
      logout: async () => {
        // Call backend to blacklist token and clear cookies
        try {
          if (get().isAuthenticated) {
            await api.post('/auth/logout')
          }
        } catch {
          // Ignore errors - we're logging out anyway
        }
        set({
          user: null,
          token: null,
          refreshToken: null,
          isAuthenticated: false,
        })
      },
      setUser: (user) => set({ user }),
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
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
