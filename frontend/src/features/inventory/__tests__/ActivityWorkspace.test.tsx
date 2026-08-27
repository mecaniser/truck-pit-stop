import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get } }))

import ActivityWorkspace, { PartLifecycleSummary } from '../ActivityWorkspace'

const event = {
  id: 'event-1',
  inventory_id: 'part-1',
  category: 'stock',
  event_type: 'stock.adjusted',
  occurred_at: '2026-08-26T12:00:00Z',
  correlation_id: 'correlation-1',
  origin: 'live',
  inventory: { id: 'part-1', sku: 'AIR-1', name: 'Primary air filter' },
  actor: { id: 'user-1', name: 'Alex' },
  reason: { code: 'count_correction', note: 'Shelf count' },
  before: { stock_quantity: 4 },
  after: { stock_quantity: 6 },
  stock: { physical_on_hand: 6, held_for_checkout: 2, available_to_sell: 4, delta: 2, wac: '12.50' },
  money: null,
  payment: null,
  source: { type: 'inventory_movement', id: 'movement-1', number: 'MOV-100', href: '/dashboard/garage/inventory?activity=movement-1' },
}

function renderUi(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>)
}

describe('DB-045 inventory Activity workspace', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    vi.restoreAllMocks()
  })

  it('applies the frozen filter contract, follows cursor pages, and preserves source deep links', async () => {
    apiMocks.get.mockImplementation((_url: string, config?: { params?: Record<string, unknown> }) => Promise.resolve({
      data: { items: [event], next_cursor: config?.params?.cursor ? null : 'cursor-2' },
    }))
    const user = userEvent.setup()
    renderUi(<ActivityWorkspace />)

    expect(await screen.findByText('stock · adjusted')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /MOV-100/ })).toHaveAttribute('href', '/dashboard/garage/inventory?activity=movement-1')
    await user.type(screen.getByRole('searchbox', { name: 'Search Activity' }), 'filter')
    await user.selectOptions(screen.getByLabelText('Category'), 'stock')
    await user.type(screen.getByLabelText('Event type'), 'stock.adjusted, stock.reserved')
    await user.type(screen.getByLabelText('Actor ID'), 'user-1')
    await user.type(screen.getByLabelText('Source type'), 'inventory_movement')
    await user.type(screen.getByLabelText('Source ID'), 'movement-1')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/activity-events', {
      params: {
        category: 'stock',
        event_type: ['stock.adjusted', 'stock.reserved'],
        actor_id: 'user-1',
        source_type: 'inventory_movement',
        source_id: 'movement-1',
        search: 'filter',
        limit: 50,
      },
    }))
    await user.click(screen.getByRole('button', { name: /Next/ }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/activity-events', {
      params: expect.objectContaining({ cursor: 'cursor-2', limit: 50 }),
    }))
    await user.click(screen.getByRole('button', { name: /Previous/ }))
    expect(screen.getByText(/6 physical · 2 held · 4 available/)).toBeInTheDocument()
  })

  it('exports the identical active filters without pagination controls', async () => {
    const createObjectUrl = vi.fn(() => 'blob:activity')
    const revokeObjectUrl = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectUrl })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    apiMocks.get.mockImplementation((url: string) => url.endsWith('.csv')
      ? Promise.resolve({ data: 'occurred_at,event_type\n' })
      : Promise.resolve({ data: { items: [], next_cursor: null } }))
    const user = userEvent.setup()
    renderUi(<ActivityWorkspace inventoryId="part-1" compact />)

    await screen.findByText('No events match these filters.')
    await user.type(screen.getByRole('searchbox', { name: 'Search Activity' }), 'sale')
    await user.selectOptions(screen.getByLabelText('Category'), 'sales')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))

    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/activity-events/export.csv', {
      params: { inventory_id: 'part-1', category: 'sales', search: 'sale' },
      responseType: 'blob',
    }))
    expect(createObjectUrl).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:activity')
  })

  it('renders authoritative part lifecycle aggregates without inventing reconstructed history', async () => {
    apiMocks.get.mockResolvedValue({ data: {
      inventory_id: 'part-1',
      as_of: '2026-08-26T12:00:00Z',
      repairs: { units_used: '12.00', repair_order_count: 5, last_used_at: null },
      purchasing: { units_received: 20, receipt_count: 3, units_returned_to_vendor: 2, open_core_obligations: 1 },
      sales: { units_sold: 6, units_returned: 1, net_units: 5, gross_item_revenue: '300.00', discounts: '10.00', refunds: '50.00', net_item_revenue: '240.00', last_sold_at: null },
      activity: { event_count: 31, last_event_at: null },
    } })
    renderUi(<PartLifecycleSummary inventoryId="part-1" />)

    expect(await screen.findByRole('heading', { name: 'Lifecycle summary' })).toBeInTheDocument()
    expect(screen.getByText('12.00')).toBeInTheDocument()
    expect(screen.getByText('20')).toBeInTheDocument()
    expect(screen.getByText('$240.00')).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts/part-1/lifecycle-summary')
  })
})
