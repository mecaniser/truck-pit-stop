import { render, screen, waitFor, within } from '@testing-library/react'
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
let fixtureStatus = 'invoiced'
let fixtureSource: string | null = null
let fixtureDeleted = false
const summary = () => ({ order_id: order.id, labor_total: '0', parts_total: '0', total_cost: '0', labor_discount_amount: '0', order_discount_amount: '0', lines: [], parts: [], warnings: [], pricing_locked: !voided, can_edit_work: voided })

function renderRevision() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/?selected=order-1']}><RepairOrdersPage /></MemoryRouter></QueryClientProvider>)
  return client
}

async function openVoid(user: ReturnType<typeof userEvent.setup>) {
  const trigger = await screen.findByRole('button', { name: 'Invoice actions', exact: true })
  await user.click(trigger)
  await user.click(await screen.findByRole('menuitem', { name: 'Void entire order…', exact: true }))
  return trigger
}

describe('Void and revise work editing', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} unobserve() {} })
    voided = false
    fixtureStatus = 'invoiced'
    fixtureSource = null
    fixtureDeleted = false
    Object.defineProperty(window, 'scrollTo', { value: vi.fn(), configurable: true })
    useAuthStore.setState({ user: owner, isAuthenticated: true })
    apiMocks.get.mockImplementation((url: string) => {
      const current = { ...order, status: voided ? 'cancelled' : fixtureStatus, source: fixtureSource, deleted_at: fixtureDeleted ? '2026-10-20T12:00:00Z' : null }
      if (url === '/repair-orders/recommended-work') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 25 } })
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
    apiMocks.post.mockImplementation(async (url: string) => {
      if (url === '/auth/step-up-grants') return { data: { grant_token: 'test-grant' } }
      voided = true
      return { data: { ...order, status: 'cancelled' } }
    })
  })
  afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals(); useAuthStore.setState({ user: null, isAuthenticated: false }) })

  it('keeps the original order and its actions available when recommendations return malformed HTTP 200 data', async () => {
    const defaultGet = apiMocks.get.getMockImplementation()!
    apiMocks.get.mockImplementation((url: string) => url === '/repair-orders/recommended-work'
      ? Promise.resolve({ data: { items: [{ description: 'Malformed row without source' }], total: 1, skip: 0, limit: 25 } })
      : defaultGet(url))
    renderRevision()
    const user = userEvent.setup()
    expect(await screen.findByText('Could not load recommendations.')).toBeVisible()
    expect(screen.queryByText('No open recommendations on other orders.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Order actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete', exact: true })).not.toBeInTheDocument()
    await openVoid(user)
    expect(screen.getByRole('textbox', { name: 'Reason for voiding' })).toBeVisible()
    expect(screen.getByLabelText('Your password')).toBeVisible()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('keeps cancellation hidden until the invoice menu opens and restores focus on Escape', async () => {
    renderRevision()
    const user = userEvent.setup()
    const trigger = await screen.findByRole('button', { name: 'Invoice actions' })
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument()
    trigger.focus()
    await user.keyboard('{ArrowDown}')
    expect(await screen.findByRole('menuitem', { name: 'Void entire order…' })).toBeVisible()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
    expect(screen.getByRole('heading', { name: '#RO-000001' })).toBeVisible()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('closes the successful void form and workspace and leaves a dismissible confirmation', async () => {
    renderRevision()
    const user = userEvent.setup()
    await openVoid(user)
    await user.type(screen.getByRole('textbox', { name: 'Reason for voiding' }), 'Wrong work order')
    await user.type(screen.getByLabelText('Your password'), 'test-password')
    await user.click(within(screen.getByRole('dialog', { name: 'Void entire order?' })).getByRole('button', { name: 'Void entire order', exact: true }))
    expect(await screen.findByText('Order RO-000001 voided. The record is preserved.')).toBeVisible()
    expect(screen.queryByLabelText('Your password')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Order actions' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Dismiss void confirmation' }))
    expect(screen.queryByText('Order RO-000001 voided. The record is preserved.')).not.toBeInTheDocument()
  })

  it('keeps the failed void form available and clears the password for retry', async () => {
    apiMocks.post.mockRejectedValueOnce(new Error('Password rejected'))
    renderRevision()
    const user = userEvent.setup()
    await openVoid(user)
    await user.type(screen.getByRole('textbox', { name: 'Reason for voiding' }), 'Wrong work order')
    await user.type(screen.getByLabelText('Your password'), 'test-password')
    await user.click(within(screen.getByRole('dialog', { name: 'Void entire order?' })).getByRole('button', { name: 'Void entire order', exact: true }))
    await waitFor(() => expect(toastMocks.error).toHaveBeenCalled())
    expect(screen.getByLabelText('Your password')).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'Reason for voiding' })).toHaveValue('Wrong work order')
    expect(screen.queryByText('Order RO-000001 voided. The record is preserved.')).not.toBeInTheDocument()
  })

  it('dismisses with Escape, restores focus, and discards sensitive fields on reopen', async () => {
    renderRevision()
    const user = userEvent.setup()
    const trigger = await openVoid(user)
    expect(screen.getByRole('dialog', { name: 'Void entire order?' })).toBeVisible()
    await user.type(screen.getByLabelText('Reason for voiding'), 'Duplicate order')
    await user.type(screen.getByLabelText('Your password'), 'test-password')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Void entire order?' })).not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
    await openVoid(user)
    expect(screen.getByLabelText('Reason for voiding')).toHaveValue('')
    expect(screen.getByLabelText('Your password')).toHaveValue('')
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('requires a nonblank reason and password and sends the existing one-time grant contract', async () => {
    renderRevision()
    const user = userEvent.setup()
    await openVoid(user)
    const submit = within(screen.getByRole('dialog', { name: 'Void entire order?' })).getByRole('button', { name: 'Void entire order', exact: true })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Reason for voiding'), '   ')
    await user.type(screen.getByLabelText('Your password'), 'test-password')
    expect(submit).toBeDisabled()
    await user.clear(screen.getByLabelText('Reason for voiding'))
    await user.type(screen.getByLabelText('Reason for voiding'), '  Duplicate order  ')
    expect(screen.getByLabelText('Reason for voiding')).toHaveAttribute('maxlength', '1000')
    await user.click(submit)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(2))
    expect(apiMocks.post).toHaveBeenNthCalledWith(1, '/auth/step-up-grants', { password: 'test-password', scope: 'repair_orders.force_void' })
    expect(apiMocks.post).toHaveBeenNthCalledWith(2, '/repair-orders/order-1/force-void', { reason: 'Duplicate order' }, { headers: { 'X-Step-Up-Authorization': 'test-grant' } })
  })

  it('shows server rejection in the dialog and never retries automatically', async () => {
    apiMocks.post.mockResolvedValueOnce({ data: { grant_token: 'test-grant' } }).mockRejectedValueOnce({ response: { status: 409, data: { detail: 'This invoice is in QuickBooks. Void it there first.' } } })
    renderRevision()
    const user = userEvent.setup()
    await openVoid(user)
    await user.type(screen.getByLabelText('Reason for voiding'), 'Duplicate order')
    await user.type(screen.getByLabelText('Your password'), 'test-password')
    await user.click(within(screen.getByRole('dialog', { name: 'Void entire order?' })).getByRole('button', { name: 'Void entire order', exact: true }))
    expect(await within(screen.getByRole('dialog', { name: 'Void entire order?' })).findByRole('alert')).toHaveTextContent('This invoice is in QuickBooks.')
    expect(screen.getByLabelText('Reason for voiding')).toHaveValue('Duplicate order')
    expect(screen.getByLabelText('Your password')).toHaveValue('')
    expect(apiMocks.post).toHaveBeenCalledTimes(2)
  })

  it('hides void and Delete for staff without override permission', async () => {
    useAuthStore.setState({ user: { ...owner, role: 'receptionist' } })
    renderRevision()
    expect(await screen.findByText('Invoice INV-1')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Invoice actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Order actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete', exact: true })).not.toBeInTheDocument()
  })


  it('locks submission and dismissal while the one-time grant request is pending', async () => {
    let rejectGrant!: (error: Error) => void
    apiMocks.post.mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectGrant = reject }))
    renderRevision()
    const user = userEvent.setup()
    await openVoid(user)
    const dialog = screen.getByRole('dialog', { name: 'Void entire order?' })
    await user.type(screen.getByLabelText('Reason for voiding'), 'Duplicate order')
    await user.type(screen.getByLabelText('Your password'), 'test-password')
    await user.dblClick(within(dialog).getByRole('button', { name: 'Void entire order', exact: true }))
    expect(within(dialog).getByRole('button', { name: 'Voiding…' })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await user.keyboard('{Escape}')
    expect(screen.getByRole('dialog', { name: 'Void entire order?' })).toBeVisible()
    expect(apiMocks.post).toHaveBeenCalledTimes(1)
    rejectGrant(new Error('Connection failed'))
    await waitFor(() => expect(screen.getByLabelText('Your password')).toHaveValue(''))
  })

  it('keeps Delete reachable for draft orders', async () => {
    fixtureStatus = 'draft'
    renderRevision()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Order actions' }))
    expect(screen.getByRole('button', { name: 'Delete', exact: true })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Invoice actions' })).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('keeps Restore reachable for deleted orders', async () => {
    fixtureStatus = 'draft'
    fixtureDeleted = true
    renderRevision()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Order actions' }))
    expect(screen.getAllByRole('button', { name: 'Restore order' }).every(button => !button.hasAttribute('disabled'))).toBe(true)
    expect(screen.queryByRole('button', { name: 'Invoice actions' })).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('does not offer native void for imported financial history', async () => {
    fixtureSource = 'easy_truck_shop_import'
    renderRevision()
    expect(await screen.findByRole('heading', { name: '#RO-000001' })).toBeVisible()
    expect(screen.queryByText('Invoice INV-1')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invoice actions' })).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

  it('makes void available beside a paid invoice for a garage admin', async () => {
    fixtureStatus = 'paid'
    useAuthStore.setState({ user: { ...owner, role: 'garage_admin' } })
    renderRevision()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Invoice actions', exact: true }))
    expect(await screen.findByRole('menuitem', { name: 'Void entire order…' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Order actions' })).not.toBeInTheDocument()
    expect(apiMocks.post).not.toHaveBeenCalled()
  })

})
