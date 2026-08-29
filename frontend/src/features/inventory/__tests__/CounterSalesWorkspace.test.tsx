import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner' }))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, post: apiMocks.post, patch: apiMocks.patch } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: authState.role } }) }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ appearance: { mode: 'dark' } }) }))

import CounterSalesWorkspace from '../CounterSalesWorkspace'
import type { CounterSale } from '../inventoryLifecycleTypes'

const summary = {
  capabilities: {
    counter_sales: true,
    counter_sale_tenders: ['cash', 'check', 'ach', 'zelle', 'external_terminal', 'fleet_reference', 'other'],
  },
}

const line = {
  id: 'line-1',
  inventory_id: 'part-1',
  sku: 'AIR-1',
  name: 'Primary air filter',
  unit_type: 'each',
  quantity: 2,
  returned_quantity: 0,
  remaining_returnable_quantity: 2,
  unit_cost: '10.00',
  list_unit_price: '20.00',
  charged_unit_price: '20.00',
  discount_amount: '0.00',
  item_subtotal: '40.00',
  tax_amount: '2.80',
  total_amount: '42.80',
  price_override_reason: null,
  physical_on_hand: 12,
  held_for_checkout: 0,
  available_to_sell: 12,
}

function sale(overrides: Partial<CounterSale> = {}): CounterSale {
  return {
    id: 'sale-1',
    sale_number: 'CS-1001',
    status: 'draft',
    version: 3,
    customer_id: null,
    buyer_name: null,
    buyer_email: null,
    buyer_phone: null,
    currency: 'USD',
    list_subtotal: '40.00',
    charged_subtotal: '40.00',
    discount_amount: '0.00',
    tax_amount: '2.80',
    total_amount: '42.80',
    lines: [line],
    payment_attempts: [],
    returns: [],
    allowed_actions: ['edit_draft', 'checkout', 'cancel'],
    created_at: '2026-08-26T12:00:00Z',
    updated_at: '2026-08-26T12:00:00Z',
    completed_at: null,
    cancelled_at: null,
    ...overrides,
  }
}

const part = {
  id: 'part-1',
  sku: 'AIR-1',
  name: 'Primary air filter',
  description: null,
  image_url: null,
  unit_type: 'each',
  location: 'A-1',
  available_packages: 12,
  physical_on_hand_packages: 12,
  held_for_checkout_packages: 0,
  available_to_sell_packages: 12,
  needed_for_open_repairs: 0,
  reorder_level: 2,
  incoming_packages: 0,
  recommended_order_packages: 0,
  average_unit_cost: '10.00',
  selling_price: '20.00',
  is_archived: false,
  is_placeholder: false,
  preferred_source: null,
  supplier_sources: [],
  repair_sources: [],
  incoming_sources: [],
}

function renderWorkspace(entry = '/dashboard/garage/inventory/sales') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}><CounterSalesWorkspace /></MemoryRouter></QueryClientProvider>)
}

function installApi(initial = sale()) {
  let currentSale = initial
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: summary })
    if (url === '/parts-operations/counter-sales') return Promise.resolve({ data: { items: [{ id: currentSale.id, sale_number: currentSale.sale_number, status: currentSale.status, buyer_name: currentSale.buyer_name, buyer_email: currentSale.buyer_email, total_amount: currentSale.total_amount, line_count: currentSale.lines.length, tender: currentSale.payment_attempts[0]?.tender || null, created_at: currentSale.created_at, completed_at: currentSale.completed_at }], next_cursor: null } })
    if (url === `/parts-operations/counter-sales/${currentSale.id}`) return Promise.resolve({ data: currentSale })
    if (url === `/parts-operations/parts/${part.id}`) return Promise.resolve({ data: part })
    if (url === '/parts-operations/parts') return Promise.resolve({ data: { items: [part], total: 1, skip: 0, limit: 20, has_more: false } })
    if (url === '/customers/typeahead') return Promise.resolve({ data: [{ id: 'customer-1', name: 'Elis Logistics', email: 'dispatch@example.test', phone: '555-0100' }] })
    if (url.endsWith('/receipt.pdf')) return Promise.resolve({ data: new Blob(['receipt']) })
    throw new Error(`Unexpected GET ${url}`)
  })
  apiMocks.post.mockImplementation((url: string) => {
    if (url === '/parts-operations/counter-sales') return Promise.resolve({ data: currentSale })
    if (url.endsWith('/checkout')) {
      currentSale = { ...currentSale, status: 'completed', version: 4, completed_at: '2026-08-26T12:05:00Z', allowed_actions: ['download_receipt', 'create_return'], payment_attempts: [{ id: 'attempt-1', tender: 'external_terminal', state: 'succeeded', amount: '42.80', reference: 'TERM-44', created_at: '2026-08-26T12:05:00Z' }] }
      return Promise.resolve({ data: currentSale })
    }
    if (url.endsWith('/cancel')) {
      currentSale = { ...currentSale, status: 'cancelled', version: 4, allowed_actions: [] }
      return Promise.resolve({ data: currentSale })
    }
    if (url.endsWith('/returns')) return Promise.resolve({ data: { id: 'return-2', sale_id: currentSale.id, version: 1, state: 'completed', item_amount: '20.00', tax_amount: '1.40', refund_amount: '21.40', reason: null, refund_reference: 'REV-1', lines: [], created_at: '2026-08-26T13:00:00Z', completed_at: '2026-08-26T13:00:00Z' } })
    throw new Error(`Unexpected POST ${url}`)
  })
  apiMocks.patch.mockResolvedValue({ data: currentSale })
}

describe('DB-045 bounded manual Parts sales workspace', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.patch.mockReset()
    authState.role = 'garage_owner'
    vi.restoreAllMocks()
  })

  it('keeps a tenant-disabled workflow inaccessible', async () => {
    apiMocks.get.mockResolvedValue({ data: { capabilities: { counter_sales: false, counter_sale_tenders: [] } } })
    renderWorkspace()
    expect(await screen.findByRole('alert')).toHaveTextContent('Parts sales is not available for this shop.')
    expect(screen.queryByRole('button', { name: 'New counter sale' })).not.toBeInTheDocument()
  })

  it('loads sale history, applies search, and owns the New counter sale action', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()
    expect(await screen.findByText('CS-1001')).toBeInTheDocument()
    await user.type(screen.getByRole('searchbox', { name: 'Search parts sales' }), 'walk in')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/counter-sales', { params: { text: 'walk in', limit: 50 } }))
    await user.click(screen.getByRole('button', { name: 'New counter sale' }))
    expect(await screen.findByRole('heading', { name: 'New counter sale' })).toBeInTheDocument()
    expect(screen.queryByText(/payment recovery/i)).not.toBeInTheDocument()
  })

  it('starts from a contextual part and creates a whole-unit draft', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?new=1&part=part-1')
    expect(await screen.findByText('Primary air filter')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Review checkout/ }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales', {
      customer_id: null,
      buyer_name: null,
      buyer_email: null,
      buyer_phone: null,
      lines: [{ inventory_id: 'part-1', quantity: 1 }],
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-create-/) } }))
  })

  it('hides price override from receptionists', async () => {
    authState.role = 'receptionist'
    installApi()
    renderWorkspace('/dashboard/garage/inventory/sales?new=1&part=part-1')
    expect(await screen.findByText('Primary air filter')).toBeInTheDocument()
    expect(screen.queryByText('Manager price override')).not.toBeInTheDocument()
  })

  it('records one manual tender and no provider payload', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')
    await user.selectOptions(await screen.findByLabelText('Tender'), 'external_terminal')
    await user.type(screen.getByLabelText('Reference'), 'TERM-44')
    await user.click(screen.getByRole('button', { name: /Complete sale/ }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/checkout', {
      expected_version: 3,
      tender: 'external_terminal',
      manual_reference: 'TERM-44',
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-checkout-/) } }))
    expect(screen.queryByText(/Stripe|QuickBooks|Reconcile payment|Accounting sync/i)).not.toBeInTheDocument()
  })

  it('requires an audited manager reason before cancelling a draft', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')
    const cancel = await screen.findByRole('button', { name: 'Cancel draft' })
    expect(cancel).toBeDisabled()
    await user.type(screen.getByLabelText('Cancellation reason'), 'Customer changed plans')
    await user.click(cancel)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/cancel', {
      expected_version: 3,
      reason: 'Customer changed plans',
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-cancel-/) } }))
  })

  it('offers only printable receipt and audited manual return after completion', async () => {
    const completed = sale({
      status: 'completed',
      completed_at: '2026-08-26T12:05:00Z',
      allowed_actions: ['download_receipt', 'create_return'],
      payment_attempts: [{ id: 'attempt-1', tender: 'cash', state: 'succeeded', amount: '42.80', reference: null, created_at: '2026-08-26T12:05:00Z' }],
    })
    installApi(completed)
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')
    expect(await screen.findByRole('button', { name: 'Download receipt' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Email receipt|Retry refund|Reconcile/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Return items' }))
    await user.click(screen.getByRole('button', { name: 'Increase Return quantity for Primary air filter' }))
    await user.type(screen.getByLabelText('Reason'), 'Damaged package')
    await user.click(screen.getByLabelText('Damaged'))
    await user.type(screen.getByLabelText('Refund or reversal reference'), 'REV-1')
    await user.click(screen.getByRole('button', { name: 'Record return' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/returns', {
      expected_version: 3,
      lines: [{ sale_line_id: 'line-1', quantity: 1, reason: 'Damaged package', disposition: 'damaged' }],
      manual_refund_reference: 'REV-1',
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-return-/) } }))
  })
})
