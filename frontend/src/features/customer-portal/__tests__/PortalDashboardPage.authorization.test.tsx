import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/authStore'
import type { Quote, RepairOrder } from '@/types'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/lib/api', () => ({
  default: { get: apiMocks.get },
}))

import PortalDashboardPage from '../PortalDashboardPage'

const order = (overrides: Partial<RepairOrder> = {}): RepairOrder => ({
  id: 'order-1',
  tenant_id: 'tenant-1',
  customer_id: 'customer-1',
  vehicle_id: 'vehicle-1',
  vehicle_make: 'Freightliner',
  vehicle_model: 'Cascadia',
  vehicle_year: 2022,
  vehicle_unit_number: '1047',
  vehicle_vin: '••••1234',
  order_number: 'RO-000001',
  status: 'in_progress',
  description: 'Additional electrical diagnosis',
  customer_notes: null,
  internal_notes: null,
  assigned_mechanic_id: null,
  total_parts_cost: '0.00',
  total_labor_cost: '1450.00',
  total_cost: '1450.00',
  created_at: '2026-08-11T12:00:00Z',
  updated_at: '2026-08-11T14:10:00Z',
  quote_sent: true,
  quote_approved: false,
  ...overrides,
})

const quote = (overrides: Partial<Quote> = {}): Quote => ({
  id: 'quote-2',
  tenant_id: 'tenant-1',
  repair_order_id: 'order-1',
  quote_number: 'Q-000002',
  total_amount: '1450.00',
  notes: null,
  expires_at: null,
  is_approved: false,
  is_declined: false,
  decline_notes: null,
  sent_to_customer: true,
  sent_at: '2026-08-11T14:00:00Z',
  created_at: '2026-08-11T13:55:00Z',
  updated_at: '2026-08-11T14:00:00Z',
  revision: 2,
  authorization_type: 'additional_work',
  previously_authorized_amount: '1000.00',
  delta_amount: '450.00',
  ...overrides,
})

function renderDashboard(repairOrders: RepairOrder[], latestQuote: Quote | null) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/customers/customer-1') {
      return Promise.resolve({ data: { id: 'customer-1', first_name: 'Casey', last_name: 'Customer' } })
    }
    if (url === '/vehicles') {
      return Promise.resolve({ data: { items: [], has_more: false, skip: 0, limit: 100 } })
    }
    if (url === '/repair-orders') {
      return Promise.resolve({ data: { items: repairOrders, has_more: false, skip: 0, limit: 100 } })
    }
    if (url === '/invoices') return Promise.resolve({ data: [] })
    if (url.startsWith('/quotes?repair_order_id=')) return Promise.resolve({ data: latestQuote })
    return Promise.reject(new Error(`Unhandled test request: ${url}`))
  })

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PortalDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('PortalDashboardPage authorization actions', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    useAuthStore.setState({
      user: {
        id: 'customer-user-1',
        email: 'casey@example.test',
        first_name: 'Casey',
        last_name: 'Customer',
        phone: null,
        role: 'customer',
        is_active: true,
        tenant_id: 'tenant-1',
        customer_id: 'customer-1',
      },
      isAuthenticated: true,
    })
  })

  it('shows review only for the latest published undecided authorization', async () => {
    renderDashboard([order()], quote())

    expect(await screen.findByText('Authorization awaiting review')).toBeInTheDocument()
    expect(screen.getByText('Review authorization')).toBeInTheDocument()
  })

  it('does not resurrect a declined authorization after work removal and finalization', async () => {
    renderDashboard(
      [order({ status: 'invoiced', total_cost: '1000.00', updated_at: '2026-08-11T15:00:00Z' })],
      quote({ is_declined: true, decline_notes: 'Please defer this work.' }),
    )

    expect(await screen.findByText('All paid up')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('Authorization awaiting review')).not.toBeInTheDocument()
      expect(screen.queryByText('Review authorization')).not.toBeInTheDocument()
      expect(screen.queryByText('Action required')).not.toBeInTheDocument()
    })
    expect(apiMocks.get).not.toHaveBeenCalledWith('/quotes?repair_order_id=order-1')
  })

  it('uses the canonical latest decision to exclude a declined active revision', async () => {
    renderDashboard([order()], quote({ is_declined: true }))

    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/quotes?repair_order_id=order-1'))
    expect(screen.queryByText('Authorization awaiting review')).not.toBeInTheDocument()
    expect(screen.queryByText('Review authorization')).not.toBeInTheDocument()
  })
})
