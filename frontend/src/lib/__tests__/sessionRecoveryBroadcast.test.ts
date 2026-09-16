import { afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../stores/authStore'
import { useSessionRecovery } from '../sessionRecovery'
import { startSessionKeepAlive, stopSessionKeepAlive, renewSessionNow } from '../sessionKeepAlive'

vi.mock('../authRefresh', () => ({ requestWorkOSSessionRefresh: vi.fn().mockRejectedValue({ response: { status: 503 } }), requestTokenRefresh: vi.fn() }))
afterEach(() => { stopSessionKeepAlive(); vi.unstubAllGlobals(); vi.useRealTimers() })
it('clears the recovery notice when a sibling renews the shared session', async () => {
  vi.useFakeTimers()
  const channels: FakeChannel[] = []
  class FakeChannel {
    onmessage: ((event: MessageEvent) => void) | null = null
    constructor() { channels.push(this) }
    postMessage() {}
  }
  vi.stubGlobal('BroadcastChannel', FakeChannel)
  useAuthStore.setState({ isAuthenticated: true, authProvider: 'workos', token: null, logoutInProgress: false })
  startSessionKeepAlive()
  await renewSessionNow()
  expect(useSessionRecovery.getState().recovering).toBe(true)
  channels[0].onmessage?.({ data: { type: 'renewed', at: Date.now() } } as MessageEvent)
  expect(useSessionRecovery.getState().recovering).toBe(false)
  expect(useAuthStore.getState().isAuthenticated).toBe(true)
})
