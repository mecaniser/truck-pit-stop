import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { fetchRoadDistances, fetchRoadGeometry, useRoadProximity } from '../roadProximity'
import type { BoardTruck } from '../types'
const reply = (body: unknown) => ({ ok: true, json: async () => body })
const matrix = (distances: (number | null)[], durations = distances.map(value => value === null ? null : 300)) => reply({ code: 'Ok', distances: [distances], durations: [durations] })
const signal = () => new AbortController().signal
beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); vi.stubEnv('VITE_MAPBOX_TOKEN', 'synthetic') })
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.useRealTimers() })
it('ranks road miles over aerial proximity and ETA; sends directed coordinate-only requests', async () => {
  vi.mocked(fetch).mockResolvedValue(matrix([30000, 5000], [200, 600]) as Response)
  const result = await fetchRoadDistances([0, 0], [{ id: 'aerial-near', point: [.01, 0] }, { id: 'road-near', point: [.1, 0] }], 'synthetic', signal())
  expect(result.routes.map(row => row.id)).toEqual(['road-near', 'aerial-near'])
  expect(result.routes[0].miles).toBeCloseTo(3.10686)
  const url = new URL(vi.mocked(fetch).mock.calls[0][0] as string)
  expect(url.pathname).toContain('/mapbox/driving/0,0;0.01,0;0.1,0')
  expect(url.searchParams.get('sources')).toBe('0')
  expect(url.searchParams.get('destinations')).toBe('1;2')
  expect(url.searchParams.get('annotations')).toBe('distance,duration')
  expect(url.toString()).not.toMatch(/aerial-near|road-near|fallback_speed/)
})
it('checks all candidates across batches; keeps zero and ties while excluding unreachable', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(matrix(Array(24).fill(1000)) as Response).mockResolvedValueOnce(matrix([0, null]) as Response)
  const result = await fetchRoadDistances([0, 0], Array.from({ length: 26 }, (_, i) => ({ id: String(i).padStart(2, '0'), point: [i, 0] as [number, number] })), 'synthetic', signal())
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(result.routes[0]).toEqual({ id: '24', miles: 0, seconds: 300 })
  expect(result.routes[1].id).toBe('00')
  expect(result.routes).toHaveLength(25)
  expect(result.unreachable).toBe(1)
})
it.each([reply({ code: 'Ok', distances: [[]], durations: [[]] }), matrix([-1]), matrix([NaN]), { ok: false }, reply({ code: 'InvalidInput' })])('rejects invalid/provider responses rather than guessing distance', async body => {
  vi.mocked(fetch).mockResolvedValue(body as Response)
  await expect(fetchRoadDistances([0, 0], [{ id: 'b', point: [1, 0] }], 'synthetic', signal())).rejects.toThrow()
})
it('reports NoRoute without inventing a straight-line distance', async () => {
  vi.mocked(fetch).mockResolvedValue(reply({ code: 'NoRoute' }) as Response)
  expect(await fetchRoadDistances([0, 0], [{ id: 'b', point: [1, 0] }], 'synthetic', signal())).toEqual({ routes: [], unreachable: 1 })
})
it('accepts road geometry and rejects missing or invalid geometry', async () => {
  const geometry = { type: 'LineString', coordinates: [[0, 0], [.3, .4], [1, 0]] }
  vi.mocked(fetch).mockResolvedValueOnce(reply({ code: 'Ok', routes: [{ geometry }] }) as Response).mockResolvedValueOnce(reply({ code: 'Ok', routes: [] }) as Response)
  expect(await fetchRoadGeometry([0, 0], [1, 0], 'synthetic', signal())).toEqual(geometry)
  await expect(fetchRoadGeometry([0, 0], [1, 0], 'synthetic', signal())).rejects.toThrow()
})
const now = Date.now()
const truck = (id: string, lng: number) => ({ id, telemetry: { location: { lat: 0, lng, observed_at: new Date(now).toISOString(), captured_at: new Date(now).toISOString() } } } as BoardTruck)
const a = truck('a', 0), b = truck('b', 1), c = truck('c', 2)
async function settle() { await act(async () => { await vi.advanceTimersByTimeAsync(251) }) }
it('drops old results immediately and ignores late replies after selection/scope changes', async () => {
  vi.useFakeTimers()
  let finish!: (response: Response) => void
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue(matrix([1609]) as Response)
  const hook = renderHook(({ trucks, focus }) => useRoadProximity(trucks, focus, now, false, 0), { initialProps: { trucks: [a, b], focus: a } })
  await settle()
  const firstSignal = vi.mocked(fetch).mock.calls[0][1]!.signal!
  hook.rerender({ trucks: [a, c], focus: c })
  expect(firstSignal.aborted).toBe(true)
  expect(hook.result.current.nearby).toEqual([])
  await act(async () => finish(matrix([999]) as Response))
  expect(hook.result.current.nearby).toEqual([])
  await settle()
  expect(hook.result.current.nearby[0].truck.id).toBe('a')
  hook.rerender({ trucks: [b], focus: b })
  expect(hook.result.current.nearby).toEqual([])
  expect(hook.result.current.geometry).toBeUndefined()
})
it('avoids calls without a configured token and handles routing failure and retry', async () => {
  vi.useFakeTimers(); vi.stubEnv('VITE_MAPBOX_TOKEN', '')
  const hook = renderHook(({ retry }) => useRoadProximity([a, b], a, now, false, retry), { initialProps: { retry: 0 } })
  await settle(); expect(fetch).not.toHaveBeenCalled(); expect(hook.result.current.phase).toBe('unconfigured')
  vi.stubEnv('VITE_MAPBOX_TOKEN', 'synthetic'); vi.mocked(fetch).mockRejectedValue(new Error('offline'))
  hook.rerender({ retry: 1 }); await settle(); expect(hook.result.current.phase).toBe('error')
  vi.mocked(fetch).mockResolvedValue(matrix([1609]) as Response)
  hook.rerender({ retry: 2 }); expect(hook.result.current.phase).toBe('loading'); await settle()
  expect(hook.result.current.nearby).toHaveLength(1); expect(hook.result.current.geometryFailed).toBe(true)
})
it('times out hung provider calls with a retryable error', async () => {
  vi.useFakeTimers()
  vi.mocked(fetch).mockImplementation((_, options) => new Promise((_, reject) => options!.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))))
  const hook = renderHook(() => useRoadProximity([a, b], a, now, false, 0))
  await act(async () => { await vi.advanceTimersByTimeAsync(15251) })
  expect(hook.result.current.phase).toBe('error')
})
