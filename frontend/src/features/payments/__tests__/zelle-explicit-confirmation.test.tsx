import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError, AxiosHeaders } from 'axios'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { InvoiceSettlementSummary, PaymentAttemptResponse } from '../types'

const api = vi.hoisted(() => ({ createPaymentAttempt: vi.fn(), fetchSettlement: vi.fn(), fetchAllocations: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), ...api }))
vi.mock('@/lib/stripe', () => ({ getStripeForAccount: vi.fn() }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
import SettlementPaymentPanel from '../SettlementPaymentPanel'
import SettlementSummaryCard from '../SettlementSummaryCard'
import PaymentStatusRefresh from '../PaymentStatusRefresh'

const base = { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, principal_total: '268.44', outstanding_balance: '268.44', allocatable_balance: '268.44' }
const access = { kind: 'authenticated' as const, invoiceId: base.invoice_id }
const recipient = { display: 'billing@example.test', memo: 'Invoice TPS-1687' }
function show(summary: InvoiceSettlementSummary = base, audience: 'customer' | 'guest' = 'customer') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const onUpdated = vi.fn()
  const props = { access: audience === 'guest' ? { kind: 'guest' as const, token: 'fictional-access' } : access, summary, audience, zelleRecipient: recipient, onUpdated }
  return { ...render(<QueryClientProvider client={client}><SettlementPaymentPanel {...props} /></QueryClientProvider>), client, props, onUpdated }
}
async function instructions() {
  await userEvent.click(screen.getByRole('radio', { name: /^Zelle/ }))
  await userEvent.click(screen.getByRole('button', { name: 'View Zelle instructions' }))
}
function reported(): PaymentAttemptResponse {
  return { attempt_id: 'reported-transfer', invoice_id: base.invoice_id, principal_amount: '268.44', card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: '268.44', rail: 'zelle', provider: 'manual', state: 'pending', expires_at: null, provider_configuration_version: 1, attempt_version: 1,
    settlement: { ...base, version: 2, active_pending_principal: '268.44', allocatable_balance: '0.00', state: 'payment_pending', allowed_actions: { rails: [], create_attempt: false } } }
}
beforeEach(() => { vi.clearAllMocks(); api.fetchSettlement.mockResolvedValue(base); api.fetchAllocations.mockResolvedValue({ items: [] }) })

describe('Customer payment choices', () => {
  it.each([
    ['customer', 'quickbooks_payments'], ['guest', 'quickbooks_payments'],
    ['customer', 'stripe_connect'], ['guest', 'stripe_connect'],
  ] as const)('uses familiar payment labels for %s with %s', async (audience, provider) => {
    show({ ...base, card_provider: provider }, audience)
    expect(screen.getByRole('radio', { name: 'Card Credit or debit', exact: true })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'Zelle No card fee', exact: true })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Continue with card', exact: true })).toBeEnabled()
    expect(screen.queryByText(/QuickBooks|Stripe/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pay in full', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Pay part', exact: true }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Payment amount', exact: true }), '50.00')
    expect(screen.getByRole('textbox', { name: 'Payment amount', exact: true })).toHaveValue('50.00')
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })
  it('discloses shop-assisted methods without creating a payment or enabling unsupported rails', async () => {
    show()
    const other = screen.getByRole('button', { name: 'Other payment methods', exact: true })
    expect(other).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(/Contact the shop about bank transfers/)).not.toBeInTheDocument()
    await userEvent.click(other)
    expect(other).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/bank transfers or fleet checks\/codes \(EFS, Comchek, T-Chek\)/)).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /ACH|EFS|Fleet/ })).not.toBeInTheDocument()
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
    await userEvent.keyboard('{Tab}')
  })
})

describe('Zelle transfer report boundary', () => {
  it.each(['customer', 'guest'] as const)('shows instructions and returns without reserving money for %s', async audience => {
    show(base, audience)
    await instructions()
    expect(screen.getByRole('heading', { name: 'Pay with Zelle' })).toHaveFocus()
    expect(screen.getByText(recipient.display)).toBeInTheDocument()
    expect(screen.getByText('$268.44')).toBeInTheDocument()
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Back to invoice' }))
    expect(screen.getByRole('button', { name: 'View Zelle instructions' })).toHaveFocus()
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })
  it('reports only after explicit confirmation and preserves the exact amount', async () => {
    api.createPaymentAttempt.mockResolvedValue(reported())
    show()
    await instructions()
    await userEvent.click(screen.getByRole('button', { name: 'I’ve sent the payment' }))
    await waitFor(() => expect(api.createPaymentAttempt).toHaveBeenCalledTimes(1))
    expect(api.createPaymentAttempt.mock.calls[0][1]).toMatchObject({ amount: '268.44', rail: 'zelle', expected_settlement_version: 1, transfer_sent_confirmed: true })
  })
  it('retains the same payload and key when reporting has an uncertain outcome', async () => {
    api.createPaymentAttempt.mockRejectedValueOnce(new Error('Network unavailable')).mockResolvedValueOnce(reported())
    show(); await instructions()
    await userEvent.click(screen.getByRole('button', { name: 'I’ve sent the payment' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Retry report' }))
    await waitFor(() => expect(api.createPaymentAttempt).toHaveBeenCalledTimes(2))
    expect(api.createPaymentAttempt.mock.calls[1]).toEqual(api.createPaymentAttempt.mock.calls[0])
  })
  it('allows correction after an explicit server rejection without reporting again', async () => {
    api.createPaymentAttempt.mockRejectedValue(new AxiosError('Conflict', undefined, undefined, undefined, { status: 409, statusText: 'Conflict', headers: {}, config: { headers: new AxiosHeaders() }, data: { error: { code: 'attempt_conflict', message: 'Review the invoice.', retryable: false } } }))
    show(); await instructions()
    await userEvent.click(screen.getByRole('button', { name: 'I’ve sent the payment' }))
    expect(await screen.findByText('Your transfer report wasn’t saved. Review the details and try again.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Back to invoice' }))
    expect(screen.getByRole('button', { name: 'View Zelle instructions' })).toBeInTheDocument()
    expect(api.createPaymentAttempt).toHaveBeenCalledTimes(1)
  })
  it('does not allow a recipient change to silently change reviewed instructions', async () => {
    const { rerender, props, client } = show(); await instructions()
    rerender(<QueryClientProvider client={client}><SettlementPaymentPanel {...props} zelleRecipient={{ ...recipient, display: 'changed@example.test' }} /></QueryClientProvider>)
    expect(screen.getByRole('button', { name: 'I’ve sent the payment' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('payment details changed')
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })
  it('does not allow an updated balance/version to be submitted from old instructions', async () => {
    const { rerender, props, client } = show(); await instructions()
    rerender(<QueryClientProvider client={client}><SettlementPaymentPanel {...props} summary={{ ...base, version: 2, allocatable_balance: '100.00' }} /></QueryClientProvider>)
    expect(screen.getByRole('button', { name: 'I’ve sent the payment' })).toBeDisabled()
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })
})

describe('Payment refresh feedback', () => {
  it('shows in-flight feedback, deduplicates clicks, and reports unchanged status', async () => {
    let resolve!: (s: InvoiceSettlementSummary) => void
    api.fetchSettlement.mockReturnValue(new Promise<InvoiceSettlementSummary>(r => { resolve = r }))
    render(<QueryClientProvider client={new QueryClient()}><PaymentStatusRefresh access={access} summary={base} onUpdated={vi.fn()} /></QueryClientProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Refresh payment status' }))
    expect(screen.getByRole('button', { name: 'Checking payment status…' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Checking for updates')
    await act(async () => { resolve(base) })
    expect(await screen.findByText('Checked just now. No change yet.')).toBeInTheDocument()
    expect(api.fetchSettlement).toHaveBeenCalledTimes(1)
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })
  it('announces changed status and updates only this access scope', async () => {
    const next = { ...base, version: 2, confirmed_principal: '68.44', outstanding_balance: '200.00', allocatable_balance: '200.00', state: 'partially_paid' as const }
    api.fetchSettlement.mockResolvedValue(next)
    const client = new QueryClient()
    const other = { ...base, invoice_id: 'other-invoice' }
    client.setQueryData(['invoice-settlement', 'authenticated', other.invoice_id], other)
    const onUpdated = vi.fn()
    render(<QueryClientProvider client={client}><PaymentStatusRefresh access={access} summary={base} onUpdated={onUpdated} /></QueryClientProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Refresh payment status' }))
    expect(await screen.findByText('Payment status updated.')).toBeInTheDocument()
    expect(onUpdated).toHaveBeenCalledWith(next)
    expect(client.getQueryData(['invoice-settlement', 'authenticated', other.invoice_id])).toEqual(other)
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })
  it('does not regress a newer cache when an older read finishes', async () => {
    let resolve!: (s: InvoiceSettlementSummary) => void
    api.fetchSettlement.mockReturnValue(new Promise<InvoiceSettlementSummary>(r => { resolve = r }))
    const client = new QueryClient()
    const onUpdated = vi.fn()
    render(<QueryClientProvider client={client}><PaymentStatusRefresh access={access} summary={base} onUpdated={onUpdated} /></QueryClientProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Refresh payment status' }))
    const newer = { ...base, version: 3, active_pending_principal: '100.00', allocatable_balance: '168.44' }
    client.setQueryData(['invoice-settlement', 'authenticated', base.invoice_id], newer)
    await act(async () => { resolve({ ...base, version: 2 }) })
    expect(client.getQueryData(['invoice-settlement', 'authenticated', base.invoice_id])).toEqual(newer)
    expect(onUpdated).not.toHaveBeenCalled()
    expect(screen.getByText('A newer payment update is already shown.')).toBeInTheDocument()
  })
  it('drops a late read after changing guest access', async () => {
    let resolve!: (s: InvoiceSettlementSummary) => void
    api.fetchSettlement.mockReturnValue(new Promise<InvoiceSettlementSummary>(r => { resolve = r }))
    const client = new QueryClient()
    const onUpdated = vi.fn()
    const view = (token: string) => <QueryClientProvider client={client}><PaymentStatusRefresh access={{ kind: 'guest', token }} summary={base} onUpdated={onUpdated} /></QueryClientProvider>
    const { rerender } = render(view('first-access'))
    await userEvent.click(screen.getByRole('button', { name: 'Refresh payment status' }))
    rerender(view('second-access'))
    await act(async () => { resolve({ ...base, version: 2 }) })
    expect(onUpdated).not.toHaveBeenCalled()
    expect(client.getQueryData(['invoice-settlement', 'guest', 'second-access'])).toBeUndefined()
    expect(client.getQueryData(['invoice-settlement', 'guest', 'first-access'])).toBeUndefined()
  })
  it('reports read failures without claiming success or replacing valid balances', async () => {
    api.fetchAllocations.mockRejectedValue(new Error('Read failed'))
    const onUpdated = vi.fn()
    render(<QueryClientProvider client={new QueryClient()}><PaymentStatusRefresh access={access} summary={base} onUpdated={onUpdated} /></QueryClientProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Refresh payment status' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t check payment status')
    expect(onUpdated).not.toHaveBeenCalled()
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })
})

it('keeps one compact pending amount and shows requested amounts in disclosed activity', async () => {
  const pending = reported().settlement
  render(<SettlementSummaryCard summary={pending} audience="customer" streamlined allocations={[{ ...DB048_SETTLEMENT_FIXTURES.pendingZelle500.allocations[0], principal_amount: '168.44', applied_principal_amount: '0.00' }]} />)
  expect(screen.getAllByText('Pending confirmation')).toHaveLength(1)
  expect(screen.queryByText('$168.44')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /Payment activity/ }))
  expect(screen.getByText('$168.44')).toBeInTheDocument()
  expect(screen.getByText('Requested')).toBeInTheDocument()
})
