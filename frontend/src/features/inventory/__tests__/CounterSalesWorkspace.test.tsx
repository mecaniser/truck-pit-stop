import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner' }))
const stripeMocks = vi.hoisted(() => ({ confirmPayment: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, post: apiMocks.post, patch: apiMocks.patch } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: authState.role } }) }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ appearance: { mode: 'dark' }, accentColors: { 500: '#f97350' } }) }))
vi.mock('@/lib/stripe', () => ({ getStripeForAccount: vi.fn().mockResolvedValue({}) }))
vi.mock('@stripe/react-stripe-js', () => ({
  Elements: ({ children }: { children: React.ReactNode }) => <div data-testid="stripe-elements">{children}</div>,
  PaymentElement: () => <div>Secure card fields</div>,
  useElements: () => ({}),
  useStripe: () => ({ confirmPayment: stripeMocks.confirmPayment }),
}))

import CounterSalesWorkspace from '../CounterSalesWorkspace'
import type { CounterSale } from '../inventoryLifecycleTypes'

const summary = {
  capabilities: {
    counter_sales: true,
    counter_sale_tenders: ['stripe', 'quickbooks_payments', 'cash', 'check', 'ach', 'zelle', 'external_terminal', 'fleet_reference', 'other'],
    counter_sale_providers: {
      stripe: { available: true, stripe_account_id: 'acct_1' },
      quickbooks_payments: { available: true, token_url: 'https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens' },
    },
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
  fee_amount: '0.00',
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
    service_fee_amount: '0.00',
    total_amount: '42.80',
    lines: [line],
    payment_attempts: [],
    returns: [],
    allowed_actions: ['edit_draft', 'checkout', 'cancel'],
    created_at: '2026-08-26T12:00:00Z',
    updated_at: '2026-08-26T12:00:00Z',
    completed_at: null,
    cancelled_at: null,
    accounting_sync_status: 'not_queued',
    receipt_email_status: null,
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
  held_for_checkout_packages: 2,
  available_to_sell_packages: 10,
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

function installApi(currentSale = sale()) {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: summary })
    if (url === '/parts-operations/counter-sales') return Promise.resolve({ data: { items: [{ id: currentSale.id, sale_number: currentSale.sale_number, status: currentSale.status, buyer_name: currentSale.buyer_name, buyer_email: currentSale.buyer_email, total_amount: currentSale.total_amount, line_count: currentSale.lines.length, tender: currentSale.payment_attempts.at(-1)?.tender || null, created_at: currentSale.created_at, completed_at: currentSale.completed_at }], next_cursor: null } })
    if (url === `/parts-operations/counter-sales/${currentSale.id}`) return Promise.resolve({ data: currentSale })
    if (url === `/parts-operations/parts/${part.id}`) return Promise.resolve({ data: part })
    if (url === '/parts-operations/parts') return Promise.resolve({ data: { items: [part], total: 1, skip: 0, limit: 20, has_more: false } })
    if (url === '/customers/typeahead') return Promise.resolve({ data: [{ id: 'customer-1', name: 'Elis Logistics', email: 'dispatch@example.test', phone: '555-0100' }] })
    if (url.endsWith('/receipt.pdf')) return Promise.resolve({ data: new Blob(['receipt']) })
    throw new Error(`Unexpected GET ${url}`)
  })
  apiMocks.post.mockImplementation((url: string) => {
    if (url === '/parts-operations/counter-sales') return Promise.resolve({ data: currentSale })
    if (url.endsWith('/checkout')) return Promise.resolve({ data: { sale: { ...currentSale, status: 'completed', allowed_actions: ['download_receipt', 'email_receipt', 'create_return'] }, payment: { attempt_id: 'attempt-1', tender: 'cash', state: 'succeeded', client_secret: null, stripe_account_id: null, reconcile_url: `/api/v1/parts-operations/counter-sales/${currentSale.id}/payment-attempts/attempt-1/reconcile` } } })
    if (url.endsWith('/cancel')) return Promise.resolve({ data: { ...currentSale, status: 'cancelled', allowed_actions: [] } })
    if (url.includes('/payment-attempts/')) return Promise.resolve({ data: currentSale })
    if (url.endsWith('/receipt/email')) return Promise.resolve({ data: { queued: true } })
    if (url.endsWith('/returns')) return Promise.resolve({ data: { id: 'return-2', sale_id: currentSale.id, version: 1, state: 'completed', refund_amount: '21.40', failure_code: null, lines: [], created_at: '2026-08-26T13:00:00Z', completed_at: '2026-08-26T13:00:00Z' } })
    if (url.endsWith('/retry-refund')) return Promise.resolve({ data: currentSale })
    throw new Error(`Unexpected POST ${url}`)
  })
  apiMocks.patch.mockResolvedValue({ data: currentSale })
}

describe('DB-045 repair-first counter sales workspace', () => {
  beforeEach(() => stripeMocks.confirmPayment.mockResolvedValue({ paymentIntent: { id: 'pi-1' } }))

  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
    apiMocks.patch.mockReset()
    stripeMocks.confirmPayment.mockReset()
    authState.role = 'garage_owner'
    vi.restoreAllMocks()
  })

  it('keeps the tenant-disabled workflow inaccessible and offers a safe return to Parts', async () => {
    apiMocks.get.mockResolvedValue({ data: { capabilities: { counter_sales: false, counter_sale_tenders: [], counter_sale_providers: { stripe: { available: false, stripe_account_id: null }, quickbooks_payments: { available: false, token_url: null } } } } })
    renderWorkspace()

    expect(await screen.findByRole('alert')).toHaveTextContent('Parts sales is not available for this shop.')
    expect(screen.queryByRole('button', { name: 'New counter sale' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to Parts' })).toBeInTheDocument()
  })

  it('loads sale history, applies the text filter contract, and owns the primary New counter sale action', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'Parts sales' })).toBeInTheDocument()
    expect(await screen.findByText('CS-1001')).toBeInTheDocument()
    await user.type(screen.getByRole('searchbox', { name: 'Search parts sales' }), 'walk in')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/counter-sales', { params: { text: 'walk in', limit: 50 } }))
    await user.click(screen.getByRole('button', { name: 'New counter sale' }))
    expect(await screen.findByRole('heading', { name: 'New counter sale' })).toBeInTheDocument()
  })

  it('starts from the contextual part without inventing a list filter and creates a whole-unit draft', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?new=1&part=part-1')

    expect(await screen.findByText('Primary air filter')).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts/part-1')
    expect(apiMocks.get.mock.calls.some(([, config]) => config?.params?.inventory_id)).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Increase Quantity for Primary air filter' }))
    expect(screen.getByRole('textbox', { name: 'Quantity for Primary air filter' })).toHaveValue('2')
    await user.click(screen.getByRole('button', { name: 'Review checkout' }))

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales', {
      customer_id: null,
      buyer_name: null,
      buyer_email: null,
      buyer_phone: null,
      lines: [{ inventory_id: 'part-1', quantity: 2 }],
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-create-/) } }))
  })

  it('edits a server-authorized draft, preserves Decimal totals, and starts one manual checkout', async () => {
    const draft = sale({ buyer_name: 'Walk-in' })
    installApi(draft)
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')

    expect(await screen.findByRole('heading', { name: 'CS-1001' })).toBeInTheDocument()
    expect(screen.getAllByText('$42.80')).toHaveLength(2)
    expect(screen.getByText(/12 physical · 0 held · 12 available/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Edit draft' }))
    expect(await screen.findByRole('heading', { name: 'Edit draft sale' })).toBeInTheDocument()
    const buyer = screen.getByLabelText('Buyer name')
    await user.clear(buyer)
    await user.type(buyer, 'Counter customer')
    await user.click(screen.getByRole('button', { name: 'Save draft' }))
    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1', expect.objectContaining({
      expected_version: 3,
      buyer_name: 'Counter customer',
      lines: [{ inventory_id: 'part-1', quantity: 2 }],
    }), { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-update-/) } }))

    expect(await screen.findByRole('heading', { name: 'Checkout' })).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Tender'), 'cash')
    await user.click(screen.getByRole('button', { name: 'Checkout $42.80' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/checkout', {
      expected_version: 3,
      tender: 'cash',
      payment_token: null,
      manual_reference: null,
      receipt_email: null,
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-checkout-/) } }))
  })

  it('previews provider fees only for provider tenders and removes them exactly for manual checkout', async () => {
    const feeDraft = sale({
      service_fee_amount: '1.50',
      total_amount: '44.30',
      lines: [{ ...line, fee_amount: '1.50', total_amount: '44.30' }],
    })
    installApi(feeDraft)
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')

    await screen.findByRole('heading', { name: 'Checkout' })
    const totals = screen.getByRole('heading', { name: 'Totals' }).closest('section')
    const saleLines = screen.getByRole('heading', { name: 'Sale lines' }).closest('section')
    expect(totals).not.toBeNull()
    expect(saleLines).not.toBeNull()

    await user.selectOptions(screen.getByLabelText('Tender'), 'stripe')
    expect(within(totals!).getByText('$1.50')).toBeInTheDocument()
    expect(within(totals!).getByText('$44.30')).toBeInTheDocument()
    expect(within(saleLines!).getByText('$44.30')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Checkout $44.30' })).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Tender'), 'cash')
    expect(within(totals!).getByText('$0.00')).toBeInTheDocument()
    expect(within(totals!).getByText('$42.80')).toBeInTheDocument()
    expect(within(saleLines!).getByText('$42.80')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Checkout $42.80' })).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Tender'), 'stripe')
    expect(within(totals!).getByText('$1.50')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Checkout $44.30' })).toBeInTheDocument()
  })

  it('requires and submits a cancellation reason for the immutable audit trail', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')

    await screen.findByRole('heading', { name: 'Checkout' })
    const cancel = screen.getByRole('button', { name: 'Cancel draft' })
    expect(cancel).toBeDisabled()
    await user.type(screen.getByLabelText('Cancellation reason'), 'Customer changed their mind')
    await user.click(cancel)

    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/cancel', {
      expected_version: 3,
      reason: 'Customer changed their mind',
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-cancel-/) } }))
  })

  it('keeps every manual tender as one full-sale checkout with the same audited envelope', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')
    await screen.findByRole('heading', { name: 'Checkout' })

    for (const tender of ['cash', 'check', 'ach', 'zelle', 'external_terminal', 'fleet_reference', 'other']) {
      await user.selectOptions(screen.getByLabelText('Tender'), tender)
      const reference = screen.getByLabelText('Reference')
      await user.clear(reference)
      await user.type(reference, `${tender} reference`)
      apiMocks.post.mockClear()
      await user.click(screen.getByRole('button', { name: 'Checkout $42.80' }))
      await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/checkout', {
        expected_version: 3,
        tender,
        payment_token: null,
        manual_reference: `${tender} reference`,
        receipt_email: null,
      }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-checkout-/) } }))
    }
  })

  it('uses the frozen Stripe checkout envelope, Elements confirmation, and returned reconcile URL', async () => {
    const draft = sale()
    installApi(draft)
    apiMocks.post.mockImplementation((url: string) => {
      if (url.endsWith('/checkout')) return Promise.resolve({ data: {
        sale: { ...draft, status: 'awaiting_payment', allowed_actions: ['reconcile_payment'] },
        payment: { attempt_id: 'attempt-stripe', tender: 'stripe', state: 'pending', client_secret: 'pi_secret', stripe_account_id: 'acct_1', reconcile_url: '/api/v1/parts-operations/counter-sales/sale-1/payment-attempts/attempt-stripe/reconcile' },
      } })
      if (url.endsWith('/payment-attempts/attempt-stripe/reconcile')) return Promise.resolve({ data: { ...draft, status: 'completed' } })
      throw new Error(`Unexpected POST ${url}`)
    })
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')

    await screen.findByRole('heading', { name: 'Checkout' })
    await user.selectOptions(screen.getByLabelText('Tender'), 'stripe')
    await user.click(screen.getByRole('button', { name: 'Checkout $42.80' }))
    expect(await screen.findByText('Secure card fields')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Pay $42.80' }))

    await waitFor(() => expect(stripeMocks.confirmPayment).toHaveBeenCalledWith({ elements: {}, clientSecret: 'pi_secret', confirmParams: { return_url: window.location.href }, redirect: 'if_required' }))
    expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/payment-attempts/attempt-stripe/reconcile', { expected_version: 3 }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-reconcile-/) } })
  })

  it('tokenizes QuickBooks card data directly with Intuit and sends only the opaque token to checkout', async () => {
    installApi()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ value: 'opaque-token' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')

    await screen.findByRole('heading', { name: 'Checkout' })
    await user.selectOptions(screen.getByLabelText('Tender'), 'quickbooks_payments')
    await user.type(screen.getByLabelText('Name on card'), 'Alex Popescu')
    await user.type(screen.getByLabelText('Card number'), '4111111111111111')
    await user.type(screen.getByLabelText('Expiry'), '12/2030')
    await user.type(screen.getByLabelText('Security code'), '123')
    await user.type(screen.getByLabelText('Billing ZIP'), '28105')
    await user.click(screen.getByRole('button', { name: 'Secure card for checkout' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens', expect.objectContaining({ method: 'POST' })))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/checkout', expect.objectContaining({ tender: 'quickbooks_payments', payment_token: 'opaque-token' }), { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-checkout-/) } }))
    expect(screen.getByLabelText('Card number')).toHaveValue('')
  })

  it('renders provider recovery only from allowed actions and reconciles the existing attempt', async () => {
    const pending = sale({
      status: 'awaiting_payment',
      allowed_actions: ['reconcile_payment'],
      payment_attempts: [{ id: 'attempt-1', tender: 'stripe', state: 'pending', amount: '42.80', failure_code: null, safe_status: 'processing', created_at: '2026-08-26T12:05:00Z' }],
    })
    installApi(pending)
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')

    expect(await screen.findByRole('heading', { name: 'Payment pending' })).toBeInTheDocument()
    expect(screen.getByText('Stock remains held. The existing attempt must converge before any new charge.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reconcile payment' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/payment-attempts/attempt-1/reconcile', { expected_version: 3 }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-reconcile-/) } }))
  })

  it('supports receipt delivery and a validated partial damaged return without optimistic stock claims', async () => {
    const completed = sale({
      status: 'completed',
      allowed_actions: ['download_receipt', 'email_receipt', 'create_return', 'retry_refund'],
      completed_at: '2026-08-26T12:10:00Z',
      buyer_email: 'buyer@example.test',
      returns: [{ id: 'return-1', sale_id: 'sale-1', version: 1, state: 'refund_failed', refund_amount: '21.40', failure_code: 'provider_unavailable', lines: [{ id: 'return-line-1', sale_line_id: 'line-1', quantity: 1, reason: 'Damaged box', disposition: 'damaged', refund_amount: '21.40' }], created_at: '2026-08-26T12:20:00Z', completed_at: null }],
    })
    installApi(completed)
    const user = userEvent.setup()
    renderWorkspace('/dashboard/garage/inventory/sales?sale=sale-1')

    expect(await screen.findByRole('button', { name: 'Email receipt' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Email receipt' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/receipt/email', { email: 'buyer@example.test' }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-receipt-/) } }))
    await user.click(screen.getByRole('button', { name: 'Retry refund' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/returns/return-1/retry-refund', { expected_version: 3 }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-refund-retry-/) } }))

    await user.click(screen.getByRole('button', { name: 'Return items' }))
    const dialog = screen.getByRole('dialog', { name: 'Return items from CS-1001' })
    expect(within(dialog).getByRole('button', { name: 'Close return' })).toHaveFocus()
    await user.click(within(dialog).getByRole('button', { name: 'Increase Return quantity for Primary air filter' }))
    await user.type(within(dialog).getByLabelText('Reason'), 'Damaged packaging')
    await user.click(within(dialog).getByLabelText('Damaged'))
    await user.click(within(dialog).getByRole('button', { name: 'Submit return and refund' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/counter-sales/sale-1/returns', {
      expected_version: 3,
      lines: [{ sale_line_id: 'line-1', quantity: 1, reason: 'Damaged packaging', disposition: 'damaged' }],
      manual_refund_reference: null,
    }, { headers: { 'Idempotency-Key': expect.stringMatching(/^counter-sale-return-/) } }))
  })
})
