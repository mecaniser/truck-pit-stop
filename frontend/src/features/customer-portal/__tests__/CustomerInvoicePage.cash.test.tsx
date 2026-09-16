import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { CashReceiptSummary } from '@/types'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get } }))
vi.mock('@/features/payments', () => ({
  useInvoiceSettlement: () => ({ data: { feature_enabled: false }, isLoading: false }),
  useInvoiceAllocations: () => ({}),
  isSettlementUnavailable: () => false,
  isPositiveMoney: () => false,
  SettlementPaymentPanel: () => null,
  SettlementCreditPanel: () => null,
  SettlementResolutionPanel: () => null,
  SettlementSummaryCard: () => null,
  paymentApiError: () => ({}),
}))
import CustomerInvoicePage from '../CustomerInvoicePage'

function renderInvoice(receipt?: CashReceiptSummary) {
  mocks.get.mockResolvedValue({ data: {
    id: 'invoice-1', status: 'paid', invoice_number: 'INV-1', order_number: 'RO-1',
    subtotal: '100.00', shop_supplies_amount: '3.00', service_fee_amount: '4.00',
    tax_amount: '8.00', discount_amount: '0.00', total_amount: '115.00',
    paid_at: '2026-09-12T18:00:00Z', cash_receipt: receipt,
  } })
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={['/portal/invoices/invoice-1']}><Routes>
      <Route path="/portal/invoices/:invoiceId" element={<CustomerInvoicePage />} />
    </Routes></MemoryRouter>
  </QueryClientProvider>)
}
const cash: CashReceiptSummary = { method: 'cash', amount: '101.00', subtotal: '100.00', shop_supplies_amount: '3.00', service_fee_amount: '0.00', tax_amount: '0.00', discount_amount: '2.00', paid_at: '2026-09-12T18:00:00Z' }

describe('customer cash receipt', () => {
  it.each(['0.00', '8.00'])('uses recorded totals and explicitly displays tax %s', async tax => {
    renderInvoice({ ...cash, tax_amount: tax, amount: tax === '0.00' ? '101.00' : '109.00' })
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(tax === '0.00' ? '$101.00' : '$109.00')
    const row = (name: string) => screen.getByText(name).closest('div')!
    expect(row('Card processing fee')).toHaveTextContent('$0.00')
    expect(row('Shop supplies')).toHaveTextContent('$3.00')
    expect(row('Discount')).toHaveTextContent('$-2.00')
    expect(row(tax === '0.00' ? 'Sales tax — not charged' : 'Sales tax')).toHaveTextContent(`$${tax}`)
    expect(row('Balance due')).toHaveTextContent('$0.00')
    expect(screen.queryByText(/Receipt emailed instantly/)).not.toBeInTheDocument()
    expect(screen.queryByText(/No card fee with Zelle/)).not.toBeInTheDocument()
    expect(screen.queryByText('$115.00')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Receipt', exact: true })).toHaveAttribute('href', '/api/v1/invoices/invoice-1/pdf')
  })
  it('does not invent a cash receipt or uncharged tax without verified evidence', async () => {
    renderInvoice()
    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByText('Sales tax — not charged')).not.toBeInTheDocument()
    expect(screen.queryByText('Balance due')).not.toBeInTheDocument()
    expect(screen.getByText('Tax').closest('div')).toHaveTextContent('$8.00')
  })
})
