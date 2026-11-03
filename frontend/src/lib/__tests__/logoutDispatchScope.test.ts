import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import api from '../api'
import { useAuthStore } from '../../stores/authStore'
import { garageOwnerSession } from '../../test-fixtures/db035/staffSession'

vi.mock('../sessionKeepAlive', () => ({ startSessionKeepAlive: vi.fn(), stopSessionKeepAlive: vi.fn() }))
const originalAdapter = api.defaults.adapter
const ownerA = { ...garageOwnerSession, id: 'synthetic-a', tenant_id: 'synthetic-shop-a' }
const ownerB = { ...garageOwnerSession, id: 'synthetic-b', tenant_id: 'synthetic-shop-b' }
const adapter = vi.fn(async (config: import('axios').InternalAxiosRequestConfig) =>
  ({ data: {}, status: 200, statusText: 'OK', headers: {}, config }))

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ user: null, token: null, refreshToken: null, authProvider: null,
    isAuthenticated: false, explicitlySignedOut: false, logoutInProgress: false,
    browserSessionId: null, authSessionEpoch: 0 })
  adapter.mockClear()
  api.defaults.adapter = adapter
})
afterEach(() => {
  api.defaults.adapter = originalAdapter
  useAuthStore.setState({ user: null, token: null, refreshToken: null, isAuthenticated: false })
  localStorage.clear()
})
function establish(provider: 'legacy' | 'workos', user: typeof ownerA) {
  const store = useAuthStore.getState()
  if (provider === 'workos') store.establishCookieSession(user)
  else store.login('synthetic-access', 'synthetic-refresh', user)
}

it.each(['legacy', 'workos'] as const)('cancels queued %s logout before it can dispatch under the next account', async provider => {
  establish(provider, ownerA)
  const logout = useAuthStore.getState().logout()
  establish(provider, ownerB)
  await logout
  expect(adapter).not.toHaveBeenCalled()
  expect(useAuthStore.getState().user).toEqual(ownerB)
  expect(useAuthStore.getState().isAuthenticated).toBe(true)
})

it('checks a peer replacement before dispatch even before its storage event is delivered', async () => {
  establish('workos', ownerA)
  const logout = useAuthStore.getState().logout()
  localStorage.setItem('auth-storage', JSON.stringify({ version: 0, state: {
    ...useAuthStore.getState(), user: ownerB, authProvider: 'workos', isAuthenticated: true,
    logoutInProgress: false, explicitlySignedOut: false, browserSessionId: 'synthetic-peer-B',
  } }))
  await logout
  expect(adapter).not.toHaveBeenCalled()
  expect(useAuthStore.getState().browserSessionId).toBe('synthetic-peer-B')
  expect(useAuthStore.getState().authProvider).toBe('workos')
  expect(useAuthStore.getState().user).toBeNull()
  expect(useAuthStore.getState().explicitlySignedOut).toBe(false)
})

it.each(['legacy', 'workos'] as const)('still dispatches and completes current-session %s logout', async provider => {
  establish(provider, ownerA)
  await useAuthStore.getState().logout()
  expect(adapter).toHaveBeenCalledTimes(1)
  expect(adapter.mock.calls[0][0].url).toBe(provider === 'workos' ? '/auth/workos/logout' : '/auth/logout')
  expect(useAuthStore.getState().isAuthenticated).toBe(false)
  expect(useAuthStore.getState().user).toBeNull()
})
