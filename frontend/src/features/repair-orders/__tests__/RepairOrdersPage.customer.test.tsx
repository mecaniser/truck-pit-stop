import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'

vi.mock('@/stores/authStore', () => ({ useAuthStore: (select: (state: {user: {role: string}}) => unknown) => select({user: {role: 'garage_owner'}}) }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ presentationVariant: 'new', accentColors: { 500: '#d97706' } }) }))
vi.mock('../PriceBuilderPanel', () => ({ default: () => <div>Repair order workspace</div> }))
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
import RepairOrdersPage from '../RepairOrdersPage'
import CustomersPage from '../../customers/CustomersPage'
const order = { id: 'order-1', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1', order_number: 'RO-1', status: 'in_progress', total_cost: '145', total_parts_cost: '0', total_labor_cost: '145', created_at: '2026-10-12T12:00:00Z', updated_at: '2026-10-12T12:00:00Z', parts_usage: [], labor_items: [], history_events: [] }
const customer = { id: 'customer-1', company_name: 'Northline Logistics', first_name: 'Nora', last_name: 'North', email: 'nora@example.invalid', created_at: '2026-10-12T12:00:00Z', balance: '145' }
function Probe() { return <output data-testid="location">{useLocation().search}</output> }
beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockImplementation((url: string) => {
    if (url === '/vehicles/typeahead') return Promise.resolve({data:[{ id:'vehicle-1',customer_id:'customer-1',unit_number:'C-001',year:2021,make:'Freightliner',model:'Cascadia',last_known_mileage:120000 }]})
    if (url === '/customers/customer-1/vehicles/vehicle-1') return Promise.resolve({ data: { id: 'vehicle-1', customer_id: 'customer-1', unit_number: 'C-001', year: 2021, make: 'Freightliner', model: 'Cascadia' } })
    if (url === '/customers/customer-1/vehicles') return Promise.resolve({ data: [{ id: 'vehicle-1', customer_id: 'customer-1', unit_number: 'C-001', year: 2021, make: 'Freightliner', model: 'Cascadia', vin: '1FUJGLDR4DLAA0001' }] })
    if (url === '/customers/customer-1/history') return Promise.resolve({ data: { items: [{ ...order, vehicle_make: 'Freightliner', vehicle_model: 'Cascadia' }], stats: { total_orders: 1, completed_orders: 0, lifetime_spend: '145', lifetime_savings: '0' } } })
    if (url === '/customers/customer-1/history/order-1') return Promise.resolve({ data: { ...order, mechanic_name: 'Alex', amount_paid: null, labor: [{ id: 'labor-1', description: 'Replace fan belt', hours: '1', hourly_rate: '145', total_cost: '145' }], parts: [] } })
    if (url === '/customers') return Promise.resolve({ data: { items: [customer], total: 1, has_more: false } })
    if (url === '/customers/customer-1') return Promise.resolve({ data: customer })
    if (url === '/repair-orders') return Promise.resolve({ data: { items: [order], total: 1, has_more: false } })
    if (url === '/repair-orders/order-1/workspace' || url === '/repair-orders/order-1/detail') return Promise.resolve({ data: order })
    if (url.startsWith('/quotes')) return Promise.resolve({ data: null })
    if (url === '/dashboard/stats') return Promise.resolve({ data: { mechanic_workload: [] } })
    if (url.includes('settings')) return Promise.resolve({ data: { labor_rate: 145 } })
    return Promise.resolve({ data: [] })
  })
})
function setup(initialEntry = '/dashboard?selected=order-1&queue=on_floor&customer=customer-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initialEntry]}><Routes><Route path='/dashboard/customers' element={<CustomersPage />} /><Route path='/dashboard/*' element={<RepairOrdersPage />} /></Routes><Probe /></MemoryRouter></QueryClientProvider>)
  return client
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

it('starts a truck draft with exact context and cancels back to the same queued truck', async () => {
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(await within(screen.getByRole('region', {name:'Northline Logistics customer workspace'})).findByRole('button', { name: 'New repair order', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'New Repair Order' })
  expect(dialog).toHaveTextContent('Northline Logistics')
  expect(await screen.findByRole('button', { name: 'Select Freightliner Cascadia · Unit C-001' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Close new repair order' }))
  expect(await screen.findByRole('heading', { name: /Repair history/i })).toBeVisible()
  expect(screen.getByTestId('location')).toHaveTextContent('?selected=order-1&queue=on_floor&customer=customer-1')
  expect(api.post).not.toHaveBeenCalled()
})

it('keeps a related truck with a different owner and bills the selected customer', async () => {
  const baseGet = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string) => {
    if (url === '/customers/customer-1/vehicles/vehicle-1') return Promise.resolve({data: { id: 'vehicle-1', customer_id: 'other-owner', customer_relationship_types: ['operator'], unit_number: 'C-001', year: 2021, make: 'Freightliner', model: 'Cascadia' }})
    if (url === '/customers/customer-1/vehicles') return Promise.resolve({data: [{ id: 'vehicle-1', customer_id: 'other-owner', customer_relationship_types: ['operator'], unit_number: 'C-001', year: 2021, make: 'Freightliner', model: 'Cascadia' }]})
    return baseGet(url)
  })
  api.post.mockResolvedValue({data: {...order, id: 'new-order', order_number: 'RO-NEW'}})
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(await within(screen.getByRole('region', {name:'Northline Logistics customer workspace'})).findByRole('button', { name: 'New repair order', exact: true }))
  await screen.findByRole('dialog', {name: 'New Repair Order'})
  const submit = screen.getByRole('button', {name: 'Create Repair Order'})
  fireEvent.click(submit)
  fireEvent.click(submit)
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({customer_id:'customer-1',vehicle_id:'vehicle-1'})))
  expect(api.post.mock.calls.filter(([url])=>url === '/repair-orders')).toHaveLength(1)
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
})


it('returns to the exact Customers truck and query after cancel, retaining it on customer refresh', async () => {
  const client = setup('/dashboard/customers?view=list&filter=active&selected=customer-1')
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(screen.getByRole('button', {name:'New repair order', exact:true}))
  const dialog = await screen.findByRole('dialog', {name:'New Repair Order'})
  expect(within(dialog).getByRole('button', {name:/Select Freightliner/})).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(within(dialog).getByRole('button', {name:'Cancel'}))
  expect(await screen.findByRole('heading', {name:/Repair history/})).toBeVisible()
  expect(screen.getByTestId('location')).toHaveTextContent('?view=list&filter=active&selected=customer-1')
  await waitFor(() => expect(screen.getByRole('button', {name:'New repair order',exact:true})).toHaveFocus())
  await act(async () => { client.setQueriesData({queryKey:['customers']}, {items:[{...customer, balance:'200'}],total:1,has_more:false}) })
  expect(screen.getByRole('heading', {name:/Repair history/})).toBeVisible()
  expect(screen.getByRole('button', {name:'Edit vehicle'})).toBeVisible()
  expect(api.post).not.toHaveBeenCalled()
})

it('requires deliberate truck selection from the customer shortcut', async () => {
  setup('/dashboard/customers?selected=customer-1')
  fireEvent.click(await screen.findByRole('button', {name:'New repair order', exact:true}))
  const dialog = await screen.findByRole('dialog', {name:'New Repair Order'})
  expect(await within(dialog).findByRole('button', {name:/Select Freightliner/})).toHaveAttribute('aria-pressed','false')
  fireEvent.click(within(dialog).getByRole('button', {name:'Create Repair Order'}))
  expect(api.post).not.toHaveBeenCalled()
  expect(dialog).toHaveTextContent('Select an available truck or add a new one.')
})

it('keeps a failed draft and blocks repeated submit and cancel until the pending save settles', async () => {
  let rejectSave!: (reason: Error) => void
  api.post.mockImplementationOnce(() => new Promise((_, reject) => { rejectSave = reject }))
  setup()
  fireEvent.click(await screen.findByRole('button', {name:/Open .*Unit C-001/}))
  fireEvent.click(within(screen.getByRole('region', {name:'Northline Logistics customer workspace'})).getByRole('button', {name:'New repair order',exact:true}))
  const dialog = await screen.findByRole('dialog', {name:'New Repair Order'})
  fireEvent.change(within(dialog).getByPlaceholderText('Briefly describe the repair work or concern...'), {target:{value:'Check air leak'}})
  const submit = within(dialog).getByRole('button', {name:'Create Repair Order'})
  fireEvent.click(submit)
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
  expect(submit).toBeDisabled()
  expect(within(dialog).getByRole('button', {name:'Cancel'})).toBeDisabled()
  fireEvent.click(submit)
  fireEvent.click(within(dialog).getByRole('button', {name:'Close new repair order'}))
  expect(dialog).toBeVisible()
  await act(async () => rejectSave(new Error('offline')))
  expect(within(dialog).getByRole('alert')).toHaveTextContent('Failed to create repair order')
  expect(within(dialog).getByPlaceholderText('Briefly describe the repair work or concern...')).toHaveValue('Check air leak')
  expect(within(dialog).getByRole('button', {name:/Select Freightliner/})).toHaveAttribute('aria-pressed','true')
  expect(submit).toBeEnabled()
  api.post.mockResolvedValueOnce({data:{...order,id:'new-order',order_number:'RO-NEW'}})
  fireEvent.click(submit)
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(api.post).toHaveBeenCalledTimes(2)
})

it.each(['/dashboard?selected=order-1&queue=on_floor&customer=customer-1', '/dashboard/customers?selected=customer-1'])('recovers truck and contact reads in place from %s', async (route) => {
  const base = api.get.getMockImplementation()!
  let failed = true
  api.get.mockImplementation((url: string) => failed && /customer-1\/(vehicles|contacts)$/.test(url) ? Promise.reject(new Error('Network unavailable')) : base(url))
  setup(route)
  expect(await screen.findByRole('button', {name:'Retry trucks'})).toBeVisible()
  expect(screen.getByRole('button', {name:'Retry contacts'})).toBeVisible()
  expect(screen.queryByText('No vehicles on file')).not.toBeInTheDocument()
  expect(screen.queryByText('Using company contact details above.')).not.toBeInTheDocument()
  failed = false
  fireEvent.click(screen.getByRole('button', {name:'Retry trucks'}))
  fireEvent.click(screen.getByRole('button', {name:'Retry contacts'}))
  expect(await screen.findByRole('button', {name:/Open .*Unit C-001/})).toBeVisible()
  expect(await screen.findByText('Using company contact details above.')).toBeVisible()
  expect(screen.getByTestId('location')).toHaveTextContent(route.split('?')[1])
  expect(api.post).not.toHaveBeenCalled()
})
it('provides an embedded customer retry and escape route without losing the order', async () => {
  const base = api.get.getMockImplementation()!
  let failed = true
  api.get.mockImplementation((url: string) => url === '/customers/customer-1' && failed ? Promise.reject(new Error('Unavailable')) : base(url))
  setup()
  expect(await screen.findByRole('button', {name:'Retry customer'})).toBeVisible()
  expect(screen.queryByRole('button', {name:'Edit Customer'})).not.toBeInTheDocument()
  expect(screen.getByRole('button', {name:'Back to #RO-1'})).toBeVisible()
  failed = false
  fireEvent.click(screen.getByRole('button', {name:'Retry customer'}))
  expect(await screen.findByRole('region', {name:'Northline Logistics customer workspace'})).toBeVisible()
  fireEvent.click(screen.getByRole('button', {name:'Back to #RO-1'}))
  expect(screen.getByTestId('location')).toHaveTextContent('?selected=order-1&queue=on_floor')
})
it('can return to the order even while the customer request is unresolved', async () => {
  const base = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string) => url === '/customers/customer-1' ? new Promise(() => {}) : base(url))
  setup()
  expect(await screen.findByText('Loading customer workspace…')).toBeVisible()
  fireEvent.click(await screen.findByRole('button', {name:'Back to #RO-1'}))
  expect(screen.getByTestId('location')).toHaveTextContent('?selected=order-1&queue=on_floor')
  expect(screen.queryByRole('region', {name:'Customer workspace'})).not.toBeInTheDocument()
})
