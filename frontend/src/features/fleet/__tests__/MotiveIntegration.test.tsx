import { StrictMode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { BoardTruck } from '../types'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), navigate: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('react-router-dom', async () => ({ ...await vi.importActual('react-router-dom'), useNavigate: () => mocks.navigate }))
vi.mock('../FleetModals', () => ({ SidekickPanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
import MotiveIntegrationPanel, { MotiveConnectionCard } from '../MotiveIntegrationPanel'
import MotiveCallback from '../MotiveCallback'

const connected = {
  fleet_customer_id: 'company-a', configured: true, can_connect: true, status: 'connected',
  company: { id: 'motive-a', name: 'Pilot fleet' }, last_sync_at: null, last_sync_error_code: null, last_sync_counts: null,
}
const remote = { provider_vehicle_id: '123', number: 'Truck 7', vin: 'VIN-7', gateway_id: null, vehicle_id: null, mapping_state: 'unmapped', match_candidates: [{ vehicle_id: 'truck-a', unit_number: '7' }] }
const trucks = [{ id: 'truck-a', unit_number: '7', fleet_customer_id: 'company-a' }, { id: 'truck-b', unit_number: '99', fleet_customer_id: 'company-b' }] as BoardTruck[]
function wrap(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  vi.resetAllMocks()
  window.history.replaceState({}, '', '/')
  useAuthStore.setState({ user: { role: 'garage_owner', id: 'owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
  mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/trucks') ? { items: [{ id: 'truck-a', unit_number: '7', vin: 'VIN-7' }] } : url.endsWith('/webhook') ? { status: 'not_configured', url: null, pending_count: 0, failed_count: 0 } : url.endsWith('/connection') ? connected : url.endsWith('/companies') ? { items: [{ id: 'company-a', company_name: 'Pilot fleet', fleet_enabled: true }, { id: 'company-b', company_name: 'Second fleet', fleet_enabled: true }] } : { items: [remote], synced_at: null } }))
})
describe('Motive integration', () => {
  it('disables connection while provider configuration is pending without pretending connected', async () => {
    mocks.get.mockResolvedValue({ data: { ...connected, configured: false, can_connect: false, status: 'not_configured', company: null } })
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    expect(await screen.findByText('Setup pending')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Connect Motive' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Sync now' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('requires review, limits mappings to the chosen company, and scopes the save', async () => {
    const user = userEvent.setup()
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    const select = await screen.findByLabelText('DieselBridge truck for Truck 7')
    expect(select).toHaveValue('')
    expect(within(select).queryByText('99')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save mapping' })).toBeDisabled()
    await user.selectOptions(select, 'truck-a')
    await user.click(screen.getByRole('button', { name: 'Save mapping' }))
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/fleet/motive/bindings/123', { fleet_customer_id: 'company-a', vehicle_id: 'truck-a' }))
  })
  it('shows no successful sync before one occurs and reports provider failure safely', async () => {
    mocks.post.mockRejectedValue({ response: { status: 502, data: { detail: 'secret-token-value' } } })
    const user = userEvent.setup()
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    expect(await screen.findByText('Last successful sync: Not synced yet')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sync now' }))
    expect(await screen.findByRole('status')).toHaveTextContent('We could not complete this request')
    expect(screen.queryByText(/secret-token/)).not.toBeInTheDocument()
  })
  it('disables immediate resync during the server cooldown', async () => {
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/trucks') ? { items: [{ id: 'truck-a', unit_number: '7', vin: 'VIN-7' }] } : url.endsWith('/webhook') ? { status: 'not_configured', url: null, pending_count: 0, failed_count: 0 } : url.endsWith('/connection') ? { ...connected, next_sync_at: new Date(Date.now() + 300000).toISOString() } : { items: [], synced_at: null } }))
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    expect(await screen.findByText(/Next sync available:/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeDisabled()
  })
  it('only disconnects after confirmation and scopes the request', async () => {
    const user = userEvent.setup()
    mocks.delete.mockResolvedValue({})
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    await user.click(await screen.findByRole('button', { name: 'Disconnect', exact: true }))
    expect(mocks.delete).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Keep connected' }))
    expect(mocks.delete).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Disconnect', exact: true }))
    mocks.get.mockResolvedValue({ data: { ...connected, status: 'disconnected', company: null } })
    await user.click(screen.getByRole('button', { name: 'Confirm disconnect' }))
    await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/fleet/motive/connection', { params: { fleet_customer_id: 'company-a' } }))
    expect(await screen.findByText('Not connected')).toBeInTheDocument()
    expect(screen.queryByText('Motive truck Truck 7')).not.toBeInTheDocument()
  })
  it('renders successful sync, stale observation time and a real zero speed', async () => {
    const user = userEvent.setup()
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/trucks') ? { items: [{ id: 'truck-a', unit_number: '7', vin: 'VIN-7' }] } : url.endsWith('/webhook') ? { status: 'not_configured', url: null, pending_count: 0, failed_count: 0 } : url.endsWith('/connection') ? connected : { items: [{ ...remote, vehicle_id: 'truck-a', telemetry: { location: { lat: 35, lng: -81, located_at: new Date(Date.now() - 3600000).toISOString(), received_at: new Date().toISOString() }, state: 'stale', speed_mph: 0, bearing_degrees: null, source: 'motive' } }], synced_at: null } }))
    mocks.post.mockResolvedValue({ data: { status: 'connected', counts: { updated: 1 }, completed_at: new Date().toISOString() } })
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    expect(await screen.findByText(/Motive location · stale/)).toHaveTextContent('0.0 mph')
    await user.click(screen.getByRole('button', { name: 'Sync now' }))
    expect(await screen.findByRole('status')).toHaveTextContent('1 truck readings updated')
    expect(mocks.post).toHaveBeenCalledWith('/fleet/motive/sync', { fleet_customer_id: 'company-a' })
  })
  it('unmaps through the company-scoped delete endpoint', async () => {
    const user = userEvent.setup()
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/trucks') ? { items: [{ id: 'truck-a', unit_number: '7', vin: 'VIN-7' }] } : url.endsWith('/webhook') ? { status: 'not_configured', url: null, pending_count: 0, failed_count: 0 } : url.endsWith('/connection') ? connected : { items: [{ ...remote, vehicle_id: 'truck-a' }], synced_at: null } }))
    mocks.delete.mockResolvedValue({})
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    await user.selectOptions(await screen.findByLabelText('DieselBridge truck for Truck 7'), '')
    await user.click(screen.getByRole('button', { name: 'Save mapping' }))
    await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/fleet/motive/bindings/123', { params: { fleet_customer_id: 'company-a' } }))
  })
  it('offers reconnect and disables sync when authorization expires', async () => {
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/trucks') ? { items: [{ id: 'truck-a', unit_number: '7', vin: 'VIN-7' }] } : url.endsWith('/webhook') ? { status: 'not_configured', url: null, pending_count: 0, failed_count: 0 } : url.endsWith('/connection') ? { ...connected, status: 'reconnect_required' } : { items: [], synced_at: null } }))
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    expect(await screen.findByRole('button', { name: 'Reconnect Motive' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Sync now' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Disconnect' })).toBeEnabled()
  })
  it('requires a company selection and isolates queries when switching companies', async () => {
    const user = userEvent.setup()
    wrap(<MotiveIntegrationPanel onClose={() => {}} trucks={trucks} />)
    const select = await screen.findByLabelText('Fleet company')
    await screen.findByRole('option', { name: 'Pilot fleet' })
    expect(screen.queryByLabelText('Motive connection')).not.toBeInTheDocument()
    await user.selectOptions(select, 'company-a')
    await screen.findByLabelText('Motive connection')
    await user.selectOptions(select, 'company-b')
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/fleet/motive/connection', expect.objectContaining({ params: { fleet_customer_id: 'company-b' } })))
  })
  it('includes internal fleet companies even when the separate fleet flag is false', async () => {
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/companies') ? { items: [{ id: 'company-a', company_name: 'Internal fleet', fleet_enabled: false, is_internal_fleet: true }] } : url.endsWith('/connection') ? connected : { items: [], synced_at: null } }))
    wrap(<MotiveIntegrationPanel onClose={() => {}} trucks={trucks} />)
    expect(await screen.findByRole('option', { name: 'Internal fleet' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Motive connection')).toBeInTheDocument()
  })
  it('does not load integrations for unscoped fleet managers', () => {
    useAuthStore.setState({ user: { role: 'fleet_manager' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> })
    wrap(<MotiveIntegrationPanel onClose={() => {}} trucks={trucks} />)
    expect(screen.getByText('Ask your company administrator to manage integrations.')).toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalled()
  })
  it('rejects an unexpected OAuth redirect destination', async () => {
    mocks.get.mockResolvedValue({ data: { ...connected, status: 'disconnected', company: null } })
    mocks.post.mockResolvedValue({ data: { authorization_url: 'https://example.test/steal' } })
    const user = userEvent.setup()
    wrap(<MotiveConnectionCard companyId="company-a" trucks={trucks} />)
    await user.click(await screen.findByRole('button', { name: 'Connect Motive' }))
    expect(await screen.findByRole('status')).toHaveTextContent('We could not complete this request')
  })
})
describe('Motive callback', () => {
  it('exchanges once and removes sensitive query values from browser history', async () => {
    window.history.replaceState({}, '', '/fleet/motive/callback?code=fixture-code&state=fixture-state')
    mocks.post.mockResolvedValue({ data: connected })
    const view = wrap(<MotiveCallback />)
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/fleet?integrations=motive&company=company-a', { replace: true }))
    view.rerender(<MemoryRouter><MotiveCallback /></MemoryRouter>)
    expect(window.location.search).toBe('')
    expect(mocks.post).toHaveBeenCalledWith('/fleet/motive/callback', { code: 'fixture-code', state: 'fixture-state' }, { skipAuthRefresh: true })
    expect(mocks.post).toHaveBeenCalledTimes(1)
  })
  it('submits cancellation for state consumption and shows a clear outcome', async () => {
    window.history.replaceState({}, '', '/fleet/motive/callback?error=access_denied&state=fixture-state')
    mocks.post.mockRejectedValue({ response: { status: 400, data: { detail: { code: 'oauth_denied', message: 'Authorization cancelled' } } } })
    wrap(<MotiveCallback />)
    expect(await screen.findByRole('alert')).toHaveTextContent('cancelled')
    expect(mocks.post).toHaveBeenCalledWith('/fleet/motive/callback', { error: 'access_denied', state: 'fixture-state' }, { skipAuthRefresh: true })
    expect(mocks.navigate).not.toHaveBeenCalled()
  })
  it('exchanges only once under React StrictMode', async () => {
    window.history.replaceState({}, '', '/fleet/motive/callback?code=fixture-code&state=fixture-state')
    mocks.post.mockResolvedValue({ data: connected })
    wrap(<StrictMode><MotiveCallback /></StrictMode>)
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalled())
    expect(mocks.post).toHaveBeenCalledTimes(1)
  })
  it('asks to restart expired authorization without exposing server details', async () => {
    window.history.replaceState({}, '', '/fleet/motive/callback?code=fixture-code&state=fixture-state')
    mocks.post.mockRejectedValue({ response: { status: 400, data: { detail: { code: 'oauth_session_invalid', message: 'private-state-value' } } } })
    wrap(<MotiveCallback />)
    expect(await screen.findByRole('alert')).toHaveTextContent('invalid or expired')
    expect(screen.queryByText(/private-state-value/)).not.toBeInTheDocument()
  })
  it('rejects missing state without sending a provider code', async () => {
    window.history.replaceState({}, '', '/fleet/motive/callback?code=fixture-code')
    wrap(<MotiveCallback />)
    expect(await screen.findByRole('alert')).toHaveTextContent('invalid or expired')
    expect(mocks.post).not.toHaveBeenCalled()
    expect(window.location.search).toBe('')
  })
})
