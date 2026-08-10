import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import type { BoardTruck, DriverProfile } from '../types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ default: apiMocks }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import { AssignDriverModal } from '../FleetModals'

beforeAll(() => vi.stubGlobal('scrollTo', vi.fn()))
afterAll(() => vi.unstubAllGlobals())

const truck: BoardTruck = {
  id: 'truck-609', unit_number: '609', display_unit_number: 'ELIS LOGISTICS 609',
  make: 'Volvo', model: 'VNR', status: 'yard', moving: false,
  odometer: 625_900, pm_interval_miles: 25_000,
  open_work_order_count: 0, open_incident_count: 0,
}

const driver: DriverProfile = {
  id: 'driver-1', first_name: 'Morgan', last_name: 'Miles',
  email: 'morgan@example.test', phone: '7045551212', employment_status: 'active',
}

function renderAssignment(onClose = vi.fn()) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/auth/workos/capabilities') return Promise.resolve({ data: {
      session_provider: 'workos', workos_auth_enabled: true, organization_provisioned: true,
      driver_invitation_management: { available: true, reason: 'available', required_permission: 'members:manage', reauth_path: null },
    } })
    if (url === `/fleet-identity/vehicles/${truck.id}/driver`) return Promise.resolve({ data: null })
    if (url === '/fleet-identity/drivers') return Promise.resolve({ data: [driver] })
    if (url === '/fleet-identity/drivers/legacy-contacts') return Promise.resolve({ data: [] })
    return Promise.reject(new Error(`Unexpected GET ${url}`))
  })
  apiMocks.put.mockResolvedValue({ data: { vehicle_id: truck.id, driver } })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><AssignDriverModal truck={truck} onClose={onClose} /></QueryClientProvider>)
  return { onClose }
}

describe('Driver profile assignment', () => {
  afterEach(() => Object.values(apiMocks).forEach((mock) => mock.mockReset()))

  it('assigns an explicitly selected profile and starts custody with the truck odometer', async () => {
    const user = userEvent.setup()
    const { onClose } = renderAssignment()

    await user.click(await screen.findByRole('button', { name: /Morgan Miles/ }))

    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(`/fleet-identity/vehicles/${truck.id}/driver`, {
      driver_id: driver.id,
      vehicle_id: truck.id,
      start_odometer: truck.odometer,
    }))
    expect(onClose).toHaveBeenCalled()
  })

  it('keeps profile creation separate from login provisioning', async () => {
    const user = userEvent.setup()
    renderAssignment()

    await user.click(await screen.findByRole('button', { name: 'New profile' }))
    expect(screen.getByText(/Creating a profile does not create a login/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Create and assign profile/i })).toBeDisabled()
  })

  it('finds a legacy truck contact and prepares it for profile conversion', async () => {
    const user = userEvent.setup()
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/auth/workos/capabilities') return Promise.resolve({ data: {
        session_provider: 'workos', workos_auth_enabled: true, organization_provisioned: true,
        driver_invitation_management: { available: true, reason: 'available', required_permission: 'members:manage', reauth_path: null },
      } })
      if (url === `/fleet-identity/vehicles/${truck.id}/driver`) return Promise.resolve({ data: null })
      if (url === '/fleet-identity/drivers') return Promise.resolve({ data: [] })
      if (url === '/fleet-identity/drivers/legacy-contacts') return Promise.resolve({ data: [{ name: 'Marcus Jones', phone: '9103013928', vehicle_count: 2 }] })
      return Promise.reject(new Error(`Unexpected GET ${url}`))
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    render(<QueryClientProvider client={client}><AssignDriverModal truck={truck} onClose={vi.fn()} /></QueryClientProvider>)

    await user.type(await screen.findByRole('searchbox', { name: 'Search driver profiles' }), 'Marcus')
    await user.click(await screen.findByRole('button', { name: /Marcus Jones.*Legacy contact/i }))

    expect(screen.getByDisplayValue('Marcus')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Jones')).toBeInTheDocument()
    expect(screen.getByDisplayValue('(910) 301-3928')).toBeInTheDocument()
    expect(screen.getByText(/Creating a profile does not create a login/i)).toBeInTheDocument()
  })
})
