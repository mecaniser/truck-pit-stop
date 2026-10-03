import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '../../../stores/authStore'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../FleetBoard', () => ({ default: () => <div>Fleet board content</div> }))
vi.mock('../FleetMap', () => ({ default: () => <div>Fleet map</div> }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 400: '#ffd000', 500: '#ffd000' } }) }))
vi.mock('../TruckDetail', () => ({ default: ({ truckId, onViewTrips }: { truckId: string; onViewTrips?: (id: string) => void }) => <div>Truck detail<button onClick={() => onViewTrips?.(truckId)}>View trips</button></div> }))
vi.mock('../FleetModals', () => ({
  AddTruckModal: () => null,
  SchedulePMModal: () => null,
  SidekickPanel: () => null,
  invalidateFleetAndCockpit: vi.fn(),
}))
vi.mock('../FleetPriceBuilderPanel', () => ({ default: () => null }))

import FleetApp from '../FleetApp'

const fleetBoard = {
  trucks: [],
  stats: { total: 0, active: 0, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 },
}

function CurrentLocation() {
  const location = useLocation()
  return <output data-testid="current-location">{`${location.pathname}${location.search}`}</output>
}

function renderFleet(initialEntries: Parameters<typeof MemoryRouter>[0]['initialEntries'], initialIndex?: number) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries} initialIndex={initialIndex}>
        <FleetApp />
        <CurrentLocation />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Fleet board return context', () => {
  beforeEach(() => {
    Element.prototype.scrollTo = vi.fn()
    window.localStorage.removeItem('tps-fleet-state')
    apiMocks.get.mockReset()
    apiMocks.get.mockResolvedValue({ data: fleetBoard })
    useAuthStore.setState({
      user: {
        id: 'owner-1',
        email: 'owner@example.com',
        first_name: 'Shop',
        last_name: 'Owner',
        phone: null,
        role: 'garage_owner',
        is_active: true,
        tenant_id: 'tenant-1',
        tenant_name: 'Truck Pit Stop',
        tenant_slug: 'truck-pit-stop',
        customer_id: null,
      },
      isAuthenticated: true,
    })
  })

  afterEach(() => {
    window.localStorage.removeItem('tps-fleet-state')
  })

  it('opens Fleet map without implying live telemetry or changing the route', async () => {
    const user = userEvent.setup()
    renderFleet(['/fleet'])
    await user.click(screen.getByRole('button', { name: /Fleet map$/ }))
    expect(await screen.findByText('Fleet map', { selector: '.topbar-title' })).toBeInTheDocument()
    expect(screen.getByTestId('current-location')).toHaveTextContent('/fleet')
    expect(screen.queryByText(/live map/i)).not.toBeInTheDocument()
  })

  it('connects truck details to Trips and returns with the same truck selected', async () => {
    const user = userEvent.setup()
    const truck = { id: 'trip-truck', unit_number: '101', display_unit_number: 'Example 101', status: 'active', make: 'VOLVO', model: 'VNR' }
    window.localStorage.setItem('tps-fleet-state', JSON.stringify({ view: 'detail', selId: truck.id }))
    apiMocks.get.mockImplementation(async (url: string) => ({ data: url === '/fleet/board' ? { ...fleetBoard, trucks: [truck] } : { items: [], total: 0, summary: { truck_count: 0, coverage: 'partial', trip_count: 0, distance_miles: 0, driving_seconds: 0 } } }))
    renderFleet(['/fleet'])
    await user.click(await screen.findByRole('button', { name: 'View trips' }))
    expect(await screen.findByLabelText('Truck')).toHaveTextContent('101')
    await user.click(screen.getByRole('button', { name: 'Back to truck 101' }))
    expect(screen.getByText('Truck detail')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /TRIPS.*Trips/ }))
    expect(await screen.findByLabelText('Truck')).toHaveTextContent('101')
  })

  it('returns to the Fleet Settings context when that is where the board was opened', async () => {
    const user = userEvent.setup()
    renderFleet([
      { pathname: '/dashboard/settings', search: '?section=fleet' },
      {
        pathname: '/fleet',
        state: { returnTo: '/dashboard/settings?section=fleet', returnLabel: 'Profile Settings' },
      },
    ], 1)

    await user.click(screen.getByRole('button', { name: 'Return to Profile Settings' }))

    expect(screen.getByTestId('current-location')).toHaveTextContent('/dashboard/settings?section=fleet')
  })

  it('keeps the existing Shop Work fallback for a direct Fleet visit', async () => {
    const user = userEvent.setup()
    renderFleet(['/fleet'])

    await user.click(screen.getByRole('button', { name: 'Shop dashboard' }))

    expect(screen.getByTestId('current-location')).toHaveTextContent('/dashboard')
  })
})
