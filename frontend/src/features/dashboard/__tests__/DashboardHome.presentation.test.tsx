import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardHome from '../DashboardHome'
import { garageOwnerSession } from '../../../test-fixtures/db035/staffSession'

const testState = vi.hoisted(() => ({
  presentationVariant: 'new' as 'new' | 'legacy',
  navigate: vi.fn(),
  invalidateQueries: vi.fn(),
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
  useLocation: () => ({ state: null }),
}))
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => testState.query,
  useQueryClient: () => ({ invalidateQueries: testState.invalidateQueries }),
}))
vi.mock('../../../stores/authStore', () => ({
  useAuthStore: () => ({ user: garageOwnerSession }),
}))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({
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
    testState.invalidateQueries.mockReset()
    testState.query = {
      data: dashboardFixture,
      isLoading: false,
      error: null,
      isFetching: false,
      dataUpdatedAt: Date.now(),
    }
  })

  it('renders the projection-only Action Ledger and opens the exact canonical Repair Orders handoff in one action', () => {
    render(<DashboardHome />)

    expect(screen.getByRole('heading', { name: 'Shop Work' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Action Ledger' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Shop Cockpit' })).not.toBeInTheDocument()

    expect(screen.queryByText('Selected repair record · read only')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open RO-1022 in Repair Orders' }))

    expect(testState.navigate).toHaveBeenCalledWith(
      '/dashboard/repair-orders?selected=ro-floor-22&queue=on_floor',
    )
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

  it('uses presentation-specific loading and error states without changing refresh behavior', () => {
    testState.query = { ...testState.query, data: undefined, isLoading: true }
    const { rerender } = render(<DashboardHome />)
    expect(screen.getByLabelText('Loading Shop Work')).toBeInTheDocument()

    testState.query = { ...testState.query, isLoading: false, error: new Error('offline') }
    rerender(<DashboardHome />)
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load work queue')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(testState.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['dashboard-action-queue'] })

    testState.presentationVariant = 'legacy'
    rerender(<DashboardHome />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('Failed to load work queue')).toHaveClass('text-red-400')
  })
})
