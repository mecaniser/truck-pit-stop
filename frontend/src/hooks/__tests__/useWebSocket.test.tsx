import type { PropsWithChildren } from 'react'
import { act, cleanup, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const refreshMocks = vi.hoisted(() => ({
  legacy: vi.fn(),
  workos: vi.fn(),
}))

vi.mock('../../lib/authRefresh', () => ({
  requestTokenRefresh: refreshMocks.legacy,
  requestWorkOSSessionRefresh: refreshMocks.workos,
}))

import { useWebSocket } from '../useWebSocket'
import { useAuthStore } from '../../stores/authStore'

class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: MockWebSocket[] = []

  readonly url: string
  readonly protocols: string | string[] | undefined
  readyState = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
  })

  constructor(url: string | URL, protocols?: string | string[]) {
    this.url = String(url)
    this.protocols = protocols
    MockWebSocket.instances.push(this)
  }

  emitOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  emitMessage(data: string) {
    this.onmessage?.({ data } as MessageEvent)
  }

  emitClose(code: number, reason = '') {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code, reason, wasClean: code === 1000 } as CloseEvent)
  }

  emitError(event: Event) {
    this.onerror?.(event)
  }
}

function latestSocket(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]
}

const user = {
  id: 'user-1',
  email: 'owner@example.test',
  first_name: 'Shop',
  last_name: 'Owner',
  phone: null,
  role: 'garage_owner' as const,
  is_active: true,
  tenant_id: 'tenant-1',
  customer_id: null,
}

function authenticateWithWorkOS() {
  useAuthStore.setState({
    user,
    token: null,
    refreshToken: null,
    isAuthenticated: true,
    authProvider: 'workos',
  })
}

function authenticateWithLegacyTokens() {
  useAuthStore.setState({
    user,
    token: 'legacy-access-secret',
    refreshToken: 'legacy-refresh-secret',
    isAuthenticated: true,
    authProvider: 'legacy',
  })
}

function renderWebSocket(options: Parameters<typeof useWebSocket>[0] = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return renderHook(() => useWebSocket(options), { wrapper })
}

describe('useWebSocket cookie-session transport', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubEnv('VITE_API_URL', 'https://api.example.test/api/v1/')
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    MockWebSocket.instances = []
    refreshMocks.legacy.mockReset()
    refreshMocks.workos.mockReset()
    refreshMocks.workos.mockResolvedValue(undefined)
    refreshMocks.legacy.mockResolvedValue({
      access_token: 'rotated-access-secret',
      refresh_token: 'rotated-refresh-secret',
    })
    localStorage.clear()
    useAuthStore.setState({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      authProvider: null,
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('connects a token-null WorkOS session to the queryless endpoint without a subprotocol', () => {
    authenticateWithWorkOS()

    renderWebSocket()

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toBe('wss://api.example.test/api/v1/ws')
    expect(new URL(MockWebSocket.instances[0].url).search).toBe('')
    expect(MockWebSocket.instances[0].protocols).toBeUndefined()
    expect(refreshMocks.workos).not.toHaveBeenCalled()
    expect(useAuthStore.getState()).toMatchObject({ token: null, refreshToken: null })
  })

  it('never logs a credential-bearing WebSocket URL or raw ErrorEvent', () => {
    authenticateWithLegacyTokens()
    const consoleLog = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    renderWebSocket({ debug: true })

    const socket = MockWebSocket.instances[0]
    socket.emitError({
      type: 'error',
      message: 'legacy-access-secret',
      filename: 'wss://api.example.test/api/v1/ws?token=legacy-access-secret',
    } as unknown as Event)

    const logged = JSON.stringify(consoleLog.mock.calls)
    expect(socket.url).not.toContain('legacy-access-secret')
    expect(socket.url).not.toContain('legacy-refresh-secret')
    expect(logged).not.toContain('legacy-access-secret')
    expect(logged).not.toContain('legacy-refresh-secret')
    expect(logged).not.toContain('?token=')
    expect(logged).toContain('Connection error')
  })

  it('uses one WorkOS HTTPS refresh and one reconnect for close 4001', async () => {
    authenticateWithWorkOS()
    renderWebSocket()

    await act(async () => {
      MockWebSocket.instances[0].emitClose(4001)
      await Promise.resolve()
    })

    expect(refreshMocks.workos).toHaveBeenCalledTimes(1)
    expect(refreshMocks.legacy).not.toHaveBeenCalled()
    expect(MockWebSocket.instances).toHaveLength(2)

    act(() => MockWebSocket.instances[1].emitClose(4001))
    await act(async () => Promise.resolve())
    expect(refreshMocks.workos).toHaveBeenCalledTimes(1)
    expect(MockWebSocket.instances).toHaveLength(2)
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

  it('uses one legacy refresh, rotates legacy tokens, and reconnects without exposing them', async () => {
    authenticateWithLegacyTokens()
    renderWebSocket()

    await act(async () => {
      MockWebSocket.instances[0].emitClose(4001)
      await Promise.resolve()
    })

    expect(refreshMocks.legacy).toHaveBeenCalledTimes(1)
    expect(refreshMocks.legacy).toHaveBeenCalledWith('legacy-refresh-secret')
    expect(refreshMocks.workos).not.toHaveBeenCalled()
    expect(useAuthStore.getState()).toMatchObject({
      token: 'rotated-access-secret',
      refreshToken: 'rotated-refresh-secret',
    })
    expect(MockWebSocket.instances).toHaveLength(2)
    expect(MockWebSocket.instances[1].url).toBe('wss://api.example.test/api/v1/ws')
  })

  it('stops and clears a stale session when the single auth refresh fails', async () => {
    authenticateWithWorkOS()
    refreshMocks.workos.mockRejectedValueOnce(new Error('refresh failed with secret'))
    const consoleLog = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    renderWebSocket({ debug: true })

    await act(async () => {
      MockWebSocket.instances[0].emitClose(4001)
      await Promise.resolve()
    })
    await act(async () => Promise.resolve())
    vi.advanceTimersByTime(60000)

    expect(refreshMocks.workos).toHaveBeenCalledTimes(1)
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
    expect(JSON.stringify(consoleLog.mock.calls)).not.toContain('refresh failed with secret')
  })

  it('does not reconnect when the hook unmounts during auth recovery', async () => {
    let resolveRefresh: (() => void) | undefined
    refreshMocks.workos.mockImplementationOnce(() => new Promise<void>((resolve) => {
      resolveRefresh = resolve
    }))
    authenticateWithWorkOS()
    const hook = renderWebSocket()

    act(() => MockWebSocket.instances[0].emitClose(4001))
    hook.unmount()
    await act(async () => {
      resolveRefresh?.()
      await Promise.resolve()
    })

    expect(refreshMocks.workos).toHaveBeenCalledTimes(1)
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it.each([1000, 1008, 1009, 4002, 4003, 4008])(
    'treats close %s as terminal, including after visibility changes',
    (code) => {
      authenticateWithWorkOS()
      renderWebSocket()

      act(() => MockWebSocket.instances[0].emitClose(code))
      act(() => {
        document.dispatchEvent(new Event('visibilitychange'))
        document.dispatchEvent(new Event('visibilitychange'))
        vi.advanceTimersByTime(60000)
      })

      expect(MockWebSocket.instances).toHaveLength(1)
      expect(refreshMocks.workos).not.toHaveBeenCalled()
    }
  )

  it('backs off transient and rate-limit closes exponentially, caps at 30s, and resets on open', () => {
    authenticateWithWorkOS()
    renderWebSocket()

    const delays = [1000, 2000, 4000, 8000, 16000, 30000, 30000]
    for (const delay of delays) {
      const before = MockWebSocket.instances.length
      act(() => latestSocket().emitClose(4029))
      act(() => vi.advanceTimersByTime(delay - 1))
      expect(MockWebSocket.instances).toHaveLength(before)
      act(() => vi.advanceTimersByTime(1))
      expect(MockWebSocket.instances).toHaveLength(before + 1)
    }

    act(() => latestSocket().emitOpen())
    const beforeResetRetry = MockWebSocket.instances.length
    act(() => latestSocket().emitClose(1011))
    act(() => vi.advanceTimersByTime(999))
    expect(MockWebSocket.instances).toHaveLength(beforeResetRetry)
    act(() => vi.advanceTimersByTime(1))
    expect(MockWebSocket.instances).toHaveLength(beforeResetRetry + 1)
  })

  it('slow-starts an ambiguous pre-open 1006 instead of creating an origin-failure storm', () => {
    authenticateWithWorkOS()
    renderWebSocket()

    act(() => MockWebSocket.instances[0].emitClose(1006))
    act(() => vi.advanceTimersByTime(4999))
    expect(MockWebSocket.instances).toHaveLength(1)
    act(() => vi.advanceTimersByTime(1))
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('cancels pending reconnect and ping work on unmount or logout', () => {
    authenticateWithWorkOS()
    const firstHook = renderWebSocket()
    act(() => MockWebSocket.instances[0].emitClose(1011))
    firstHook.unmount()
    act(() => vi.advanceTimersByTime(60000))
    expect(MockWebSocket.instances).toHaveLength(1)

    authenticateWithWorkOS()
    renderWebSocket()
    const secondSocket = latestSocket()
    act(() => secondSocket.emitOpen())
    act(() => useAuthStore.getState().clearSession())
    act(() => vi.advanceTimersByTime(60000))
    expect(secondSocket.send).not.toHaveBeenCalled()
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('coalesces repeated visible-tab recovery with an already scheduled reconnect', () => {
    authenticateWithWorkOS()
    renderWebSocket()

    act(() => MockWebSocket.instances[0].emitClose(1011))
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
      document.dispatchEvent(new Event('visibilitychange'))
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(MockWebSocket.instances).toHaveLength(2)
    act(() => vi.advanceTimersByTime(30000))
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('keeps one intentional reconnect and ignores the replaced socket close', () => {
    authenticateWithWorkOS()
    const { result } = renderWebSocket()
    const original = MockWebSocket.instances[0]
    const timersBeforeOpen = vi.getTimerCount()
    act(() => original.emitOpen())
    expect(vi.getTimerCount()).toBe(timersBeforeOpen + 1)

    act(() => result.current.reconnect())
    expect(original.close).toHaveBeenCalledTimes(1)
    expect(MockWebSocket.instances).toHaveLength(2)
    expect(vi.getTimerCount()).toBe(timersBeforeOpen)

    act(() => original.emitClose(1011))
    act(() => vi.advanceTimersByTime(60000))
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('preserves ping and notification behavior on an open cookie-authenticated socket', () => {
    authenticateWithWorkOS()
    const onNotification = vi.fn()
    renderWebSocket({ onNotification })
    const socket = MockWebSocket.instances[0]

    act(() => socket.emitOpen())
    act(() => vi.advanceTimersByTime(30000))
    expect(socket.send).toHaveBeenCalledWith('ping')

    act(() => socket.emitMessage(JSON.stringify({
      type: 'quote_approved',
      order_id: 'order-1',
      quote_number: 'Q-100',
    })))
    expect(onNotification).toHaveBeenCalledWith({
      type: 'quote_approved',
      orderId: 'order-1',
      quoteNumber: 'Q-100',
    })
  })
})
