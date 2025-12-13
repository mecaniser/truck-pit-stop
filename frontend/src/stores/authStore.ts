import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import api from '../lib/api'

interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  phone: string | null
  role: 'super_admin' | 'garage_admin' | 'mechanic' | 'receptionist' | 'customer'
  is_active: boolean
  tenant_id: string | null
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
    }),
    {
      name: 'auth-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

