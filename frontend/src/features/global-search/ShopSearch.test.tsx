import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { garageOwnerSession } from '@/test-fixtures/db035/staffSession'
import { ShopSearchButton, ShopSearchProvider } from './ShopSearch'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get } }))

const customer = { id: 'customer-1', first_name: 'Nora', last_name: 'North', company_name: 'Northline', email: 'nora@example.test', phone: '555-0100' }
const vehicle = { id: 'vehicle-1', customer_id: customer.id, unit_number: '144', year: 2020, make: 'Freightliner', model: 'Cascadia', vin: 'VIN144', license_plate: 'ABC144' }
const order = { id: 'order-1', order_number: 'TPS-144', customer_company_name: 'Northline', vehicle_unit_number: '144', description: 'Brake repair' }
const part = { id: 'part-1', name: 'Brake pad', sku: 'BP-144', stock_quantity: 0 }
const responses: Record<string, unknown[]> = { '/customers/typeahead': [customer], '/vehicles/typeahead': [vehicle], '/repair-orders': [order], '/inventory/typeahead': [part] }

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderSearch() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboard']}>
    <ShopSearchProvider><ShopSearchButton /><LocationProbe /></ShopSearchProvider>
  </MemoryRouter></QueryClientProvider>)
  return { ...view, client }
}

async function openSearch(query?: string) {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Search shop' }))
  const input = screen.getByRole('textbox', { name: 'Search shop records' })
  if (query) await user.type(input, query)
  return { user, input }
}

beforeEach(() => {
  useAuthStore.setState({ user: { ...garageOwnerSession }, isAuthenticated: true, authProvider: 'legacy', authSessionEpoch: 4, logoutInProgress: false })
  apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: responses[url] ?? [] }))
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
})
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})

describe('staff shop search', () => {
  it('does not fetch while closed or below the minimum, and debounces rapid typing', async () => {
    renderSearch()
    expect(apiMocks.get).not.toHaveBeenCalled()
    const { input } = await openSearch('a')
    expect(screen.getByText('Enter at least 2 characters to search.')).toBeInTheDocument()
    expect(apiMocks.get).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: 'br' } })
    fireEvent.change(input, { target: { value: 'brake' } })
    expect(apiMocks.get).not.toHaveBeenCalled()
    await screen.findByRole('link', { name: /Brake pad/ })
    expect(apiMocks.get).toHaveBeenCalledTimes(4)
    expect(apiMocks.get).toHaveBeenCalledWith('/customers/typeahead', expect.objectContaining({ params: { q: 'brake', limit: 5 }, signal: expect.any(AbortSignal) }))
    expect(apiMocks.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ params: { search: 'brake', limit: 5, skip: 0 } }))
    expect(apiMocks.get).toHaveBeenCalledWith('/inventory/typeahead', expect.objectContaining({ params: { q: 'brake', limit: 5, in_stock: false } }))
  })

  it.each([
    [/Northline 555/, '/dashboard/customers?selected=customer-1'],
    [/Unit 144 · 2020/, '/dashboard/customers?selected=customer-1&vehicle=vehicle-1'],
    [/RO TPS-144/, '/dashboard/repair-orders?selected=order-1'],
    [/Brake pad/, '/dashboard/garage/inventory?selected=part-1'],
  ])('opens the original result through its detail link (%s)', async (label, destination) => {
    renderSearch()
    const { user } = await openSearch('144')
    await user.click(await screen.findByRole('link', { name: label }))
    expect(screen.getByTestId('location')).toHaveTextContent(destination)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('supports Cmd/Ctrl K, arrow browsing, Enter, Escape and return focus', async () => {
    renderSearch()
    const trigger = screen.getByRole('button', { name: 'Search shop' })
    trigger.focus()
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    const input = await screen.findByRole('textbox', { name: 'Search shop records' })
    await waitFor(() => expect(input).toHaveFocus())
    fireEvent.change(input, { target: { value: '144' } })
    const customerLink = await screen.findByRole('link', { name: /Northline 555/ })
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(customerLink).toHaveFocus()
    fireEvent.keyDown(customerLink, { key: 'ArrowDown' })
    expect(screen.getByRole('link', { name: /Unit 144 · 2020/ })).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowUp' })
    fireEvent.keyDown(customerLink, { key: 'ArrowUp' })
    expect(input).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('textbox')).toHaveValue('')
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '144' } })
    await screen.findByRole('link', { name: /Northline 555/ })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'ArrowDown' })
    await userEvent.keyboard('{Enter}')
    expect(screen.getByTestId('location')).toHaveTextContent('/dashboard/customers?selected=customer-1')
  })

  it('clears results immediately when a query is shortened and ignores cancelled old responses', async () => {
    let resolveOld!: (value: { data: unknown[] }) => void
    const oldRequest = new Promise<{ data: unknown[] }>(resolve => { resolveOld = resolve })
    apiMocks.get.mockImplementation((_url: string, config: { params: { q?: string; search?: string } }) => (config.params.q ?? config.params.search) === 'old' ? oldRequest : Promise.resolve({ data: [] }))
    renderSearch()
    const { input } = await openSearch('old')
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledTimes(4))
    const signals = apiMocks.get.mock.calls.map(call => call[1].signal as AbortSignal)
    fireEvent.change(input, { target: { value: 'n' } })
    expect(screen.getByText('Enter at least 2 characters to search.')).toBeInTheDocument()
    expect(signals.every(signal => signal.aborted)).toBe(true)
    await act(async () => { resolveOld({ data: [customer] }) })
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledTimes(4)
    fireEvent.change(input, { target: { value: 'new' } })
    expect(await screen.findByText('No matches for “new”')).toBeInTheDocument()
    expect(screen.queryByText('Northline')).not.toBeInTheDocument()
  })

  it('hides settled results while a replacement query is still debouncing', async () => {
    renderSearch()
    const { input } = await openSearch('144')
    await screen.findByRole('link', { name: /Northline 555/ })
    fireEvent.change(input, { target: { value: 'other' } })
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).getByRole('status')).toHaveTextContent('Searching…')
  })

  it('announces a single matching record in the singular', async () => {
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url === '/customers/typeahead' ? [customer] : [] }))
    renderSearch()
    await openSearch('Northline')
    expect(await screen.findByText('1 result')).toBeInTheDocument()
  })

  it('keeps successful groups usable when one source fails, and retries only that source', async () => {
    apiMocks.get.mockImplementation((url: string) => url === '/vehicles/typeahead' ? Promise.reject(new Error('Unavailable')) : Promise.resolve({ data: responses[url] }))
    renderSearch()
    const { user } = await openSearch('144')
    expect(await screen.findByRole('link', { name: /Brake pad/ })).toBeInTheDocument()
    expect(await screen.findByText('Vehicles unavailable.')).toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).getByRole('status')).toHaveTextContent('Some sources unavailable')
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: responses[url] }))
    await user.click(screen.getByRole('button', { name: 'Retry vehicles' }))
    expect(await screen.findByRole('link', { name: /Unit 144 · 2020/ })).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledTimes(5)
  })

  it('aborts pending requests and removes search cache on close', async () => {
    apiMocks.get.mockImplementation(() => new Promise(() => {}))
    const { client } = renderSearch()
    const { user } = await openSearch('144')
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledTimes(4))
    const signals = apiMocks.get.mock.calls.map(call => call[1].signal as AbortSignal)
    await user.click(screen.getByRole('button', { name: 'Close search' }))
    expect(signals.every(signal => signal.aborted)).toBe(true)
    await waitFor(() => expect(client.getQueryCache().findAll({ queryKey: ['shop-search'] })).toHaveLength(0))
  })

  it.each(['customer', 'driver', 'fleet_manager', 'super_admin'] as const)('does not expose staff search to %s', role => {
    useAuthStore.setState({ user: { ...garageOwnerSession, role } })
    renderSearch()
    expect(screen.queryByRole('button', { name: 'Search shop' })).not.toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(apiMocks.get).not.toHaveBeenCalled()
  })

  it('limits mechanic sources to customer, vehicle and repair-order workflows', async () => {
    useAuthStore.setState({ user: { ...garageOwnerSession, role: 'mechanic' } })
    renderSearch()
    await openSearch('144')
    await screen.findByRole('link', { name: /RO TPS-144/ })
    expect(screen.queryByRole('heading', { name: 'Inventory' })).not.toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledTimes(3)
  })

  it.each(['tenant', 'user', 'epoch', 'logout'] as const)('discards the open query and results on a %s change', async kind => {
    const { client } = renderSearch()
    await openSearch('144')
    await screen.findByRole('link', { name: /Brake pad/ })
    expect(client.getQueryCache().findAll()[0].queryKey[1]).toContain('tenant-wisconsin')
    act(() => {
      if (kind === 'tenant') useAuthStore.setState({ user: { ...garageOwnerSession, tenant_id: 'tenant-other' } })
      if (kind === 'user') useAuthStore.setState({ user: { ...garageOwnerSession, id: 'other-user' } })
      if (kind === 'epoch') useAuthStore.setState({ authSessionEpoch: 5 })
      if (kind === 'logout') useAuthStore.setState({ logoutInProgress: true })
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Northline')).not.toBeInTheDocument()
    if (kind !== 'logout') {
      await openSearch()
      expect(screen.getByRole('textbox')).toHaveValue('')
      expect(within(screen.getByRole('dialog')).queryByRole('link')).not.toBeInTheDocument()
    }
  })

  it('does not search without an active authenticated tenant session', () => {
    useAuthStore.setState({ user: { ...garageOwnerSession, tenant_id: null } })
    renderSearch()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    act(() => useAuthStore.setState({ user: { ...garageOwnerSession }, isAuthenticated: false }))
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    act(() => useAuthStore.setState({ isAuthenticated: true, user: { ...garageOwnerSession, is_active: false } }))
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
