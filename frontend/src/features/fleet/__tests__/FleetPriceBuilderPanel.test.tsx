import { chooseSelectOption } from '@/test-utils/selectOption'
import type { OperationExecution, OperationPage } from '@/features/operation-execution/queries'
import { orderMaintenance, program, targetPreview, work } from '@/features/maintenance/__tests__/fixtures'
import type { TargetRequest } from '@/features/maintenance/contract'
import { quote } from '@/features/parts-pricing/__tests__/fixtures'
import type { ResolveRequest } from '@/features/parts-pricing/contract'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types'
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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: { ...apiMocks, post: (url: string, body: ResolveRequest, ...args: unknown[]) => url === '/parts-pricing/resolve' ? Promise.resolve({ data: quote({ plan: body.plan, projection: 'fleet', required: false }) }) : apiMocks.post(url, body, ...args) } }))
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
  vehicle_id: 'veh-1',
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

const operation: OperationExecution = {
  labor_id: 'line-1', description: 'Replace air line', mechanic_id: null, mechanic_name: null,
  status: 'pending', version: 2, completed_at: null, completed_by: null, tracked_seconds: 0,
  active_session: null, required_tasks_remaining: 0, can_assign: true, can_complete: true,
  can_reopen: false, can_start_timer: false, can_stop_timer: false,
}
function operationPage(item: OperationExecution, status = 'in_progress'): OperationPage {
  return { items: [item], summary: { tracked: item.status === null ? 0 : 1, completed: item.status === 'completed' ? 1 : 0, remaining: item.status === 'pending' ? 1 : 0, legacy_untracked: item.status === null ? 1 : 0 }, order_status: status, is_order_lead: false }
}

function mockQueries(overrides: Record<string, unknown> = {}) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === `/repair-orders/${ORDER_ID}/detail`) {
      return Promise.resolve({ data: { ...detail, ...overrides } })
    }
    if (url === `/repair-orders/${ORDER_ID}/price-build`) {
      return Promise.resolve({ data: summary })
    }
    if (url === `/repair-orders/${ORDER_ID}/operations`) return Promise.resolve({ data: operationPage({ ...operation, status: null, can_assign: false, can_complete: false, tracked_seconds: null }, String(overrides.status ?? detail.status)) })
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
  beforeEach(() => useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role: 'fleet_manager' } as User, authSessionEpoch: 1, logoutInProgress: false }))
  it('shows the work and the visit total, but no per-line money', async () => {
    mockQueries()
    const user = userEvent.setup()
    const { container } = renderPanel()

    // A line summarises itself; its parts appear when it is opened.
    await user.click(await screen.findByRole('button', {
      name: /^Replace air line/, expanded: false,
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

  it('routes a bundled operation through the fleet service preview and canonical attachment', async () => {
    mockQueries()
    apiMocks.post.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/repair-ops/search') ? { candidates: [{ operation_id: 'service:service-1', name: 'Filter service bundle', estimated_hours: '0.25', provider: 'service_catalog' }] } : summary }))
    const user = userEvent.setup(); renderPanel()
    await user.type(await screen.findByLabelText('Search operations'), 'filter service')
    const candidate = await screen.findByText('Filter service bundle')
    await user.click(within(candidate.closest('li')!).getByRole('button', { name: 'Add', exact: true }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith(`/repair-orders/${ORDER_ID}/price-build/flat-service`, { service_id: 'service-1', quantity: 1, pricing_preview_fingerprint: 'opaque-1', pricing_presentation: 'fleet' }, expect.objectContaining({ headers: { 'Idempotency-Key': expect.stringMatching(/^[0-9a-f-]{36}$/) } })))
    expect(apiMocks.post.mock.calls.some(([url]) => url.endsWith('/repair-ops/apply'))).toBe(false)
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
      if (url === '/fleet/trucks/veh-1/pm-services') {
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
    // A PM is one tier, not a basket: radio semantics, not checkbox.
    const row = pmService.closest('button')!
    expect(row).toHaveAttribute('role', 'radio')
    expect(row).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radiogroup', { name: 'PM scope' })).toBeInTheDocument()
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
    renderPanel()
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

  it('picks one PM, replacing rather than accumulating', async () => {
    // The API takes a list because a package could be composed, but this
    // catalog is tiers — Level A/B/C — so choosing one must deselect the other.
    apiMocks.get.mockImplementation((url: string) => {
      if (url === `/repair-orders/${ORDER_ID}/detail`) {
        return Promise.resolve({ data: { ...detail, is_pm: true, status: 'draft' } })
      }
      if (url === `/repair-orders/${ORDER_ID}/price-build`) return Promise.resolve({ data: summary })
      if (url === '/fleet/pm-service-catalog') {
        return Promise.resolve({
          data: [
            { service_id: 'svc-a', name: 'PM Level A', duration_minutes: 90 },
            { service_id: 'svc-b', name: 'PM Level B', duration_minutes: 120 },
          ],
        })
      }
      if (url === `/fleet/work-orders/${ORDER_ID}/pm-services`) {
        return Promise.resolve({ data: [{ service_id: 'svc-a' }] })
      }
      if (url === '/fleet/trucks/veh-1/pm-services') {
        return Promise.resolve({ data: [{ service_id: 'svc-a' }] })
      }
      if (url === '/fleet/mechanics') return Promise.resolve({ data: [] })
      if (url === '/fleet/settings') {
        return Promise.resolve({ data: { internal_labor_rate: 80, labor_rate: 100 } })
      }
      return Promise.resolve({ data: [] })
    })
    apiMocks.put.mockResolvedValue({ data: [] })

    const user = userEvent.setup()
    renderPanel()

    const levelA = (await screen.findByText('PM Level A')).closest('button')!
    expect(levelA).toHaveAttribute('aria-checked', 'true')

    await user.click(screen.getByText('PM Level B').closest('button')!)
    expect(screen.getByText('PM Level B').closest('button')!).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('PM Level A').closest('button')!).toHaveAttribute('aria-checked', 'false')

    // Saving sends exactly one id, not both.
    await user.click(screen.getByRole('button', { name: /Save PM scope/ }))
    await waitFor(() => {
      const call = apiMocks.put.mock.calls.find(
        (c) => String(c[0]).includes('/work-orders/') && String(c[0]).endsWith('/pm-services'),
      )
      expect(call).toBeTruthy()
      expect(call[1].service_ids).toEqual(['svc-b'])
    })
  })

  it('lets a manager abandon a visit they changed their mind about', async () => {
    // Emptying the work and parts is not enough: the order stays open, on the
    // board and in the shop's queue, until it is deleted or closed.
    mockQueries()
    apiMocks.delete.mockResolvedValue({ data: {} })
    const onClose = vi.fn()
    const user = userEvent.setup()

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <FleetPriceBuilderPanel repairOrderId={ORDER_ID} onClose={onClose} onChanged={vi.fn()} />
        </QueryClientProvider>
      </ThemeProvider>,
    )

    await user.click(await screen.findByRole('button', { name: /Delete this repair order/ }))
    // Deleting is confirmed, never a single tap on a touch surface.
    const dialog = await screen.findByRole('dialog', { name: /Delete this repair order/ })
    await user.click(within(dialog).getByRole('button', { name: 'Delete repair order' }))

    await waitFor(() => {
      expect(apiMocks.delete).toHaveBeenCalledWith(`/repair-orders/${ORDER_ID}`)
      // The panel closes: the visit it was showing no longer exists.
      expect(onClose).toHaveBeenCalled()
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

it('retains a grouped part quantity draft on stale CAS and retries with the refreshed fleet version', async () => {
  mockQueries()
  const originalGet = apiMocks.get.getMockImplementation()!
  apiMocks.get.mockImplementation((url: string) => url === `/repair-orders/${ORDER_ID}/price-build` ? Promise.resolve({ data: { ...summary, parts: summary.parts.map(part => ({ ...part, quantity: apiMocks.patch.mock.calls.length ? '5' : '2', pricing_version: apiMocks.patch.mock.calls.length ? 5 : 4 })) } }) : originalGet(url))
  apiMocks.patch.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'pricing_version_conflict', message: 'Saved quantity changed.' } } } }).mockResolvedValue({ data: {} })
  const user = userEvent.setup(); renderPanel(); await user.click(await screen.findByRole('button', { name: /^Replace air line/ })); await user.click(screen.getByRole('button', { name: 'Increase Quantity of Air line fitting' }))
  await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledWith(`/repair-orders/${ORDER_ID}/parts/part-1`, { quantity: 3, expected_pricing_version: 4, pricing_presentation: 'fleet' }))
  const conflict = await screen.findByText(/Saved quantity changed. Saved quantity 5/); const retry = within(conflict).getByRole('button', { name: 'Retry' }); expect(screen.getByLabelText('Quantity of Air line fitting')).toHaveValue('3'); await user.click(retry)
  await waitFor(() => expect(apiMocks.patch).toHaveBeenLastCalledWith(`/repair-orders/${ORDER_ID}/parts/part-1`, { quantity: 3, expected_pricing_version: 5, pricing_presentation: 'fleet' }))
})


it('assigns and completes the operation before reviewing maintenance and completing the fleet order', async () => {
  useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role: 'fleet_manager' } as User, authSessionEpoch: 1, logoutInProgress: false })
  mockQueries({ status: 'in_progress' })
  const originalGet = apiMocks.get.getMockImplementation()!
  const item = program('program-1', { vehicle_id: 'veh-1', work: work('link-1', { repair_order_id: ORDER_ID, operation_ids: ['line-1'] }) })
  apiMocks.get.mockImplementation((url: string, config?: { params?: { channel?: string } }) => { if (url.endsWith('/maintenance')) { if (config?.params?.channel !== 'fleet') return Promise.reject(new Error('422: fleet maintenance channel is required')); return Promise.resolve({ data: { ...orderMaintenance([item]), repair_order_id: ORDER_ID } }) } return originalGet(url, config) })
  const maintenanceGet = apiMocks.get.getMockImplementation()!
  let currentOperation = { ...operation }
  apiMocks.get.mockImplementation((url: string, config?: unknown) => {
    if (url.endsWith('/operations')) return Promise.resolve({ data: operationPage(currentOperation) })
    if (url === '/fleet/mechanics') return Promise.resolve({ data: [{ id: 'tech-1', name: 'Dana Mechanic' }] })
    if (url.endsWith('/checklist')) return Promise.resolve({ data: { items: [1, 2].map(index => ({ id: `task-${index}`, labor_id: 'line-1', service_name: 'Air line service', label: `Inspection ${index}`, required: true, position: index, is_completed: true, completed_at: '2026-10-16T12:00:00Z', completed_by: { id: 'user-1', name: 'Manager' }, version: 1 })), total: 2, skip: 0, limit: 100, summary: { total: 2, completed: 2, required: 2, required_remaining: 0 }, can_update: true } })
    return maintenanceGet(url, config)
  })
  apiMocks.put.mockImplementation(async (url: string, body: unknown) => {
    if (url.endsWith('/assignment')) {
      expect(body).toEqual({ expected_version: 2, mechanic_id: 'tech-1' })
      currentOperation = { ...currentOperation, mechanic_id: 'tech-1', mechanic_name: 'Dana Mechanic', version: 3 }
    } else if (url.endsWith('/completion')) {
      expect(body).toEqual({ expected_version: 3, is_completed: true })
      currentOperation = { ...currentOperation, status: 'completed', version: 4, can_assign: false, can_complete: false, can_reopen: true, completed_at: '2026-10-16T12:05:00Z', completed_by: { id: 'user-1', name: 'Manager' } }
    } else throw new Error(`Unexpected PUT ${url}`)
    return { data: operationPage(currentOperation) }
  })
  apiMocks.post.mockImplementation(async (url: string, body: TargetRequest) => {
    if (url.endsWith('/maintenance-target-preview')) { expect(currentOperation.status).toBe('completed'); return { data: targetPreview(body) } }
    if (url === `/fleet/work-orders/${ORDER_ID}/complete`) { expect(currentOperation.status).toBe('completed'); return { data: {} } }
    throw new Error(`Unexpected POST ${url}`)
  })
  const user = userEvent.setup(); renderPanel()
  await screen.findByText('Checklist · 2/2')
  expect(screen.getByRole('button', { name: 'Complete', exact: true })).toBeDisabled()
  expect(await screen.findByText('Complete 1 remaining operation before finishing.')).toBeVisible()
  await user.click(screen.getByRole('button', { name: /^Replace air line/ }))
  const technician = screen.getByRole('combobox', { name: 'Technician for Replace air line' })
  await waitFor(() => expect(technician).toBeEnabled())
  await chooseSelectOption(technician, 'tech-1', user)
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Technician for Replace air line' })).toHaveValue('tech-1'))
  const completeOperation = screen.getByRole('button', { name: 'Complete operation' })
  await waitFor(() => expect(completeOperation).toBeEnabled())
  await user.click(completeOperation)
  await screen.findByText('Completed')
  expect(apiMocks.put).toHaveBeenCalledTimes(2)
  expect(apiMocks.put).toHaveBeenNthCalledWith(1, `/repair-orders/${ORDER_ID}/operations/line-1/assignment`, { expected_version: 2, mechanic_id: 'tech-1' })
  expect(apiMocks.put).toHaveBeenNthCalledWith(2, `/repair-orders/${ORDER_ID}/operations/line-1/completion`, { expected_version: 3, is_completed: true })
  expect(apiMocks.post).not.toHaveBeenCalled()
  const completeOrder = screen.getByRole('button', { name: 'Complete', exact: true })
  await waitFor(() => expect(completeOrder).toBeEnabled())
  await user.click(completeOrder)
  const sheet = screen.getByRole('dialog', { name: 'Complete repair order' })
  await user.type(within(sheet).getByLabelText(/Odometer out/), '621566')
  await user.click(within(sheet).getByRole('button', { name: 'Complete' }))
  const firstReview = await screen.findByRole('dialog', { name: 'Review maintenance completion' })
  await waitFor(() => expect(firstReview).toContainElement(document.activeElement as HTMLElement))
  await user.keyboard('{Escape}')
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Review maintenance completion' })).not.toBeInTheDocument())
  expect(within(sheet).getByLabelText(/Odometer out/)).toHaveValue('621566')
  await user.click(within(sheet).getByRole('button', { name: 'Complete' }))
  const review = await screen.findByRole('dialog', { name: 'Review maintenance completion' })
  await user.click(within(review).getByText('Review targets'))
  await screen.findByLabelText('Target review')
  await user.click(within(review).getByRole('button', { name: 'Complete repair order' }))
  await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith(`/fleet/work-orders/${ORDER_ID}/complete`, expect.objectContaining({ mileage_out: 621566, maintenance_review: expect.objectContaining({ expected_review_fingerprint: 'review-1', expected_target_fingerprint: 'target-1', entries: [expect.objectContaining({ work_link_id: 'link-1', attestation: null })] }) })))
  expect(apiMocks.get).toHaveBeenCalledWith(`/repair-orders/${ORDER_ID}/maintenance`, expect.objectContaining({ params: { channel: 'fleet' } }))
})

it.each(['garage_owner', 'fleet_manager'] as const)('uses fleet review and deletion presentation for %s removing linked work in the fleet panel', async role => {
  useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role } as User, authSessionEpoch: 1, logoutInProgress: false }); mockQueries(); const originalGet = apiMocks.get.getMockImplementation()!
  const item = program('program-1', { vehicle_id: 'veh-1', work: work('link-1', { repair_order_id: ORDER_ID, operation_ids: ['line-1'] }) })
  apiMocks.get.mockImplementation((url: string, config?: { params?: { channel?: string } }) => { if (url.endsWith('/maintenance')) { if (config?.params?.channel !== 'fleet') return Promise.reject(new Error('422: fleet maintenance channel is required')); return Promise.resolve({ data: { ...orderMaintenance([item]), repair_order_id: ORDER_ID } }) } return originalGet(url, config) })
  apiMocks.delete.mockResolvedValue({ data: {} }); const user = userEvent.setup(); renderPanel(); await user.click(await screen.findByRole('button', { name: 'Remove Replace air line' })); const dialog = await screen.findByRole('dialog', { name: 'Remove work' }); expect(dialog).toHaveTextContent('Oil service'); await user.click(within(dialog).getByRole('button', { name: 'Remove work' }))
  await waitFor(() => expect(apiMocks.delete).toHaveBeenCalledWith(`/repair-orders/${ORDER_ID}/price-build/lines/line-1`, { params: { pricing_presentation: 'fleet', expected_maintenance_fingerprint: 'review-1' } })); expect(apiMocks.get).toHaveBeenCalledWith(`/repair-orders/${ORDER_ID}/maintenance`, expect.objectContaining({ params: { channel: 'fleet' } }))
})

it('keeps denied operation actions hidden and blocks fleet finalization while required work remains', async () => {
  useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role: 'fleet_manager' } as User })
  mockQueries({ status: 'in_progress' }); const originalGet = apiMocks.get.getMockImplementation()!
  apiMocks.get.mockImplementation((url: string) => url.endsWith('/operations') ? Promise.resolve({ data: operationPage({ ...operation, can_assign: false, can_complete: false, required_tasks_remaining: 1 }) }) : originalGet(url))
  const user = userEvent.setup(); renderPanel()
  await screen.findByText('Complete 1 remaining operation before finishing.')
  await user.click(screen.getByRole('button', { name: /^Replace air line/ }))
  expect(screen.queryByRole('combobox', { name: /Technician for/ })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Complete operation' })).not.toBeInTheDocument()
  expect(screen.getByText('1 required checklist task remaining.')).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Complete', exact: true }))
  expect(screen.queryByRole('dialog', { name: 'Complete repair order' })).not.toBeInTheDocument()
  expect(apiMocks.put).not.toHaveBeenCalled(); expect(apiMocks.post).not.toHaveBeenCalled()
})

it('does not complete or enter maintenance review after an operation write conflict and failed refresh', async () => {
  useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role: 'fleet_manager' } as User })
  mockQueries({ status: 'in_progress' }); const originalGet = apiMocks.get.getMockImplementation()!
  let progressUnavailable = false
  apiMocks.get.mockImplementation((url: string) => url.endsWith('/operations') ? progressUnavailable ? Promise.reject(new Error('Offline')) : Promise.resolve({ data: operationPage(operation) }) : originalGet(url))
  apiMocks.put.mockImplementation(async () => { progressUnavailable = true; throw { response: { status: 409, data: { detail: 'Operation changed. Review current progress.' } } } })
  const user = userEvent.setup(); renderPanel()
  await user.click(await screen.findByRole('button', { name: /^Replace air line/ }))
  const completeOperation = await screen.findByRole('button', { name: 'Complete operation' })
  await waitFor(() => expect(completeOperation).toBeEnabled()); await user.click(completeOperation)
  await screen.findByText(/Operation progress could not be refreshed/)
  expect(screen.getByRole('button', { name: 'Complete', exact: true })).toBeDisabled()
  expect(screen.queryByText('Completed')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Complete operation' })).not.toBeInTheDocument()
  expect(apiMocks.put).toHaveBeenCalledTimes(1); expect(apiMocks.post).not.toHaveBeenCalled()
  progressUnavailable = false
  await user.click(screen.getByRole('button', { name: 'Retry operation progress' }))
  await screen.findByRole('button', { name: 'Complete operation' })
  expect(screen.getByRole('button', { name: 'Complete', exact: true })).toBeDisabled()
  expect(apiMocks.put).toHaveBeenCalledTimes(1)
})
