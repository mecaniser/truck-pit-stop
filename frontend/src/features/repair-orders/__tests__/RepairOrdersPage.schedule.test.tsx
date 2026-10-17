import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const auth = vi.hoisted(() => ({ user: { id: 'actor-1', tenant_id: 'tenant-1', role: 'garage_owner' }, authSessionEpoch: 1 }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (select: (state: typeof auth) => unknown) => select(auth) }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ presentationVariant: 'new', accentColors: { 500: '#d97706' } }) }))
vi.mock('../PriceBuilderPanel', () => ({ default: ({ onClose, schedule }: { onClose: () => void; schedule?: { is_overdue?: boolean } }) => <><button onClick={onClose}>Close repair order</button><span data-testid="schedule-summary">{schedule?.is_overdue ? 'Overdue' : 'Due'}</span></> }))
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
import RepairOrdersPage from '../RepairOrdersPage'
const order = { id: 'order-1', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1', order_number: 'RO-1', status: 'in_progress', description: 'Brake inspection', total_cost: '145', total_parts_cost: '0', total_labor_cost: '145', created_at: '2026-10-12T12:00:00Z', updated_at: '2026-10-12T12:00:00Z', parts_usage: [], labor_items: [], history_events: [], promised_finish_at: '2026-10-16T21:00:00Z', schedule_timezone: 'America/New_York', is_overdue: true }
function Probe() { const navigate = useNavigate(); return <><output data-testid="location">{useLocation().pathname}{useLocation().search}</output><button onClick={() => navigate(-1)}>Browser Back</button></> }
function mount(entry: string, daily = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}><Routes><Route path="/dashboard" element={<RepairOrdersPage workbenchScope={daily ? 'daily' : 'all'} />} /><Route path="/dashboard/repair-orders" element={<RepairOrdersPage />} /></Routes><Probe /></MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url === '/repair-orders') return Promise.resolve({ data: { items: config?.params?.skip ? [{ ...order, id: 'order-26', order_number: 'RO-26' }] : [order], total: 26, has_more: !config?.params?.skip } })
    if (url === '/repair-orders/status-counts') return Promise.resolve({ data: { all: 26, in_progress: 26 } })
    if (url === '/repair-orders/value-summary') return Promise.resolve({ data: { order_count: 26, order_value: '3770' } })
    if (url === '/repair-orders/order-1/workspace' || url === '/repair-orders/order-1/detail') return Promise.resolve({ data: order })
    if (url === '/dashboard/action-queue') return Promise.resolve({ data: { orders_on_floor: [], orders_needing_action: [], orders_ready_to_close: [] } })
    if (url === '/dashboard/daily-workset') return Promise.resolve({ data: { timezone: 'America/New_York', business_date: '2026-10-16', needs_attention: { items: [], has_more: false }, on_floor: { items: [], has_more: false }, ready_to_close: { items: [], has_more: false }, closed_today: { items: [], has_more: false } } })
    if (url.startsWith('/quotes')) return Promise.resolve({ data: null })
    if (url.includes('settings')) return Promise.resolve({ data: { labor_rate: 145 } })
    return Promise.resolve({ data: [] })
  })
})
it('applies overdue/search/customer/vehicle filters consistently before pagination, counts and value', async () => {
  mount('/dashboard/repair-orders?overdue=true&search=Brake&customer_id=customer-1&vehicle_id=vehicle-1')
  await screen.findByRole('button', { name: 'Open repair order RO-1' })
  for (const url of ['/repair-orders', '/repair-orders/status-counts', '/repair-orders/value-summary']) {
    expect(api.get).toHaveBeenCalledWith(url, expect.objectContaining({ params: expect.objectContaining({ overdue: true, search: 'Brake', customer_id: 'customer-1', vehicle_id: 'vehicle-1' }) }))
  }
  expect(screen.getByRole('button', { name: 'Overdue', exact: true })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText(/Overdue · Oct 16, 5:00 PM EDT/)).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: /Load more/ }))
  await screen.findByRole('button', { name: 'Open repair order RO-26' })
  expect(api.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ params: expect.objectContaining({ skip: 25, limit: 25, overdue: true, customer_id: 'customer-1' }) }))
  fireEvent.click(screen.getByRole('button', { name: 'Open repair order RO-1' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Close repair order' }))
  expect(screen.getByTestId('location')).toHaveTextContent('overdue=true&search=Brake&customer_id=customer-1&vehicle_id=vehicle-1')
})
it('switches the bounded daily lane to All overdue work and preserves search/filter context', async () => {
  mount('/dashboard?queue=on_floor&search=Brake&customer_id=customer-1', true)
  fireEvent.click(await screen.findByRole('button', { name: 'All overdue work' }))
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/dashboard/repair-orders?search=Brake&customer_id=customer-1&overdue=true'))
  expect(screen.getByTestId('location')).not.toHaveTextContent('queue=')
  await screen.findByRole('button', { name: 'Open repair order RO-1' })
  expect(api.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ params: expect.objectContaining({ overdue: true, search: 'Brake', customer_id: 'customer-1' }) }))
  fireEvent.click(screen.getByRole('button', { name: 'Browser Back' }))
  expect(screen.getByTestId('location')).toHaveTextContent('/dashboard?queue=on_floor&search=Brake&customer_id=customer-1')
})

afterEach(() => vi.useRealTimers())
it('refreshes the selected order summary as its promise becomes overdue without reopening it', async () => {
  vi.useFakeTimers()
  let due = false
  const original = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url === '/repair-orders/order-1/workspace') return Promise.resolve({ data: { ...order, is_overdue: due } })
    return original(url, config)
  })
  mount('/dashboard/repair-orders?selected=order-1')
  await act(async () => { await vi.advanceTimersByTimeAsync(50) })
  expect(screen.getByTestId('schedule-summary')).toHaveTextContent('Due')
  due = true
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
  await act(async () => { await vi.advanceTimersByTimeAsync(10) })
  expect(screen.getByTestId('schedule-summary')).toHaveTextContent('Overdue')
  expect(api.get.mock.calls.filter(([url]) => url === '/repair-orders/order-1/workspace').length).toBeGreaterThan(1)
})
