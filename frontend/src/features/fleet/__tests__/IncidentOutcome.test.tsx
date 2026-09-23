/**
 * DB-070/071 — what happens to a road incident, and where it goes after.
 *
 * Resolving used to be a single blind PATCH carrying only `status`, and a
 * resolved incident then vanished from the only page that showed it. These
 * tests pin both.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { BoardTruck, IncidentEntry, TruckDetail as TruckDetailData } from '../types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../FleetMap', () => ({ default: () => <div data-testid="fleet-map" /> }))

import TruckDetail from '../TruckDetail'

const truck: BoardTruck = {
  id: 'truck-603',
  unit_number: '603',
  display_unit_number: 'ELIS LOGISTICS LLC 603',
  year: 2020,
  make: 'VOLVO TRUCK',
  model: 'VNR',
  status: 'yard',
  odometer: 621_565,
  pm_interval_miles: 25_000,
  moving: false,
  open_work_order_count: 0,
  open_incident_count: 1,
}

const detail: TruckDetailData = {
  truck,
  open_work_orders: [],
  bill_labor_at_customer_rate: false,
  lifetime_spend: 0,
  incidents_count: 1,
  crew: [],
  history: [],
  parts: [],
  incidents: [],
  nearest: [],
}

const openIncident: IncidentEntry = {
  id: 'inc-1',
  date: '2026-09-15T12:00:00Z',
  type: 'Transmission issues',
  severity: 'high',
  status: 'open',
  location: 'I-85 mile 42',
  note: 'Transmission issues, previous repair problem',
  repair_order_id: null,
  photos: [],
}

const resolvedIncident: IncidentEntry = {
  id: 'inc-2',
  date: '2026-08-02T12:00:00Z',
  type: 'Blown marker lamp',
  severity: 'low',
  status: 'resolved',
  location: 'Yard',
  note: 'Blown marker lamp',
  repair_order_id: null,
  photos: [],
  resolution_notes: 'Replaced the lamp and reseated the harness',
  resolved_at: '2026-08-03T09:00:00Z',
}

function renderTruck() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <TruckDetail truckId={truck.id} trucks={[truck]} onOpen={vi.fn()} />
    </QueryClientProvider>,
  )
}

function mockQueries(incidents: IncidentEntry[], extra: Record<string, unknown> = {}) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === `/fleet/trucks/${truck.id}`) return Promise.resolve({ data: detail })
    if (url === `/fleet/trucks/${truck.id}/incidents`) return Promise.resolve({ data: incidents })
    if (url === '/fleet/inspections') return Promise.resolve({ data: [] })
    if (url in extra) return Promise.resolve({ data: extra[url] })
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
}

async function openIncidentMenu(user: ReturnType<typeof userEvent.setup>) {
  const trigger = await screen.findByRole('button', { name: 'Incident actions' })
  await user.click(trigger)
}

describe('DB-070 resolving an incident records why', () => {
  afterEach(() => {
    Object.values(apiMocks).forEach((mock) => mock.mockReset())
  })

  it('asks for an outcome instead of resolving on the click', async () => {
    mockQueries([openIncident])
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /resolve/i }))

    expect(await screen.findByRole('textbox', { name: /outcome/i })).toBeInTheDocument()
    expect(apiMocks.patch).not.toHaveBeenCalled()
  })

  it('will not submit an outcome that is only whitespace', async () => {
    mockQueries([openIncident])
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /resolve/i }))
    const field = await screen.findByRole('textbox', { name: /outcome/i })
    await user.type(field, '   ')

    expect(screen.getByRole('button', { name: /^resolve incident$/i })).toBeDisabled()
    expect(apiMocks.patch).not.toHaveBeenCalled()
  })

  it('sends the typed outcome with the resolved status', async () => {
    mockQueries([openIncident])
    apiMocks.patch.mockResolvedValue({ data: { ...openIncident, status: 'resolved' } })
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /resolve/i }))
    const field = await screen.findByRole('textbox', { name: /outcome/i })
    await user.type(field, 'Tightened the clamp roadside')
    await user.click(screen.getByRole('button', { name: /^resolve incident$/i }))

    await waitFor(() => {
      expect(apiMocks.patch).toHaveBeenCalledWith('/fleet/incidents/inc-1', {
        status: 'resolved',
        resolution_notes: 'Tightened the clamp roadside',
      })
    })
  })
})

describe('DB-071 resolved incidents keep a visible home', () => {
  afterEach(() => {
    Object.values(apiMocks).forEach((mock) => mock.mockReset())
  })

  it('lists a resolved incident that the unresolved card no longer shows', async () => {
    mockQueries([resolvedIncident])
    const user = userEvent.setup()
    renderTruck()

    const section = await screen.findByRole('button', { name: /resolved incidents/i })
    await user.click(section)

    expect(await screen.findByText('Blown marker lamp')).toBeInTheDocument()
  })

  it('shows the recorded outcome so the history reads as an answer', async () => {
    mockQueries([resolvedIncident])
    const user = userEvent.setup()
    renderTruck()

    await user.click(await screen.findByRole('button', { name: /resolved incidents/i }))

    expect(
      await screen.findByText(/Replaced the lamp and reseated the harness/i),
    ).toBeInTheDocument()
  })

  it('stays collapsed until asked, so history does not compete with open work', async () => {
    mockQueries([resolvedIncident])
    renderTruck()

    await screen.findByRole('button', { name: /resolved incidents/i })
    expect(screen.queryByText('Blown marker lamp')).not.toBeInTheDocument()
  })
})

describe('DB-073 the void action says what it does', () => {
  afterEach(() => {
    Object.values(apiMocks).forEach((mock) => mock.mockReset())
  })

  it('offers to void the incident rather than delete it', async () => {
    mockQueries([openIncident])
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)

    expect(screen.getByRole('button', { name: /^void$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^delete$/i })).toBeNull()
  })

  it('says the record is kept when asking to confirm', async () => {
    mockQueries([openIncident])
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /^void$/i }))

    expect(await screen.findByText(/kept/i)).toBeInTheDocument()
  })

  it('still sends the same request the backend already answers', async () => {
    mockQueries([openIncident])
    apiMocks.delete.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /^void$/i }))
    await user.click(screen.getByRole('button', { name: /^void incident$/i }))

    await waitFor(() => {
      expect(apiMocks.delete).toHaveBeenCalledWith('/fleet/incidents/inc-1')
    })
  })
})

describe('DB-072 attaching an incident to an existing order', () => {
  afterEach(() => {
    Object.values(apiMocks).forEach((mock) => mock.mockReset())
  })

  const linkable = [
    {
      id: 'ro-9',
      order_number: 'RO-000123',
      status: 'in_progress',
      is_pm: false,
      description: 'Clutch replacement',
      created_at: '2026-09-14T08:00:00Z',
    },
  ]

  it('offers the open orders for this truck', async () => {
    mockQueries([openIncident], { '/fleet/incidents/inc-1/linkable-orders': linkable })
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /assign to repair order/i }))

    expect(await screen.findByText(/RO-000123/)).toBeInTheDocument()
  })

  it('posts the chosen order to the link route', async () => {
    mockQueries([openIncident], { '/fleet/incidents/inc-1/linkable-orders': linkable })
    apiMocks.post.mockResolvedValue({ data: { ...openIncident, repair_order_id: 'ro-9' } })
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /assign to repair order/i }))
    const option = await screen.findByRole('button', { name: /RO-000123/ })
    await user.click(option)

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenCalledWith('/fleet/incidents/inc-1/repair-order', {
        repair_order_id: 'ro-9',
      })
    })
  })

  it('says so plainly when the truck has no open order to attach to', async () => {
    mockQueries([openIncident], { '/fleet/incidents/inc-1/linkable-orders': [] })
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)
    await user.click(screen.getByRole('button', { name: /assign to repair order/i }))

    expect(await screen.findByText(/no open repair orders/i)).toBeInTheDocument()
  })

  it('does not offer assignment for an incident that already has an order', async () => {
    mockQueries([{ ...openIncident, repair_order_id: 'ro-existing' }])
    const user = userEvent.setup()
    renderTruck()

    await openIncidentMenu(user)

    const menu = screen.getByRole('button', { name: /edit/i }).parentElement as HTMLElement
    expect(within(menu).queryByRole('button', { name: /assign to repair order/i })).toBeNull()
  })
})
