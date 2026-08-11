import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Quote, RepairOrderHistoryEvent } from '@/types'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
}))
const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock('@/lib/api', () => ({
  default: { get: apiMocks.get, post: apiMocks.post, put: apiMocks.put },
}))
vi.mock('react-hot-toast', () => ({ default: toastMocks }))

vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#f59e0b' } }) }))
vi.mock('../PriceBuilderPanel', () => ({
  default: (props: {
    canEdit?: boolean
    historyEvents?: Array<{ id: string; label: string; detail?: string; actor?: string }>
    onHistoryOpen?: () => void
    quoteActionLabel?: string
    onQuoteAction?: () => void
  }) => (
    <div>
      <span>{props.canEdit ? 'Price editing enabled' : 'Price editing unavailable'}</span>
      {props.onQuoteAction
        ? <button type="button" onClick={props.onQuoteAction}>{props.quoteActionLabel}</button>
        : <span>Publication unavailable</span>}
      <button type="button" onClick={props.onHistoryOpen}>Open history</button>
      <output aria-label="History count">History count: {props.historyEvents?.length ?? 0}</output>
      <ol>
        {props.historyEvents?.map((event) => (
          <li key={event.id}>
            {event.label}
            {(event.actor || event.detail) && ` · ${event.actor || ''}${event.actor && event.detail ? ' · ' : ''}${event.detail || ''}`}
          </li>
        ))}
      </ol>
    </div>
  ),
}))

import { useAuthStore } from '@/stores/authStore'
import RepairOrdersPage from '../RepairOrdersPage'

const order = {
  id: 'order-1', tenant_id: 'tenant-1', customer_id: 'customer-1', vehicle_id: 'vehicle-1',
  vehicle_make: 'Freightliner', vehicle_model: 'Cascadia', vehicle_year: 2022, vehicle_unit_number: '22',
  vehicle_vin: 'VIN22', customer_company_name: 'North Freight', customer_email: 'dispatch@example.test',
  order_number: 'RO-000001', status: 'draft', description: 'No-start diagnosis', customer_notes: null,
  internal_notes: null, assigned_mechanic_id: null, total_parts_cost: '450.00', total_labor_cost: '1000.00',
  total_cost: '1450.00', created_at: '2026-08-11T12:00:00Z', updated_at: '2026-08-11T13:00:00Z',
  is_internal: false,
}

const draft: Quote = {
  id: 'quote-1', tenant_id: 'tenant-1', repair_order_id: 'order-1', quote_number: 'Q-000001',
  total_amount: '1450.00', notes: null, expires_at: null, is_approved: false, is_declined: false,
  decline_notes: null, sent_to_customer: false, sent_at: null, created_at: '2026-08-11T13:00:00Z',
  updated_at: '2026-08-11T13:00:00Z', revision: 1, authorization_type: 'initial_estimate',
  previously_authorized_amount: '0.00', delta_amount: '1450.00',
}

const owner = {
  id: 'owner-1', email: 'owner@example.test', first_name: 'Olivia', last_name: 'Owner', phone: null,
  role: 'garage_owner' as const, is_active: true, tenant_id: 'tenant-1', customer_id: null,
}

let detailHistoryEvents: RepairOrderHistoryEvent[] = []
let authorizationHistoryEvents: RepairOrderHistoryEvent[] = []

const renderPage = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/?selected=order-1']}>
        <RepairOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('RepairOrdersPage authorization publication', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'scrollTo', { value: vi.fn(), configurable: true })
    detailHistoryEvents = []
    authorizationHistoryEvents = []
    useAuthStore.setState({ user: owner, isAuthenticated: true })
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
      if (url === '/repair-orders/order-1/workspace') return Promise.resolve({ data: order })
      if (url === '/repair-orders/order-1/detail') {
        return Promise.resolve({ data: { ...order, parts_usage: [], labor_items: [], history_events: detailHistoryEvents } })
      }
      if (url === '/quotes?repair_order_id=order-1') return Promise.resolve({ data: draft })
      if (url === '/quotes/repair-order/order-1/history') {
        return Promise.resolve({ data: { revisions: [draft], events: authorizationHistoryEvents } })
      }
      if (url === '/dashboard/stats') return Promise.resolve({ data: { mechanic_workload: [] } })
      if (url === '/dashboard/mechanics/options') return Promise.resolve({ data: [] })
      if (url === '/repair-orders/order-1/recommended-services') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: { labor_rate: 100 } })
    })
    apiMocks.put.mockResolvedValue({ data: draft })
    apiMocks.post.mockResolvedValue({ data: { ...draft, sent_to_customer: true, sent_at: '2026-08-11T14:00:00Z' } })
  })

  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.put.mockReset()
    apiMocks.post.mockReset()
    toastMocks.success.mockReset()
    toastMocks.error.mockReset()
    useAuthStore.setState({ user: null, isAuthenticated: false })
  })

  it('requires a fresh PUT review before a publisher can send', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Send estimate' }))

    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith('/quotes/quote-1'))
    expect(apiMocks.post).not.toHaveBeenCalled()
    const heading = await screen.findByRole('heading', { name: 'Send estimate carefully' })
    expect(heading).toBeInTheDocument()

    fireEvent.click(within(heading.closest('.relative') as HTMLElement).getByRole('button', { name: 'Send estimate' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/quotes/quote-1/send'))
  })

  it('keeps the loading search input controlled when the order workspace opens', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    try {
      const view = renderPage()
      expect(await screen.findByText('Price editing enabled')).toBeInTheDocument()
      await waitFor(() => expect(screen.getByRole('button', { name: 'Send estimate' })).toBeEnabled())
      view.unmount()
      expect(consoleError).not.toHaveBeenCalled()
    } finally {
      consoleError.mockRestore()
    }
  })

  it('does not expose publication when the current role is not a publisher', async () => {
    useAuthStore.setState({ user: { ...owner, id: 'mechanic-1', role: 'mechanic' } })
    renderPage()

    expect(await screen.findByText('Price editing enabled')).toBeInTheDocument()
    expect(await screen.findByText('Publication unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /send estimate/i })).not.toBeInTheDocument()
    expect(apiMocks.put).not.toHaveBeenCalled()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('refreshes after a 409 and never retries publication blindly', async () => {
    apiMocks.post.mockRejectedValueOnce({
      response: { status: 409, data: { detail: 'Authorization draft is stale' } },
    })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Send estimate' }))
    const heading = await screen.findByRole('heading', { name: 'Send estimate carefully' })

    fireEvent.click(within(heading.closest('.relative') as HTMLElement).getByRole('button', { name: 'Send estimate' }))

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(toastMocks.error).toHaveBeenCalledWith(expect.stringMatching(/refreshed.*review.*publishing/i)))
    expect(screen.queryByRole('heading', { name: 'Send estimate carefully' })).not.toBeInTheDocument()
    expect(apiMocks.post).toHaveBeenCalledTimes(1)
  })

  it('renders one formatted semantic event across duplicate history projections', async () => {
    const detail = JSON.stringify({
      revision: 2,
      authorization_type: 'additional_work',
      previous_amount: '1000.00',
      delta_amount: '450.00',
      resulting_total: '1450.00',
      source: 'staff_publication',
    })
    const published: RepairOrderHistoryEvent = {
      id: 'published-detail',
      event_type: 'authorization_published',
      label: 'Additional work published',
      detail,
      entity_id: 'quote-2',
      actor_name: null,
      created_at: '2026-08-11T14:00:00Z',
    }
    const declined: RepairOrderHistoryEvent = {
      id: 'declined-shared',
      event_type: 'authorization_customer_declined',
      label: 'Additional work declined',
      detail: detail.replace('staff_publication', 'customer_portal'),
      entity_id: 'quote-2',
      actor_name: null,
      created_at: '2026-08-11T14:05:00Z',
    }
    detailHistoryEvents = [published, published, declined]
    authorizationHistoryEvents = [
      { ...published, id: 'published-projection', actor_name: 'Olivia Owner' },
      { ...declined, actor_name: 'Casey Customer' },
    ]

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Open history' }))

    expect(await screen.findByText('History count: 4')).toBeInTheDocument()
    expect(screen.getAllByText(/Additional work published/)).toHaveLength(1)
    expect(screen.getAllByText(/Additional work declined/)).toHaveLength(1)
    expect(screen.getByText(/Olivia Owner.*Revision 2.*Previously authorized \$1,000\.00.*Change \$450\.00.*Resulting total \$1,450\.00.*Staff publication/)).toBeInTheDocument()
    expect(screen.getByText(/Casey Customer.*Revision 2.*Customer portal/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('"revision"')
  })
})
