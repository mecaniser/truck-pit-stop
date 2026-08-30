import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))
const themeState = vi.hoisted(() => ({ presentationVariant: 'legacy' as 'legacy' | 'new' }))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
  },
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({
    accentColors: { 400: '#f59e0b', 500: '#d97706', 600: '#b45309', primary: '#2563eb' },
    presentationVariant: themeState.presentationVariant,
  }),
}))

vi.mock('../PriceBuilderPanel', () => ({
  default: () => null,
}))

import type { PartsUsage, RepairOrderHistoryEvent } from '../../../types'
import REPAIR_ORDER_CSS from '../../../index.css?inline'
import RepairOrdersPage from '../RepairOrdersPage'
import { buildPartHistoryEvents } from '../repairOrderHistory'

function renderPage(
  initialEntries: string[] = ['/'],
  props: React.ComponentProps<typeof RepairOrdersPage> = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <RepairOrdersPage {...props} />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="repair-orders-location">{location.search}</output>
}

describe('RepairOrdersPage request cancellation', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    themeState.presentationVariant = 'legacy'
  })

  it('switches only the Repair Orders presentation while preserving the same page API', async () => {
    const order = {
      id: 'order-presentation', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1',
      vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_year: 2022, vehicle_unit_number: '218', vehicle_vin: 'VIN218',
      customer_company_name: 'Northline Logistics', order_number: 'RO-1017', status: 'in_progress',
      description: 'Diagnose intermittent no-start', customer_notes: null, internal_notes: null,
      assigned_mechanic_id: null, total_parts_cost: '2780.50', total_labor_cost: '1500.00', total_cost: '4280.50',
      created_at: '2026-08-12T12:00:00Z', updated_at: '2026-08-12T15:00:00Z',
    }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') return Promise.resolve({ data: { items: [order], total: 1, has_more: false } })
      return Promise.resolve({ data: {} })
    })

    themeState.presentationVariant = 'new'
    const { unmount } = renderPage()
    expect(await screen.findByRole('region', { name: 'Repair order ledger' })).toBeInTheDocument()
    expect(await screen.findByRole('article', { name: 'Repair order RO-1017' })).toBeInTheDocument()
    expect(document.querySelector('.db-repair-orders-new')).toBeInTheDocument()
    unmount()

    themeState.presentationVariant = 'legacy'
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Repair Orders' })).toHaveClass('text-white')
    expect(screen.queryByRole('region', { name: 'Repair order ledger' })).not.toBeInTheDocument()
    expect(document.querySelector('.db-repair-orders-new')).not.toBeInTheDocument()
  })

  it('keeps a completed new-presentation repair order in the clipped canonical workspace region, not a modal drawer', async () => {
    const order = {
      id: 'workspace-order', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1',
      vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_year: 2022, vehicle_unit_number: '218', vehicle_vin: 'VIN218',
      customer_company_name: 'Northline Logistics', order_number: 'RO-2018', status: 'completed',
      description: 'Replace damaged air line', customer_notes: null, internal_notes: null,
      assigned_mechanic_id: null, total_parts_cost: '0.00', total_labor_cost: '0.00', total_cost: '0.00',
      created_at: '2026-08-12T12:00:00Z', updated_at: '2026-08-12T15:00:00Z',
    }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') return Promise.resolve({ data: { items: [order], total: 1, has_more: false } })
      if (url === '/repair-orders/workspace-order/workspace') return Promise.resolve({ data: order })
      return Promise.resolve({ data: {} })
    })
    themeState.presentationVariant = 'new'

    renderPage(['/?selected=workspace-order'])

    const workspace = await screen.findByRole('region', { name: '#RO-2018' })
    expect(workspace).toBeInTheDocument()
    expect(workspace).toHaveClass('db-repair-order-detail-new--price-builder')
    expect(REPAIR_ORDER_CSS).toMatch(
      /\.db-repair-order-detail-new--price-builder\s*>\s*\.slide-panel-content\s*\{[^}]*clip-path:\s*inset\(0 round var\(--db-repair-order-content-clip-radius\)\)/,
    )
    expect(document.querySelector('.db-repair-orders-workspace--detail-open')).toBeInTheDocument()
    expect(document.querySelector('[role="dialog"]')).not.toBeInTheDocument()
    expect(workspace).not.toHaveFocus()
  })

  it('keeps a Shop Work lane through ordinary ledger selection until the operator chooses All orders', async () => {
    const queueOrder = {
      id: 'queue-order', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1',
      vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_year: 2022, vehicle_unit_number: '218', vehicle_vin: 'VIN218',
      customer_company_name: 'Northline Logistics', order_number: 'RO-QUEUE-1', status: 'draft',
      description: 'Queue repair', customer_notes: null, internal_notes: null, assigned_mechanic_id: null,
      total_parts_cost: '0.00', total_labor_cost: '0.00', total_cost: '0.00',
      created_at: '2026-08-12T12:00:00Z', updated_at: '2026-08-12T15:00:00Z',
    }
    const siblingOrder = { ...queueOrder, id: 'sibling-order', order_number: 'RO-QUEUE-2', description: 'Follow-up repair' }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') return Promise.resolve({ data: { items: [queueOrder, siblingOrder], total: 2, has_more: false } })
      if (url === '/dashboard/action-queue') return Promise.resolve({
        data: {
          orders_needing_action: [queueOrder, siblingOrder].map((order) => ({
            id: order.id,
            order_number: order.order_number,
            status: order.status,
            description: order.description,
            customer_name: order.customer_company_name,
            vehicle_info: `${order.vehicle_year} ${order.vehicle_make} ${order.vehicle_model}`,
            total_cost: order.total_cost,
            updated_at: order.updated_at,
            mechanic_name: null,
            work_started_at: null,
            hold_reason: null,
            held_at: null,
            quote_sent: null,
          })),
          orders_needing_action_has_more: false,
          orders_on_floor: [],
          orders_on_floor_has_more: false,
          orders_ready_to_close: [],
          orders_ready_to_close_has_more: false,
        },
      })
      if (url === '/repair-orders/queue-order/workspace') return Promise.resolve({ data: queueOrder })
      if (url === '/repair-orders/sibling-order/workspace') return Promise.resolve({ data: siblingOrder })
      return Promise.resolve({ data: {} })
    })
    themeState.presentationVariant = 'new'

    renderPage(['/?selected=queue-order&queue=needs_action'])

    expect(await screen.findByRole('article', { name: 'Repair order RO-QUEUE-2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Repair Orders scope: Needs Action, 2 orders' })).toBeInTheDocument()
    expect(screen.queryByText('2 total')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show details for RO-QUEUE-2' }))
    expect(screen.getByTestId('repair-orders-location')).toHaveTextContent('?selected=queue-order&queue=needs_action')
    expect(apiMocks.get).not.toHaveBeenCalledWith('/repair-orders/sibling-order/workspace')
    fireEvent.click(screen.getByRole('button', { name: 'Open repair order RO-QUEUE-2' }))
    await waitFor(() => expect(screen.getByTestId('repair-orders-location')).toHaveTextContent('?selected=sibling-order&queue=needs_action'))

    fireEvent.click(screen.getByRole('button', { name: 'Repair Orders scope: Needs Action, 2 orders' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'All repair orders' }))
    await waitFor(() => expect(screen.getByTestId('repair-orders-location')).toHaveTextContent('?selected=sibling-order'))
  })

  it('uses the daily workset in place without falling back to the legacy queue or archive page', async () => {
    const queueOrder = {
      id: 'daily-order', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1',
      vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_year: 2022, vehicle_unit_number: '218', vehicle_vin: 'VIN218',
      customer_company_name: 'Northline Logistics', order_number: 'RO-DAILY-1', status: 'pending_review',
      description: 'Confirm customer authorization', customer_notes: null, internal_notes: null, assigned_mechanic_id: null,
      total_parts_cost: '80.00', total_labor_cost: '120.00', total_cost: '200.00',
      created_at: '2026-08-14T12:00:00Z', updated_at: '2026-08-14T15:00:00Z',
    }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/dashboard/daily-workset') return Promise.resolve({
        data: {
          timezone: 'America/New_York', business_date: '2026-08-14', next_reset_at: '2026-08-15T04:00:00Z',
          needs_attention: { items: [{
            id: queueOrder.id, order_number: queueOrder.order_number, status: queueOrder.status,
            description: queueOrder.description, customer_name: queueOrder.customer_company_name,
            vehicle_info: '2022 Freightliner Cascadia · Unit 218', total_cost: queueOrder.total_cost,
            updated_at: queueOrder.updated_at, mechanic_name: null, work_started_at: null,
            hold_reason: null, held_at: null, quote_sent: false, paid_at: null,
          }], has_more: false },
          on_floor: { items: [], has_more: false },
          ready_to_close: { items: [], has_more: false },
          closed_today: { items: [], has_more: false },
        },
      })
      if (url === '/repair-orders/daily-order/workspace') return Promise.resolve({ data: queueOrder })
      if (url === '/dashboard/mechanics/options') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: {} })
    })
    themeState.presentationVariant = 'new'

    renderPage(['/?selected=daily-order&queue=needs_action'], { workbenchScope: 'daily' })

    expect(await screen.findByRole('region', { name: '#RO-DAILY-1' })).toBeInTheDocument()
    const row = screen.getByRole('article', { name: 'Repair order RO-DAILY-1' })
    expect(screen.getByRole('heading', { name: 'Shop Work' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Needs Action · today' })).toBeInTheDocument()
    expect(row).toHaveTextContent('Confirm customer authorization')
    expect(row).toHaveTextContent('200.00')
    expect(row).toHaveTextContent('Pending Review')
    expect(apiMocks.get).toHaveBeenCalledWith('/dashboard/daily-workset')
    expect(apiMocks.get).not.toHaveBeenCalledWith('/dashboard/action-queue')
    expect(apiMocks.get).not.toHaveBeenCalledWith('/repair-orders', expect.anything())
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

  it('uses the compact workspace projection for a deep-linked repair order', async () => {
    const order = {
      id: 'order-1',
      tenant_id: 'tenant-1',
      customer_id: 'customer-1',
      vehicle_id: 'vehicle-1',
      vehicle_make: 'Freightliner',
      vehicle_model: 'Cascadia',
      vehicle_year: 2024,
      vehicle_unit_number: '204',
      vehicle_vin: 'VIN204',
      customer_company_name: 'Northline Freight',
      order_number: 'RO-000001',
      status: 'draft',
      description: 'Deep-linked order',
      customer_notes: null,
      internal_notes: null,
      assigned_mechanic_id: null,
      total_parts_cost: '0.00',
      total_labor_cost: '0.00',
      total_cost: '0.00',
      created_at: '2026-07-24T12:00:00Z',
      updated_at: '2026-07-24T12:00:00Z',
    }

    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') {
        return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
      }
      if (url === '/repair-orders/order-1/workspace') return Promise.resolve({ data: order })
      if (url === '/repair-orders/order-1/price-build') {
        return Promise.resolve({
          data: {
            order_id: 'order-1', labor_total: '0.00', parts_total: '0.00', total_cost: '0.00',
            pricing_locked: false, lines: [], parts: [], warnings: [],
          },
        })
      }
      if (url === '/quotes?repair_order_id=order-1') return Promise.resolve({ data: null })
      return Promise.resolve({ data: {} })
    })

    renderPage(['/?selected=order-1'])

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith(
        '/repair-orders/order-1/workspace',
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      )
    })

    expect(apiMocks.get).not.toHaveBeenCalledWith(
      '/repair-orders/order-1/detail',
      expect.anything(),
    )
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

    const heading = await screen.findByRole('heading', { name: 'New Repair Order' })
    const dialog = heading.closest('[role="dialog"]')
    expect(dialog).toHaveClass('h-[100dvh]', 'overflow-hidden')
    expect(screen.getByTestId('new-repair-order-scroll-region')).toHaveClass(
      'overflow-y-auto',
      'overscroll-contain',
      'pb-[max(1.5rem,env(safe-area-inset-bottom))]',
    )
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
