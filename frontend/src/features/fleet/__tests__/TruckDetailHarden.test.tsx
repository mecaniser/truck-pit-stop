import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
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
import toast from 'react-hot-toast'
import { driverTruck } from './driverRecordFixture'

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
  return render(
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
  it('refreshes speed while the detail stays open, preserves zero, and expires unchanged observations', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-16T14:00:00Z'))
    const speed = { source: 'motive_dashboard_manual' as const, observed_at: new Date().toISOString(), captured_at: new Date().toISOString(), freshness: 'fresh' as const, snapshot_id: 'initial-speed', source_age_text: null, value: 45, unit: 'mph' as const, basis: null }
    let response: TruckDetailData = { ...detail, truck: { ...truck, telemetry: { location: null, speed, odometer: null, engine_hours: null, fuel: null, fault_count: null, motion: 'moving' } } }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === `/fleet/trucks/${truck.id}`) return Promise.resolve({ data: response })
      if (url === `/fleet/trucks/${truck.id}/incidents` || url === '/fleet/inspections') return Promise.resolve({ data: [] })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    const view = renderTruck()
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(1) })
      expect(screen.getByText('45 mph')).toBeInTheDocument()
      response = { ...response, truck: { ...response.truck, telemetry: { ...response.truck.telemetry!, speed: { ...speed, value: 0, observed_at: '2026-10-16T14:01:00Z', captured_at: '2026-10-16T14:01:00Z', snapshot_id: 'new-speed' }, motion: 'stopped' } } }

      await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
      expect(screen.getByText('0 mph')).toBeInTheDocument()
      expect(screen.queryByText('45 mph')).not.toBeInTheDocument()

      await act(async () => { await vi.advanceTimersByTimeAsync(300000) })
      expect(screen.getByText('0 mph')).toBeInTheDocument()
      await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
      expect(screen.queryByText('0 mph')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Speed unavailable')).toBeInTheDocument()
      expect(apiMocks.get.mock.calls.filter(([url]) => url === `/fleet/trucks/${truck.id}`).length).toBeGreaterThan(2)
      expect(apiMocks.get.mock.calls.filter(([url]) => url === `/fleet/trucks/${truck.id}/incidents`)).toHaveLength(1)
      expect(apiMocks.get.mock.calls.filter(([url]) => url === '/fleet/inspections')).toHaveLength(1)
    } finally {
      view.unmount()
      vi.useRealTimers()
    }
  })

  it('keeps a managed custody profile separate from the current Motive identity and score', async () => {
    const sourceTruck = { ...driverTruck, id: truck.id }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === `/fleet/trucks/${truck.id}`) return Promise.resolve({ data: { ...detail, truck: sourceTruck } })
      if (url === '/auth/workos/capabilities') return Promise.resolve({ data: { session_provider: 'workos', driver_invitation_management: { available: false } } })
      if (url === `/fleet-identity/vehicles/${truck.id}/driver`) return Promise.resolve({ data: { driver: { id: 'managed-driver', first_name: 'Managed', last_name: 'Custodian', phone: '7045550199' } } })
      if (url === `/fleet/trucks/${truck.id}/incidents` || url === '/fleet/inspections') return Promise.resolve({ data: [] })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    renderTruck([sourceTruck])
    expect(await screen.findByText('Example Driver')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Open truck details' }))
    const managed = await screen.findByText('Managed Custodian')
    const custodyRow = managed.closest('.fleet-driver-profile-row') as HTMLElement
    expect(within(custodyRow).getByText('Managed driver profile')).toBeVisible()
    expect(within(custodyRow).queryByRole('button', { name: /Driver record/ })).not.toBeInTheDocument()
    expect(within(custodyRow).getByRole('link', { name: 'Call Managed Custodian' })).toHaveAttribute('href', 'tel:7045550199')
    const providerRow = document.querySelector('.fleet-motive-driver') as HTMLElement
    expect(within(providerRow).getByText('Example Driver')).toBeVisible()
    expect(within(providerRow).getByRole('button', { name: /Driver record for Example Driver/ })).toHaveTextContent('82')
    expect(within(providerRow).getByText('Example · (704) 555-0123')).toBeVisible()
  })

  it('keeps mileage comparison and speed in the header, with hours and entry in details', async () => {
    const source = { source: 'motive_dashboard_manual' as const, observed_at: null, captured_at: new Date().toISOString(), freshness: 'unknown' as const, snapshot_id: 'fixture', source_age_text: '12s ago' }
    truck.telemetry = { location: { ...source, label: 'Fixture town', lat: null, lng: null }, odometer: { ...source, value: 625000, unit: 'mi', basis: 'dashboard_unspecified' }, speed: { ...source, observed_at: new Date().toISOString(), value: 0, unit: 'mph', basis: null }, fuel: { ...source, value: 38, unit: 'percent', basis: null }, engine_hours: { ...source, value: 4000, unit: 'h', basis: null }, fault_count: null, motion: 'unknown' }
    mockSuccessfulQueries(); renderTruck()
    await screen.findByText('625,000 mi')
    expect(screen.getByText('621,565')).toBeInTheDocument()
    expect(screen.getByText('0 mph')).toBeInTheDocument()
    expect(screen.getByText('38%')).toBeInTheDocument()
    expect(screen.getByText('Fixture town')).toBeInTheDocument()
    expect(screen.queryByText('4,000 h')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reading details' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add reading' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open truck details' }))
    expect(screen.getByText('Truck vitals')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add reading' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'VIN verified in Motive' })).not.toBeInTheDocument()
    expect(screen.getByText('4,000 h')).toBeInTheDocument()
  })

  afterEach(() => {
    delete truck.telemetry
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

it('retries an uncertain empty fleet order creation with the same command identity', async () => {
  const { useAuthStore } = await import('@/stores/authStore')
  const { quote } = await import('@/features/parts-pricing/__tests__/fixtures')
  const previous = useAuthStore.getState().user
  useAuthStore.setState({ user: { id: 'actor-1', tenant_id: 'tenant-1', role: 'fleet_manager' } as import('@/types').User, logoutInProgress: false })
  let writes = 0
  mockSuccessfulQueries()
  apiMocks.post.mockImplementation((url, body) => url === '/parts-pricing/resolve' ? Promise.resolve({ data: quote({ plan: body.plan, projection: 'fleet', required: false, total: '0.00' }) }) : ++writes === 1 ? Promise.reject(new Error('offline')) : Promise.resolve({ data: {} }))
  try {
    const user = userEvent.setup(); renderTruck(); const button = await screen.findByRole('button', { name: /Create repair order/ }); await user.click(button); await waitFor(() => expect(writes).toBe(1)); await waitFor(() => expect(button).toBeEnabled()); await user.click(button); await waitFor(() => expect(writes).toBe(2))
    const commands = apiMocks.post.mock.calls.filter(([url]) => url === `/fleet/trucks/${truck.id}/work-order`); expect(commands[1][2].headers).toEqual(commands[0][2].headers); expect(commands[1][1]).toEqual({ pricing_preview_fingerprint: 'opaque-1', pricing_presentation: 'fleet' }); expect(apiMocks.post.mock.calls.filter(([url]) => url === '/parts-pricing/resolve')).toHaveLength(1)
  } finally { useAuthStore.setState({ user: previous }) }
})


it.each([null, 0])('requires actual PM mileage even when the generic history reading is %s', async odometer => {
  const user = userEvent.setup()
  apiMocks.get.mockImplementation((url: string) => {
    if (url === `/fleet/trucks/${truck.id}`) return Promise.resolve({ data: detail })
    if (url === `/fleet/trucks/${truck.id}/history`) return Promise.resolve({ data: [{ id: 'historical-pm', kind: 'Repair', date: '2026-10-01', summary: 'Preventive maintenance', odometer }] })
    return Promise.resolve({ data: [] })
  })
  renderTruck()
  await user.click(await screen.findByRole('button', { name: /Service history/ }))
  await user.click(await screen.findByRole('button', { name: 'Recognize as PM' }))
  expect(screen.getByLabelText('Odometer at service')).toHaveValue('')
  expect(screen.queryByText(/The next PM will be set to/)).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('Odometer at service'), '0')
  expect(screen.getByLabelText('Odometer at service')).toHaveValue('0')
  expect(screen.getByLabelText('Odometer at service')).not.toHaveValue(String(truck.odometer))
})


it.each([
  ['maintenance_review_required', 'Use this truck’s maintenance programs to edit its service schedule.'],
  ['maintenance_operation_linked', 'Review the existing maintenance program before changing its legacy schedule.'],
])('retains actual-service draft and shows the structured %s legacy guard', async (code, message) => {
  const user = userEvent.setup()
  apiMocks.get.mockImplementation((url: string) => {
    if (url === `/fleet/trucks/${truck.id}`) return Promise.resolve({ data: detail })
    if (url === `/fleet/trucks/${truck.id}/history`) return Promise.resolve({ data: [{ id: 'historical-pm', kind: 'Repair', date: '2026-10-01', summary: 'Preventive maintenance', odometer: 620000 }] })
    return Promise.resolve({ data: [] })
  })
  apiMocks.post.mockRejectedValue({ response: { status: 409, data: { detail: { code, message } } } })
  renderTruck(); await user.click(await screen.findByRole('button', { name: /Service history/ })); await user.click(await screen.findByRole('button', { name: 'Recognize as PM' })); await user.type(screen.getByLabelText('Odometer at service'), '0'); await user.click(screen.getByRole('button', { name: 'Record PM completion' }))
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith(message))
  expect(screen.getByLabelText('Odometer at service')).toHaveValue('0'); expect(screen.getByLabelText('PM performed date')).toHaveValue('2026-10-01'); expect(screen.getByRole('dialog', { name: 'Recognize prior PM' })).toBeInTheDocument()
})
