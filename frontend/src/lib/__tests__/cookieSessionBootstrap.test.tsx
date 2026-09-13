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
  useAuthStore.setState({ isAuthenticated: false, authProvider: 'workos', user: null, logoutInProgress: false })
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
