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
vi.mock('../TruckDetail', () => ({ default: () => <div>Truck detail</div> }))
vi.mock('../FleetModals', () => ({
  AddTruckModal: () => null,
  SchedulePMModal: () => null,
  SidekickPanel: () => null,
  WorkOrderPanel: () => null,
  invalidateFleetAndCockpit: vi.fn(),
}))

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
