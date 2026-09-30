import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), navigate: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('react-router-dom', async () => ({ ...await vi.importActual('react-router-dom'), useNavigate: () => mocks.navigate }))
import { MotiveIntegrationWorkspace, MotiveConnectionCard } from '../MotiveIntegrationPanel'
import { MotiveGrants, MotiveWebhook } from '../MotiveManagement'
import MotiveCallback from '../MotiveCallback'
import { MotivePortalEntry } from '../../customer-portal/MotivePortalPage'

const company = { id: 'company-a', company_name: 'Fleet A', fleet_enabled: true, is_internal_fleet: false, can_manage_grants: false }
const connection = { fleet_customer_id: company.id, configured: true, can_connect: true, status: 'connected', company: { id: 'provider-a', name: company.company_name }, last_sync_at: null, last_sync_counts: null }
const webhook = { status: 'awaiting_provider', url: 'https://api.example.test/webhooks/motive/opaque/1', last_received_at: null, pending_count: 0, failed_count: 0 }
function actor(role = 'customer') { useAuthStore.setState({ user: { id: 'customer-a', role, tenant_id: 'selected-shop', customer_id: 'company-a' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']> }) }
function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const view = render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>)
  return { ...view, client }
}
beforeEach(() => {
  vi.resetAllMocks(); actor(); window.history.replaceState({}, '', '/')
  mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/companies') ? { items: [company] } : url.endsWith('/connection') ? connection : url.endsWith('/webhook') ? webhook : { items: [] } }))
})

describe('complete Motive customer and staff flow', () => {
  it('renders exactly one live-update panel alongside staff grant controls', async () => {
    actor('garage_owner')
    wrap(<MotiveConnectionCard companyId="company-a" canManageGrants />)
    expect(await screen.findByLabelText('Motive administrators')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Motive webhook setup')).toHaveLength(1)
  })
  it('shows continuation as saved progress without a failure or false completion', async () => {
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/connection') ? { ...connection, last_sync_error_code: 'reconciliation_incomplete' } : url.endsWith('/webhook') ? webhook : { items: [] } }))
    mocks.post.mockResolvedValue({ data: { status: 'connected', completed_at: null, counts: { updated: 2 } } })
    const user = userEvent.setup(); wrap(<MotiveConnectionCard companyId="company-a" />)
    expect(await screen.findByText('Sync in progress')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Sync now' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Remaining trucks continue automatically')
    expect(screen.queryByText(/Sync finished/)).not.toBeInTheDocument()
  })
  it('uses only Motive scoped companies and truck options for a granted customer', async () => {
    wrap(<MotiveIntegrationWorkspace />)
    expect(await screen.findByText('Connected company:', { exact: false })).toBeInTheDocument()
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/fleet/motive/trucks', expect.objectContaining({ params: { fleet_customer_id: 'company-a' } })))
    expect(mocks.get.mock.calls.every(([url]) => String(url).startsWith('/fleet/motive/'))).toBe(true)
    expect(screen.queryByLabelText('Motive administrators')).not.toBeInTheDocument()
    expect(mocks.get.mock.calls.some(([url]) => String(url).includes('grant'))).toBe(false)
  })
  it('hides the portal entry and connection controls when no company grant exists', async () => {
    mocks.get.mockResolvedValue({ data: { items: [] } })
    wrap(<><MotivePortalEntry /><MotiveIntegrationWorkspace /></>)
    expect(await screen.findByText(/Ask your shop administrator to grant Motive access/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Integrations' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Motive connection')).not.toBeInTheDocument()
    expect(mocks.get.mock.calls.every(([url]) => url === '/fleet/motive/companies')).toBe(true)
  })
  it('returns a successful customer callback to customer integrations', async () => {
    window.history.replaceState({}, '', '/fleet/motive/callback?code=fixture-code&state=fixture-state')
    mocks.post.mockResolvedValue({ data: connection })
    wrap(<MotiveCallback />)
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/portal/integrations?company=company-a', { replace: true }))
    expect(window.location.search).toBe('')
    expect(mocks.post).toHaveBeenCalledTimes(1)
  })
  it('scopes staff grant and revoke requests to the selected company', async () => {
    actor('garage_owner')
    let granted = false
    const person = { user_id: 'linked-user', name: 'Fleet Admin', email: 'admin@example.test' }
    mocks.get.mockImplementation(async (url: string) => ({ data: { items: url.endsWith('grant-candidates') || granted ? [person] : [] } }))
    mocks.put.mockImplementation(async () => { granted = true; return { data: person } })
    mocks.delete.mockImplementation(async () => { granted = false; return {} })
    const user = userEvent.setup(); wrap(<MotiveGrants companyId="company-a" />)
    await screen.findByRole('option', { name: 'Fleet Admin · admin@example.test' })
    await user.selectOptions(screen.getByLabelText('Linked customer'), 'linked-user')
    await user.click(screen.getByRole('button', { name: 'Grant administrator access' }))
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith('/fleet/motive/grants/linked-user', { fleet_customer_id: 'company-a' }))
    await user.click(await screen.findByRole('button', { name: 'Revoke Fleet Admin' }))
    await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith('/fleet/motive/grants/linked-user', { params: { fleet_customer_id: 'company-a' } }))
    expect(await screen.findByText('Administrator access revoked.')).toBeInTheDocument()
  })
  it('requires confirmation before rotation and keeps the one-time secret out of caches/storage', async () => {
    const user = userEvent.setup()
    const { client } = wrap(<MotiveWebhook companyId="company-a" />)
    mocks.post.mockResolvedValue({ data: { ...webhook, shared_secret: 'fixture-one-time-secret' } })
    await user.click(await screen.findByRole('button', { name: 'Rotate webhook secret' }))
    expect(mocks.post).not.toHaveBeenCalled()
    const writes = vi.spyOn(Storage.prototype, 'setItem')
    await user.click(screen.getByRole('button', { name: 'Generate webhook secret' }))
    expect(await screen.findByLabelText('One-time shared secret')).toHaveValue('fixture-one-time-secret')
    expect(mocks.post).toHaveBeenCalledWith('/fleet/motive/webhook/rotate', { fleet_customer_id: 'company-a' })
    expect(JSON.stringify(client.getQueryCache().getAll().map((q) => q.state.data))).not.toContain('fixture-one-time-secret')
    expect(client.getMutationCache().getAll()).toHaveLength(0)
    expect(writes).not.toHaveBeenCalled(); writes.mockRestore()
    await user.click(screen.getByRole('button', { name: 'Hide secret' }))
    expect(screen.queryByLabelText('One-time shared secret')).not.toBeInTheDocument()
    expect(screen.getByText('Awaiting Motive setup')).toBeInTheDocument()
  })
  it('shows actual zero readings, separates absent true readings from virtual, and shows fault lifecycle', async () => {
    const stamp = new Date(Date.now() - 3600000).toISOString()
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('/connection') ? connection : url.endsWith('/webhook') ? webhook : url.endsWith('/trucks') ? { items: [{ id: 'truck-a', unit_number: '7', vin: null }] } : { items: [{ provider_vehicle_id: 'p7', number: '7', vehicle_id: 'truck-a', mapping_state: 'mapped', match_candidates: [], gateway_id: 'g7', gateway_identifier: 'device-7', gateway_model: 'lbb', metrics: { odometer_miles: null, virtual_odometer_miles: 500, engine_hours: 0, virtual_engine_hours: null, observed_at: stamp, received_at: stamp, source: 'motive' }, faults_synced_at: stamp, faults: [{ id: 'fault-1', code_label: 'SPN-100', code: null, description: 'Reported engine fault', status: 'closed', first_observed_at: stamp, last_observed_at: stamp, fmi: null }] }] } }))
    wrap(<MotiveConnectionCard companyId="company-a" />)
    expect(await screen.findByText('500 mi')).toBeInTheDocument()
    expect(screen.getByText('0 h')).toBeInTheDocument()
    expect(screen.getByText('Calibrated odometer').parentElement).toHaveTextContent('Not reported')
    expect(screen.getByText(/Device: device-7/)).toBeInTheDocument()
    expect(screen.getByText('SPN-100').parentElement).toHaveTextContent('closed')
    expect(screen.getByText(/Motive · stale/)).toBeInTheDocument()
  })
  it('suppresses cached connection details after access is revoked', async () => {
    const { client } = wrap(<MotiveConnectionCard companyId="company-a" />)
    expect(await screen.findByText(/Connected company:/)).toBeInTheDocument()
    mocks.get.mockRejectedValue({ response: { status: 403 } })
    await client.invalidateQueries({ queryKey: ['motive-connection'] })
    expect(await screen.findByText(/Only an authorized company administrator/)).toBeInTheDocument()
    expect(screen.queryByText(/Connected company:/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sync now' })).not.toBeInTheDocument()
  })
})
