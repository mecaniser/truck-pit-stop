/**
 * The fleet builder shows what the work IS, not what each piece of it costs.
 *
 * A fleet manager scopes work standing at the truck; pricing is the shop's job
 * and the numbers are the server's. The panel therefore renders hours and
 * quantities per line and exactly one money figure — the visit total — and
 * these tests pin that, because it is the rule most easily lost the next time
 * someone reaches for parity with the shop's price builder.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

import { ThemeProvider } from '@/contexts/ThemeContext'
import FleetPriceBuilderPanel from '../FleetPriceBuilderPanel'

const ORDER_ID = 'ro-1'

const detail = {
  id: ORDER_ID,
  order_number: 'RO-000123',
  status: 'draft',
  description: 'Air leak at the rear axle',
  is_internal: true,
  is_fleet_work: true,
  is_pm: false,
  bill_labor_at_customer_rate: false,
  assigned_mechanic_id: null,
  mileage_in: 621_565,
  mileage_out: null,
  customer_company_name: 'House Account',
  customer_first_name: null,
  customer_last_name: null,
  vehicle_unit_number: '603',
  vehicle_year: 2020,
  vehicle_make: 'VOLVO',
  vehicle_model: 'VNR',
  vehicle_vin: null,
  history_events: [
    {
      id: 'ev-1',
      event_type: 'part_added',
      label: 'Part added',
      detail: 'Air line fitting × 2',
      actor_name: 'Dana Fleet',
      created_at: '2026-09-01T15:04:00Z',
    },
  ],
  labor_items: [],
  parts_usage: [],
}

/** Distinctive amounts, so a leak into the line rows is unmistakable. */
const summary = {
  order_id: ORDER_ID,
  labor_total: '160.00',
  parts_total: '47.53',
  total_cost: '207.53',
  pricing_locked: false,
  can_edit_work: true,
  lines: [
    {
      id: 'line-1',
      repair_order_id: ORDER_ID,
      description: 'Replace air line',
      hours: '2.00',
      hourly_rate: '80.00',
      total_cost: '160.00',
      mechanic_id: null,
    },
  ],
  parts: [
    {
      id: 'part-1',
      repair_order_id: ORDER_ID,
      inventory_id: 'inv-1',
      inventory_sku: 'AL-9921',
      inventory_name: 'Air line fitting',
      quantity: '2',
      unit_type: 'each',
      unit_price: '23.765',
      unit_cost: '23.765',
      list_price: '41.00',
      savings: '0.00',
      total_price: '47.53',
      source_service_id: null,
      source_line_id: 'line-1',
      created_at: '2026-09-01T15:04:00Z',
    },
  ],
  warnings: [],
}

function mockQueries(overrides: Record<string, unknown> = {}) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === `/repair-orders/${ORDER_ID}/detail`) {
      return Promise.resolve({ data: { ...detail, ...overrides } })
    }
    if (url === `/repair-orders/${ORDER_ID}/price-build`) {
      return Promise.resolve({ data: summary })
    }
    if (url === '/fleet/mechanics') return Promise.resolve({ data: [] })
    if (url === '/fleet/settings') {
      return Promise.resolve({ data: { internal_labor_rate: 80, labor_rate: 100 } })
    }
    return Promise.resolve({ data: [] })
  })
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <FleetPriceBuilderPanel
          repairOrderId={ORDER_ID}
          onClose={vi.fn()}
          onChanged={vi.fn()}
        />
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

afterEach(() => {
  vi.clearAllMocks()
  document.body.style.overflow = ''
})

describe('FleetPriceBuilderPanel', () => {
  it('shows the work and the visit total, but no per-line money', async () => {
    mockQueries()
    const user = userEvent.setup()
    const { container } = renderPanel()

    // A line summarises itself; its parts appear when it is opened.
    await user.click(await screen.findByRole('button', {
      name: /Replace air line/, expanded: false,
    }))
    expect(await screen.findByText('Air line fitting')).toBeInTheDocument()
    expect(screen.getByText('AL-9921')).toBeInTheDocument()

    // One money figure, and it is the visit total.
    expect(screen.getByText('$207.53')).toBeInTheDocument()
    const amounts = (container.textContent || '').match(/\$[\d,]+\.\d{2}/g) ?? []
    expect(amounts).toEqual(['$207.53'])

    // None of the per-line figures the shop builder would show — checked with
    // the line expanded, which is where they would surface if they leaked.
    for (const leaked of ['160.00', '80.00', '47.53', '23.76', '41.00']) {
      expect(container.textContent).not.toContain(leaked)
    }
  })

  it('names which pricing the truck is on', async () => {
    mockQueries()
    renderPanel()
    expect(await screen.findByText('House account · at cost')).toBeInTheDocument()
  })

  it('says when a member truck bills labor at the customer rate', async () => {
    mockQueries({ bill_labor_at_customer_rate: true })
    renderPanel()
    expect(
      await screen.findByText('At-cost parts · customer labor rate'),
    ).toBeInTheDocument()
  })

  it('names the carrier on a customer-billed fleet order', async () => {
    mockQueries({ is_internal: false, customer_company_name: 'Elis Logistics' })
    renderPanel()
    expect(await screen.findByText('Billed to Elis Logistics')).toBeInTheDocument()
  })

  it('shows who did what and when, beside the work rather than under it', async () => {
    // Activity is a second view of the order, so it is a peer of the work list
    // and takes the same room — not a button parked under the mechanic.
    mockQueries()
    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole('tab', { name: /Activity/ }))

    expect(await screen.findByText('Part added')).toBeInTheDocument()
    expect(screen.getByText(/Dana Fleet/)).toBeInTheDocument()
    // Switching views replaces the work list rather than stacking below it.
    expect(screen.queryByText('Replace air line')).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: /Work & parts/ }))
    expect(await screen.findByText('Replace air line')).toBeInTheDocument()
  })

  it('offers availability, not price, when searching parts', async () => {
    mockQueries()
    apiMocks.get.mockImplementation((url: string, config?: { params?: { q?: string } }) => {
      if (url === `/repair-orders/${ORDER_ID}/detail`) return Promise.resolve({ data: detail })
      if (url === `/repair-orders/${ORDER_ID}/price-build`) return Promise.resolve({ data: summary })
      if (url === '/fleet/mechanics') return Promise.resolve({ data: [] })
      if (url === '/fleet/settings') {
        return Promise.resolve({ data: { internal_labor_rate: 80, labor_rate: 100 } })
      }
      if (url === '/inventory/typeahead' && config?.params?.q === 'filter') {
        return Promise.resolve({
          data: [{
            id: 'inv-2', sku: 'OF-7', name: 'Oil filter',
            stock_quantity: 12, on_order_quantity: 0, unit_type: 'each',
            // The endpoint returns cost; the picker must not surface it.
            cost: '10.00', selling_price: '25.00',
          }],
        })
      }
      return Promise.resolve({ data: [] })
    })

    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole('tab', { name: 'Part' }))
    await user.type(screen.getByLabelText('Search parts'), 'filter')

    expect(await screen.findByText('Oil filter')).toBeInTheDocument()
    expect(screen.getByText(/12 on hand/)).toBeInTheDocument()
    expect(screen.queryByText(/\$10\.00|\$25\.00/)).not.toBeInTheDocument()
  })

  it('keeps PM scope separate from work found during the PM', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === `/repair-orders/${ORDER_ID}/detail`) {
        return Promise.resolve({ data: { ...detail, is_pm: true } })
      }
      if (url === `/repair-orders/${ORDER_ID}/price-build`) return Promise.resolve({ data: summary })
      if (url === '/fleet/pm-service-catalog') {
        return Promise.resolve({
          data: [{ service_id: 'svc-1', name: 'Oil & filter', duration_minutes: 60 }],
        })
      }
      if (url === `/fleet/work-orders/${ORDER_ID}/pm-services`) {
        return Promise.resolve({ data: [{ service_id: 'svc-1' }] })
      }
      if (url === '/fleet/mechanics') return Promise.resolve({ data: [] })
      if (url === '/fleet/settings') {
        return Promise.resolve({ data: { internal_labor_rate: 80, labor_rate: 100 } })
      }
      return Promise.resolve({ data: [] })
    })

    renderPanel()

    // The PM's own scope, and the discovered work, are both present and distinct.
    expect(await screen.findByText('PM scope')).toBeInTheDocument()
    const pmService = await screen.findByText('Oil & filter')
    expect(pmService.closest('button')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Replace air line')).toBeInTheDocument()
  })

  it('lets the manager write the complaint an empty order arrives without', async () => {
    // An order opened from the yard has no description: the server stopped
    // stamping a placeholder, so the field is genuinely empty until someone
    // says what is wrong.
    mockQueries({ description: null })
    apiMocks.put.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    renderPanel()

    const box = await screen.findByLabelText('Complaint')
    expect(box).toHaveValue('')

    // Chips beat spelling it out on a tablet keyboard.
    await user.click(screen.getByRole('button', { name: /Air leak/ }))
    expect(box).toHaveValue('Air leak')

    await user.click(screen.getByRole('button', { name: /Save complaint/ }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(
      `/repair-orders/${ORDER_ID}`,
      { description: 'Air leak' },
    ))
  })

  it('keeps every complaint suggestion reachable in one scrolling row', async () => {
    // The chips are a fixed set with no search behind them, so capping the
    // rendered count would make the tail unreachable. One row that scrolls,
    // faded at the edge, is what says it continues.
    mockQueries({ description: null })
    const { container } = renderPanel()
    await screen.findByLabelText('Complaint')

    const row = container.querySelector('.wo-chips-scroll')
    expect(row).not.toBeNull()
    expect(row!.querySelectorAll('.wo-chip')).toHaveLength(10)
    for (const chip of ['Air leak', 'Oil leak', "Won't start"]) {
      expect(within(row as HTMLElement).getByText(chip)).toBeInTheDocument()
    }
  })

  it('puts the add bar above the list it fills', async () => {
    mockQueries()
    const { container } = renderPanel()
    await screen.findByText('Replace air line')

    const addWork = screen.getByRole('heading', { name: 'Add work' })
    const workTab = screen.getByRole('tab', { name: /Work & parts/ })
    // You add work, then you see it accumulate — not the reverse.
    expect(addWork.compareDocumentPosition(workTab))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('asks for hours on work the shop has never done, then sends them', async () => {
    // A custom operation comes back with estimated_hours 0.00, and the server
    // requires at least 0.01 — so forwarding the candidate's own hours was
    // refused with a 422 the panel surfaced nowhere. Add read as a dead button.
    mockQueries()
    apiMocks.post.mockImplementation((url) => {
      if (url.endsWith('/repair-ops/search')) {
        return Promise.resolve({
          data: {
            candidates: [{
              operation_id: 'custom:weld-bracket',
              name: 'Weld Bracket',
              description: 'New custom repair operation.',
              estimated_hours: '0.00',
              provider: 'internal_library',
            }],
            warnings: [],
          },
        })
      }
      return Promise.resolve({ data: {} })
    })

    const user = userEvent.setup()
    renderPanel()

    await user.type(await screen.findByLabelText('Search operations'), 'weld bracket')
    expect(await screen.findByText('Weld Bracket')).toBeInTheDocument()
    // It says why it needs input rather than claiming '0m book time'.
    expect(screen.getByText(/set how long it takes/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Increase duration/ }))
    await user.click(screen.getByRole('button', { name: /^Add$/ }))

    await waitFor(() => {
      const applyCall = apiMocks.post.mock.calls.find(
        (call) => String(call[0]).endsWith('/repair-ops/apply'),
      )
      expect(applyCall).toBeTruthy()
      // Whatever the operator entered — never the candidate's unusable 0.00.
      expect(Number(applyCall[1].estimated_hours)).toBeGreaterThan(0)
    })
  })

  it('does not offer editing once the order is frozen', async () => {
    mockQueries()
    apiMocks.get.mockImplementation((url: string) => {
      if (url === `/repair-orders/${ORDER_ID}/detail`) {
        return Promise.resolve({ data: { ...detail, status: 'completed' } })
      }
      if (url === `/repair-orders/${ORDER_ID}/price-build`) {
        return Promise.resolve({ data: { ...summary, can_edit_work: false } })
      }
      if (url === '/fleet/mechanics') return Promise.resolve({ data: [] })
      if (url === '/fleet/settings') {
        return Promise.resolve({ data: { internal_labor_rate: 80, labor_rate: 100 } })
      }
      return Promise.resolve({ data: [] })
    })

    renderPanel()
    await screen.findByText('Replace air line')

    expect(screen.queryByRole('tab', { name: 'Operation' })).not.toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^Remove / })).not.toBeInTheDocument())
  })
})
