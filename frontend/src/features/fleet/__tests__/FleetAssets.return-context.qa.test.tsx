import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { stopSessionKeepAlive } from '@/lib/sessionKeepAlive'
const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('../TruckDetail', () => ({ default: ({ truckId, onOpen }: { truckId: string; onOpen: (id: string) => void }) => <div><p>Equipment detail {truckId}</p><button onClick={() => onOpen('603')}>Open counterpart</button></div> }))
vi.mock('../FleetMap', () => ({ default: () => null }))
vi.mock('../FleetActivity', () => ({ default: () => null }))
vi.mock('../FleetPriceBuilderPanel', () => ({ default: () => null }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 400: '#ffd000', 500: '#ffd000' } }) }))
import FleetApp from '../FleetApp'
const fleet = { trucks: ['24', '603'].map(id => ({ id, unit_number: id, equipment_type: id === '24' ? 'trailer' : 'tractor', make: 'Demo', model: 'Equipment', status: 'active', moving: false, pm_interval_miles: 25000, pm_days_remaining: 30, open_work_order_count: 0, open_incident_count: 0 })), stats: { total: 2, active: 2, shop: 0, pm: 0, parts: 0, open_wo: 0, incidents_total: 0 } }
const view = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><FleetApp /></MemoryRouter></QueryClientProvider>)
beforeEach(() => {
  Element.prototype.scrollTo = vi.fn()
  localStorage.removeItem('tps-fleet-state')
  api.get.mockResolvedValue({ data: fleet })
  useAuthStore.setState({ isAuthenticated: true, user: { id: 'qa-owner', email: 'qa@example.invalid', first_name: 'QA', last_name: 'Owner', role: 'garage_owner', is_active: true, tenant_id: 'qa-tenant', customer_id: null, phone: null, tenant_name: 'QA', tenant_slug: 'qa' } })
})
afterEach(() => { stopSessionKeepAlive(); localStorage.removeItem('tps-fleet-state'); vi.resetAllMocks() })
it('returns from a trailer detail to the same filtered task and retains it on remount', async () => {
  const first = view()
  fireEvent.click(await screen.findByText('Trailers · 1', { selector: 'button' }))
  fireEvent.click(screen.getByLabelText('Open 24 trailer details'))
  expect(await screen.findByText('Equipment detail 24')).toBeVisible()
  fireEvent.click(screen.getByText('Fleet board', { selector: '.topbar-back span' }))
  expect(await screen.findByText('Trailers · 1', { selector: 'button' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByLabelText('Open 603 truck details')).not.toBeInTheDocument()
  await waitFor(() => expect(screen.getByLabelText('Open 24 trailer details')).toHaveFocus())
  await waitFor(() => expect(JSON.parse(localStorage.getItem('tps-fleet-state')!).assetFilter).toBe('trailer'))
  fireEvent.click(screen.getByLabelText('Open 24 trailer details'))
  fireEvent.click(screen.getByText('Open counterpart', { selector: 'button' }))
  expect(await screen.findByText('Equipment detail 603')).toBeVisible()
  fireEvent.click(screen.getByText('Fleet board', { selector: '.topbar-back span' }))
  await waitFor(() => expect(screen.getByText('Action now', { selector: 'h2' })).toHaveFocus())
  first.unmount()
  view()
  expect(await screen.findByText('Trailers · 1', { selector: 'button' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByLabelText('Open 603 truck details')).not.toBeInTheDocument()
})
