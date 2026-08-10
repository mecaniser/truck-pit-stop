import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock the api module before importing the store
vi.mock('../lib/api', () => ({
  default: {
    post: vi.fn().mockResolvedValue({}),
  },
}))

import { useAuthStore } from '../stores/authStore'
import api from '../lib/api'

const fakeUser = {
  id: 'u-1',
  email: 'test@example.com',
  first_name: 'Test',
  last_name: 'User',
  phone: null,
  role: 'customer' as const,
  is_active: true,
  tenant_id: null,
  customer_id: null,
}

describe('authStore', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      authProvider: null,
    })
    vi.mocked(api.post).mockClear()
  })

  it('starts unauthenticated', () => {
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
  })

  it('login sets user and tokens', () => {
    useAuthStore.getState().login('access-tok', 'refresh-tok', fakeUser)
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(true)
    expect(state.token).toBe('access-tok')
    expect(state.refreshToken).toBe('refresh-tok')
    expect(state.user?.email).toBe('test@example.com')
  })

  it('logout clears everything', async () => {
    useAuthStore.getState().login('access-tok', 'refresh-tok', fakeUser)
    await useAuthStore.getState().logout()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.user).toBeNull()
    expect(state.token).toBeNull()
    expect(api.post).toHaveBeenCalledWith('/auth/logout')
  })

  it('uses tenant-only WorkOS logout for cookie sessions', async () => {
    useAuthStore.getState().establishCookieSession(fakeUser)
    await useAuthStore.getState().logout()
    expect(api.post).toHaveBeenCalledWith('/auth/workos/logout')
    expect(useAuthStore.getState().authProvider).toBeNull()
  })

  it('setUser updates user only', () => {
    useAuthStore.getState().login('tok', 'ref', fakeUser)
    const updatedUser = { ...fakeUser, first_name: 'Updated' }
    useAuthStore.getState().setUser(updatedUser)
    expect(useAuthStore.getState().user?.first_name).toBe('Updated')
    expect(useAuthStore.getState().token).toBe('tok')
  })

  it('setTokens updates tokens only', () => {
    useAuthStore.getState().login('old-tok', 'old-ref', fakeUser)
    useAuthStore.getState().setTokens('new-tok', 'new-ref')
    expect(useAuthStore.getState().token).toBe('new-tok')
    expect(useAuthStore.getState().refreshToken).toBe('new-ref')
    expect(useAuthStore.getState().user?.email).toBe('test@example.com')
  })
})
