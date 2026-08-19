import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Customer } from '../../types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))
const themeState = vi.hoisted(() => ({ presentationVariant: 'new' as 'legacy' | 'new' }))

vi.mock('../../lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({
    accentColors: { 400: '#f59e0b', 500: '#d97706', 600: '#b45309', primary: '#2563eb' },
    presentationVariant: themeState.presentationVariant,
  }),
}))

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: 'shop_owner' } }),
}))

import CustomersPage from './CustomersPage'

const customer = {
  id: 'customer-1',
  first_name: 'Nora',
  last_name: 'North',
  company_name: 'Northline Logistics',
  email: 'dispatch@northline.test',
  phone: '(704) 555-0102',
  billing_address_line1: '100 Service Road',
  billing_address_line2: null,
  billing_city: 'Charlotte',
  billing_state: 'NC',
  billing_zip: '28202',
  billing_country: 'US',
  notes: null,
  auto_approval_threshold: null,
  usdot_number: '1234567',
  mc_number: '7654321',
  fleet_enabled: false,
  vehicle_count: 1,
  balance: '125.00',
  created_at: '2026-08-10T12:00:00Z',
  updated_at: '2026-08-12T12:00:00Z',
} as Customer

const secondCustomer = {
  ...customer,
  id: 'customer-2',
  first_name: 'Maya',
  last_name: 'Miles',
  company_name: 'Miles Freight',
  email: 'maya@miles.test',
  phone: '(704) 555-0118',
  usdot_number: null,
  mc_number: null,
  fleet_enabled: true,
  vehicle_count: 3,
  balance: '0.00',
} as Customer

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="customers-location">{location.search}</output>
}

function renderPage(initialEntry = '/dashboard/customers?view=list') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return {
    queryClient,
    ...render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <CustomersPage />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
    ),
  }
}

function installApiFixture(pageCustomers: Customer[] = [customer]) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/customers') {
      return Promise.resolve({ data: { items: pageCustomers, total: pageCustomers.length, has_more: false } })
    }
    const matchedCustomer = [customer, secondCustomer].find((candidate) => url === `/customers/${candidate.id}`)
    if (matchedCustomer) return Promise.resolve({ data: matchedCustomer })
    if (/\/customers\/[^/]+\/(vehicles|contacts)$/.test(url)) return Promise.resolve({ data: [] })
    return Promise.resolve({ data: [] })
  })
}

describe('DB-035C customer workstation', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    themeState.presentationVariant = 'new'
  })

  it('opens the canonical page-owned workspace and preserves unrelated query state', async () => {
    installApiFixture()
    renderPage()

    fireEvent.click(await screen.findByRole('row', { name: /Northline Logistics/ }))

    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1'))
    expect(screen.getByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to Customers' })).toBeInTheDocument()
    expect(document.querySelector('.db-customers-workspace--detail-open')).toBeInTheDocument()
  })

  it('restores a deep-linked customer using the existing customer endpoint', async () => {
    installApiFixture([])
    renderPage('/dashboard/customers?filter=active&selected=customer-1')

    expect(await screen.findByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/customers/customer-1')
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?filter=active&selected=customer-1')
  })

  it('moves focus into the workspace for keyboard activation and restores it on Back', async () => {
    installApiFixture()
    renderPage()

    const row = await screen.findByRole('row', { name: /Northline Logistics/ })
    row.focus()
    fireEvent.keyDown(row, { key: 'Enter' })

    const heading = await screen.findByRole('heading', { name: 'Northline Logistics' })
    await waitFor(() => expect(heading).toHaveFocus())
    fireEvent.click(screen.getByRole('button', { name: 'Back to Customers' }))

    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list'))
    await waitFor(() => expect(row).toHaveFocus())
  })

  it('retains the legacy Sidekick and leaves the physical URL unchanged', async () => {
    themeState.presentationVariant = 'legacy'
    installApiFixture()
    renderPage()

    fireEvent.click(await screen.findByRole('row', { name: /Northline Logistics/ }))

    expect(await screen.findByRole('dialog', { name: /Northline Logistics/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list')
    expect(document.querySelector('.db-customer-detail-workspace')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Details' })).not.toBeInTheDocument()
  })

  it('inspects a different customer without replacing the selected workspace or URL', async () => {
    installApiFixture([customer, secondCustomer])
    renderPage('/dashboard/customers?view=list&selected=customer-1')

    expect(await screen.findByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    const details = await screen.findAllByRole('button', { name: 'Details' })
    const requestsBeforeInspection = apiMocks.get.mock.calls.length
    fireEvent.click(details[1])

    expect(await screen.findByRole('region', { name: 'Miles Freight details' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Northline Logistics' })).toBeInTheDocument()
    expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-1')
    expect(apiMocks.get).toHaveBeenCalledTimes(requestsBeforeInspection)
    expect(details[1]).toHaveAttribute('aria-expanded', 'true')
  })

  it('keeps only one flat Details disclosure open and restores focus when it closes', async () => {
    installApiFixture([customer, secondCustomer])
    renderPage()

    const details = await screen.findAllByRole('button', { name: 'Details' })
    fireEvent.click(details[0])
    expect(await screen.findByRole('region', { name: 'Northline Logistics details' })).toBeInTheDocument()

    fireEvent.click(details[1])
    expect(screen.queryByRole('region', { name: 'Northline Logistics details' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Miles Freight details' })).toBeInTheDocument()
    expect(details[0]).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(details[1])
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Miles Freight details' })).not.toBeInTheDocument())
    await waitFor(() => expect(details[1]).toHaveFocus())
  })

  it('uses the explicit Open customer action to select an inspected record', async () => {
    installApiFixture([customer, secondCustomer])
    renderPage('/dashboard/customers?view=list&selected=customer-1')

    const details = await screen.findAllByRole('button', { name: 'Details' })
    fireEvent.click(details[1])
    fireEvent.click(await screen.findByRole('button', { name: 'Open customer' }))

    await waitFor(() => expect(screen.getByTestId('customers-location')).toHaveTextContent('?view=list&selected=customer-2'))
    expect(await screen.findByRole('region', { name: 'Miles Freight' })).toBeInTheDocument()
  })
})
