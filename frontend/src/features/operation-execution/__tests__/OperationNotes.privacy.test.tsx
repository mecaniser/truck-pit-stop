import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { useRepairOrderDetail } from '@/features/fleet/priceBuild'
import RepairOrdersPage from '@/features/repair-orders/RepairOrdersPage'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ presentationVariant: 'new', accentColors: { 500: '#f59e0b' } }) }))
vi.mock('@/features/repair-orders/PriceBuilderPanel', () => ({ default: ({ onHistoryOpen, historyEvents }: { onHistoryOpen: () => void; historyEvents: Array<{ id: string; detail?: string }> }) => <><button onClick={onHistoryOpen}>History</button>{historyEvents.map(event => <p key={event.id}>{event.detail}</p>)}</> }))
const order = { id: 'private-order', tenant_id: 'tenant-a', customer_id: 'customer-a', vehicle_id: 'vehicle-a', order_number: 'QA118', status: 'in_progress', total_cost: '0', total_parts_cost: '0', total_labor_cost: '0', created_at: '2026-10-14T10:00:00Z', updated_at: '2026-10-14T10:00:00Z' }
const detail = { ...order, labor_items: [], parts_usage: [], history_events: [{ id: 'note-a', event_type: 'operation_note_shop', label: 'Shop note · Brake check', detail: 'PRIVATE OPERATION FINDING', actor_name: 'Owner', created_at: order.created_at }] }
function user(role = 'garage_owner', id = 'owner-a', epoch = 1) {
  useAuthStore.setState({ user: { id, tenant_id: 'tenant-a', role } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, authSessionEpoch: epoch })
}
function FleetHistoryProbe() {
  const query = useRepairOrderDetail(order.id)
  return <>{query.data?.history_events?.map(event => <p key={event.id}>{event.detail}</p>)}</>
}
function mount(fleet = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/?selected=private-order']}>{fleet ? <FleetHistoryProbe /> : <RepairOrdersPage />}</MemoryRouter></QueryClientProvider>)
  return client
}
beforeEach(() => {
  vi.clearAllMocks(); user()
  api.get.mockImplementation(async (path: string) => {
    if (path === '/repair-orders') return { data: { items: [order], total: 1, has_more: false } }
    if (path.endsWith('/workspace')) return { data: order }
    if (path.endsWith('/detail')) return { data: detail }
    if (path.startsWith('/quotes?')) return { data: null }
    if (path.endsWith('/history')) return { data: { revisions: [], events: [] } }
    if (path.endsWith('/recommended-work')) return { data: { items: [], total: 0, skip: 0, limit: 25 } }
    return { data: [] }
  })
})
afterEach(() => useAuthStore.setState({ user: null }))

describe.each([false, true])('private operation history in fleet=%s', fleet => {
  it('does not reuse a prior staff session while another account response is pending', async () => {
    mount(fleet)
    if (!fleet) await userEvent.setup().click(await screen.findByRole('button', { name: 'History' }))
    expect(await screen.findByText('PRIVATE OPERATION FINDING')).toBeVisible()
    api.get.mockImplementation(() => new Promise(() => {}))
    act(() => user('fleet_manager', 'manager-b', 2))
    await waitFor(() => expect(screen.queryByText('PRIVATE OPERATION FINDING')).not.toBeInTheDocument())
  })
  it('partitions a new session even for the same account and role', async () => {
    mount(fleet)
    if (!fleet) await userEvent.setup().click(await screen.findByRole('button', { name: 'History' }))
    expect(await screen.findByText('PRIVATE OPERATION FINDING')).toBeVisible()
    api.get.mockImplementation(() => new Promise(() => {}))
    act(() => user('garage_owner', 'owner-a', 2))
    await waitFor(() => expect(screen.queryByText('PRIVATE OPERATION FINDING')).not.toBeInTheDocument())
  })
})
