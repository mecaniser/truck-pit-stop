import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { InvoiceSettlementSummary } from '../types'

const confirmCash = vi.hoisted(() => vi.fn())
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), confirmFullCashPayment: confirmCash }))
import FullCashPaymentPanel from '../FullCashPaymentPanel'
import SettlementSummaryCard from '../SettlementSummaryCard'

const eligible: InvoiceSettlementSummary = {
  ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
  allowed_actions: { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary.allowed_actions, confirm_cash: true },
}
const paid: InvoiceSettlementSummary = { ...eligible, state: 'paid', accounting_sync_status: 'not_applicable_local_cash', outstanding_balance: '0.00' }
const show = (summary = eligible, onUpdated = vi.fn()) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <FullCashPaymentPanel invoiceId={summary.invoice_id} summary={summary} onUpdated={onUpdated} onChoosingChange={vi.fn()} />
  </QueryClientProvider>,
)

describe('Staff full-cash confirmation', () => {
  beforeEach(() => vi.resetAllMocks())

  it('does not expose cash with an older summary or after payment', () => {
    const view = show(DB048_SETTLEMENT_FIXTURES.unpaid.summary)
    expect(screen.queryByRole('region', { name: 'Full cash payment' })).not.toBeInTheDocument()
    view.unmount()
    show(paid)
    expect(screen.queryByText('Choose cash')).not.toBeInTheDocument()
  })

  it('shows the server reason instead of allowing an unsafe cash confirmation', () => {
    show({ ...eligible, allowed_actions: { ...eligible.allowed_actions, confirm_cash: false, cash_unavailable_reason: 'This invoice has already been exported to QuickBooks.' } })
    expect(screen.getByText(/already been exported/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cash/ })).toBeDisabled()
    expect(confirmCash).not.toHaveBeenCalled()
  })

  it('never offers cash using another invoice’s stale summary during navigation', () => {
    render(<QueryClientProvider client={new QueryClient()}><FullCashPaymentPanel invoiceId="different-invoice" summary={eligible} onUpdated={vi.fn()} onChoosingChange={vi.fn()} /></QueryClientProvider>)
    expect(screen.queryByText('Choose cash')).not.toBeInTheDocument()
  })

  it('requires receipt confirmation and sends no client amount or accounting policy', async () => {
    const updated = vi.fn()
    confirmCash.mockResolvedValue({ payment_id: 'receipt', settlement: paid })
    show(eligible, updated)
    await userEvent.click(screen.getByText('Choose cash'))
    expect(confirmCash).not.toHaveBeenCalled()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Receipt note (optional)'), 'Desk receipt 41')
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    await waitFor(() => expect(updated).toHaveBeenCalledWith(paid))
    expect(confirmCash.mock.calls[0][1]).toEqual({ expected_settlement_version: eligible.version, note: 'Desk receipt 41' })
    expect(confirmCash.mock.calls[0][0]).toBe(eligible.invoice_id)
  })

  it('blocks repeated clicks while pending and reuses the receipt key after uncertainty', async () => {
    let reject!: (error: Error) => void
    confirmCash.mockImplementationOnce(() => new Promise((_, failure) => { reject = failure }))
    const updated = vi.fn()
    show(eligible, updated)
    await userEvent.click(screen.getByText('Choose cash'))
    await userEvent.dblClick(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    expect(confirmCash).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Recording cash…' })).toBeDisabled()
    await act(async () => reject(new Error('network unavailable')))
    expect(updated).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toBeInTheDocument()
    confirmCash.mockResolvedValue({ payment_id: 'receipt', settlement: paid })
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    expect(confirmCash.mock.calls[1][2]).toBe(confirmCash.mock.calls[0][2])
  })

  it('does not update a different screen after unmount', async () => {
    let resolve!: (result: unknown) => void
    confirmCash.mockImplementation(() => new Promise(success => { resolve = success }))
    const updated = vi.fn()
    const view = show(eligible, updated)
    await userEvent.click(screen.getByText('Choose cash'))
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    view.unmount()
    await act(async () => resolve({ payment_id: 'receipt', settlement: paid }))
    expect(updated).not.toHaveBeenCalled()
  })

  it('refreshes and prevents confirmation against a definitively rejected stale version', async () => {
    const failure = new AxiosError('stale')
    failure.response = { status: 409, statusText: 'Conflict', headers: {}, config: {} as never,
      data: { error: { code: 'stale_settlement_version', message: 'Invoice changed.', current_version: eligible.version + 1 } } }
    confirmCash.mockRejectedValue(failure)
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const updated = vi.fn()
    const panel = (summary: InvoiceSettlementSummary) => <QueryClientProvider client={client}><FullCashPaymentPanel invoiceId={summary.invoice_id} summary={summary} onUpdated={updated} onChoosingChange={vi.fn()} /></QueryClientProvider>
    const view = render(panel(eligible))
    await userEvent.click(screen.getByText('Choose cash'))
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['invoice-settlement', 'authenticated', eligible.invoice_id] })
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeDisabled()
    expect(updated).not.toHaveBeenCalled()
    view.rerender(panel({ ...eligible, version: eligible.version + 1 }))
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeEnabled()
    confirmCash.mockResolvedValue({ payment_id: 'receipt', settlement: paid })
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    expect(confirmCash.mock.calls[1][1].expected_settlement_version).toBe(eligible.version + 1)
    expect(confirmCash.mock.calls[1][2]).not.toBe(confirmCash.mock.calls[0][2])
  })

  it('labels local cash as paid without a false QuickBooks error', () => {
    render(<SettlementSummaryCard summary={paid} />)
    expect(screen.getByText('Paid in cash')).toBeInTheDocument()
    expect(screen.getByText('Cash recorded locally. Not synced to QuickBooks.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
