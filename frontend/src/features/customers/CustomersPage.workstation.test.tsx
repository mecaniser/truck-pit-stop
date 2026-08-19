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

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <CustomersPage />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function installApiFixture(pageCustomers: Customer[] = [customer]) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/customers') {
      return Promise.resolve({ data: { items: pageCustomers, total: pageCustomers.length, has_more: false } })
    }
    if (url === `/customers/${customer.id}`) return Promise.resolve({ data: customer })
    if (url === `/customers/${customer.id}/vehicles`) return Promise.resolve({ data: [] })
    if (url === `/customers/${customer.id}/contacts`) return Promise.resolve({ data: [] })
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
  })
})
