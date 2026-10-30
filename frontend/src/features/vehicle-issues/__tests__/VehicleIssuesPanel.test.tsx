import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import type { ComponentProps } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import VehicleIssuesPanel from '../VehicleIssuesPanel'
import { issueFields, scopedIssue, scopedPage, type VehicleIssue } from '../contract'
import { readTruckIssueReturn, readTruckIssueRestore } from '../navigation'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ appearance: { mode: 'dark' } }), appearanceTokenRecord: () => ({ '--workspace-text': '#fff' }) }))
const vehicle = '10000000-0000-4000-8000-000000000001'
const issueId = '10000000-0000-4000-8000-000000000002'
const ownerId = '10000000-0000-4000-8000-000000000003'
const orderId = '10000000-0000-4000-8000-000000000004'
const now = '2026-10-30T12:00:00Z'
const issue = (changes: Partial<VehicleIssue> = {}): VehicleIssue => ({ id: issueId, vehicle_id: vehicle, description: 'Inspect the rear seal', priority: 'soon', state: 'open', version: 1, responsible_user: null, follow_up_on: null, follow_up_state: 'unscheduled', created_at: now, updated_at: now, state_changed_at: null, state_reason: null, current_link: null, capabilities: { can_edit: true, can_change_state: true, can_link_context: true, can_end_link: false }, ...changes })
const page = (items = [issue()], extra = {}) => ({ items, total: items.length, skip: 0, limit: 25, has_more: false, as_of: now, timezone: 'America/New_York', ...extra })
const staff = (role = 'garage_owner', tenant: string | null = 'tenant-a', active = true) => ({ id: ownerId, tenant_id: tenant, role, is_active: active, customer_id: null }) as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>
function setup(props: ComponentProps<typeof VehicleIssuesPanel> = { vehicleId: vehicle, contextOrderId: orderId }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const content = (next = props) => <QueryClientProvider client={client}><MemoryRouter><VehicleIssuesPanel {...next} /></MemoryRouter></QueryClientProvider>
  const result = render(content())
  return { ...result, client, change: (next: typeof props) => result.rerender(content(next)) }
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  useAuthStore.setState({ user: staff(), isAuthenticated: true, logoutInProgress: false, authSessionEpoch: 1 })
  mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('issue-owners') ? { items: [{ id: ownerId, display_name: 'Sam Staff' }] } : url.endsWith(`issues/${issueId}`) ? issue() : page() }))
  mocks.post.mockResolvedValue({ data: { issue: issue(), replayed: false } })
  mocks.patch.mockResolvedValue({ data: { issue: issue(), replayed: false } })
})
afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals() })

describe('C3 staff truck issues', () => {
  it.each(['mechanic', 'fleet_manager', 'customer', 'driver', 'super_admin'])('hides existing cache and makes no requests for %s', role => {
    useAuthStore.setState({ user: staff(role) }); setup(); expect(screen.queryByRole('region')).not.toBeInTheDocument(); expect(mocks.get).not.toHaveBeenCalled()
  })
  it.each([[null, true], ['tenant-a', false]] as const)('rejects missing tenant or inactive actor', (tenant, active) => {
    useAuthStore.setState({ user: staff('garage_owner', tenant, active) }); setup(); expect(mocks.get).not.toHaveBeenCalled()
  })
  it('does not expose a persisted user without an authenticated session', () => {
    useAuthStore.setState({ isAuthenticated: false }); setup(); expect(mocks.get).not.toHaveBeenCalled()
  })
  it('loads exact context with cancellation, shows honest nulls, and keeps a separate empty state', async () => {
    setup(); expect(await screen.findByText('Inspect the rear seal')).toBeVisible()
    expect(screen.getByText('Unassigned')).toBeVisible(); expect(screen.getByText('Not scheduled')).toBeVisible()
    expect(mocks.get).toHaveBeenCalledWith(`/vehicles/${vehicle}/issues`, { params: { customer_id: undefined, context_order_id: orderId, state: 'open', skip: 0, limit: 25 }, signal: expect.any(AbortSignal) })
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('creates only metadata without an RO and preserves the same request on an uncertain retry', async () => {
    const user = userEvent.setup(); setup({ vehicleId: vehicle })
    await user.click(screen.getByRole('button', { name: 'Add issue' })); await user.type(screen.getByLabelText('Description'), 'Check air leak')
    await screen.findByRole('button', { name: 'Save issue' })
    mocks.post.mockRejectedValueOnce(new Error('Network disconnected'))
    await user.click(screen.getByRole('button', { name: 'Save issue' })); await screen.findByText(/Save could not be confirmed/)
    expect(screen.getByLabelText('Description')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Retry same request' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(mocks.post.mock.calls[1][1]).toEqual(mocks.post.mock.calls[0][1])
    expect(mocks.post.mock.calls[0][0]).toBe(`/vehicles/${vehicle}/issues`)
    expect(mocks.post.mock.calls[0][1]).toEqual({ request_id: expect.any(String), description: 'Check air leak', priority: 'soon', responsible_user_id: null, follow_up_on: null })
  })
  it('untouched and dirty cancellation make no writes; discard restores caller focus', async () => {
    const user = userEvent.setup(); setup()
    const add = screen.getByRole('button', { name: 'Add issue' }); await user.click(add)
    await user.click(screen.getByRole('button', { name: 'Cancel' })); expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await user.click(add); await user.type(screen.getByLabelText('Description'), 'Keep draft'); await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('heading', { name: 'Discard unsaved issue changes?' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Keep editing' })); expect(screen.getByLabelText('Description')).toHaveValue('Keep draft')
    await user.click(screen.getByRole('button', { name: 'Cancel' })); await user.click(screen.getByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect(add).toHaveFocus()); expect(mocks.post).not.toHaveBeenCalled()
  })
  it('uses themed open menus and clears owner/date explicitly on edit', async () => {
    const owned = issue({ responsible_user: { id: ownerId, display_name: 'Sam Staff', active: true }, follow_up_on: '2026-11-01', follow_up_state: 'upcoming' })
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith('issue-owners') ? { items: [{ id: ownerId, display_name: 'Sam Staff' }] } : url.endsWith(issueId) ? owned : page([owned]) }))
    const user = userEvent.setup(); setup(); await user.click(await screen.findByRole('button', { name: /View truck issue/ })); await user.click(await screen.findByRole('button', { name: 'Edit', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Responsible staff' })); const list = screen.getByRole('listbox'); expect(list).toHaveAttribute('data-appearance-mode', 'dark')
    await user.click(within(list).getByRole('option', { name: 'Unassigned' })); await user.clear(screen.getByLabelText('Follow-up date'))
    await user.click(screen.getByRole('button', { name: 'Save issue' })); await waitFor(() => expect(mocks.patch).toHaveBeenCalled())
    expect(mocks.patch.mock.calls[0][1]).toMatchObject({ expected_version: 1, responsible_user_id: null, follow_up_on: null })
  })
  it('requires a reason and explicit reference confirmation, never converting work', async () => {
    const user = userEvent.setup(); setup(); await user.click(await screen.findByRole('button', { name: /View truck issue/ })); await user.click(await screen.findByRole('button', { name: 'Link this visit' }))
    expect(screen.getByText(/This creates no work/)).toBeVisible(); expect(mocks.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Link this visit' })); await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1))
    expect(mocks.post.mock.calls[0][0]).toBe(`/vehicles/${vehicle}/issues/${issueId}/links`)
    expect(mocks.post.mock.calls[0][1]).toMatchObject({ expected_version: 1, target_order_id: orderId })
  })
  it('carries an exact scoped caller through a linked visit and restores its issue-row focus', async () => {
    const targetId = '10000000-0000-4000-8000-000000000005'
    const linked = issue({ current_link: { id: ownerId, target_order_id: targetId, order_number: 'RO-1', availability: 'available', created_at: now } })
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith(issueId) ? linked : page([linked]) }))
    let location!: ReturnType<typeof useLocation>
    let navigate!: ReturnType<typeof useNavigate>
    function Workspace() { location = useLocation(); navigate = useNavigate(); return <VehicleIssuesPanel vehicleId={vehicle} contextOrderId={new URLSearchParams(location.search).get('selected')!} /> }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const search = `?selected=${orderId}&queue=on_floor&search=truck`
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/dashboard${search}`]}><Workspace /></MemoryRouter></QueryClientProvider>)
    const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: /View truck issue/ })); await user.click(await screen.findByRole('link', { name: 'Visit RO-1' }))
    await waitFor(() => expect(new URLSearchParams(location.search).get('selected')).toBe(targetId))
    const scope = JSON.stringify(['tenant-a', ownerId, 'garage_owner', 1])
    const origin = readTruckIssueReturn(location.state, scope, targetId)!
    expect(origin).toMatchObject({ pathname: '/dashboard', search, sourceOrderId: orderId, targetOrderId: targetId, vehicleId: vehicle, issueId, filter: 'open', skip: 0 })
    expect(readTruckIssueReturn(location.state, 'different-session', targetId)).toBeNull()
    expect(readTruckIssueReturn(location.state, scope, orderId)).toBeNull()
    act(() => navigate({ pathname: origin.pathname, search: origin.search }, { replace: true, state: { truckIssueRestore: origin } }))
    await waitFor(() => expect(screen.getByRole('button', { name: /View truck issue/ })).toHaveFocus())
    expect(location.search).toBe(search); expect(mocks.post).not.toHaveBeenCalled()
  })
  it('labels an already-current linked visit without creating a self-return loop', async () => {
    const linked = issue({ current_link: { id: ownerId, target_order_id: orderId, order_number: 'RO-2', availability: 'available', created_at: now } })
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith(issueId) ? linked : page([linked]) }))
    const user = userEvent.setup(); setup(); await user.click(await screen.findByRole('button', { name: /View truck issue/ })); expect(await screen.findByText('This visit · RO-2')).toBeVisible(); expect(screen.queryByRole('link', { name: /Visit/ })).not.toBeInTheDocument()
  })
  it('returns from a linked visit to the exact customer truck and issue row', async () => {
    const linked = issue({ current_link: { id: ownerId, target_order_id: orderId, order_number: 'RO-1', availability: 'available', created_at: now } })
    mocks.get.mockImplementation(async (url: string) => ({ data: url.endsWith(issueId) ? linked : page([linked]) }))
    let location!: ReturnType<typeof useLocation>
    let navigate!: ReturnType<typeof useNavigate>
    function Workspace() { location = useLocation(); navigate = useNavigate(); return <VehicleIssuesPanel vehicleId={vehicle} customerId={location.pathname === '/dashboard/customers' ? ownerId : undefined} contextOrderId={location.pathname === '/dashboard/customers' ? undefined : orderId} /> }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const search = `?selected=${ownerId}&vehicle=${vehicle}&historyStatus=paid`
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[`/dashboard/customers${search}`]}><Workspace /></MemoryRouter></QueryClientProvider>)
    const user = userEvent.setup(); await user.click(await screen.findByRole('button', { name: /View truck issue/ })); await user.click(await screen.findByRole('link', { name: 'Visit RO-1' }))
    await waitFor(() => expect(location.pathname).toBe('/dashboard/repair-orders'))
    expect(location.search).toBe(`?selected=${orderId}`)
    const scope = JSON.stringify(['tenant-a', ownerId, 'garage_owner', 1])
    const origin = readTruckIssueReturn(location.state, scope, orderId)!
    expect(origin).toMatchObject({ pathname: '/dashboard/customers', search, customerId: ownerId, sourceOrderId: null, vehicleId: vehicle })
    expect(readTruckIssueReturn({ truckIssueReturn: { ...origin, vehicleId: orderId } }, scope, orderId)).toBeNull()
    act(() => navigate({ pathname: origin.pathname, search: origin.search }, { replace: true, state: { truckIssueRestore: origin } }))
    await waitFor(() => expect(screen.getByRole('button', { name: /View truck issue/ })).toHaveFocus())
    expect(location.search).toBe(search); expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not infer resolution from paid or unavailable linked visits; state changes require a reason', async () => {
    const linked = issue({ current_link: { id: ownerId, target_order_id: null, order_number: null, availability: 'unavailable', created_at: now } })
    mocks.get.mockResolvedValueOnce({ data: page([linked]) }).mockResolvedValueOnce({ data: linked })
    const user = userEvent.setup(); setup(); await user.click(await screen.findByRole('button', { name: /View truck issue/ })); await user.click(await screen.findByRole('button', { name: 'Resolve', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Resolve issue' })); expect(mocks.post).not.toHaveBeenCalled()
    await user.type(screen.getByLabelText('Reason'), 'Inspected and corrected'); await user.click(screen.getByRole('button', { name: 'Resolve issue' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1)); expect(mocks.post.mock.calls[0][1]).toMatchObject({ expected_version: 1, state: 'resolved', reason: 'Inspected and corrected' })
  })
  it('holds stale version conflicts for explicit reload, never silently overwriting', async () => {
    const user = userEvent.setup(); setup(); await user.click(await screen.findByRole('button', { name: /View truck issue/ })); await user.click(await screen.findByRole('button', { name: 'Edit', exact: true }))
    await user.type(screen.getByLabelText('Description'), ' more')
    mocks.patch.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'issue_changed', message: 'Issue changed. Reload before editing.' } } } })
    await user.click(screen.getByRole('button', { name: 'Save issue' })); await screen.findByText('Issue changed. Reload before editing.')
    expect(await screen.findByRole('button', { name: 'Back to latest issue' })).toBeVisible(); expect(screen.getByRole('button', { name: 'Save issue' })).toBeDisabled(); expect(mocks.patch).toHaveBeenCalledTimes(1)
  })
  it('aborts late requests and removes old truck data on context and role changes', async () => {
    const { change } = setup(); await screen.findByText('Inspect the rear seal')
    mocks.get.mockImplementation(() => new Promise(() => {})); change({ vehicleId: orderId, contextOrderId: orderId })
    expect(screen.queryByText('Inspect the rear seal')).not.toBeInTheDocument(); const signal = mocks.get.mock.calls.at(-1)?.[1].signal
    act(() => useAuthStore.setState({ user: staff('mechanic') })); expect(screen.queryByRole('region')).not.toBeInTheDocument(); await waitFor(() => expect(signal.aborted).toBe(true))
  })
  it('does not turn malformed list responses into false empty results', async () => {
    mocks.get.mockResolvedValue({ data: page([issue({ vehicle_id: orderId })]) }); setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load truck issues'); expect(screen.queryByText('No open truck issues.')).not.toBeInTheDocument()
  })
  it.each(['tenant', 'customer', 'order'] as const)('separates cached data on %s context changes', async kind => {
    const { change, client } = setup({ vehicleId: vehicle, customerId: ownerId, contextOrderId: orderId }); await screen.findByText('Inspect the rear seal')
    mocks.get.mockImplementation(() => new Promise(() => {}))
    if (kind === 'tenant') act(() => useAuthStore.setState({ user: staff('garage_owner', 'tenant-b') }))
    else change({ vehicleId: vehicle, customerId: kind === 'customer' ? orderId : ownerId, contextOrderId: kind === 'order' ? ownerId : orderId })
    expect(screen.queryByText('Inspect the rear seal')).not.toBeInTheDocument()
    expect(client.getQueryCache().getAll().length).toBeGreaterThan(1)
  })
  it('guards programmatic route changes until discard is explicit', async () => {
    let navigate!: ReturnType<typeof useNavigate>
    function Probe() { navigate = useNavigate(); return <output>{useLocation().pathname}</output> }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/truck']}><VehicleIssuesPanel vehicleId={vehicle} /><Probe /></MemoryRouter></QueryClientProvider>)
    const user = userEvent.setup(); await user.click(screen.getByRole('button', { name: 'Add issue' })); await user.type(screen.getByLabelText('Description'), 'Keep draft')
    act(() => navigate('/elsewhere')); expect(screen.getByText('/truck')).toBeInTheDocument(); expect(screen.getByRole('heading', { name: 'Discard unsaved issue changes?' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Keep editing' })); expect(screen.getByLabelText('Description')).toHaveValue('Keep draft')
    act(() => navigate('/elsewhere')); await user.click(screen.getByRole('button', { name: 'Discard changes' })); expect(screen.getByText('/elsewhere')).toBeInTheDocument(); expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expect(mocks.post).not.toHaveBeenCalled()
  })
  it('renders HTML as text and follows server pagination separately from recommendations', async () => {
    mocks.get.mockResolvedValueOnce({ data: page([issue({ description: '<script>bad()</script>' })], { total: 26, has_more: true }) }).mockResolvedValueOnce({ data: page([issue()], { skip: 25, total: 26 }) })
    const user = userEvent.setup(); setup(); expect(await screen.findByText('<script>bad()</script>')).toBeVisible(); await user.click(screen.getByRole('button', { name: 'Next' })); await screen.findByText('26–26 of 26')
    expect(mocks.get.mock.calls[1][1].params.skip).toBe(25)
  })
  it('warns on unload only while dirty', async () => {
    const events = vi.spyOn(window, 'addEventListener')
    const user = userEvent.setup(); setup(); await user.click(screen.getByRole('button', { name: 'Add issue' }))
    const before = events.mock.calls.filter(call => call[0] === 'beforeunload').length
    await user.type(screen.getByLabelText('Description'), 'Draft')
    const handlers = events.mock.calls.filter(call => call[0] === 'beforeunload')
    expect(handlers.length).toBeGreaterThan(before)
    const dirty = new Event('beforeunload', { cancelable: true }); (handlers.at(-1)![1] as EventListener)(dirty); expect(dirty.defaultPrevented).toBe(true)
    events.mockRestore()
  })
})

describe('C3 response and metadata boundaries', () => {
  it('rejects malformed detail identities, duplicate rows, invalid dates and missing link identities', () => {
    expect(() => scopedIssue(issue(), vehicle, orderId)).toThrow(); expect(() => scopedPage(page([issue(), issue()]), vehicle, 0, 'open')).toThrow()
    expect(() => scopedIssue(issue({ follow_up_on: '2026-02-30' }), vehicle)).toThrow()
    expect(() => scopedIssue(issue({ current_link: { id: ownerId, availability: 'available', target_order_id: null, order_number: null, created_at: now } }), vehicle)).toThrow()
  })
  it('preserves an inactive existing assignment without sending it as a new owner', () => {
    const original = issue({ responsible_user: { id: ownerId, display_name: 'Former staff', active: false } })
    expect(issueFields({ description: 'Updated', priority: 'soon', owner: ownerId, date: '' }, original)).not.toHaveProperty('responsible_user_id')
  })
  it('rejects untrusted return routes and restores only the exact vehicle/session', () => {
    const origin = { pathname: 'https://elsewhere.invalid', search: `?selected=${orderId}`, scope: 'scope', vehicleId: vehicle, issueId, sourceOrderId: orderId, customerId: null, targetOrderId: ownerId, filter: 'all', skip: 25 }
    expect(readTruckIssueReturn({ truckIssueReturn: origin }, 'scope', ownerId)).toBeNull()
    expect(readTruckIssueRestore({ truckIssueRestore: origin }, 'scope', orderId)).toBeNull()
    expect(readTruckIssueRestore({ truckIssueRestore: origin }, 'other-scope', vehicle)).toBeNull()
  })
})
