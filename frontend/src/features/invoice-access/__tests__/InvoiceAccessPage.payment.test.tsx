import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { post: mocks.post } }))
vi.mock('@/features/payments', () => ({
  useInvoiceSettlement: () => ({ data: { feature_enabled: false }, isLoading: false }),
  useInvoiceAllocations: () => ({}), isSettlementUnavailable: () => false,
  isPositiveMoney: () => false, SettlementPaymentPanel: () => null,
  SettlementCreditPanel: () => null, SettlementResolutionPanel: () => null,
  SettlementSummaryCard: () => null, paymentApiError: () => ({}),
}))
import InvoiceAccessPage from '../InvoiceAccessPage'

describe('guest invoice payment clarity', () => {
  it('does not claim paid or zero due when the current summary is partial', async () => {
    mocks.post.mockResolvedValue({ data: {
      invoice_id: 'demo', invoice_number: 'DEMO', order_number: 'RO-DEMO', customer_name: 'Sample Customer', vehicle_info: 'Sample truck',
      status: 'paid', is_paid: true, subtotal: '1000.00', total_amount: '1000.00', amount_due: '1000.00',
      shop_supplies_amount: '0.00', service_fee_amount: '0.00', tax_amount: '0.00', discount_amount: '0.00', zelle_amount: '1000.00',
      payment_summary: { state: 'partially_paid', applied_amount: '400.00', balance_due: '600.00', pending_amount: null, basis: 'settlement', note: null },
    } })
    render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={['/invoice/sample-token']}><Routes><Route path="/invoice/:token" element={<InvoiceAccessPage/>}/></Routes></MemoryRouter></QueryClientProvider>)
    await screen.findByRole('heading', { name: 'Partially paid' })
    const print = screen.getByRole('link', { name: 'Print', exact: true })
    expect(print).toHaveAttribute('href', '/api/v1/invoice-access/pdf/sample-token?print_view=true')
    expect(print).toHaveAttribute('target', '_blank')
    expect(print).toHaveAttribute('rel', 'noopener noreferrer')
    expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('href', '/api/v1/invoice-access/pdf/sample-token')
    expect(screen.queryByText('Payment received.')).not.toBeInTheDocument()
    expect(screen.getAllByText('$600.00')).toHaveLength(2)
    expect(screen.queryByText('This invoice is already paid')).not.toBeInTheDocument()
  })
})
