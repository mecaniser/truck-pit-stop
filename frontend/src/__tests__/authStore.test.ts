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
      authSessionEpoch: 0,
      logoutInProgress: false,
      webSocketRecoverySessionKey: null,
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

  it('allows one WebSocket auth recovery per authenticated session epoch', () => {
    useAuthStore.getState().login('access-tok', 'refresh-tok', fakeUser)
    const firstEpoch = useAuthStore.getState().authSessionEpoch

    expect(useAuthStore.getState().claimWebSocketAuthRecovery()).toBe(true)
    expect(useAuthStore.getState().claimWebSocketAuthRecovery()).toBe(false)
    useAuthStore.getState().setTokens('rotated-access', 'rotated-refresh')
    expect(useAuthStore.getState().authSessionEpoch).toBe(firstEpoch)
    expect(useAuthStore.getState().claimWebSocketAuthRecovery()).toBe(false)

    useAuthStore.getState().login('new-access', 'new-refresh', fakeUser)
    expect(useAuthStore.getState().authSessionEpoch).toBe(firstEpoch + 1)
    expect(useAuthStore.getState().claimWebSocketAuthRecovery()).toBe(true)
  })

  it('publishes logout start and does not let a slow logout clear a newer session', async () => {
    let resolveLogout: (() => void) | undefined
    vi.mocked(api.post).mockImplementationOnce(() => new Promise((resolve) => {
      resolveLogout = () => resolve({})
    }))
    useAuthStore.getState().login('old-access', 'old-refresh', fakeUser)

    const logoutPromise = useAuthStore.getState().logout()
    expect(useAuthStore.getState().logoutInProgress).toBe(true)

    const replacementUser = { ...fakeUser, id: 'u-2', email: 'new@example.com' }
    useAuthStore.getState().establishCookieSession(replacementUser)
    resolveLogout?.()
    await logoutPromise

    expect(useAuthStore.getState()).toMatchObject({
      isAuthenticated: true,
      logoutInProgress: false,
      authProvider: 'workos',
      user: replacementUser,
    })
  })
})
