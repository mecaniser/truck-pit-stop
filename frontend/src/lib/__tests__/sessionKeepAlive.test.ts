import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const refreshMocks = vi.hoisted(() => ({
  requestTokenRefresh: vi.fn(),
  requestWorkOSSessionRefresh: vi.fn(),
}))

vi.mock('../authRefresh', () => ({
  requestTokenRefresh: refreshMocks.requestTokenRefresh,
  requestWorkOSSessionRefresh: refreshMocks.requestWorkOSSessionRefresh,
}))

import { useSessionRecovery, setSessionRecovering } from '../sessionRecovery'
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
    setSessionRecovering(false)
    Object.defineProperty(window, 'location', { value: { href: '', pathname: '/dashboard', search: '' }, writable: true })
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

    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(window.location.href).toContain('reason=session_ended')
    expect(logoutSpy).not.toHaveBeenCalled()
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
  it('survives the 9m45s renewal outage, remains signed in past 10m, and recovers', async () => {
    setWorkOSSession()
    refreshMocks.requestWorkOSSessionRefresh.mockRejectedValue({ response: { status: 503 } })
    startSessionKeepAlive()
    await vi.advanceTimersByTimeAsync(585_000)
    expect(refreshMocks.requestWorkOSSessionRefresh).toHaveBeenCalledTimes(1)
    expect(useSessionRecovery.getState().recovering).toBe(true)
    await vi.advanceTimersByTimeAsync(75_000)
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(window.location.href).toBe('')
    refreshMocks.requestWorkOSSessionRefresh.mockResolvedValue(undefined)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(useSessionRecovery.getState().recovering).toBe(false)
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
  })

  it('ignores an old rejection after another user signs in', async () => {
    setWorkOSSession()
    let reject!: (reason: unknown) => void
    refreshMocks.requestWorkOSSessionRefresh.mockImplementation(() => new Promise((_, r) => { reject = r }))
    startSessionKeepAlive()
    const pending = renewSessionNow()
    useAuthStore.getState().establishCookieSession({ id: 'u2', role: 'driver', tenant_id: 't2', is_active: true } as never)
    reject({ response: { status: 401 } })
    await pending
    expect(useAuthStore.getState().user?.id).toBe('u2')
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(window.location.href).toBe('')
  })

  it('routes confirmed expiration to the driver login with truthful reason', async () => {
    setWorkOSSession()
    useAuthStore.setState({ user: { id: 'u1', role: 'driver', tenant_id: 't1', is_active: true } as never })
    refreshMocks.requestWorkOSSessionRefresh.mockRejectedValue({ response: { status: 401, data: { detail: { code: 'session_expired' } } } })
    startSessionKeepAlive()
    await vi.advanceTimersByTimeAsync(585_000)
    expect(window.location.href).toBe('/driver/login?reason=session_expired&tenant_id=t1')
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

})
