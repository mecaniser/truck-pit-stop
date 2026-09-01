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
    refreshMocks.requestTokenRefresh.mockReset()
    refreshMocks.requestWorkOSSessionRefresh.mockReset()
    useAuthStore.setState({
      isAuthenticated: true,
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
    expect(logoutSpy).toHaveBeenCalled()
    logoutSpy.mockRestore()
  })
})
