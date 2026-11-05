import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { InvoiceSettlementSummary } from '@/features/payments/types'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), settlement: null as unknown, settlementError: null as unknown, savedApplied: undefined as string | null | undefined }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock('@/features/payments', async () => ({ ...await vi.importActual('@/features/payments'),
  useInvoiceSettlement: () => ({ data: mocks.settlement, error: mocks.settlementError, isLoading: false }),
  useInvoiceAllocations: () => ({ data: { items: [] } }),
}))
import InvoiceAccessPage from '../InvoiceAccessPage'
import CustomerInvoicePage from '@/features/customer-portal/CustomerInvoicePage'
function show(audience: 'guest' | 'portal', overrides: Partial<InvoiceSettlementSummary>, prior?: string, initialUnavailable?: unknown) {
  const summary = { invoice_id: 'matrix-invoice', currency: 'USD', principal_total: '100.00', confirmed_principal: '0.00',
    active_pending_principal: '0.00', outstanding_balance: '100.00', allocatable_balance: '100.00', unapplied_credit: '0.00',
    refund_pending: '0.00', state: 'unpaid', version: 1, card_provider: null, card_provider_status: 'not_configured',
    accounting_sync_status: 'not_started', feature_enabled: true, allowed_actions: { create_attempt: false, rails: [] }, ...overrides } as InvoiceSettlementSummary
  mocks.settlement = initialUnavailable ? null : summary
  if (initialUnavailable !== undefined) mocks.settlementError = initialUnavailable
  const invoice = { invoice_id: 'matrix-invoice', id: 'matrix-invoice', repair_order_id: 'order-matrix', invoice_number: prior === undefined ? 'MATRIX' : 'DBN-COL-INTERNAL',
    order_number: 'RO-MATRIX', customer_name: 'Synthetic customer', vehicle_info: 'Synthetic truck', source: prior === undefined ? 'native' : 'ets_collection_handoff',
    status: summary.state === 'paid' ? 'paid' : 'sent', is_paid: summary.state === 'paid', subtotal: '100.00', total_amount: '100.00',
    amount_due: summary.outstanding_balance, shop_supplies_amount: '0.00', service_fee_amount: '0.00', tax_amount: '0.00', discount_amount: '0.00', has_portal_account: true,
    payment_summary: { state: summary.state, applied_amount: mocks.savedApplied === null ? null : summary.confirmed_principal, balance_due: summary.outstanding_balance, pending_amount: summary.active_pending_principal, basis: 'settlement', note: null },
    ...(prior === undefined ? {} : { source_collection: { id: 'collection', state: 'active', collection_enabled: true, source_invoice_number: '1687', display_invoice_number: 'TPS-1687', original_bill_to_name: 'Original Fleet LLC',
      original_issued_total: String(100 + Number(prior)), source_prior_allocated: prior, opening_principal: '100.00', native_confirmed_principal: summary.confirmed_principal,
      native_pending_principal: summary.active_pending_principal, balance_due: summary.outstanding_balance, source_sync_state: 'current', hold_reasons: [] } }),
  }
  mocks.post.mockImplementation(async (url: string) => { if (url === '/invoice-access/resolve') return { data: invoice }; throw new Error(`Unexpected write ${url}`) })
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/invoices/matrix-invoice') return { data: invoice }
    if (url.includes('allocations')) return { data: { items: [] } }
    return { data: {} }
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const tree = () => <QueryClientProvider client={client}>
    <MemoryRouter initialEntries={[audience === 'guest' ? '/invoice/matrix-token' : '/portal/invoices/matrix-invoice']}><Routes>
      <Route path="/invoice/:token" element={<InvoiceAccessPage />} /><Route path="/portal/invoices/:invoiceId" element={<CustomerInvoicePage />} />
    </Routes></MemoryRouter></QueryClientProvider>
  const view = render(tree())
  return { ...view, rerenderCurrent: () => view.rerender(tree()) }
}
beforeEach(() => { mocks.get.mockReset(); mocks.post.mockReset(); mocks.settlement = null; mocks.settlementError = null; mocks.savedApplied = undefined })
describe.each(['guest', 'portal'] as const)('%s actual invoice state presentation', audience => {
  it.each(['0.00', '20.00'])('shows the original total only when prior credit %s changes the balance', async prior => {
    show(audience, { allowed_actions: { create_attempt: true, rails: ['card', 'zelle'] }, state: 'payment_pending', active_pending_principal: '20.00', allocatable_balance: '80.00' }, prior)
    await screen.findByText('Synthetic truck')
    expect(screen.getByText('Pending confirmation')).toBeInTheDocument()
    expect(screen.getByLabelText('Payment amount')).toHaveValue('80.00')
    expect(screen.getByRole('button', { name: 'Partial payment' })).toBeInTheDocument()
    expect(screen.queryByText('Available to pay')).not.toBeInTheDocument()
    if (audience === 'guest') {
      const details = screen.getByRole('button', { name: 'Invoice details', exact: true })
      expect(details).toHaveAttribute('aria-expanded', 'false')
      expect(screen.queryByText('Invoice total', { exact: true })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Continue with card' }).compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      await userEvent.click(details)
      expect(details).toHaveAttribute('aria-expanded', 'true')
    }
    if (prior === '0.00') expect(screen.queryByText('Invoice total', { exact: true })).not.toBeInTheDocument()
    else expect(screen.getByText('Invoice total', { exact: true }).parentElement).toHaveTextContent('$120.00')
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
  it.each([
    ['refund', { refund_pending: '20.00' }, /\$20.00 refund pending/],
    ['credit', { unapplied_credit: '15.00' }, /\$15.00 is unapplied/],
  ] as const)('retains the %s notice on a paid split invoice', async (_, extras, notice) => {
    show(audience, { state: 'paid', confirmed_principal: '100.00', outstanding_balance: '0.00', allocatable_balance: '0.00', ...extras })
    await screen.findByText('Synthetic truck')
    expect(await screen.findByText(notice)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Partial payment' })).not.toBeInTheDocument()
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
  it.each([
    ['unpaid', '0.00', '0.00', '100.00'],
    ['partially_paid', '40.00', '0.00', '60.00'],
    ['payment_pending', '0.00', '20.00', '100.00'],
    ['partially_paid_pending', '40.00', '20.00', '60.00'],
    ['paid', '100.00', '0.00', '0.00'],
  ] as const)('retains %s balance through a component remount without starting a payment', async (state, applied, pending, due) => {
    const args = { state, confirmed_principal: applied, active_pending_principal: pending, outstanding_balance: due, allocatable_balance: String(Number(due) - Number(pending)) }
    const first = show(audience, args)
    await screen.findByText('Synthetic truck')
    if (audience === 'portal') expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(`$${due}`)
    else expect(screen.getAllByText(`$${due}`).length).toBeGreaterThan(0)
    if (pending !== '0.00') expect(screen.getByText('Pending confirmation')).toBeInTheDocument()
    first.unmount()
    show(audience, args)
    await screen.findByText('Synthetic truck')
    if (audience === 'portal') expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(`$${due}`)
    else expect(screen.getAllByText(`$${due}`).length).toBeGreaterThan(0)
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
  it('retains the paid refund notice without inventing tender for an unknown payment breakdown', async () => {
    mocks.savedApplied = null
    show(audience, { state: 'paid', confirmed_principal: '100.00', outstanding_balance: '0.00', allocatable_balance: '0.00', refund_pending: '20.00' })
    expect(await screen.findByText(/\$20.00 refund pending/)).toBeInTheDocument()
    expect(screen.queryByText('Paid toward invoice')).not.toBeInTheDocument()
    expect(screen.queryByText('Payments / credits applied')).not.toBeInTheDocument()
  })
  it('shows both refund and credit when they coexist on a paid invoice', async () => {
    show(audience, { state: 'paid', confirmed_principal: '100.00', outstanding_balance: '0.00', allocatable_balance: '0.00', refund_pending: '20.00', unapplied_credit: '15.00' })
    expect(await screen.findByText(/\$20.00 refund pending/)).toBeInTheDocument()
    expect(screen.getByText(/\$15.00 is unapplied/)).toBeInTheDocument()
  })
  it('shows a failed fresh settlement read instead of enabling stale split controls', async () => {
    mocks.settlementError = new Error('Synthetic failed settlement read')
    show(audience, { state: 'partially_paid', confirmed_principal: '40.00', outstanding_balance: '60.00' })
    expect(await screen.findByRole('alert')).toHaveTextContent(/Payment details could not be loaded/)
    expect(screen.queryByRole('button', { name: 'Partial payment' })).not.toBeInTheDocument()
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
  it.each([
    ['0.00', '0.00', '0.00'], ['20.00', '0.00', '0.00'],
    ['0.00', '40.00', '0.00'], ['20.00', '40.00', '0.00'],
    ['0.00', '100.00', '0.00'], ['20.00', '100.00', '0.00'],
    ['0.00', '0.00', '20.00'], ['20.00', '40.00', '20.00'],
  ])('shows prior %s and confirmed native %s while pending %s stays unapplied', async (prior, native, pending) => {
    const due = (100 - Number(native)).toFixed(2)
    const state = native === '100.00' ? 'paid' : native !== '0.00' ? pending !== '0.00' ? 'partially_paid_pending' : 'partially_paid' : pending !== '0.00' ? 'payment_pending' : 'unpaid'
    show(audience, { state, confirmed_principal: native, active_pending_principal: pending, outstanding_balance: due, allocatable_balance: (Number(due) - Number(pending)).toFixed(2) }, prior)
    await screen.findByText('Synthetic truck')
    expect(screen.queryByText('Paid toward invoice')).not.toBeInTheDocument()
    expect(screen.getByText('Invoice TPS-1687')).toBeInTheDocument()
    expect(screen.queryByText(/DBN-COL-INTERNAL/)).not.toBeInTheDocument()
    const applied = Number(prior) + Number(native)
    if (applied) {
      const label = await screen.findByText('Payments / credits applied')
      expect(label.parentElement).toHaveTextContent(`$-${applied.toFixed(2)}`)
    } else expect(screen.queryByText('Payments / credits applied')).not.toBeInTheDocument()
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
})

describe('guest payment details disclosure', () => {
  it('keeps every native charge below the payment action and reveals it accessibly', async () => {
    show('guest', { allowed_actions: { create_attempt: true, rails: ['card', 'zelle'] } })
    await screen.findByText('Synthetic truck')
    expect(screen.queryByText('Status: Unpaid')).not.toBeInTheDocument()
    expect(screen.queryByText('Subtotal')).not.toBeInTheDocument()
    const details = screen.getByRole('button', { name: 'Invoice details', exact: true })
    const primary = screen.getByRole('button', { name: 'Continue with card' })
    const otherMethods = screen.getByRole('button', { name: 'Other payment methods' })
    expect(primary.compareDocumentPosition(otherMethods) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(otherMethods.compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await userEvent.click(details)
    for (const label of ['Subtotal', 'Shop Supplies', 'Card Processing Fee', 'Sales tax']) expect(screen.getByText(label, { exact: true })).toBeInTheDocument()
    expect(details).toHaveFocus()
    await userEvent.click(details)
    expect(screen.queryByText('Subtotal')).not.toBeInTheDocument()
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
})

// Cached-read failures and unknown collection tender stay non-actionable.
describe.each(['guest', 'portal'] as const)('%s adverse-state regressions', audience => {
  it('withholds collection tender when saved native breakdown is unknown', async () => {
    mocks.savedApplied = null
    show(audience, {state:'paid', confirmed_principal:'100.00', outstanding_balance:'0.00', allocatable_balance:'0.00', refund_pending:'20.00'}, '20.00')
    expect(await screen.findByText(/\$20.00 refund pending/)).toBeInTheDocument()
    expect(screen.queryByText('Payments / credits applied')).not.toBeInTheDocument()
    expect(screen.queryByText('Paid toward invoice')).not.toBeInTheDocument()
    expect(screen.getByText('Invoice TPS-1687')).toBeInTheDocument()
  })
  it('removes previously actionable split controls on cached read failure and restores on recovery', async () => {
    const enabled = {state:'partially_paid' as const, confirmed_principal:'40.00', outstanding_balance:'60.00', allocatable_balance:'60.00', allowed_actions:{create_attempt:true,rails:['zelle' as const]}}
    const first=show(audience,enabled)
    expect(await screen.findByRole('button',{name:'Partial payment'})).toBeEnabled()
    mocks.settlementError=new Error('Independent cached-read failure')
    first.rerender(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={[audience==='guest'?'/invoice/matrix-token':'/portal/invoices/matrix-invoice']}><Routes><Route path="/invoice/:token" element={<InvoiceAccessPage/>}/><Route path="/portal/invoices/:invoiceId" element={<CustomerInvoicePage/>}/></Routes></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByRole('alert')).toHaveTextContent('Payment details could not be loaded')
    expect(screen.queryByRole('button',{name:'Partial payment'})).not.toBeInTheDocument()
    first.unmount()
    mocks.settlementError=null
    show(audience,enabled)
    expect(await screen.findByRole('button',{name:'Partial payment'})).toBeEnabled()
    expect(mocks.post.mock.calls.every(([url])=>url==='/invoice-access/resolve')).toBe(true)
  })
})


function unavailableResponse(code: string) {
  const missing = code === 'route_missing'
  return new AxiosError('Synthetic unavailable response', 'ERR_BAD_REQUEST', undefined, undefined, {
    status: missing ? 404 : 409, statusText: missing ? 'Not Found' : 'Conflict', headers: {}, config: { headers: new AxiosHeaders() },
    data: missing ? { detail: 'Not Found' } : { error: { code, message: 'Split payments unavailable' } },
  })
}
const unavailableCodes = ['feature_disabled', 'invoice_split_payments_disabled', 'split_payments_disabled', 'route_missing']
describe.each(['guest', 'portal'] as const)('%s unavailable settlement transitions', audience => {
  it.each(unavailableCodes)('blocks cached controls after %s and recovers on a successful read', async code => {
    const view = show(audience, { state: 'partially_paid', confirmed_principal: '40.00', outstanding_balance: '60.00', allocatable_balance: '60.00', allowed_actions: { create_attempt: true, rails: ['zelle'] } })
    expect(await screen.findByRole('button', { name: 'Partial payment' })).toBeEnabled()
    mocks.settlementError = unavailableResponse(code)
    view.rerenderCurrent()
    expect(await screen.findByRole('alert')).toHaveTextContent('Payment details could not be loaded')
    expect(screen.queryByRole('button', { name: 'Partial payment' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pay in full' })).not.toBeInTheDocument()
    if (audience === 'portal') expect(mocks.get.mock.calls.some(([url]) => url.includes('quickbooks/payments/availability'))).toBe(false)
    mocks.settlementError = null
    view.rerenderCurrent()
    expect(await screen.findByRole('button', { name: 'Partial payment' })).toBeEnabled()
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
  it.each(unavailableCodes)('preserves first-read legacy fallback for %s without cached split data', async code => {
    show(audience, { feature_enabled: false }, undefined, unavailableResponse(code))
    await screen.findByText('Synthetic truck')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Partial payment' })).not.toBeInTheDocument()
    if (audience === 'guest') expect(await screen.findByRole('button', { name: 'Open My Portal' })).toBeEnabled()
    expect(mocks.post.mock.calls.every(([url]) => url === '/invoice-access/resolve')).toBe(true)
  })
})
