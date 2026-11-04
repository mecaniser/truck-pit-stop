import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import axios from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCookieSessionBootstrap } from '../useCookieSessionBootstrap'
import { useAuthStore } from '../../stores/authStore'

vi.mock('../sessionKeepAlive', () => ({ startSessionKeepAlive: vi.fn(), stopSessionKeepAlive: vi.fn() }))
const user = { id: 'u1', role: 'garage_owner', tenant_id: 't1', is_active: true }
const get = vi.fn()
const post = vi.fn()
beforeEach(() => {
  get.mockReset(); post.mockReset()
  useAuthStore.setState({ isAuthenticated: false, authProvider: 'workos', user: null, logoutInProgress: false, explicitlySignedOut: false, browserSessionId: null })
  vi.spyOn(axios, 'create').mockReturnValue({ get, post } as never)
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers() })

function unauthorized() {
  const error = new axios.AxiosError('Unauthorized')
  error.response = { status: 401 } as never
  return error
}

describe('cookie session bootstrap', () => {
  it('keeps protected content gated during an outage and retries successfully', async () => {
    vi.useFakeTimers()
    get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ data: user })
    const { result } = renderHook(() => useCookieSessionBootstrap())
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(result.current).toMatchObject({ checkingSession: true, recovering: true })
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    expect(result.current).toMatchObject({ checkingSession: false, recovering: false })
  })
  it('exposes a confirmed expiry for the login notice', async () => {
    get.mockRejectedValue(unauthorized())
    post.mockRejectedValue({ response: { status: 401, data: { detail: { code: 'session_expired' } } } })
    const { result } = renderHook(() => useCookieSessionBootstrap())
    await waitFor(() => expect(result.current.checkingSession).toBe(false))
    expect(result.current.endReason).toBe('session_expired')
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })
  it.each(['signed-out', 'replacement'] as const)('discards a late cookie response after a peer %s transition', async phase => {
    let finish!: (data: { data: typeof user }) => void
    get.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    renderHook(useCookieSessionBootstrap)
    // A previous client may not have written a browser session ID. Model a
    // suspended tab which has not yet received the storage event.
    const replacement = { ...user, id: 'owner-b', tenant_id: 'shop-b' }
    const token = `header.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 600 }))}.signature`
    const saved = phase === 'replacement'
      ? { isAuthenticated: true, authProvider: 'legacy', user: replacement, token }
      : { isAuthenticated: false, user: null, explicitlySignedOut: true }
    await act(async () => {
      localStorage.setItem('auth-storage', JSON.stringify({ version: 0, state: saved }))
      finish({ data: user })
    })
    if (phase === 'replacement') expect(useAuthStore.getState().user?.id).toBe('owner-b')
    else expect(useAuthStore.getState()).toMatchObject({ user: null, explicitlySignedOut: true })
    expect(post).not.toHaveBeenCalled()
  })
  it('does not restore a stale bootstrap response after a new login', async () => {
    let resolve!: (value: unknown) => void
    get.mockImplementation(() => new Promise(r => { resolve = r }))
    renderHook(() => useCookieSessionBootstrap())
    await act(async () => {
      useAuthStore.getState().establishCookieSession({ ...user, id: 'u2', tenant_id: 't2' } as never)
      resolve({ data: user })
    })
    expect(useAuthStore.getState().user?.id).toBe('u2')
  })
})
