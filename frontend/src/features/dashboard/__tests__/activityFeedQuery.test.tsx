import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { activityCountLabel, useActivityFeed } from '../activityFeedQuery'

const state = vi.hoisted(() => ({ user: { id: 'owner', tenant_id: 'shop-a', role: 'garage_owner', is_active: true }, epoch: 1, get: vi.fn() }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (select: (s: unknown) => unknown) => select({ user: state.user, authSessionEpoch: state.epoch }) }))
vi.mock('@/lib/api', () => ({ default: { get: state.get } }))
const page = { items: [{ id: 'event' }], has_more: true, next_cursor: 'next', warnings: [], available_actors: [] }
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { client, wrapper }
}
beforeEach(() => { state.user = { id: 'owner', tenant_id: 'shop-a', role: 'garage_owner', is_active: true }; state.epoch = 1; state.get.mockReset().mockResolvedValue({ data: page }) })
describe('Shop Work activity summary', () => {
  it('loads on arrival before mounting the feed and shares its unfiltered first page', async () => {
    const { wrapper } = setup()
    const summary = renderHook(() => useActivityFeed(), { wrapper })
    await waitFor(() => expect(summary.result.current.isSuccess).toBe(true))
    const feed = renderHook(() => useActivityFeed({ actor_id: undefined, event_type: undefined, date_from: undefined, date_to: undefined }), { wrapper })
    expect(feed.result.current.data).toEqual(page)
    expect(state.get).toHaveBeenCalledTimes(1)
    expect(activityCountLabel(summary.result.current.data, false)).toBe('1+')
  })
  it('keeps summary unchanged when feed filters change', async () => {
    const { wrapper } = setup()
    const summary = renderHook(() => useActivityFeed(), { wrapper })
    await waitFor(() => expect(summary.result.current.isSuccess).toBe(true))
    state.get.mockResolvedValueOnce({ data: { ...page, items: [], has_more: false } })
    const feed = renderHook(() => useActivityFeed({ event_type: 'invoice_paid' }), { wrapper })
    await waitFor(() => expect(feed.result.current.isSuccess).toBe(true))
    expect(summary.result.current.data?.items).toHaveLength(1)
    expect(feed.result.current.data?.items).toHaveLength(0)
  })
  it('does not request activity for a mechanic or inactive principal', () => {
    state.user.role = 'mechanic'
    renderHook(() => useActivityFeed(), setup())
    state.user.role = 'garage_owner'; state.user.is_active = false
    renderHook(() => useActivityFeed(), setup())
    expect(state.get).not.toHaveBeenCalled()
  })
  it('does not reuse another shop or session cache', async () => {
    const { wrapper } = setup()
    const hook = renderHook(() => useActivityFeed(), { wrapper })
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    state.user = { ...state.user, tenant_id: 'shop-b' }; state.epoch++
    state.get.mockResolvedValueOnce({ data: { ...page, items: [], has_more: false } })
    hook.rerender()
    expect(hook.result.current.data).toBeUndefined()
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    expect(hook.result.current.data?.items).toHaveLength(0)
  })
  it('drops the cached first page when the current principal becomes inactive', async () => {
    const { wrapper } = setup()
    const hook = renderHook(() => useActivityFeed(), { wrapper })
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true))
    state.user = { ...state.user, is_active: false }
    hook.rerender()
    expect(hook.result.current.data).toBeUndefined()
  })
  it.each([[8, false, '8'], [9, false, '9'], [9, true, '9+'], [10, false, '9+'], [20, true, '9+']])('caps %s events with more=%s as %s', (count, more, label) => {
    const items = Array.from({ length: count as number }, (_, index) => ({ id: `${index}`, event_type: 'order_created', label: 'Created', occurred_at: '2026-10-30T12:00:00Z' }))
    expect(activityCountLabel({ ...page, items, has_more: more as boolean }, false)).toBe(label)
  })
  it('distinguishes no results from loading or failure', () => {
    expect(activityCountLabel(undefined, false)).toBeNull()
    expect(activityCountLabel({ ...page, items: [], has_more: false }, false)).toBe('0')
    expect(activityCountLabel({ ...page, items: [], has_more: false }, true)).toBeNull()
  })
})
