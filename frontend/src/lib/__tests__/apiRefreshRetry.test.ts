import axios from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const refreshMocks = vi.hoisted(() => ({
  requestTokenRefresh: vi.fn(),
  requestWorkOSSessionRefresh: vi.fn(),
}))

vi.mock('../authRefresh', () => ({
  requestTokenRefresh: refreshMocks.requestTokenRefresh,
  requestWorkOSSessionRefresh: refreshMocks.requestWorkOSSessionRefresh,
}))

vi.mock('../sessionKeepAlive', () => ({
  stopSessionKeepAlive: vi.fn(),
  startSessionKeepAlive: vi.fn(),
}))

import api from '../api'
import { useSessionRecovery, setSessionRecovering } from '../sessionRecovery'
import { useAuthStore } from '../../stores/authStore'

function unauthorizedOnce() {
  let served = false
  return async (config: import('axios').InternalAxiosRequestConfig) => {
    if (!served) {
      served = true
      const error = new axios.AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config)
      error.response = { status: 401, data: {}, statusText: '', headers: {}, config }
      throw error
    }
    return { status: 200, data: { ok: true }, statusText: 'OK', headers: {}, config }
  }
}

describe('api 401 refresh retry', () => {
  beforeEach(() => {
    setSessionRecovering(false)
    Object.defineProperty(window, 'location', { value: { href: '', pathname: '/dashboard', search: '' }, writable: true })
    refreshMocks.requestTokenRefresh.mockReset()
    refreshMocks.requestWorkOSSessionRefresh.mockReset()
    useAuthStore.setState({
      isAuthenticated: true,
      logoutInProgress: false,
      authProvider: 'legacy',
      token: 'stale',
      refreshToken: 'r1',
      user: { id: 'u1', role: 'garage_owner', tenant_id: 't1', is_active: true } as never,
    })
  })

  afterEach(() => {
    useAuthStore.setState({ isAuthenticated: false, authProvider: null, token: null, refreshToken: null, user: null })
  })

  it('retries a transiently failing refresh, then replays the original request', async () => {
    // First refresh attempt fails with a network error (no response), second succeeds.
    refreshMocks.requestTokenRefresh
      .mockRejectedValueOnce(new Error('network blip'))
      .mockResolvedValueOnce({ access_token: 'fresh', refresh_token: 'r2' })

    const res = await api.get('/repair-orders', { adapter: unauthorizedOnce() })

    expect(res.data).toEqual({ ok: true })
    expect(refreshMocks.requestTokenRefresh).toHaveBeenCalledTimes(2)
    expect(useAuthStore.getState().token).toBe('fresh')
  })

  it('does not retry when the refresh endpoint itself answers 401', async () => {
    refreshMocks.requestTokenRefresh.mockRejectedValue({ response: { status: 401 } })
    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout').mockResolvedValue()
    // jsdom has no navigation; guard the redirect assignment.
    Object.defineProperty(window, 'location', { value: { href: '', pathname: '/dashboard', search: '' }, writable: true })

    await expect(api.get('/repair-orders', { adapter: unauthorizedOnce() })).rejects.toBeTruthy()

    expect(refreshMocks.requestTokenRefresh).toHaveBeenCalledTimes(1)
    expect(logoutSpy).not.toHaveBeenCalled()
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(window.location.href).toContain('reason=session_ended')
    logoutSpy.mockRestore()
  })
  it.each(['legacy', 'workos'] as const)('preserves %s auth after all temporary retries fail', async (provider) => {
    vi.useFakeTimers()
    useAuthStore.setState({ authProvider: provider })
    const refresh = provider === 'workos' ? refreshMocks.requestWorkOSSessionRefresh : refreshMocks.requestTokenRefresh
    refresh.mockRejectedValue({ response: { status: 503 } })
    const request = expect(api.get('/repair-orders', { adapter: unauthorizedOnce() })).rejects.toBeTruthy()
    await vi.runAllTimersAsync()
    await request
    expect(refresh).toHaveBeenCalledTimes(4)
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(useSessionRecovery.getState().recovering).toBe(true)
    expect(window.location.href).toBe('')
    vi.useRealTimers()
  })

  it('does not replay or replace tokens after the session changes during renewal', async () => {
    let resolve!: (value: unknown) => void
    refreshMocks.requestTokenRefresh.mockImplementation(() => new Promise(r => { resolve = r }))
    const adapter = vi.fn(unauthorizedOnce())
    const pending = expect(api.get('/repair-orders', { adapter })).rejects.toBeTruthy()
    await vi.waitFor(() => expect(refreshMocks.requestTokenRefresh).toHaveBeenCalledTimes(1))
    useAuthStore.getState().login('new-user-token', 'new-user-refresh', { id: 'u2', role: 'garage_owner', tenant_id: 't2', is_active: true } as never)
    resolve({ access_token: 'old-result', refresh_token: 'old-refresh' })
    await pending
    expect(adapter).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().token).toBe('new-user-token')
    expect(window.location.href).toBe('')
  })

})
