import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { QueryClient, QueryClientProvider, keepPreviousData } from '@tanstack/react-query'
import DashboardHome from '../DashboardHome'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'

const apiMock = vi.hoisted(() => ({ get: vi.fn() }))
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
  useQuery: (options: { queryKey: unknown[] }) => { const { queryKey } = options; testState.queryKeys.push(queryKey); if (testState.realQueries && ['shop-work-overview', 'dashboard-action-queue', 'dashboard-daily-workset'].includes(queryKey[0] as string)) return actual.useQuery(options); return queryKey[0] === 'shop-work-overview'
    ? { ...testState.query, data: { as_of: '2026-11-01T15:00:00Z', timezone: 'America/New_York', scope: 'shop', active_jobs: 1, sources: [], actions: [], upcoming: [], actions_total: 0, upcoming_total: 0, has_more_actions: false, has_more_upcoming: false }, refetch: testState.overviewRefetch, error: testState.overviewError ? new Error('overview offline') : null }
    : queryKey[0] === 'dashboard-wip-aging'
    ? { ...testState.query, data: wipFixture, isError: false }
    : queryKey[0] === 'activity-feed'
      ? { ...testState.query, data: { items: Array.from({ length: 20 }, (_, id) => ({ id: String(id) })), has_more: true }, isError: false }
      : testState.query },
  useQueryClient: () => testState.realQueries ? actual.useQueryClient() : ({ invalidateQueries: testState.invalidateQueries }),
} })
vi.mock('../../../stores/authStore', () => ({
  useAuthStore: (selector?: (state: { user: typeof garageOwnerSession | null; authSessionEpoch: number }) => unknown) => {
    const state = { user: testState.signedOut ? null : testState.actor ?? garageOwnerSession, authSessionEpoch: testState.epoch }
    return selector ? selector(state) : state
  },
}))
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

describe('DashboardHome DB-035 presentation boundary', () => {
  beforeEach(() => {
    testState.presentationVariant = 'new'
    testState.navigate.mockReset()
    testState.overviewError = false
    testState.overviewRefetch.mockReset()
    testState.actor = null
    testState.epoch = 1
    testState.signedOut = false
    testState.realQueries = false
    testState.queryKeys = []
    testState.locationSearch = ''
    testState.locationState = null
    testState.invalidateQueries.mockReset()
    testState.query = {
      data: dashboardFixture,
      isLoading: false,
      error: null,
      isFetching: false,
      dataUpdatedAt: Date.now(),
    }
  })

  it('shows capped Activity count before opening the feed and refreshes it with Shop Work', () => {
    render(<DashboardHome />)
    expect(screen.getByRole('button', { name: 'Activity 9+', exact: true })).toBeInTheDocument()
    expect(screen.queryByText('Activity surface')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Refresh Shop Work/ }))
    expect(testState.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['activity-feed'] })
  })

  it.each(['shop-work-overview', 'dashboard-action-queue', 'dashboard-daily-workset', 'value-summary'])('isolates cached %s data after same-actor role, payment grant, and session changes', (prefix) => {
    const { rerender } = render(<DashboardHome />)
    const latestKey = () => testState.queryKeys.filter(key => prefix === 'value-summary' ? key[1] === 'value-summary' : key[0] === prefix && key[1] !== 'value-summary').at(-1)
    const owner = latestKey()
    testState.actor = { ...garageOwnerSession, role: 'garage_admin', permissions: { payments: true } }
    rerender(<DashboardHome />)
    const admin = latestKey()
    expect(admin).not.toEqual(owner)
    testState.actor = { ...testState.actor, permissions: { payments: false } }
    testState.overviewError = true
    rerender(<DashboardHome />)
    const revoked = latestKey()
    expect(revoked).not.toEqual(admin)
    testState.epoch = 2
    rerender(<DashboardHome />)
    expect(latestKey()).not.toEqual(revoked)
  })

  it('does not retain prior tenant Closeout rows, badge, or totals during same-browser signout and signin', async () => {
    testState.realQueries = true
    const clearDaily = { ...dashboardFixture, needs_attention: { items: [], has_more: false }, on_floor: { items: [], has_more: false }, ready_to_close: { items: [], has_more: false }, closed_today: { items: [], has_more: false } }
    let resolveClear: (value: { data: typeof clearDaily }) => void = () => undefined
    const clearResponse = new Promise<{ data: typeof clearDaily }>(resolve => { resolveClear = resolve })
    apiMock.get.mockImplementation((url: string) => {
      if (url === '/dashboard/daily-workset') return testState.actor?.tenant_id === 'clear-tenant' ? clearResponse : Promise.resolve({ data: dashboardFixture })
      if (url === '/dashboard/shop-work-overview') return Promise.resolve({ data: { as_of: '2026-11-01T15:00:00Z', timezone: 'America/New_York', scope: 'shop', active_jobs: 0, sources: [], actions: [], upcoming: [], actions_total: 0, upcoming_total: 0, has_more_actions: false, has_more_upcoming: false } })
      if (url === '/dashboard/daily-workset/value-summary') return Promise.resolve({ data: { order_count: testState.actor?.tenant_id === 'clear-tenant' ? 0 : 1, order_value: testState.actor?.tenant_id === 'clear-tenant' ? '0' : '1840.25', currency: 'USD', amount_basis: 'repair_order_net' } })
      throw new Error(`Unexpected request ${url}`)
    })
    // Retain the real query cache and a global previous-data default across logins.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity, placeholderData: keepPreviousData } } })
    const view = () => <QueryClientProvider client={client}><DashboardHome /></QueryClientProvider>
    const { rerender, unmount } = render(view())
    fireEvent.click(await screen.findByRole('button', { name: /^Closeout 1/ }))
    expect(await screen.findByRole('button', { name: 'Open RO-1009 in Repair Orders' })).toBeInTheDocument()
    await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith('/dashboard/daily-workset/value-summary', expect.anything()))
    testState.signedOut = true
    testState.epoch = 2
    rerender(view())
    expect(screen.queryByRole('button', { name: 'Open RO-1009 in Repair Orders' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Closeout 1/ })).not.toBeInTheDocument()
    testState.actor = { ...garageOwnerSession, tenant_id: 'clear-tenant', id: 'clear-actor' }
    testState.signedOut = false
    testState.epoch = 3
    rerender(view())
    expect(screen.queryByRole('button', { name: 'Open RO-1009 in Repair Orders' })).not.toBeInTheDocument()
    expect(screen.queryByText('$1,840.25')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Closeout 1/ })).not.toBeInTheDocument()
    await act(async () => { resolveClear({ data: clearDaily }); await clearResponse })
    expect(await screen.findByRole('button', { name: /^Closeout 0/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open RO-1009 in Repair Orders' })).not.toBeInTheDocument()
    expect(client.getQueryCache().findAll({ queryKey: ['dashboard-daily-workset'] }).length).toBeGreaterThan(2)
    unmount()
    client.clear()
  })

  it('refreshes on entering Overview and keeps its stale timestamp separate from Closeout', () => {
    testState.overviewError = true
    render(<DashboardHome />)
    expect(screen.getByRole('alert')).toHaveTextContent('Last checked')
    expect(screen.getByRole('button', { name: /Refresh Shop Work/ })).toHaveAttribute('aria-label', expect.stringContaining('Checked'))
    fireEvent.click(screen.getByRole('button', { name: /^Active work/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Overview', exact: true }))
    expect(testState.overviewRefetch).toHaveBeenCalledOnce()
    testState.overviewError = false
  })

  it('defaults to Overview and preserves active-work navigation to the canonical workspace in place', () => {
    render(<DashboardHome />)

    expect(screen.getByRole('heading', { name: 'Shop Work' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Overview' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: /^Active work/ }))
    expect(screen.getByRole('button', { name: /^Active work/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByText('Payment Due')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Shop Cockpit' })).not.toBeInTheDocument()

    expect(screen.queryByText('Selected repair record · read only')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open RO-1022 in Shop Work' }))

    expect(testState.navigate).toHaveBeenCalledWith(
      '/dashboard?selected=ro-floor-22&queue=on_floor&work_view=active',
    )
  })

  it('keeps unpaid closeout separate and preserves existing payment status', () => {
    render(<DashboardHome />)
    fireEvent.click(screen.getByRole('button', { name: /^Closeout \d/ }))
    expect(screen.getByText('Payment Due')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open RO-1009 in Repair Orders' })).toBeInTheDocument()
    expect(screen.queryByText('Work in progress')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /On the Floor/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Active work/ }))
    expect(screen.getByText('Work in progress')).toBeInTheDocument()
    expect(screen.queryByText('Payment Due')).not.toBeInTheDocument()
  })

  it('restores external Closeout navigation without losing the active-work filter', () => {
    const { rerender } = render(<DashboardHome />)
    fireEvent.click(screen.getByRole('button', { name: /^Active work/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Parts 0' }))
    testState.locationState = { shopWorkQueue: 'ready_to_close' }
    rerender(<DashboardHome />)
    expect(screen.getByRole('button', { name: /^Closeout \d/ })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: /^Active work/ }))
    expect(screen.getByRole('button', { name: 'Parts 0' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('restores Payment review after opening and closing its existing workspace', () => {
    testState.query.data = { ...dashboardFixture, needs_attention: { items: [order({ pending_zelle_confirmation: true })], has_more: false } }
    const { rerender } = render(<DashboardHome />)
    fireEvent.click(screen.getByRole('button', { name: /^Closeout \d/ }))
    fireEvent.click(screen.getByRole('tab', { name: 'Payment review 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Open RO-1017 in Repair Orders' }))
    expect(testState.navigate).toHaveBeenCalledWith('/dashboard?selected=ro-needs-17&queue=needs_action&work_view=closeout')
    testState.locationSearch = '?selected=ro-needs-17&queue=needs_action&work_view=closeout'
    rerender(<DashboardHome />)
    expect(screen.getByTestId('repair-order-workspace')).toBeInTheDocument()
    testState.locationSearch = '?queue=needs_action&work_view=closeout'
    rerender(<DashboardHome />)
    expect(screen.getByRole('button', { name: /^Closeout \d/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('tab', { name: 'Payment review 1' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Zelle Review')).toBeInTheDocument()
  })

  it.each(['completed', 'invoiced'])('keeps legacy imported %s history free of billing instructions', (status) => {
    testState.presentationVariant = 'legacy'
    testState.query.data = { ...dashboardFixture, orders_ready_to_close: [order({ status, source: 'easy_truck_shop_import', pending_zelle_confirmation: true })] }
    render(<DashboardHome />)
    expect(screen.getByText('ETS history')).toBeInTheDocument()
    expect(screen.queryByText('Invoice Customer')).not.toBeInTheDocument()
    expect(screen.queryByText('Payment Due')).not.toBeInTheDocument()
    expect(screen.queryByText('Customer marked payment sent. Confirm receipt before closing.')).not.toBeInTheDocument()
  })

  it('preserves the existing three-lane DashboardHome when the presentation flag is legacy', () => {
    testState.presentationVariant = 'legacy'
    render(<DashboardHome />)

    expect(screen.getByRole('heading', { name: 'Shop Cockpit' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Needs Action', level: 3 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'On the Floor', level: 3 })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Ready to Close', level: 3 })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Action Ledger' })).not.toBeInTheDocument()
    expect(document.querySelector('.db-shop-work-new')).not.toBeInTheDocument()
  })

  it('keeps the daily ledger route and mounts the canonical repair-order workspace in place', () => {
    testState.locationSearch = '?selected=ro-floor-22&queue=on_floor'

    render(<DashboardHome />)

    expect(screen.getByTestId('repair-order-workspace')).toHaveTextContent('daily')
    expect(testState.navigate).not.toHaveBeenCalled()
  })

  it('uses presentation-specific loading and error states without changing refresh behavior', () => {
    testState.locationSearch = '?work_view=active'
    testState.query = { ...testState.query, data: undefined, isLoading: true }
    const { rerender } = render(<DashboardHome />)
    expect(screen.getByLabelText('Loading Shop Work')).toBeInTheDocument()

    testState.query = { ...testState.query, isLoading: false, error: new Error('offline') }
    rerender(<DashboardHome />)
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load work queue')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(testState.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['dashboard-action-queue'] })
    expect(testState.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['dashboard-daily-workset'] })

    testState.presentationVariant = 'legacy'
    rerender(<DashboardHome />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('Failed to load work queue')).toHaveClass('text-red-400')
  })
})
