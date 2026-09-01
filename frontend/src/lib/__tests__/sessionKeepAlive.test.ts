import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const refreshMocks = vi.hoisted(() => ({
  requestTokenRefresh: vi.fn(),
  requestWorkOSSessionRefresh: vi.fn(),
}))

vi.mock('../authRefresh', () => ({
  requestTokenRefresh: refreshMocks.requestTokenRefresh,
  requestWorkOSSessionRefresh: refreshMocks.requestWorkOSSessionRefresh,
}))

import { useAuthStore } from '../../stores/authStore'
import {
  isSessionKeepAliveRunning,
  renewSessionNow,
  startSessionKeepAlive,
  stopSessionKeepAlive,
} from '../sessionKeepAlive'

function setWorkOSSession() {
  useAuthStore.setState({
    isAuthenticated: true,
    authProvider: 'workos',
    logoutInProgress: false,
    token: null,
    refreshToken: null,
    user: { id: 'u1', role: 'garage_owner', tenant_id: 't1', is_active: true } as never,
  })
}

describe('sessionKeepAlive', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    refreshMocks.requestTokenRefresh.mockReset()
    refreshMocks.requestWorkOSSessionRefresh.mockReset()
  })

  afterEach(() => {
    stopSessionKeepAlive()
    vi.useRealTimers()
    useAuthStore.setState({
      isAuthenticated: false,
      authProvider: null,
      token: null,
      refreshToken: null,
      user: null,
    })
  })

  it('starts and stops idempotently', () => {
    setWorkOSSession()
    startSessionKeepAlive()
    startSessionKeepAlive()
    expect(isSessionKeepAliveRunning()).toBe(true)
    stopSessionKeepAlive()
    expect(isSessionKeepAliveRunning()).toBe(false)
  })

  it('renews the WorkOS session proactively without a 401', async () => {
    setWorkOSSession()
    refreshMocks.requestWorkOSSessionRefresh.mockResolvedValue(undefined)
    startSessionKeepAlive()

    await renewSessionNow()

    expect(refreshMocks.requestWorkOSSessionRefresh).toHaveBeenCalledTimes(1)
  })

  it('is single-flight: overlapping renew calls collapse to one request', async () => {
    setWorkOSSession()
    let resolveRefresh: () => void = () => {}
    refreshMocks.requestWorkOSSessionRefresh.mockImplementation(
      () => new Promise<void>((resolve) => { resolveRefresh = resolve })
    )
    startSessionKeepAlive()

    const a = renewSessionNow()
    const b = renewSessionNow()
    resolveRefresh()
    await Promise.all([a, b])

    expect(refreshMocks.requestWorkOSSessionRefresh).toHaveBeenCalledTimes(1)
  })

  it('does not log out on a transient (network) failure - it retries', async () => {
    setWorkOSSession()
    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout').mockResolvedValue()
    refreshMocks.requestWorkOSSessionRefresh.mockRejectedValue(new Error('network down'))
    startSessionKeepAlive()

    await renewSessionNow()

    expect(logoutSpy).not.toHaveBeenCalled()
    logoutSpy.mockRestore()
  })

  it('logs out when the refresh endpoint returns 401 (session really gone)', async () => {
    setWorkOSSession()
    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout').mockResolvedValue()
    refreshMocks.requestWorkOSSessionRefresh.mockRejectedValue({ response: { status: 401 } })
    startSessionKeepAlive()

    await renewSessionNow()

    expect(logoutSpy).toHaveBeenCalledTimes(1)
    expect(isSessionKeepAliveRunning()).toBe(false)
    logoutSpy.mockRestore()
  })

  it('does nothing once the session is no longer authenticated', async () => {
    setWorkOSSession()
    startSessionKeepAlive()
    useAuthStore.setState({ isAuthenticated: false })

    await renewSessionNow()

    expect(refreshMocks.requestWorkOSSessionRefresh).not.toHaveBeenCalled()
  })
})
