import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ presentationVariant: 'new', accentColors: { 500: '#d97706' } }) }))
vi.mock('../PriceBuilderPanel', () => ({ default: () => <div>Repair order workspace</div> }))
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
import RepairOrdersPage from '../RepairOrdersPage'
const order = { id: 'order-1', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1', order_number: 'RO-1', status: 'in_progress', total_cost: '145', total_parts_cost: '0', total_labor_cost: '145', created_at: '2026-10-12T12:00:00Z', updated_at: '2026-10-12T12:00:00Z', parts_usage: [], labor_items: [], history_events: [] }
const customer = { id: 'customer-1', company_name: 'Northline Logistics', first_name: 'Nora', last_name: 'North', email: 'nora@example.invalid', created_at: '2026-10-12T12:00:00Z', balance: '145' }
function Probe() { return <output data-testid="location">{useLocation().search}</output> }
beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockImplementation((url: string) => {
    if (url === '/customers/customer-1/vehicles') return Promise.resolve({ data: [{ id: 'vehicle-1', customer_id: 'customer-1', unit_number: 'C-001', year: 2021, make: 'Freightliner', model: 'Cascadia', vin: '1FUJGLDR4DLAA0001' }] })
    if (url === '/customers/customer-1/history') return Promise.resolve({ data: { items: [{ ...order, vehicle_make: 'Freightliner', vehicle_model: 'Cascadia' }], stats: { total_orders: 1, completed_orders: 0, lifetime_spend: '145', lifetime_savings: '0' } } })
    if (url === '/customers/customer-1/history/order-1') return Promise.resolve({ data: { ...order, mechanic_name: 'Alex', amount_paid: null, labor: [{ id: 'labor-1', description: 'Replace fan belt', hours: '1', hourly_rate: '145', total_cost: '145' }], parts: [] } })
    if (url === '/customers/customer-1') return Promise.resolve({ data: customer })
    if (url === '/repair-orders') return Promise.resolve({ data: { items: [order], total: 1, has_more: false } })
    if (url === '/repair-orders/order-1/workspace' || url === '/repair-orders/order-1/detail') return Promise.resolve({ data: order })
    if (url.startsWith('/quotes')) return Promise.resolve({ data: null })
    if (url === '/dashboard/stats') return Promise.resolve({ data: { mechanic_workload: [] } })
    if (url.includes('settings')) return Promise.resolve({ data: { labor_rate: 145 } })
    return Promise.resolve({ data: [] })
  })
})
function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboard?selected=order-1&queue=on_floor&customer=customer-1']}><RepairOrdersPage /><Probe /></MemoryRouter></QueryClientProvider>)
}
it('names the embedded customer workspace and returns to the same repair-order queue', async () => {
  setup()
  expect(await screen.findByRole('region', { name: 'Northline Logistics customer workspace' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Northline Logistics' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Back to #RO-1' }))
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('?selected=order-1&queue=on_floor'))
  expect(screen.getByTestId('location')).not.toHaveTextContent('customer=')
  expect(api.put).not.toHaveBeenCalled()
  expect(api.post).not.toHaveBeenCalled()
})

it('opens a connected truck in place and returns through the customer to the same queue', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  expect(await screen.findByRole('heading', { name: /Repair history/i })).toBeVisible()
  expect(screen.getByText('1FUJGLDR4DLAA0001')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Back to Northline Logistics' }))
  expect(screen.getByRole('button', { name: 'History', exact: true })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Back to #RO-1' }))
  expect(screen.getByTestId('location')).toHaveTextContent('?selected=order-1&queue=on_floor')
  expect(api.put).not.toHaveBeenCalled()
  expect(api.post).not.toHaveBeenCalled()
})
it('expands repair history with real work details and can reopen its order', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button', { name: 'History', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'RO-1', exact: true }))
  expect(await screen.findByText('Replace fan belt')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Open repair order RO-1' }))
  await waitFor(() => expect(screen.getByTestId('location')).not.toHaveTextContent('customer='))
  expect(screen.getByTestId('location')).toHaveTextContent('queue=on_floor')
})
