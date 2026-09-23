/** DB-076: the poll that turns a stale tab into a fresh one. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { resetStaleBuild, startStaleBuildWatch } from '../staleBuild'
import { useStaleDeploy } from '../staleDeploy'

function respond(sha: string | null) {
  return vi.fn().mockResolvedValue({ ok: true, json: async () => ({ sha, built_at: '2026-09-23T12:00:00Z' }) })
}

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); resetStaleBuild(); useStaleDeploy.setState({ stale: false, handled: false }); vi.restoreAllMocks() })

describe('startStaleBuildWatch', () => {
  it('adopts the first sha it sees as the running build, without reloading', async () => {
    const reload = vi.fn()
    vi.stubGlobal('fetch', respond('a'.repeat(40)))
    const stop = startStaleBuildWatch({ intervalMs: 1000, reload })
    await vi.advanceTimersByTimeAsync(0)
    expect(reload).not.toHaveBeenCalled()
    stop()
  })

  it('reloads a clean idle page when the served sha changes', async () => {
    const reload = vi.fn()
    const fetchMock = respond('a'.repeat(40))
    vi.stubGlobal('fetch', fetchMock)
    const stop = startStaleBuildWatch({ intervalMs: 1000, reload, mutationsInFlight: () => 0 })
    await vi.advanceTimersByTimeAsync(0)
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ sha: 'b'.repeat(40), built_at: 'x' }) })
    await vi.advanceTimersByTimeAsync(1000)
    expect(reload).toHaveBeenCalledTimes(1)
    stop()
  })

  it('prompts instead of reloading when a mutation is in flight', async () => {
    const reload = vi.fn()
    const fetchMock = respond('a'.repeat(40))
    vi.stubGlobal('fetch', fetchMock)
    const stop = startStaleBuildWatch({ intervalMs: 1000, reload, mutationsInFlight: () => 1 })
    await vi.advanceTimersByTimeAsync(0)
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ sha: 'b'.repeat(40), built_at: 'x' }) })
    await vi.advanceTimersByTimeAsync(1000)
    expect(reload).not.toHaveBeenCalled()
    expect(useStaleDeploy.getState().stale).toBe(true)
    stop()
  })

  it('never reloads when the endpoint is unreachable', async () => {
    const reload = vi.fn()
    const fetchMock = respond('a'.repeat(40))
    vi.stubGlobal('fetch', fetchMock)
    const stop = startStaleBuildWatch({ intervalMs: 1000, reload, mutationsInFlight: () => 0 })
    await vi.advanceTimersByTimeAsync(0)
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    await vi.advanceTimersByTimeAsync(1000)
    expect(reload).not.toHaveBeenCalled()
    stop()
  })

  it('stops polling once torn down', async () => {
    const fetchMock = respond('a'.repeat(40))
    vi.stubGlobal('fetch', fetchMock)
    const stop = startStaleBuildWatch({ intervalMs: 1000, reload: vi.fn(), mutationsInFlight: () => 0 })
    await vi.advanceTimersByTimeAsync(0)
    const callsAtStop = fetchMock.mock.calls.length
    stop()
    await vi.advanceTimersByTimeAsync(5000)
    expect(fetchMock.mock.calls.length).toBe(callsAtStop)
  })
})
