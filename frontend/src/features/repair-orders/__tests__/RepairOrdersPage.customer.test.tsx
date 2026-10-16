import type { ReactNode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const authState = vi.hoisted(() => ({ user: { id: 'actor-1', tenant_id: 'tenant-1', role: 'garage_owner' }, authSessionEpoch: 1 }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: Object.assign((select: (state: typeof authState) => unknown) => select(authState), { getState: () => authState }) }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ presentationVariant: 'new', accentColors: { 500: '#d97706' } }) }))
vi.mock('../PriceBuilderPanel', () => ({ default: ({ workspaceNotice, onClose, onOpenCustomer, onOpenVehicleHistory }: { workspaceNotice?: ReactNode; onClose: () => void; onOpenCustomer: () => void; onOpenVehicleHistory?: () => void }) => <section aria-label="Repair order work">{workspaceNotice}Repair order workspace<button onClick={onClose}>Close repair order</button><button onClick={onOpenCustomer}>Open customer</button>{onOpenVehicleHistory && <button onClick={onOpenVehicleHistory}>View vehicle history</button>}</section> }))
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
import RepairOrdersPage from '../RepairOrdersPage'
import CustomersPage from '../../customers/CustomersPage'
const order = { id: 'order-1', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1', order_number: 'RO-1', status: 'in_progress', total_cost: '145', total_parts_cost: '0', total_labor_cost: '145', created_at: '2026-10-12T12:00:00Z', updated_at: '2026-10-12T12:00:00Z', parts_usage: [], labor_items: [], history_events: [] }
const customer = { id: 'customer-1', company_name: 'Northline Logistics', first_name: 'Nora', last_name: 'North', email: 'nora@example.invalid', created_at: '2026-10-12T12:00:00Z', balance: '145' }
const vehicle = { id: 'vehicle-1', tenant_id: 'tenant-1', customer_id: 'customer-1', unit_number: 'C-001', year: 2021, make: 'Freightliner', model: 'Cascadia', vin: '1FUJGLDR4DLAA0001' }
function Probe() { return <output data-testid="location">{useLocation().search}</output> }
beforeEach(() => {
  vi.clearAllMocks()
  authState.user = { id: 'actor-1', tenant_id: 'tenant-1', role: 'garage_owner' }
  authState.authSessionEpoch = 1
  api.get.mockImplementation((url: string) => {
    if (url === '/vehicles/vehicle-1') return Promise.resolve({ data: vehicle })
    if (url === '/vehicles/vehicle-1/external-services') return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
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
function setup(initialEntry: string | string[] = '/dashboard?selected=order-1&queue=on_floor&customer=customer-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={Array.isArray(initialEntry) ? initialEntry : [initialEntry]}><Routes><Route path='/dashboard/customers' element={<CustomersPage />} /><Route path='/dashboard/*' element={<RepairOrdersPage />} /></Routes><Probe /></MemoryRouter></QueryClientProvider>)
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
  fireEvent.click(await within(screen.getByRole('region', {name:'Northline Logistics customer workspace'})).findByRole('button', {name:'New repair order',exact:true}))
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


it('closes to the queue after a customer round trip instead of reopening a historical order', async () => {
  setup(['/dashboard?queue=on_floor', '/dashboard?selected=order-1&queue=on_floor'])
  fireEvent.click(await screen.findByRole('button', { name: 'Open customer', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Back to #RO-1' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Close repair order', exact: true }))
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('?queue=on_floor'))
  expect(screen.queryByText('Repair order workspace')).not.toBeInTheDocument()
  expect(api.post).not.toHaveBeenCalled()
  expect(api.put).not.toHaveBeenCalled()
})

it('closes a direct-linked order while retaining list filters and removing record-only context', async () => {
  setup('/dashboard/repair-orders?selected=order-1&queue=on_floor&customer_vehicle=vehicle-1&operation=labor-1&recommendation=rec-1&filter=active')
  fireEvent.click(await screen.findByRole('button', { name: 'Close repair order', exact: true }))
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('?queue=on_floor&filter=active'))
  expect(screen.queryByText('Repair order workspace')).not.toBeInTheDocument()
})

it('opens the exact order truck when transferred or absent from the first customer-truck page', async () => {
  const base = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string) => {
    if (url === '/customers/customer-1/vehicles') return Promise.resolve({ data: [] })
    if (url === '/vehicles/vehicle-1') return Promise.resolve({ data: { ...vehicle, customer_id: 'new-owner' } })
    return base(url)
  })
  setup('/dashboard?selected=order-1&queue=on_floor&filter=active')
  fireEvent.click(await screen.findByRole('button', { name: 'View vehicle history' }))
  expect(await screen.findByRole('heading', { name: 'Repair history (1)' })).toBeVisible()
  expect(screen.getByText(vehicle.vin)).toBeVisible()
  expect(api.get).toHaveBeenCalledWith('/vehicles/vehicle-1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  expect(screen.getByTestId('location')).toHaveTextContent('customer=customer-1&customer_vehicle=vehicle-1')
  expect(screen.getByTestId('location')).toHaveTextContent('filter=active')
  expect(screen.queryByRole('button', { name: 'History', exact: true })).not.toBeInTheDocument()
})

it('restores explicit vehicle history after reload and clears its URL context on both back steps', async () => {
  setup('/dashboard?selected=order-1&queue=on_floor&filter=active&customer=customer-1&customer_vehicle=vehicle-1')
  expect(await screen.findByText(vehicle.vin)).toBeVisible()
  expect(await screen.findByRole('heading', { name: 'Repair history (1)' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Back to Northline Logistics' }))
  expect(screen.getByTestId('location')).not.toHaveTextContent('customer_vehicle')
  expect(screen.getByTestId('location')).toHaveTextContent('customer=customer-1')
  fireEvent.click(screen.getByRole('button', { name: 'Back to #RO-1' }))
  expect(screen.getByTestId('location').textContent).toBe('?selected=order-1&queue=on_floor&filter=active')
  fireEvent.click(screen.getByRole('button', { name: 'Open customer' }))
  expect(screen.getByTestId('location')).not.toHaveTextContent('customer_vehicle')
  expect(await screen.findByRole('button', { name: 'History', exact: true })).toBeVisible()
})

it('shows exact-truck loading and failure without falling back to company controls, then retries', async () => {
  const base = api.get.getMockImplementation()!
  let rejectVehicle!: (error: Error) => void
  api.get.mockImplementation((url: string) => url === '/vehicles/vehicle-1' ? new Promise((_, reject) => { rejectVehicle = reject }) : base(url))
  setup('/dashboard?selected=order-1&queue=on_floor&customer=customer-1&customer_vehicle=vehicle-1')
  expect(await screen.findByText('Loading vehicle history…')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Back to Northline Logistics' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Edit Customer' })).not.toBeInTheDocument()
  await act(async () => rejectVehicle(new Error('Unavailable')))
  expect(await screen.findByRole('button', { name: 'Retry vehicle history' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'History', exact: true })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit vehicle' })).not.toBeInTheDocument()
  api.get.mockImplementation(base)
  fireEvent.click(screen.getByRole('button', { name: 'Retry vehicle history' }))
  expect(await screen.findByText(vehicle.vin)).toBeVisible()
  fireEvent.click(await screen.findByRole('button', { name: 'Open repair order RO-1' }))
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('?selected=order-1&queue=on_floor'))
  expect(api.post).not.toHaveBeenCalled()
  expect(api.put).not.toHaveBeenCalled()
})

it.each([{ id: 'wrong-truck' }, { tenant_id: 'other-tenant' }])('rejects an exact-truck response with mismatched scope %o', async (mismatch) => {
  const base = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string) => url === '/vehicles/vehicle-1' ? Promise.resolve({ data: { ...vehicle, ...mismatch } }) : base(url))
  setup('/dashboard?selected=order-1&queue=on_floor&customer=customer-1&customer_vehicle=vehicle-1')
  expect(await screen.findByRole('button', { name: 'Retry vehicle history' })).toBeVisible()
  expect(screen.queryByText(vehicle.vin)).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: /Repair history/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Back to Northline Logistics' }))
  expect(screen.getByTestId('location')).not.toHaveTextContent('customer_vehicle')
})

it('scopes exact-truck cache to tenant, actor, role and auth session', async () => {
  const client = setup('/dashboard?selected=order-1&queue=on_floor&customer=customer-1&customer_vehicle=vehicle-1')
  expect(await screen.findByText(vehicle.vin)).toBeVisible()
  expect(client.getQueryData(['customerVehicles', 'customer-1', 'selected', 'tenant-1', 'actor-1', 'garage_owner', 1, 'vehicle-1'])).toEqual(vehicle)
  const base = api.get.getMockImplementation()!
  let resolveNew!: (value: { data: typeof vehicle }) => void
  api.get.mockImplementation((url: string) => url === '/vehicles/vehicle-1' ? new Promise(resolve => { resolveNew = resolve }) : base(url))
  await act(async () => {
    authState.user = { id: 'actor-2', tenant_id: 'tenant-1', role: 'garage_admin' }
    authState.authSessionEpoch = 2
    client.setQueryData(['customer', 'customer-1'], { ...customer, phone: '555-010-0002' })
  })
  expect(await screen.findByText('Loading vehicle history…')).toBeVisible()
  expect(screen.queryByText(vehicle.vin)).not.toBeInTheDocument()
  await act(async () => resolveNew({ data: vehicle }))
  expect(await screen.findByText(vehicle.vin)).toBeVisible()
  expect(client.getQueryData(['customerVehicles', 'customer-1', 'selected', 'tenant-1', 'actor-2', 'garage_admin', 2, 'vehicle-1'])).toEqual(vehicle)
})

it('keeps enriched owner and operating-authority facts when opening the exact truck', async () => {
  const base = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string) => url === '/vehicles/vehicle-1'
    ? Promise.resolve({ data: { ...vehicle, owner_company_name: 'Current Truck Owner LLC', operating_authority_company_name: 'Current Truck Operator LLC' } }) : base(url))
  setup('/dashboard?selected=order-1&queue=on_floor&customer=customer-1&customer_vehicle=vehicle-1')
  expect(await screen.findByText('Current Truck Owner LLC')).toBeVisible()
  expect(screen.getByText('Current Truck Operator LLC')).toBeVisible()
})

it('offers recovery without live truck controls when the exact vehicle is archived', async () => {
  const base = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string) => url === '/vehicles/vehicle-1'
    ? Promise.reject({ response: { status: 404, data: { detail: 'Vehicle not found' } } }) : base(url))
  setup('/dashboard?selected=order-1&queue=on_floor&customer=customer-1&customer_vehicle=vehicle-1')
  expect(await screen.findByRole('button', { name: 'Retry vehicle history' })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Edit vehicle' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add outside service' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Edit Customer' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Back to Northline Logistics' }))
  expect(screen.getByTestId('location')).not.toHaveTextContent('customer_vehicle')
})


it('keeps typed customer search and page through a cancelled truck order and allows clearing it afterward', async () => {
  const base = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string, options?: { params?: { skip?: number } }) => url === '/customers'
    ? Promise.resolve({ data: { items: [customer], total: 26, has_more: !options?.params?.skip } }) : base(url))
  setup('/dashboard/customers?view=list&filter=active')
  await screen.findByRole('button', { name: 'Open Northline Logistics customer workspace' })
  const search = screen.getByRole('searchbox', { name: 'Search customers' })
  fireEvent.change(search, { target: { value: 'Northline' } })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/customers', expect.objectContaining({ params: expect.objectContaining({ search: 'Northline' }) })))
  fireEvent.click(screen.getByRole('button', { name: 'Next', exact: true }))
  await screen.findByText('26–26 of 26 customers')
  fireEvent.click(screen.getByRole('button', { name: 'Open Northline Logistics customer workspace', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(screen.getByRole('button', { name: 'New repair order', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'New Repair Order' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Back to Northline Logistics' }))
  fireEvent.click(screen.getByRole('button', { name: 'Back to Customers' }))
  expect(screen.getByRole('searchbox', { name: 'Search customers' })).toHaveValue('Northline')
  expect(screen.getByText('26–26 of 26 customers')).toBeInTheDocument()
  expect(screen.getByTestId('location')).toHaveTextContent('filter=active')
  api.get.mockClear()
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search customers' }), { target: { value: '' } })
  expect(screen.getByRole('searchbox', { name: 'Search customers' })).toHaveValue('')
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search customers' }), { target: { value: 'Other' } })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/customers', expect.objectContaining({ params: expect.objectContaining({ search: 'Other', skip: 0 }) })))
  expect(api.post).not.toHaveBeenCalled()
  expect(api.put).not.toHaveBeenCalled()
})


afterEach(() => vi.unstubAllGlobals())

it('never drains order pages behind contextual customer intake and resumes after cancel', async () => {
  const callbacks: IntersectionObserverCallback[] = []
  vi.stubGlobal('IntersectionObserver', vi.fn((callback: IntersectionObserverCallback) => {
    callbacks.push(callback)
    return { observe: vi.fn(), disconnect: vi.fn() }
  }))
  const baseGet = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string, config?: { params?: { skip?: number } }) => {
    if (url === '/repair-orders') return Promise.resolve({ data: { items: [{ ...order, id: `order-${config?.params?.skip ?? 0}` }], total: 100, has_more: (config?.params?.skip ?? 0) === 0 } })
    return baseGet(url, config)
  })
  setup('/dashboard?newCustomer=customer-1&newVehicle=vehicle-1')
  const dialog = await screen.findByRole('dialog', { name: 'New Repair Order' })
  expect(dialog).toHaveTextContent('Northline Logistics')
  expect(await within(dialog).findByRole('button', { name: /Select Freightliner/ })).toHaveAttribute('aria-pressed', 'true')
  const emitVisible = () => callbacks.forEach(callback => callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver))
  await act(async () => { emitVisible() })
  expect(api.get.mock.calls.filter(([url, config]) => url === '/repair-orders' && config?.params?.skip > 0)).toHaveLength(0)
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel', exact: true }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New Repair Order' })).not.toBeInTheDocument())
  await act(async () => { emitVisible() })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ params: expect.objectContaining({ skip: 25 }) })))
  expect(api.post).not.toHaveBeenCalled()
})

it.each([true, false])('sends only an explicitly selected call token and preserves it after save failure (selected=%s)', async selected => {
  const option = { reference_token: 'signed-reference', call_id: 'private-call-id', opportunity_id: 'private-op-id', started_at: '2026-10-14T15:00:00Z', contact_label: 'Shop contact', service_summary: 'Tire repair', expires_at: '2026-10-15T15:00:00Z' }
  api.post.mockImplementation((url: string) => url.endsWith('/originating-call-options')
    ? Promise.resolve({ data: { options: [option] } }) : Promise.reject(new Error('offline')))
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(await within(screen.getByRole('region', { name: 'Northline Logistics customer workspace' })).findByRole('button', { name: 'New repair order', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'New Repair Order' })
  if (selected) {
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link originating call' }))
    fireEvent.click(await within(dialog).findByRole('radio', { name: /Shop contact/ }))
  }
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create Repair Order' }))
  await within(dialog).findByRole('alert')
  const payload = api.post.mock.calls.find(([url]) => url === '/repair-orders')![1]
  expect(payload.originating_call_reference).toBe(selected ? 'signed-reference' : undefined)
  expect(payload).not.toHaveProperty('call_id')
  expect(payload).not.toHaveProperty('opportunity_id')
  if (selected) expect(within(dialog).getByRole('radio', { name: /Shop contact/ })).toBeChecked()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  fireEvent.click(await within(screen.getByRole('region', { name: 'Northline Logistics customer workspace' })).findByRole('button', { name: 'New repair order', exact: true }))
  const reopened = await screen.findByRole('dialog', { name: 'New Repair Order' })
  expect(within(reopened).queryByRole('radio')).not.toBeInTheDocument()
})

it.each(['fleet_manager', 'customer', 'driver'])('removes call selection and its payload after changing to %s', async role => {
  const option = { reference_token: 'signed-reference', call_id: 'call-1', opportunity_id: 'op-1', started_at: '2026-10-14T15:00:00Z', contact_label: 'Shop contact', service_summary: 'Tire repair', expires_at: '2026-10-15T15:00:00Z' }
  api.post.mockImplementation((url: string) => url.endsWith('/originating-call-options')
    ? Promise.resolve({ data: { options: [option] } }) : Promise.reject(new Error('offline')))
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(await within(screen.getByRole('region', { name: 'Northline Logistics customer workspace' })).findByRole('button', { name: 'New repair order', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'New Repair Order' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Link originating call' }))
  fireEvent.click(await within(dialog).findByRole('radio', { name: /Shop contact/ }))
  authState.user = { ...authState.user, role }
  fireEvent.change(within(dialog).getByPlaceholderText('Briefly describe the repair work or concern...'), { target: { value: 'Tire repair' } })
  expect(within(dialog).queryByText('Originating call')).not.toBeInTheDocument()
  expect(within(dialog).queryByRole('radio')).not.toBeInTheDocument()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create Repair Order' }))
  await within(dialog).findByRole('alert')
  expect(api.post.mock.calls.find(([url]) => url === '/repair-orders')![1]).not.toHaveProperty('originating_call_reference')
})

it('keeps history-filter focus after order cancellation and restores return focus on the next cancellation', async () => {
  setup('/dashboard/customers?view=list&filter=active&selected=customer-1')
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  const cancelOrder = async () => {
    fireEvent.click(screen.getByRole('button', {name:'New repair order',exact:true}))
    const dialog = await screen.findByRole('dialog', {name:'New Repair Order'})
    fireEvent.click(within(dialog).getByRole('button', {name:'Cancel'}))
    await waitFor(() => expect(screen.getByRole('button', {name:'New repair order',exact:true})).toHaveFocus())
  }
  await cancelOrder()
  const search = screen.getByRole('searchbox', {name:'Search this truck’s repair history'})
  search.focus()
  fireEvent.change(search, {target:{value:'R'}})
  await act(async () => { await new Promise(resolve => requestAnimationFrame(resolve)) })
  expect(search).toHaveFocus()
  fireEvent.change(search, {target:{value:'RO'}})
  const status = screen.getByRole('combobox', {name:'Repair history status'})
  status.focus()
  fireEvent.change(status, {target:{value:'in_progress'}})
  await act(async () => { await new Promise(resolve => requestAnimationFrame(resolve)) })
  expect(status).toHaveFocus()
  expect(screen.getByTestId('location')).toHaveTextContent('filter=active')
  expect(screen.getByRole('button',{name:'Edit vehicle'})).toBeVisible()
  await cancelOrder()
  expect(screen.getByRole('searchbox',{name:'Search this truck’s repair history'})).toHaveValue('RO')
  expect(screen.getByRole('combobox',{name:'Repair history status'})).toHaveValue('in_progress')
  expect(api.post).not.toHaveBeenCalled()
})


it('reloads the truck chosen after cancellation with its own history filters', async () => {
  const otherVehicle = { ...vehicle, id: 'vehicle-2', unit_number: 'C-002', vin: '1FUJGLDR4DLAA0002' }
  const baseGet = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string, options?: unknown) => {
    if (url === '/customers/customer-1/vehicles') return Promise.resolve({ data: [vehicle, otherVehicle] })
    if (url === '/customers/customer-1/vehicles/vehicle-2' || url === '/vehicles/vehicle-2') return Promise.resolve({ data: otherVehicle })
    if (url === '/repair-orders') return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
    return baseGet(url, options)
  })
  setup('/dashboard/customers?view=list&selected=customer-1')
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'New repair order', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'New Repair Order' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel', exact: true }))
  fireEvent.click(await screen.findByRole('button', { name: 'Back to Northline Logistics' }))
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-002/ }))
  fireEvent.change(await screen.findByRole('searchbox', { name: 'Search this truck’s repair history' }), { target: { value: 'brake' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Repair history status' }), { target: { value: 'completed' } })
  expect(screen.getByTestId('location')).toHaveTextContent('vehicle=vehicle-2')
  const restoredRoute = `/dashboard/customers${screen.getByTestId('location').textContent}`
  cleanup()
  setup(restoredRoute)
  expect(await screen.findByRole('searchbox', { name: 'Search this truck’s repair history' })).toHaveValue('brake')
  expect(screen.getByRole('combobox', { name: 'Repair history status' })).toHaveValue('completed')
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ params: expect.objectContaining({ vehicle_id: 'vehicle-2', search: 'brake', status: 'completed' }) })))
  fireEvent.click(screen.getByRole('button', { name: 'Back to Northline Logistics' }))
  expect(screen.getByTestId('location')).not.toHaveTextContent('vehicle=')
  expect(screen.getByRole('region', { name: 'Account details' })).toBeVisible()
  expect(api.post).not.toHaveBeenCalled()
})

async function startOrderWithService() {
  const originalGet = api.get.getMockImplementation()!
  api.get.mockImplementation((url: string) => url === '/services/typeahead' ? Promise.resolve({ data: [{ id: 'service-1', name: 'Filter service', base_price: '15.00' }] }) : originalGet(url))
  setup()
  fireEvent.click(await screen.findByRole('button', { name: /Open .*Unit C-001/ }))
  fireEvent.click(await within(screen.getByRole('region', { name: 'Northline Logistics customer workspace' })).findByRole('button', { name: 'New repair order', exact: true }))
  const dialog = await screen.findByRole('dialog', { name: 'New Repair Order' })
  fireEvent.click(await within(dialog).findByRole('button', { name: 'Filter service', exact: true }))
  fireEvent.click(within(dialog).getByRole('button', { name: 'Create Repair Order' }))
  return dialog
}

it('retains the created order and original service request identity after an uncertain attachment', async () => {
  const { quote } = await import('@/features/parts-pricing/__tests__/fixtures')
  let writes = 0
  api.post.mockImplementation((url, body) => {
    if (url === '/repair-orders') return Promise.resolve({ data: { ...order, id: 'new-order', order_number: 'RO-NEW' } })
    if (url === '/parts-pricing/resolve') return Promise.resolve({ data: quote({ plan: body.plan, required: false }) })
    if (url.endsWith('/flat-service')) { writes++; return writes === 1 ? Promise.reject(new Error('offline')) : Promise.resolve({ data: { warnings: [] } }) }
    return Promise.resolve({ data: {} })
  })
  await startOrderWithService()
  const work = await screen.findByRole('region', { name: 'Repair order work' })
  expect(within(work).getByRole('alert')).toHaveTextContent('Your draft is kept')
  fireEvent.click(within(work).getByRole('button', { name: 'Retry remaining' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Retry remaining' })).not.toBeInTheDocument())
  expect(api.post.mock.calls.filter(([url]) => url === '/repair-orders')).toHaveLength(1)
  expect(api.post.mock.calls.filter(([url]) => url === '/parts-pricing/resolve')).toHaveLength(1)
  const writesMade = api.post.mock.calls.filter(([url]) => url.endsWith('/flat-service'))
  expect(writesMade).toHaveLength(2); expect(writesMade[1][2].headers).toEqual(writesMade[0][2].headers)
  expect(screen.getByTestId('location')).toHaveTextContent('selected=new-order')
})

it('keeps the created order when the service preview is cancelled and resumes without another create', async () => {
  const { quote } = await import('@/features/parts-pricing/__tests__/fixtures')
  api.post.mockImplementation((url, body) => url === '/repair-orders' ? Promise.resolve({ data: { ...order, id: 'new-order', order_number: 'RO-NEW' } }) : url === '/parts-pricing/resolve' ? Promise.resolve({ data: quote({ plan: body.plan }) }) : Promise.resolve({ data: { warnings: [] } }))
  await startOrderWithService()
  const review = await screen.findByRole('dialog', { name: 'Review parts pricing' }); fireEvent.click(within(review).getByRole('button', { name: 'Cancel' }))
  const work = await screen.findByRole('region', { name: 'Repair order work' })
  expect(within(work).getByRole('status', { name: 'Unfinished service attachment' })).toHaveTextContent('RO-NEW created')
  fireEvent.click(within(work).getByRole('button', { name: 'Retry remaining' })); fireEvent.click(await screen.findByRole('button', { name: 'Confirm price' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Retry remaining' })).not.toBeInTheDocument())
  expect(api.post.mock.calls.filter(([url]) => url === '/repair-orders')).toHaveLength(1); expect(api.post.mock.calls.filter(([url]) => url.endsWith('/flat-service'))).toHaveLength(1)
})

it.each(['Retry remaining', 'Keep current work'])('keeps recovery inside the ledger and %s reopens the same order', async action => {
  const { quote } = await import('@/features/parts-pricing/__tests__/fixtures')
  api.post.mockImplementation((url, body) => url === '/repair-orders' ? Promise.resolve({ data: { ...order, id: 'new-order', order_number: 'RO-NEW' } }) : url === '/parts-pricing/resolve' ? Promise.resolve({ data: quote({ plan: body.plan }) }) : Promise.resolve({ data: {} }))
  await startOrderWithService()
  fireEvent.click(within(await screen.findByRole('dialog', { name: 'Review parts pricing' })).getByRole('button', { name: 'Cancel' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Close repair order' }))
  const notice = await screen.findByRole('status', { name: 'Unfinished service attachment' })
  expect(notice.closest('section')).toHaveClass('db-repair-orders-new')
  fireEvent.click(within(notice).getByRole('button', { name: action }))
  if (action === 'Retry remaining') fireEvent.click(await screen.findByRole('button', { name: 'Confirm price' }))
  expect(await screen.findByRole('region', { name: 'Repair order work' })).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('status', { name: 'Unfinished service attachment' })).not.toBeInTheDocument())
  expect(screen.getByTestId('location')).toHaveTextContent('selected=new-order')
  expect(api.post.mock.calls.filter(([url]) => url === '/repair-orders')).toHaveLength(1)
  expect(api.post.mock.calls.filter(([url]) => url.endsWith('/flat-service'))).toHaveLength(action === 'Retry remaining' ? 1 : 0)
})

it.each(['preview', 'write'])('does not restore another actor\'s order recovery after pending service %s completes', async stage => {
  const { quote } = await import('@/features/parts-pricing/__tests__/fixtures')
  let settle!: (value: unknown) => void
  const pending = new Promise(resolve => { settle = resolve })
  api.post.mockImplementation((url, body) => url === '/repair-orders' ? Promise.resolve({ data: { ...order, id: 'new-order', order_number: 'RO-NEW' } }) : url === '/parts-pricing/resolve' ? stage === 'preview' ? pending : Promise.resolve({ data: quote({ plan: body.plan, required: false }) }) : pending)
  const dialog = await startOrderWithService()
  await waitFor(() => expect(api.post.mock.calls.some(([url]) => stage === 'preview' ? url === '/parts-pricing/resolve' : url.endsWith('/flat-service'))).toBe(true))
  authState.user = { id: 'actor-2', tenant_id: 'tenant-2', role: 'garage_owner' }; authState.authSessionEpoch++
  fireEvent.change(within(dialog).getByPlaceholderText('Briefly describe the repair work or concern...'), { target: { value: 'New session' } })
  await act(async () => { settle(stage === 'preview' ? { data: quote({ plan: { kind: 'service_apply', service_id: 'service-1', quantity: '1' }, required: false }) } : { data: { warnings: [] } }) })
  expect(screen.queryByRole('button', { name: 'Retry remaining' })).not.toBeInTheDocument(); expect(screen.queryByText('RO-NEW created')).not.toBeInTheDocument(); expect(screen.getByTestId('location')).not.toHaveTextContent('selected=new-order')
  if (stage === 'preview') expect(api.post.mock.calls.some(([url]) => url.endsWith('/flat-service'))).toBe(false)
})
