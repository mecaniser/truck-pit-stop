import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { Vehicle } from '@/types'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get } }))
import PortalVehiclesPage from '../PortalVehiclesPage'

const vehicle = { id: 'vehicle-a', unit_number: '603', year: 2021, make: 'Volvo', model: 'VNR' } as Vehicle
function show(vehicles: Vehicle[] = [vehicle], query = '') {
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/vehicles') return { data: vehicles }
    if (url === '/repair-orders') return { data: [] }
    throw new Error(`Unexpected request ${url}`)
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/portal/vehicles${query}`]}><PortalVehiclesPage/></MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  mocks.get.mockReset()
  useAuthStore.setState({ user: { id: 'user', tenant_id: 'tenant', customer_id: 'customer', role: 'customer' } as never, isAuthenticated: true })
})
it('separates the single page-level creation action from scoped vehicle actions', async () => {
  show()
  const add = await screen.findByRole('link', { name: 'Add vehicle' })
  expect(add).toHaveAttribute('href', '/portal/settings?tab=vehicles')
  expect(within(screen.getByRole('banner')).getByRole('link', { name: 'Add vehicle' })).toBe(add)
  const row = screen.getByRole('article')
  expect(within(row).queryByRole('link', { name: 'Add vehicle' })).not.toBeInTheDocument()
  expect(within(row).getByRole('link', { name: 'Book service' })).toHaveAttribute('href', '/portal/services?vehicle_id=vehicle-a')
  expect(within(row).getByRole('link', { name: 'View history' })).toHaveAttribute('href', '/portal/repairs?vehicle_id=vehicle-a')
  expect(screen.getAllByRole('link', { name: 'Add vehicle' })).toHaveLength(1)
})
it('keeps one header creation action when the vehicle list is empty', async () => {
  show([])
  expect(await screen.findByRole('heading', { name: 'No vehicles yet' })).toBeInTheDocument()
  expect(screen.getAllByRole('link', { name: 'Add vehicle' })).toHaveLength(1)
  expect(within(screen.getByRole('banner')).getByRole('link', { name: 'Add vehicle' })).toBeInTheDocument()
})
it('does not expose vehicle or creation actions for a foreign vehicle scope', async () => {
  show([vehicle], '?vehicle_id=foreign')
  expect(await screen.findByRole('heading', { name: 'Vehicle unavailable' })).toBeInTheDocument()
  expect(screen.queryByRole('article')).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Add vehicle' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Book service' })).not.toBeInTheDocument()
})
