import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { useOrderSurfaceReady } from '../useOrderSurfaceReady'

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>
  return { client, wrapper }
}
describe('initial order surface readiness', () => {
  it('waits for primary data and resets on order or session identity changes', async () => {
    const { wrapper } = setup()
    const view = renderHook(({ id, scope, pending }) => useOrderSurfaceReady(id, scope, pending), { wrapper, initialProps: { id: 'a', scope: 'tenant:user:1', pending: true } })
    expect(view.result.current).toBe(false)
    view.rerender({ id: 'a', scope: 'tenant:user:1', pending: false })
    await waitFor(() => expect(view.result.current).toBe(true))
    view.rerender({ id: 'b', scope: 'tenant:user:1', pending: true })
    expect(view.result.current).toBe(false)
    view.rerender({ id: 'a', scope: 'tenant:user:2', pending: true })
    expect(view.result.current).toBe(false)
  })
  it('waits for a child checklist but never conceals an open surface on background refresh', async () => {
    const { client, wrapper } = setup()
    let finish!: (data: object) => void
    const read = () => new Promise<object>(resolve => { finish = resolve })
    const view = renderHook(() => {
      const ready = useOrderSurfaceReady('a', 'scope', false)
      useQuery({ queryKey: ['order-checklist', 'tenant', 'a'], queryFn: read })
      return ready
    }, { wrapper })
    expect(view.result.current).toBe(false)
    await act(async () => finish({ total: 0 }))
    await waitFor(() => expect(view.result.current).toBe(true))
    act(() => { void client.invalidateQueries() })
    expect(view.result.current).toBe(true)
  })
  it('reveals error states instead of leaving a failed child read hidden forever', async () => {
    const { wrapper } = setup()
    const view = renderHook(() => {
      const ready = useOrderSurfaceReady('a', 'scope', false)
      useQuery({ queryKey: ['order-checklist', 'tenant', 'a'], queryFn: async () => { throw new Error('offline') } })
      return ready
    }, { wrapper })
    await waitFor(() => expect(view.result.current).toBe(true))
  })
})
