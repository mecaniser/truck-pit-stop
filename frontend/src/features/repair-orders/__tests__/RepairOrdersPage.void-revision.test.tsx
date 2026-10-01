import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Quote } from '@/types'

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


const invoice = { id: 'invoice-1', repair_order_id: order.id, invoice_number: 'INV-1', status: 'unpaid', total_amount: '1450.00', due_date: '2026-10-15' }
let voided = false
const summary = () => ({ order_id: order.id, labor_total: '0', parts_total: '0', total_cost: '0', labor_discount_amount: '0', order_discount_amount: '0', lines: [], parts: [], warnings: [], pricing_locked: !voided, can_edit_work: voided })

function renderRevision() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/?selected=order-1']}><RepairOrdersPage /></MemoryRouter></QueryClientProvider>)
  return client
}

describe('Void and revise work editing', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} })
    voided = false
    Object.defineProperty(window, 'scrollTo', { value: vi.fn(), configurable: true })
    useAuthStore.setState({ user: owner, isAuthenticated: true })
    apiMocks.get.mockImplementation((url: string) => {
      const current = { ...order, status: voided ? 'pending_review' : 'invoiced' }
      if (url === '/repair-orders') return Promise.resolve({ data: { items: [current], total: 1, has_more: false } })
      if (url.endsWith('/workspace')) return Promise.resolve({ data: current })
      if (url.endsWith('/detail')) return Promise.resolve({ data: { ...current, parts_usage: [], labor_items: [], history_events: [] } })
      if (url.endsWith('/price-build')) return Promise.resolve({ data: summary() })
      if (url.startsWith('/invoices?')) return Promise.resolve({ data: voided ? [] : [invoice] })
      if (url.endsWith('/settlement')) return Promise.resolve({ data: { feature_enabled: false } })
      if (url === '/quotes?repair_order_id=order-1') return Promise.resolve({ data: draft })
      if (url.endsWith('/history')) return Promise.resolve({ data: { revisions: [], events: [] } })
      if (url === '/dashboard/stats') return Promise.resolve({ data: { mechanic_workload: [] } })
      if (url.includes('/settings')) return Promise.resolve({ data: { labor_rate: 100 } })
      return Promise.resolve({ data: [] })
    })
    apiMocks.post.mockImplementation(async () => { voided = true; return { data: { ...invoice, status: 'cancelled' } } })
  })
  afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals(); useAuthStore.setState({ user: null, isAuthenticated: false }) })

  it('refreshes the locked summary so parts, labor and operations can be added without reopening the panel', async () => {
    const client = renderRevision()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Void & revise' }))
    expect(screen.queryByRole('button', { name: 'Operation', exact: true })).not.toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('Describe what needs to be corrected'), 'Add additional work')
    await user.click(screen.getByRole('button', { name: 'Void & reopen' }))
    expect(await screen.findByRole('button', { name: 'Operation', exact: true })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Part', exact: true })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Labor', exact: true })).toBeEnabled()
    expect(client.getQueryData(['price-build', order.id])).toMatchObject({ pricing_locked: false, can_edit_work: true })
    expect(apiMocks.post).toHaveBeenCalledWith('/invoices/invoice-1/void', { reason: 'Add additional work' })
  })
  it('retains the lock and invoice actions when the server rejects voiding', async () => {
    apiMocks.post.mockRejectedValueOnce(new Error('Payment pending'))
    const client = renderRevision()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Void & revise' }))
    await user.type(screen.getByPlaceholderText('Describe what needs to be corrected'), 'Add additional work')
    await user.click(screen.getByRole('button', { name: 'Void & reopen' }))
    await waitFor(() => expect(toastMocks.error).toHaveBeenCalled())
    expect(client.getQueryData(['price-build', order.id])).toMatchObject({ pricing_locked: true, can_edit_work: false })
    expect(screen.queryByRole('button', { name: 'Operation', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Void & revise' })).toBeInTheDocument()
  })

  it('does not override a refreshed server capability that still forbids editing', async () => {
    const defaultGet = apiMocks.get.getMockImplementation()!
    apiMocks.get.mockImplementation((url: string) => url.endsWith('/price-build')
      ? Promise.resolve({ data: { ...summary(), pricing_locked: false, can_edit_work: false } })
      : defaultGet(url))
    const client = renderRevision()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Void & revise' }))
    await user.type(screen.getByPlaceholderText('Describe what needs to be corrected'), 'Add additional work')
    await user.click(screen.getByRole('button', { name: 'Void & reopen' }))
    await waitFor(() => expect(apiMocks.get.mock.calls.filter(([url]) => url.endsWith('/price-build'))).toHaveLength(2))
    expect(client.getQueryData(['price-build', order.id])).toMatchObject({ can_edit_work: false })
    expect(screen.queryByRole('button', { name: 'Operation', exact: true })).not.toBeInTheDocument()
  })

})
