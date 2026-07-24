import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
  },
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({ accentColors: { primary: '#2563eb' } }),
}))

import type { PartsUsage, RepairOrderHistoryEvent } from '../../../types'
import RepairOrdersPage from '../RepairOrdersPage'
import { buildPartHistoryEvents } from '../repairOrderHistory'

function renderPage(initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <RepairOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RepairOrdersPage request cancellation', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
  })

  it('aborts an in-flight repair-order page request when the page unmounts', async () => {
    let resolveRequest: (() => void) | undefined
    const pendingRequest = new Promise<{ data: { items: []; total: number; has_more: boolean } }>((resolve) => {
      resolveRequest = () => resolve({ data: { items: [], total: 0, has_more: false } })
    })

    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') return pendingRequest
      return Promise.resolve({ data: url === '/dashboard/stats' ? { mechanic_workload: [] } : { labor_rate: 100 } })
    })

    const { unmount } = renderPage()

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    })

    const [, config] = apiMocks.get.mock.calls.find(([url]) => url === '/repair-orders')!
    const signal = config.signal as AbortSignal
    expect(signal.aborted).toBe(false)

    unmount()

    await waitFor(() => expect(signal.aborted).toBe(true))
    resolveRequest?.()
  })

  it('does not load workspace-only settings before an order workflow needs them', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') {
        return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
      }
      return Promise.resolve({ data: {} })
    })

    renderPage()

    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith(
      '/repair-orders',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))

    expect(apiMocks.get).not.toHaveBeenCalledWith('/admin/tax-fee-settings', expect.anything())
    expect(apiMocks.get).not.toHaveBeenCalledWith('/fleet/settings', expect.anything())
    expect(apiMocks.get).not.toHaveBeenCalledWith('/vehicles/undefined/relationships')
  })

  it('shows the selected company trucks as model-and-unit cards', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') {
        return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
      }
      if (url === '/customers/typeahead') {
        return Promise.resolve({
          data: [{
            id: 'customer-1', first_name: 'Elis', last_name: 'Logistics', company_name: 'ELIS LOGISTICS LLC',
            email: 'dispatch@elis.example', phone: null,
          }],
        })
      }
      if (url === '/vehicles/typeahead') {
        return Promise.resolve({
          data: [{
            id: 'vehicle-1', customer_id: 'customer-1', make: 'Freightliner', model: 'Cascadia',
            year: 2022, unit_number: '204', license_plate: 'ELIS-204', vin: 'VIN204',
          }],
        })
      }
      if (url === '/services/typeahead') return Promise.resolve({ data: [] })
      if (url === '/dashboard/stats') return Promise.resolve({ data: { mechanic_workload: [] } })
      return Promise.resolve({ data: { labor_rate: 100 } })
    })

    renderPage(['/?new=true'])

    await screen.findByRole('heading', { name: 'New Repair Order' })
    fireEvent.click(await screen.findByRole('button', { name: /choose a customer/i }))
    fireEvent.mouseDown(await screen.findByText('ELIS LOGISTICS LLC'))

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith('/vehicles/typeahead', expect.objectContaining({
        params: expect.objectContaining({ customer_id: 'customer-1', limit: 50 }),
      }))
    })
    expect(await screen.findByText('Available trucks')).toBeInTheDocument()
    expect(screen.getByText('Unit 204')).toBeInTheDocument()
    expect(screen.getByText('Freightliner Cascadia')).toBeInTheDocument()
    expect(screen.queryByText('2022 · ELIS-204')).not.toBeInTheDocument()
  })

  it('returns from the new-customer form to customer search without closing the repair-order modal', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') {
        return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
      }
      if (url === '/customers/typeahead') return Promise.resolve({ data: [] })
      if (url === '/services/typeahead') return Promise.resolve({ data: [] })
      if (url === '/dashboard/stats') return Promise.resolve({ data: { mechanic_workload: [] } })
      return Promise.resolve({ data: { labor_rate: 100 } })
    })

    renderPage(['/?new=true'])

    await screen.findByRole('heading', { name: 'New Repair Order' })
    fireEvent.click(await screen.findByRole('button', { name: /choose a customer/i }))
    fireEvent.mouseDown(await screen.findByRole('option', { name: /add new customer/i }))

    const backButton = await screen.findByRole('button', { name: 'Back to customer search' })
    expect(screen.getByPlaceholderText('Acme')).toBeInTheDocument()

    fireEvent.click(backButton)

    expect(screen.getByRole('heading', { name: 'New Repair Order' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /choose a customer/i })).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Acme')).not.toBeInTheDocument()
  })

  it('records normal and stock-override part additions in repair-order history', () => {
    const basePart: PartsUsage = {
      id: 'usage-1',
      repair_order_id: 'order-1',
      inventory_id: 'part-1',
      inventory_sku: 'BP-1',
      inventory_name: 'Brake Pad',
      quantity: '1',
      unit_type: 'each',
      unit_price: '50.00',
      unit_cost: '30.00',
      list_price: '50.00',
      savings: '0.00',
      total_price: '50.00',
      source_service_id: null,
      source_line_id: null,
      stock_shortage_override: false,
      created_at: '2026-07-19T10:00:00Z',
    }
    const events = buildPartHistoryEvents([
      basePart,
      {
        ...basePart,
        id: 'usage-2',
        inventory_id: 'part-2',
        inventory_name: 'Engine Oil',
        quantity: '2.50',
        unit_type: 'gallon',
        stock_shortage_override: true,
        created_at: '2026-07-19T10:05:00Z',
      },
    ])

    expect(events).toEqual([
      {
        id: 'part-usage-1',
        label: 'Part added to repair order',
        at: '2026-07-19T10:00:00Z',
        detail: 'Brake Pad · 1 ea',
        entityId: 'usage-1',
      },
      {
        id: 'part-usage-2',
        label: 'Part added with stock override',
        at: '2026-07-19T10:05:00Z',
        detail: 'Engine Oil · 2.50 gal',
        entityId: 'usage-2',
      },
    ])
  })

  it('prefers persisted quantity and removal events without duplicating the current part row', () => {
    const historyEvents: RepairOrderHistoryEvent[] = [
      {
        id: 'history-add',
        event_type: 'part_added',
        label: 'Part added to repair order',
        detail: 'Brake Pad · 2 ea',
        entity_id: 'usage-1',
        actor_name: 'Shop Admin',
        created_at: '2026-07-19T10:00:00Z',
      },
      {
        id: 'history-update',
        event_type: 'part_quantity_updated',
        label: 'Part quantity updated',
        detail: 'Brake Pad · 2 ea → 3 ea',
        entity_id: 'usage-1',
        actor_name: 'Shop Admin',
        created_at: '2026-07-19T10:01:00Z',
      },
      {
        id: 'history-remove',
        event_type: 'part_removed',
        label: 'Part removed from repair order',
        detail: 'Brake Pad · 3 ea',
        entity_id: 'usage-1',
        actor_name: 'Shop Admin',
        created_at: '2026-07-19T10:02:00Z',
      },
    ]

    expect(buildPartHistoryEvents([], historyEvents)).toEqual([
      {
        id: 'history-add',
        label: 'Part added to repair order',
        at: '2026-07-19T10:00:00Z',
        detail: 'Brake Pad · 2 ea',
        actor: 'Shop Admin',
        entityId: 'usage-1',
      },
      {
        id: 'history-update',
        label: 'Part quantity updated',
        at: '2026-07-19T10:01:00Z',
        detail: 'Brake Pad · 2 ea → 3 ea',
        actor: 'Shop Admin',
        entityId: 'usage-1',
      },
      {
        id: 'history-remove',
        label: 'Part removed from repair order',
        at: '2026-07-19T10:02:00Z',
        detail: 'Brake Pad · 3 ea',
        actor: 'Shop Admin',
        entityId: 'usage-1',
      },
    ])
  })

  it('preserves persisted admin override lifecycle events in repair-order history', () => {
    const historyEvents: RepairOrderHistoryEvent[] = [
      {
        id: 'history-admin-started',
        event_type: 'admin_override_started_work',
        label: 'Work started by admin override',
        detail: 'Technician assignment was bypassed; work is being handled outside the mechanic portal.',
        entity_id: null,
        actor_name: 'Shop Manager',
        created_at: '2026-07-19T10:03:00Z',
      },
      {
        id: 'history-admin-completed',
        event_type: 'admin_completed_work',
        label: 'Work marked complete by admin',
        detail: 'Admin completed override-started work without a technician assignment.',
        entity_id: null,
        actor_name: 'Shop Manager',
        created_at: '2026-07-19T10:20:00Z',
      },
      {
        id: 'history-admin-approved',
        event_type: 'admin_approved_completion',
        label: 'Completion approved by admin',
        detail: 'Admin reviewed and approved work completed outside the mechanic portal.',
        entity_id: null,
        actor_name: 'Shop Manager',
        created_at: '2026-07-19T10:25:00Z',
      },
    ]

    expect(buildPartHistoryEvents([], historyEvents)).toEqual([
      {
        id: 'history-admin-started',
        label: 'Work started by admin override',
        at: '2026-07-19T10:03:00Z',
        detail: 'Technician assignment was bypassed; work is being handled outside the mechanic portal.',
        actor: 'Shop Manager',
      },
      {
        id: 'history-admin-completed',
        label: 'Work marked complete by admin',
        at: '2026-07-19T10:20:00Z',
        detail: 'Admin completed override-started work without a technician assignment.',
        actor: 'Shop Manager',
      },
      {
        id: 'history-admin-approved',
        label: 'Completion approved by admin',
        at: '2026-07-19T10:25:00Z',
        detail: 'Admin reviewed and approved work completed outside the mechanic portal.',
        actor: 'Shop Manager',
      },
    ])
  })
})
