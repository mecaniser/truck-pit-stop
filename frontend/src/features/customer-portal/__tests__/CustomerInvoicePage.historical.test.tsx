import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { InvoicePaymentPresentation } from '@/types'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
import CustomerInvoicePage from '../CustomerInvoicePage'

function renderInvoice(status: string, source: string | null = 'easy_truck_shop_import', state = status === 'sent' ? 'unpaid' : status, includeSummary = true) {
  const summary: InvoicePaymentPresentation = {
    state: state as InvoicePaymentPresentation['state'],
    applied_amount: status === 'paid' ? '100.00' : '0.00',
    balance_due: status === 'cancelled' || state === 'unknown' ? null : status === 'paid' ? '0.00' : '100.00',
    pending_amount: null, basis: 'legacy_payments', note: null,
  }
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/invoices/history-1') return { data: {
      id: 'history-1', repair_order_id: 'archived-order', source, status,
      invoice_number: 'HIST-1', order_number: 'RO-HIST-1', vehicle_info: 'Sample truck',
      subtotal: '100.00', total_amount: '100.00', shop_supplies_amount: '0.00',
      service_fee_amount: '0.00', tax_amount: '0.00', discount_amount: '0.00',
      payment_summary: includeSummary ? summary : null, review_url: 'https://example.com/review',
    } }
    if (url.includes('/settlement')) throw new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, undefined, {
      status: 404, statusText: 'Not Found', data: { detail: 'Invoice not found' }, headers: {}, config: {} as never,
    })
    return { data: {} }
  })
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MemoryRouter initialEntries={['/portal/invoices/history-1']}><Routes>
      <Route path="/portal/invoices/:invoiceId" element={<CustomerInvoicePage />} />
    </Routes></MemoryRouter>
  </QueryClientProvider>)
}

beforeEach(() => { mocks.get.mockReset(); mocks.post.mockReset() })

describe('historical customer invoices', () => {
  it.each(['paid', 'sent', 'cancelled'])('shows %s imported invoice as a readable record without payment requests', async status => {
    renderInvoice(status)
    expect(await screen.findByRole('heading', { name: 'Historical invoice' })).toBeInTheDocument()
    expect(screen.getByText(/This imported invoice is read-only/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Invoice PDF' })).toHaveAttribute('href', '/api/v1/invoices/history-1/pdf')
    expect(screen.getByRole('link', { name: 'Leave a review' })).toHaveAttribute('href', 'https://example.com/review')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Invoice not found')).not.toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Payment method' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /pay|zelle|card/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/Receipt emailed instantly|No card fee with Zelle/)).not.toBeInTheDocument()
    expect(mocks.get.mock.calls.map(([url]) => url)).toEqual(['/invoices/history-1'])
    expect(mocks.post).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(status === 'cancelled' ? 'Cancelled' : status === 'paid' ? '$0.00' : '$100.00')
    expect(screen.queryByText('Labor / Services')).not.toBeInTheDocument()
  })

  it('preserves unknown historical balance without inventing zero', async () => {
    renderInvoice('sent', 'easy_truck_shop_import', 'unknown')
    await screen.findByRole('heading', { name: 'Historical invoice' })
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Unavailable')
    expect(mocks.get.mock.calls.map(([url]) => url)).toEqual(['/invoices/history-1'])
  })

  it('labels an older response without balance evidence as the recorded invoice total', async () => {
    renderInvoice('sent', 'easy_truck_shop_import', 'unpaid', false)
    await screen.findByRole('heading', { name: 'Historical invoice' })
    expect(screen.getByText('Invoice total (recorded)')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('$100.00')
    expect(screen.queryByText('Balance due')).not.toBeInTheDocument()
    expect(mocks.get.mock.calls.map(([url]) => url)).toEqual(['/invoices/history-1'])
  })

  it.each([null, 'native'])('retains the payment-control error for non-imported source %s', async source => {
    renderInvoice('sent', source)
    expect(await screen.findByRole('alert')).toHaveTextContent('Invoice not found')
    expect(screen.queryByRole('heading', { name: 'Historical invoice' })).not.toBeInTheDocument()
    await waitFor(() => expect(mocks.get).toHaveBeenCalledWith('/payments/invoices/history-1/settlement'))
    expect(mocks.post).not.toHaveBeenCalled()
  })
})
