import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CustomerAccount from './CustomerAccount'

const auth = vi.hoisted(() => ({ session: 'tenant-a:owner-a' }))
const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('@/stores/authStore', () => ({
  getAuthenticatedSessionIdentity: () => auth.session,
  useAuthStore: Object.assign((select: (state: unknown) => unknown) => select({}), { getState: () => ({}) }),
}))

const orderId = '11111111-1111-4111-8111-111111111111'
const account = {
  as_of_date: '2026-10-17', generated_at: '2026-10-17T12:00:00Z', currency: 'USD',
  customer: { id: 'customer-a', name: 'Northline' },
  native: { collectible: '85.00', current: '30.00', days_1_30: '55.00', days_31_60: '0.00', days_61_90: '0.00', days_90_plus: '0.00', undated_due: '0.00', unapplied_credit: '15.00', review_required_count: 1 },
  ets_history: { observed_open_balance: null, balance_basis: 'unavailable', review_required_count: 0, collectible: false },
  transactions: [
    { id: 'invoice-a', kind: 'invoice', source_owner: 'native', occurred_at: '2026-10-01', date_basis: 'issued_date', invoice_id: 'invoice-a', amount: '100.00', principal_total: '100.00', settled_principal: '15.00', remaining_principal: '85.00', drilldown_route: `/dashboard/repair-orders?selected=${orderId}`, review_reason: null },
    { id: 'invoice-ets', kind: 'invoice', source_owner: 'ets_history', occurred_at: null, date_basis: 'unknown', invoice_id: 'invoice-ets', amount: '500.00', remaining_principal: null, drilldown_route: `/dashboard/repair-orders?selected=${orderId}`, review_reason: null },
    { id: 'invoice-review', kind: 'invoice', source_owner: 'review_required', occurred_at: null, date_basis: 'unknown', invoice_id: 'invoice-review', amount: null, remaining_principal: null, drilldown_route: `/dashboard/repair-orders?selected=${orderId}`, review_reason: 'merged_customer_identity' },
  ], next_cursor: null,
}

function setup(customerId = 'customer-a') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<MemoryRouter><QueryClientProvider client={client}><CustomerAccount customerId={customerId} /></QueryClientProvider></MemoryRouter>)
}

beforeEach(() => { api.get.mockReset(); auth.session = 'tenant-a:owner-a' })
afterEach(() => { vi.restoreAllMocks() })

describe('customer account', () => {
  it('keeps native collectible, unapplied credit and unknown ETS balance separate', async () => {
    api.get.mockResolvedValue({ data: account })
    setup()
    const view = await screen.findByRole('region', { name: 'Customer account' })
    expect(within(view).getByText('$85.00')).toBeVisible()
    expect(within(view).getByText('$15.00')).toBeVisible()
    expect(within(view).getByText('Principal $100.00 · Settled $15.00 · $85.00 remaining')).toBeVisible()
    expect(within(view).getByText(/Outstanding ETS balance is unavailable/)).toBeVisible()
    expect(within(view).queryByText('$500.00 remaining')).not.toBeInTheDocument()
    expect(within(view).getByText('1 native item needs review and is excluded from these totals.')).toBeVisible()
    const activity = within(view).getByRole('region', { name: 'Account activity' })
    expect(within(activity).getAllByRole('link', { name: /Open order/ })).toHaveLength(2)
    const reviewRow = within(activity).getByText('Needs review').closest('li')!
    expect(within(reviewRow).queryByRole('link')).not.toBeInTheDocument()
    expect(within(reviewRow).queryByText('$100.00')).not.toBeInTheDocument()
  })

  it('rejects a mismatched customer reply instead of showing another account', async () => {
    api.get.mockResolvedValue({ data: { ...account, customer: { id: 'customer-b', name: 'Other' } } })
    setup()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Account unavailable')
    expect(screen.queryByText('$85.00')).not.toBeInTheDocument()
  })

  it('retries a failed read and does not present a false empty account', async () => {
    api.get.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce({ data: { ...account, transactions: [] } })
    setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('Account unavailable')
    expect(screen.queryByText('No account activity in this view.')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry account' }))
    expect(await screen.findByText('No account activity in this view.')).toBeVisible()
  })

  it('marks an unconfirmed payment and blocks an unsafe drill-down route', async () => {
    api.get.mockResolvedValue({ data: { ...account, transactions: [{
      id: 'payment-pending', kind: 'payment', source_owner: 'review_required', occurred_at: '2026-10-17T12:00:00Z',
      source_date: null, date_basis: 'created_at', invoice_id: 'invoice-a', amount: '50.00', remaining_principal: null,
      drilldown_route: 'https://outside.example/steal', review_reason: 'payment_pending', payment_status: 'pending',
    }] } })
    setup()
    expect(await screen.findByText('Pending payment')).toBeVisible()
    expect(screen.getByText('Payment not confirmed; does not reduce the collectible balance.')).toBeVisible()
    expect(screen.queryByRole('link', { name: /Open order/ })).not.toBeInTheDocument()
  })

  it('paginates with the opaque server cursor and preserves source separation', async () => {
    api.get.mockImplementation((_path: string, config: { params: { cursor?: string } }) => Promise.resolve({ data: config.params.cursor
      ? { ...account, transactions: [], next_cursor: null }
      : { ...account, next_cursor: 'opaque:1' } }))
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Older' }))
    expect(await screen.findByText('No account activity in this view.')).toBeVisible()
    expect(api.get).toHaveBeenLastCalledWith('/customers/customer-a/account', { signal: expect.any(AbortSignal), params: { limit: 50, cursor: 'opaque:1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Newer' }))
    expect(await screen.findByText('1 native item needs review and is excluded from these totals.')).toBeVisible()
  })

  it('downloads only a bounded PDF response and never sends a statement', async () => {
    const create = vi.fn(() => 'blob:account'), revoke = vi.fn(), click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke })
    api.get.mockImplementation((path: string) => path.endsWith('.pdf')
      ? Promise.resolve({ data: new Blob(['%PDF-test'], { type: 'application/pdf' }), headers: { 'content-type': 'application/pdf' } })
      : Promise.resolve({ data: account }))
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Download statement' }))
    expect(await screen.findByRole('button', { name: 'Download statement' })).toBeEnabled()
    expect(api.get).toHaveBeenCalledWith('/customers/customer-a/account/statement.pdf', { responseType: 'blob', signal: expect.any(AbortSignal) })
    expect(click).toHaveBeenCalledOnce()
    expect(create).toHaveBeenCalledOnce()
    expect(api.get.mock.calls.every(([path]) => !String(path).includes('send'))).toBe(true)
  })

  it('does not download a non-PDF error response', async () => {
    const create = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create })
    api.get.mockImplementation((path: string) => path.endsWith('.pdf')
      ? Promise.resolve({ data: new Blob(['error'], { type: 'text/html' }), headers: { 'content-type': 'text/html' } })
      : Promise.resolve({ data: account }))
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Download statement' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Statement unavailable')
    expect(create).not.toHaveBeenCalled()
  })
})
