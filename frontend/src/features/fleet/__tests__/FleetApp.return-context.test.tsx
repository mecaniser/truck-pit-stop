import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '../../../stores/authStore'
import { stopSessionKeepAlive } from '../../../lib/sessionKeepAlive'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../FleetBoard', () => ({ default: () => <div>Fleet board content</div> }))
vi.mock('../FleetMap', () => ({ default: ({ trucks, focusId, onFocusChange, onSelect }: { trucks: { id: string }[]; focusId?: string; onFocusChange: (id: string) => void; onSelect: (truck: { id: string }) => void }) => <div>Fleet map<span data-testid="map-focus">{focusId || 'none'}</span><button onClick={() => onFocusChange(trucks[0].id)}>Select map truck</button><button onClick={() => onSelect(trucks[0])}>Open map truck</button></div> }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 400: '#ffd000', 500: '#ffd000' } }) }))
vi.mock('../TruckDetail', () => ({ default: ({ truckId, onViewTrips }: { truckId: string; onViewTrips?: (id: string) => void }) => <div>Truck detail<button onClick={() => onViewTrips?.(truckId)}>View trips</button></div> }))
vi.mock('../FleetModals', () => ({
  AddTruckModal: () => null,
  SchedulePMModal: () => null,
  SidekickPanel: ({ children, title }: { children: ReactNode; title: string }) => <div role="dialog" aria-label={title}>{children}</div>,
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
    apiMocks.put.mockReset()
    apiMocks.post.mockReset()
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
    stopSessionKeepAlive()
    window.localStorage.removeItem('tps-fleet-state')
  })

  it('does not continue an earlier profile save into a password change for the next account', async () => {
    let finish!: () => void
    const owner = useAuthStore.getState().user!
    const pendingSave = new Promise(resolve => { finish = () => resolve({ data: { user: owner } }) })
    apiMocks.put.mockReturnValueOnce(pendingSave)
    const view = renderFleet(['/fleet'])
    // This exercises save ordering, so target the controls in their existing
    // named panel instead of repeatedly computing roles across the Fleet shell.
    fireEvent.click(screen.getByLabelText('Open profile menu'))
    fireEvent.click(within(screen.getByLabelText('Profile actions')).getByText('Settings'))
    const settings = within(screen.getByLabelText('My account'))
    fireEvent.click(settings.getByText('Edit account', { selector: 'button' }))
    fireEvent.click(settings.getByText('Change password', { selector: 'button' }))
    fireEvent.change(settings.getByLabelText('Current password').querySelector('input')!, { target: { value: 'Synthetic-current-1!' } })
    fireEvent.change(settings.getByLabelText('New password').querySelector('input')!, { target: { value: 'Synthetic-next-2!' } })
    fireEvent.click(settings.getByText('Save changes', { selector: 'button' }))
    // save() starts the profile request before its first await. Hold that exact
    // request open until the original component and authenticated actor are gone.
    expect(apiMocks.put).toHaveBeenCalledExactlyOnceWith('/auth/me', {
      first_name: 'Shop', last_name: 'Owner', phone: null, email: 'owner@example.com',
    })
    expect(apiMocks.post).not.toHaveBeenCalled()
    view.unmount()
    const originatingEpoch = useAuthStore.getState().authSessionEpoch
    await act(async () => {
      useAuthStore.getState().login('test-access', 'test-refresh', { ...owner, id: 'b', tenant_id: 'shop-b' })
      finish()
      await pendingSave
    })
    expect(useAuthStore.getState().authSessionEpoch).toBeGreaterThan(originatingEpoch)
    expect(apiMocks.post).not.toHaveBeenCalled()
    expect(useAuthStore.getState().user?.id).toBe('b')
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
    await user.click(await screen.findByRole('button', { name: 'Truck 101 View truck' }))
    expect(screen.getByText('Truck detail')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /TRIPS.*Trips/ }))
    expect(await screen.findByLabelText('Truck')).toHaveTextContent('101')
  })

  it('retains the comparison truck when returning from details to the map', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockResolvedValue({ data: { ...fleetBoard, trucks: [{ id: 'map-truck', status: 'out_of_service', unit_number: '101' }] } })
    renderFleet(['/fleet'])
    await user.click(screen.getByRole('button', { name: /Fleet map$/ }))
    await user.click(await screen.findByRole('button', { name: 'Select map truck' }))
    expect(screen.getByTestId('map-focus')).toHaveTextContent('map-truck')
    await user.click(screen.getByRole('button', { name: 'Open map truck' }))
    expect(screen.getByText('Truck detail')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Fleet map$/ }))
    expect(screen.getByTestId('map-focus')).toHaveTextContent('map-truck')
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
  it('requires a tractor before adding a new trailer to the fleet', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url === '/fleet/board' ? { ...fleetBoard, trucks: [{ id: 'tractor-603', unit_number: '603', equipment_type: 'tractor', make: 'Demo', model: 'Tractor', status: 'active' }] } : url === '/fleet/companies' ? [{ id: 'customer-1', company_name: 'Demo Fleet' }] : url === '/fleet/settings' ? { default_fleet_authority_customer_id: 'customer-1' } : [] }))
    apiMocks.post.mockResolvedValue({ data: { id: 'new-trailer' } })
    renderFleet(['/fleet'])
    await user.click(await screen.findByTitle('Add equipment'))
    const fields = within(screen.getByLabelText('Add or link equipment'))
    // Identity text is setup; the interaction under test is tractor admission.
    fireEvent.change(fields.getByPlaceholderText('Freightliner'), { target: { value: 'Extreme' } })
    fireEvent.change(fields.getByPlaceholderText('Cascadia'), { target: { value: 'Flatbed' } })
    await user.click(fields.getByLabelText('Equipment type', { selector: 'button' }))
    await user.click(screen.getByText('Trailer', { selector: '[role="option"] span' }))
    const submit = fields.getByText('Add equipment', { selector: 'button' })
    expect(submit).toBeDisabled()
    expect(apiMocks.post).not.toHaveBeenCalled()
    await user.click(fields.getByLabelText('Assigned tractor', { selector: 'button' }))
    await user.click(screen.getByText('603 · Demo', { selector: '[role="option"] span' }))
    await user.click(submit)
    expect(apiMocks.post).toHaveBeenCalledWith('/fleet/trucks', expect.objectContaining({ equipment_type: 'trailer', tractor_id: 'tractor-603', customer_id: 'customer-1' }))
  })

})
