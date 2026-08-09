import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { BoardTruck, TruckDetail as TruckDetailData } from '../types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: apiMocks,
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

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
  open_incident_count: 0,
}

const detail: TruckDetailData = {
  truck,
  open_work_orders: [],
  bill_labor_at_customer_rate: false,
  lifetime_spend: 0,
  incidents_count: 0,
  crew: [],
  history: [],
  parts: [],
  incidents: [],
  nearest: [],
}

function renderTruck(trucks: BoardTruck[] = [truck]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={queryClient}>
      <TruckDetail truckId={truck.id} trucks={trucks} onOpen={vi.fn()} />
    </QueryClientProvider>,
  )
}

function mockSuccessfulQueries() {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === `/fleet/trucks/${truck.id}`) return Promise.resolve({ data: detail })
    if (url === `/fleet/trucks/${truck.id}/incidents`) return Promise.resolve({ data: [] })
    if (url === '/fleet/inspections') return Promise.resolve({ data: [] })
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
}

describe('TruckDetail hardening', () => {
  afterEach(() => {
    Object.values(apiMocks).forEach((mock) => mock.mockReset())
  })

  it('shows a recoverable truck error and loads the workspace after retry', async () => {
    let attempts = 0
    apiMocks.get.mockImplementation((url: string) => {
      if (url === `/fleet/trucks/${truck.id}`) {
        attempts += 1
        return attempts === 1
          ? Promise.reject(new Error('offline'))
          : Promise.resolve({ data: detail })
      }
      if (url === `/fleet/trucks/${truck.id}/incidents` || url === '/fleet/inspections') {
        return Promise.resolve({ data: [] })
      }
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    const user = userEvent.setup()

    renderTruck([])

    expect(await screen.findByRole('alert')).toHaveTextContent('Truck details are unavailable')
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('region', { name: 'Start yard inspection' })).toBeInTheDocument()
    expect(attempts).toBe(2)
  })

  it('exposes an accessible status menu with arrow navigation, Escape dismissal, and focus return', async () => {
    mockSuccessfulQueries()
    const user = userEvent.setup()
    renderTruck()

    const trigger = await screen.findByRole('button', { name: /change truck status/i })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    await user.click(trigger)
    const menu = screen.getByRole('menu', { name: 'Set truck status' })
    const automatic = screen.getByRole('menuitemradio', { name: /auto/i })
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(menu).toBeInTheDocument()
    await waitFor(() => expect(automatic).toHaveFocus())

    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitemradio', { name: 'On the road' })).toHaveFocus()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('defers the below-fold fleet map until the operator asks for it', async () => {
    mockSuccessfulQueries()
    const user = userEvent.setup()
    renderTruck()

    const showMap = await screen.findByRole('button', { name: 'Show map' })
    expect(showMap).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('fleet-map')).not.toBeInTheDocument()

    await user.click(showMap)

    expect(screen.getByTestId('fleet-map')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide map' })).toHaveAttribute('aria-expanded', 'true')
  })
})
