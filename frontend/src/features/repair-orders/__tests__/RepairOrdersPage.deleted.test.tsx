import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import RepairOrdersPage from '../RepairOrdersPage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('react-hot-toast', () => ({ default: toast }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ presentationVariant: 'new', accentColors: { 500: '#f59e0b' } }) }))

const order = {
  id: 'order-116', tenant_id: 'tenant-116', customer_id: 'customer-116', vehicle_id: 'vehicle-116',
  order_number: 'QA116', status: 'in_progress', description: 'Inspect QA vehicle',
  vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_unit_number: 'QA116',
  customer_company_name: 'QA Company', assigned_mechanic_id: null, is_internal: false,
  total_parts_cost: '0', total_labor_cost: '0', total_cost: '0',
  created_at: '2026-10-13T12:00:00Z', updated_at: '2026-10-13T13:00:00Z', deleted_at: null,
}
const deletedOrder = { ...order, deleted_at: '2026-10-13T14:00:00Z', deleted_by_name: 'QA Owner', updated_at: '2026-10-13T14:00:00Z' }
const summary = { order_id: order.id, labor_total: '0', parts_total: '0', total_cost: '0', lines: [], parts: [], warnings: [], pricing_locked: false, can_edit_work: true }
let deleted = true
const current = () => deleted ? deletedOrder : { ...order, updated_at: '2026-10-13T15:00:00Z' }
const activeOnly = (url: string) => /\/(detail|checklist|operations|notes|photos|price-build|recommended-services)$/.test(url)
  || url.startsWith('/quotes') || url === '/repair-orders/recommended-work'

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/?selected=order-116']}><RepairOrdersPage /></MemoryRouter></QueryClientProvider>)
  return client
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  useAuthStore.setState({ user: { id: 'owner-116', tenant_id: 'tenant-116', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
  deleted = true
  api.get.mockImplementation(async (url: string, config?: { params?: { deleted?: boolean } }) => {
    if (url === '/repair-orders') {
      const items = Boolean(config?.params?.deleted) === deleted ? [current()] : []
      return { data: { items, total: items.length, has_more: false } }
    }
    if (url.endsWith('/workspace')) return { data: current() }
    if (deleted && activeOnly(url)) throw new Error(`Unavailable deleted panel requested: ${url}`)
    if (url.endsWith('/detail')) return { data: { ...current(), labor_items: [], parts_usage: [], history_events: [] } }
    if (url.endsWith('/price-build')) return { data: summary }
    if (url === '/repair-orders/recommended-work') return { data: { items: [], total: 0, skip: 0, limit: 25 } }
    if (url.endsWith('/checklist')) return { data: { items: [], total: 0, summary: { total: 0, required_remaining: 0 } } }
    if (url.endsWith('/operations')) return { data: { items: [], summary: { tracked: 0, completed: 0, remaining: 0, legacy_untracked: 0 } } }
    if (url.startsWith('/quotes?')) return { data: null }
    if (url.endsWith('/history')) return { data: { revisions: [], events: [] } }
    return { data: [] }
  })
  api.delete.mockImplementation(async () => { deleted = true; return { status: 204 } })
  api.post.mockImplementation(async () => { deleted = false; return { data: { order: current(), stock_shortages: [] } } })
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); useAuthStore.setState({ user: null }) })

describe('deleted repair-order workspace', () => {
  it('shows a direct Restore action and requests no unavailable panels on a fresh deleted link', async () => {
    mount()
    expect(await screen.findByRole('button', { name: 'Restore order', exact: true })).toBeEnabled()
    expect(screen.getByRole('region', { name: 'Deleted repair order' })).toHaveTextContent('QA Owner')
    for (const name of ['History', 'Edit work requested', 'Put on hold', 'Mark Completed', 'Complete', 'Create estimate']) {
      expect(screen.queryByRole('button', { name, exact: true })).not.toBeInTheDocument()
    }
    expect(api.get.mock.calls.filter(([url]) => activeOnly(url))).toEqual([])
    expect(api.post).not.toHaveBeenCalled()
  })

  it('reopens a deleted order immediately after a warm History visit, without stale detail or panel requests', async () => {
    deleted = false
    const client = mount(); const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'History', exact: true }))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/repair-orders/order-116/detail', expect.anything()))
    await user.click(screen.getByRole('button', { name: 'Order actions', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Delete', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Delete order', exact: true }))
    await waitFor(() => expect(screen.queryByRole('region', { name: '#QA116', exact: true })).not.toBeInTheDocument())
    // A disabled observer may recreate an empty cache entry; no scoped data may survive.
    expect(client.getQueriesData({ queryKey: ['repair-order-detail', order.id] }).filter(([, data]) => data !== undefined)).toEqual([])
    api.get.mockClear()
    await user.click(screen.getByRole('button', { name: 'Deleted', exact: true }))
    await user.click(await screen.findByRole('button', { name: 'Open repair order QA116', exact: true }))
    expect(await screen.findByRole('button', { name: 'Restore order', exact: true })).toBeEnabled()
    expect(api.get.mock.calls.filter(([url]) => activeOnly(url))).toEqual([])
    await user.click(screen.getByRole('button', { name: 'Order actions', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Close danger zone', exact: true }))
    expect(api.post).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Restore order', exact: true })).toBeVisible()
  })

  it('keeps failed restores recoverable, blocks repeat submission, then restores the live workspace without reload', async () => {
    mount(); const user = userEvent.setup()
    api.post.mockRejectedValueOnce(new Error('Offline'))
    await user.click(await screen.findByRole('button', { name: 'Restore order', exact: true }))
    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(screen.getByRole('region', { name: 'Deleted repair order' })).toBeVisible()
    let finish!: (response: unknown) => void
    api.post.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await user.click(screen.getByRole('button', { name: 'Restore order', exact: true }))
    expect(await screen.findByRole('button', { name: /Restoring…/ })).toBeDisabled()
    expect(api.post).toHaveBeenCalledTimes(2)
    await act(async () => { deleted = false; finish({ data: { order: current(), stock_shortages: [] } }) })
    expect(await screen.findByRole('button', { name: 'Edit work requested', exact: true })).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Deleted repair order' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Restore order', exact: true })).not.toBeInTheDocument()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/repair-orders/order-116/price-build', expect.anything()))
  })

  it('does not offer owner/admin restore to a mechanic viewing a deleted order', async () => {
    useAuthStore.setState({ user: { id: 'mechanic-116', tenant_id: 'tenant-116', role: 'mechanic' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
    mount()
    expect(await screen.findByRole('region', { name: 'Deleted repair order' })).toBeVisible()
    expect(within(screen.getByRole('region', { name: '#QA116', exact: true })).queryByRole('button', { name: 'Restore order' })).not.toBeInTheDocument()
    expect(api.get.mock.calls.filter(([url]) => activeOnly(url))).toEqual([])
  })
})
