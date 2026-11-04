import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import SettlementPaymentPanel from '../SettlementPaymentPanel'
import SettlementSummaryCard from '../SettlementSummaryCard'
import type { InvoiceSettlementSummary } from '../types'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'

const calls = vi.hoisted(() => ({ create: vi.fn(), quote: vi.fn() }))
vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  createPaymentAttempt: calls.create,
  fetchPaymentQuote: calls.quote,
}))

const renderPanel = (summary: InvoiceSettlementSummary, audience: 'customer' | 'guest' | 'staff') => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><SettlementPaymentPanel
    summary={{ ...summary, payment_verification_required: true }} audience={audience} tone="dark"
    access={audience === 'guest' ? { kind: 'guest', token: 'fixture-token' } : { kind: 'authenticated', invoiceId: summary.invoice_id }}
    onUpdated={vi.fn()} /></QueryClientProvider>)
}

describe('booking prepayment source verification', () => {
  it.each(['customer', 'guest', 'staff'] as const)('pauses new %s payments even when stale summary offers tenders', audience => {
    calls.create.mockClear(); calls.quote.mockClear()
    renderPanel(DB048_SETTLEMENT_FIXTURES.unpaid.summary, audience)
    expect(screen.getByText('Payment status needs review')).toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /pay|continue|confirm|submit/i })).not.toBeInTheDocument()
    expect(calls.create).not.toHaveBeenCalled()
    expect(calls.quote).not.toHaveBeenCalled()
  })
  it('does not label an invalidated source paid despite a zero cached balance', () => {
    renderPanel({ ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, state: 'paid', outstanding_balance: '0.00', allocatable_balance: '0.00' }, 'customer')
    expect(screen.getByText('Payment status needs review')).toBeInTheDocument()
    expect(screen.queryByText('Invoice paid in full')).not.toBeInTheDocument()
  })
})


it('does not turn a cached settlement into paid or available funds during source review', () => {
  render(<SettlementSummaryCard summary={{ ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, state: 'paid',
    confirmed_principal: '834.00', outstanding_balance: '0.00', allocatable_balance: '0.00',
    payment_verification_required: true }} />)
  expect(screen.getByRole('heading', { name: 'Payment status needs review' })).toBeInTheDocument()
  expect(screen.getByText('Unavailable')).toBeInTheDocument()
  expect(screen.queryByText('Paid in full')).not.toBeInTheDocument()
  expect(screen.queryByText('$834.00')).not.toBeInTheDocument()
  expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
})
