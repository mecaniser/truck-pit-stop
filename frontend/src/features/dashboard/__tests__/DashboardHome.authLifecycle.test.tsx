import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { QueryClient, QueryClientProvider, keepPreviousData } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import DashboardHome from '../DashboardHome'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'

const apiMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../../../lib/api', () => ({ default: apiMock }))

const testState = vi.hoisted(() => ({
  presentationVariant: 'new' as 'new' | 'legacy',
  navigate: vi.fn(),
  locationSearch: '',
  locationState: null as { shopWorkQueue: string; shopWorkView?: string } | null,
  invalidateQueries: vi.fn(),
  overviewRefetch: vi.fn(),
  overviewError: false,
  actor: null as (typeof garageOwnerSession & { permissions?: Record<string, boolean> }) | null,
  epoch: 1,
  signedOut: false,
  realQueries: false,
  queryKeys: [] as unknown[][],
  query: {
    data: undefined as Record<string, unknown> | undefined,
    isLoading: false,
    error: null as Error | null,
    isFetching: false,
    dataUpdatedAt: Date.now(),
  },
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => testState.navigate,
  useLocation: () => ({ state: testState.locationState, search: testState.locationSearch }),
}))
vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return { ...actual,
  useQuery: (options: Parameters<typeof actual.useQuery>[0]) => { const { queryKey } = options; testState.queryKeys.push(queryKey); if (testState.realQueries && ['shop-work-overview', 'dashboard-action-queue', 'dashboard-daily-workset'].includes(queryKey[0] as string)) return actual.useQuery(options); return queryKey[0] === 'shop-work-overview'
    ? { ...testState.query, data: { as_of: '2026-11-01T15:00:00Z', timezone: 'America/New_York', scope: 'shop', active_jobs: 1, sources: [], actions: [], upcoming: [], actions_total: 0, upcoming_total: 0, has_more_actions: false, has_more_upcoming: false }, refetch: testState.overviewRefetch, error: testState.overviewError ? new Error('overview offline') : null }
    : queryKey[0] === 'dashboard-wip-aging'
    ? { ...testState.query, data: wipFixture, isError: false }
    : queryKey[0] === 'activity-feed'
      ? { ...testState.query, data: { items: Array.from({ length: 20 }, (_, id) => ({ id: String(id) })), has_more: true }, isError: false }
      : testState.query },
  useQueryClient: () => testState.realQueries ? actual.useQueryClient() : ({ invalidateQueries: testState.invalidateQueries }),
} })
import { useAuthStore } from '../../../stores/authStore'
vi.mock('../../../contexts/ThemeContext', () => ({
  appearanceTokenRecord: () => ({}),
  useTheme: () => ({
    appearance: { mode: 'light' },
    presentationVariant: testState.presentationVariant,
    accentColors: { 400: '#d39a54', 500: '#b87333', 600: '#8a5424' },
    fontSize: 'default',
  }),
}))
vi.mock('../../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ isConnected: true, reconnect: vi.fn() }),
}))
vi.mock('../../../hooks/useNotificationManager', () => ({
  useNotificationManager: () => ({
    notify: vi.fn(), banners: [], dismissBanner: vi.fn(), clearBanners: vi.fn(),
  }),
}))
vi.mock('../../../components/NotificationBanner', () => ({ default: () => null }))
vi.mock('../../../components/AlertsBanner', () => ({ default: () => null }))
vi.mock('../../../components/SectionInfoTooltip', () => ({ default: () => null }))
vi.mock('../../../components/SuggestingInput', () => ({
  default: ({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder?: string }) => (
    <input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
  ),
}))
vi.mock('../RecentActivityFeed', () => ({ default: () => <div>Activity surface</div> }))
vi.mock('../../repair-orders/RepairOrdersPage', () => ({
  default: ({ workbenchScope }: { workbenchScope?: string }) => <div data-testid="repair-order-workspace">{workbenchScope}</div>,
}))

const order = (overrides: Record<string, unknown> = {}) => ({
  id: 'ro-needs-17',
  order_number: 'RO-1017',
  status: 'pending_review',
  pending_zelle_confirmation: false,
  description: 'Diagnose intermittent no-start',
  customer_name: 'Apex Freight',
  vehicle_info: '2021 Freightliner Cascadia · Unit 41',
  total_cost: '1840.25',
  created_at: '2026-08-12T12:00:00Z',
  updated_at: '2026-08-12T15:00:00Z',
  mechanic_name: 'Morgan Lee',
  work_started_at: null,
  hold_reason: null,
  held_at: null,
  quote_sent: true,
  ...overrides,
})

const dashboardFixture = {
  total_customers: 0,
  total_vehicles: 0,
  total_repair_orders: 3,
  orders_by_status: [],
  active_orders: 1,
  awaiting_approval: 1,
  pending_invoices: 1,
  low_stock_count: 0,
  recent_orders: [],
  my_assigned_orders: 0,
  my_in_progress: 0,
  revenue: {},
  mechanic_workload: [],
  overdue_approvals: 0,
  declined_quotes: 0,
  orders_needing_action: [order()],
  orders_needing_action_has_more: false,
  orders_on_floor: [order({ id: 'ro-floor-22', order_number: 'RO-1022', status: 'in_progress' })],
  orders_on_floor_has_more: false,
  orders_ready_to_close: [order({ id: 'ro-close-09', order_number: 'RO-1009', status: 'invoiced' })],
  orders_ready_to_close_has_more: false,
  timezone: 'America/New_York',
  business_date: '2026-08-12',
  next_reset_at: '2026-08-13T04:00:00Z',
  needs_attention: { items: [order()], has_more: false },
  on_floor: { items: [order({ id: 'ro-floor-22', order_number: 'RO-1022', status: 'in_progress' })], has_more: false },
  ready_to_close: { items: [order({ id: 'ro-close-09', order_number: 'RO-1009', status: 'invoiced' })], has_more: false },
  closed_today: { items: [], has_more: false },
}

const wipFixture = {
  scope: 'shop', timezone: 'America/New_York', filters: { search: '' },
  summary: { total_jobs: 1, overdue_jobs: 0, unknown_wait_jobs: 0, category_counts: { approval: 0, parts: 0, technician: 0, review: 0, other_hold: 0, active: 1, preparation: 0 } },
  filtered_total: 1, offset: 0, limit: 50, has_more: false,
  items: [{ ...order({ id: 'ro-floor-22', order_number: 'RO-1022', status: 'in_progress' }), category: 'active', reason: 'work_in_progress', assignment: 'assigned', technician_names: ['Morgan Lee'], order_age: { state: 'known', seconds: 3600 }, current_wait: { state: 'not_applicable' }, promised_finish_at: null, action_lane: 'on_floor' }],
}

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(min-width: 1024px)',
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
})

describe('dashboard authenticated lifecycle with real authStore', () => {
  const overview = { as_of: '2026-11-02T15:00:00Z', timezone: 'America/New_York', scope: 'shop', active_jobs: 0, sources: [], actions: [{ id: 'inventory:private', source: 'inventory', destination: { kind: 'inventory', id: 'private', view: null }, title: 'Private tenant stock', reason: 'stock_preparation', action_label: 'Review stock', status: 'needs_review', created_at: null, due_at: null, due_kind: null, evidence: 'verified', quantity: 1, related_repair_order_ids: [] }], upcoming: [], actions_total: 1, upcoming_total: 0, has_more_actions: false, has_more_upcoming: false }
  let client: QueryClient
  beforeEach(() => {
    apiMock.get.mockReset(); apiMock.post.mockReset()
    testState.realQueries = true
    testState.presentationVariant = 'new'; testState.locationSearch = ''; testState.locationState = null
    useAuthStore.setState({ user: { ...garageOwnerSession }, isAuthenticated: true, logoutInProgress: false, authProvider: 'legacy', authSessionEpoch: 1, token: null, refreshToken: null })
    client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, placeholderData: keepPreviousData } } })
    apiMock.get.mockImplementation((url: string) => Promise.resolve({ data: url.includes('shop-work-overview') ? overview : dashboardFixture }))
  })
  afterEach(() => { cleanup(); client.clear(); useAuthStore.getState().clearSession() })
  const view = () => <QueryClientProvider client={client}><DashboardHome /></QueryClientProvider>

  it('hides warm rows immediately and starts no reads while real logout is pending or completed', async () => {
    let finishLogout!: () => void
    apiMock.post.mockImplementation(() => new Promise<void>(resolve => { finishLogout = resolve }))
    render(view())
    await screen.findByText('Private tenant stock')
    const before = apiMock.get.mock.calls.length
    let logout!: Promise<void>
    act(() => { logout = useAuthStore.getState().logout() })
    expect(useAuthStore.getState().logoutInProgress).toBe(true)
    expect(useAuthStore.getState().user).not.toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('Signing out…')
    expect(screen.queryByText('Private tenant stock')).not.toBeInTheDocument()
    expect(apiMock.get.mock.calls.length).toBe(before)
    await act(async () => { finishLogout(); await logout })
    expect(screen.queryByRole('heading', { name: 'Shop Work' })).not.toBeInTheDocument()
    expect(apiMock.get.mock.calls.length).toBe(before)
  })

  it('discards in-flight successful reads after logout starts with one persistent QueryClient', async () => {
    let finishRead!: () => void
    const delayed = new Promise<void>(resolve => { finishRead = resolve })
    apiMock.get.mockImplementation((url: string) => delayed.then(() => ({ data: url.includes('shop-work-overview') ? overview : dashboardFixture })))
    let finishLogout!: () => void
    apiMock.post.mockImplementation(() => new Promise<void>(resolve => { finishLogout = resolve }))
    render(view())
    await waitFor(() => expect(apiMock.get).toHaveBeenCalledTimes(2))
    let logout!: Promise<void>
    act(() => { logout = useAuthStore.getState().logout() })
    expect(apiMock.get).toHaveBeenCalledTimes(2)
    await act(async () => { finishRead(); await delayed })
    expect(screen.queryByText('Private tenant stock')).not.toBeInTheDocument()
    expect(useAuthStore.getState().logoutInProgress).toBe(true)
    expect(client.getQueryCache().findAll({ queryKey: ['shop-work-overview'] }).every(query => query.state.data === undefined)).toBe(true)
    await act(async () => { finishLogout(); await logout })
  })

  it('suppresses reads and cached rows on the real inactive setUser transition', async () => {
    render(view()); await screen.findByText('Private tenant stock')
    const before = apiMock.get.mock.calls.length
    act(() => { useAuthStore.getState().setUser({ ...garageOwnerSession, is_active: false }) })
    expect(useAuthStore.getState().authSessionEpoch).toBe(2)
    expect(screen.queryByText('Private tenant stock')).not.toBeInTheDocument()
    expect(apiMock.get.mock.calls.length).toBe(before)
  })

  it.each(['inactive', 'signed-out', 'pending-logout'] as const)('mounts no dashboard when %s retains an actor', state => {
    useAuthStore.setState({ user: { ...garageOwnerSession, is_active: state !== 'inactive' }, isAuthenticated: state !== 'signed-out', logoutInProgress: state === 'pending-logout' })
    render(view())
    expect(apiMock.get).not.toHaveBeenCalled()
    expect(screen.queryByRole('heading', { name: 'Shop Work' })).not.toBeInTheDocument()
  })

  it.each(['closeout', 'legacy', 'selected'] as const)('unmounts the %s surface and aborts its reads on logout intent', async mode => {
    testState.presentationVariant = mode === 'legacy' ? 'legacy' : 'new'
    testState.locationSearch = mode === 'closeout' ? '?work_view=closeout' : mode === 'selected' ? '?selected=ro-floor-22' : ''
    let finishLogout!: () => void
    apiMock.post.mockImplementation(() => new Promise<void>(resolve => { finishLogout = resolve }))
    apiMock.get.mockImplementation(() => new Promise(() => {}))
    const { container } = render(view())
    if (mode !== 'selected') await waitFor(() => expect(apiMock.get.mock.calls.length).toBeGreaterThan(0))
    expect(container.childElementCount).toBeGreaterThan(0)
    const before = apiMock.get.mock.calls.length
    const signals = apiMock.get.mock.calls.map(call => call[1]?.signal).filter(Boolean) as AbortSignal[]
    let logout!: Promise<void>
    act(() => { logout = useAuthStore.getState().logout() })
    expect(container).not.toHaveTextContent('Shop Work')
    expect(screen.queryByTestId('repair-order-workspace')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Signing out…')
    expect(apiMock.get.mock.calls.length).toBe(before)
    expect(signals.every(signal => signal.aborted)).toBe(true)
    await act(async () => { finishLogout(); await logout })
  })

  it('does not announce a previously submitted repair when its response arrives in the next shop', async () => {
    const notice = vi.spyOn(toast, 'success')
    let complete!: () => void
    apiMock.post.mockImplementationOnce(() => new Promise(resolve => {
      complete = () => resolve({ data: { order_number: 'A-PRIVATE' } })
    }))
    render(view())
    await screen.findByText('Private tenant stock')
    fireEvent.click(screen.getByRole('button', { name: 'Lightning Order' }))
    fireEvent.change(screen.getByPlaceholderText('(555) 123-4567'), { target: { value: '5551112222' } })
    fireEvent.change(screen.getByPlaceholderText('Engine overheating'), { target: { value: 'Repair in A' } })
    fireEvent.click(screen.getByRole('button', { name: /create order/i }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledTimes(1))
    act(() => useAuthStore.getState().establishCookieSession({ ...garageOwnerSession, id: 'b', tenant_id: 'b' }))
    await act(async () => complete())
    expect(notice).not.toHaveBeenCalled()
    notice.mockRestore()
  })

  it('never revives old rows after a different tenant authenticates while old reads finish', async () => {
    let finishRead!: () => void
    const delayed = new Promise<void>(resolve => { finishRead = resolve })
    apiMock.get.mockImplementation((url: string) => delayed.then(() => ({ data: url.includes('shop-work-overview') ? overview : dashboardFixture })))
    render(view()); await waitFor(() => expect(apiMock.get).toHaveBeenCalledTimes(2))
    act(() => useAuthStore.getState().clearSession())
    const emptyOverview = { ...overview, actions: [], actions_total: 0 }
    apiMock.get.mockImplementation((url: string) => Promise.resolve({ data: url.includes('shop-work-overview') ? emptyOverview : { ...dashboardFixture, needs_attention: { items: [], has_more: false }, on_floor: { items: [], has_more: false }, ready_to_close: { items: [], has_more: false }, closed_today: { items: [], has_more: false } } }))
    act(() => useAuthStore.getState().establishCookieSession({ ...garageOwnerSession, id: 'new-owner', tenant_id: 'new-tenant' }))
    await screen.findByRole('heading', { name: 'Shop Work' })
    await act(async () => { finishRead(); await delayed })
    expect(screen.queryByText('Private tenant stock')).not.toBeInTheDocument()
  })
})
