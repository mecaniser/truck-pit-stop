import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { InvoiceSettlementSummary } from '../types'

const api = vi.hoisted(() => ({ applyInvoiceTaxExemption: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), ...api }))
import InvoiceTaxExemptionControl from '../InvoiceTaxExemptionControl'

const summary = (): InvoiceSettlementSummary => ({
  ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
  tax_exemption: { applied: false, can_apply: true, unavailable_reason: null,
    current_tax_amount: '20.12', removed_tax_amount: '0.00', exempt_principal_total: '204.50', reason: null, support_reference: null },
})
const updated = vi.fn()
const editing = vi.fn()
const show = (value = summary()) => render(<QueryClientProvider client={new QueryClient()}>
  <InvoiceTaxExemptionControl invoiceId={value.invoice_id} summary={value} onUpdated={updated} onEditingChange={editing} />
</QueryClientProvider>)
async function fill() {
  await userEvent.click(screen.getByRole('switch', { name: 'Sales tax exemption' }))
  await userEvent.click(screen.getByRole('button', { name: 'Add certificate/reference' }))
  await userEvent.type(screen.getByLabelText('Certificate or supporting reference (optional)'), 'CERT-001')
}
describe('Invoice exemption is explicit and independent of tender', () => {
  beforeEach(() => vi.clearAllMocks())
  it('does not expose an unsupported control on an older server', () => {
    show({ ...summary(), tax_exemption: undefined })
    expect(screen.queryByRole('region', { name: 'Invoice tax exemption' })).not.toBeInTheDocument()
  })
  it('reveals the optional reference on demand and toggles the draft off without mutation', async () => {
    show()
    await userEvent.click(screen.getByRole('switch', { name: 'Sales tax exemption' }))
    expect(screen.queryByLabelText('Exemption reason')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Certificate or supporting reference (optional)')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Add certificate/reference' }))
    expect(screen.getByLabelText('Certificate or supporting reference (optional)')).not.toBeRequired()
    expect(screen.getByRole('button', { name: 'Update invoice' })).toBeEnabled()
    expect(screen.queryByText(/Shop supplies stay unchanged/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('switch', { name: 'Sales tax exemption' }))
    expect(editing).toHaveBeenLastCalledWith(false)
    expect(api.applyInvoiceTaxExemption).not.toHaveBeenCalled()
  })
  it('submits the exact version and evidence, updates from server response, without recording payment', async () => {
    const next = { ...summary(), version: 2, principal_total: '204.50' }
    api.applyInvoiceTaxExemption.mockResolvedValue(next)
    show()
    await fill()
    await userEvent.click(screen.getByRole('button', { name: 'Update invoice' }))
    expect(api.applyInvoiceTaxExemption).toHaveBeenCalledWith(summary().invoice_id, {
      expected_settlement_version: summary().version, support_reference: 'CERT-001',
    }, expect.any(String))
    expect(updated).toHaveBeenCalledWith(next)
    expect(editing).toHaveBeenLastCalledWith(false)
  })
  it.each(['', '   '])('applies with a blank optional reference %j and sends no reason', async reference => {
    api.applyInvoiceTaxExemption.mockResolvedValue({ ...summary(), version: 2, principal_total: '204.50' })
    show()
    await userEvent.click(screen.getByRole('switch', { name: 'Sales tax exemption' }))
    if (reference) {
      await userEvent.click(screen.getByRole('button', { name: 'Add certificate/reference' }))
      await userEvent.type(screen.getByLabelText('Certificate or supporting reference (optional)'), reference)
    }
    await userEvent.click(screen.getByRole('button', { name: 'Update invoice' }))
    expect(api.applyInvoiceTaxExemption).toHaveBeenCalledWith(summary().invoice_id, {
      expected_settlement_version: summary().version, support_reference: null,
    }, expect.any(String))
    expect(updated).toHaveBeenCalledTimes(1)
  })
  it('retains request identity and evidence through an uncertain response', async () => {
    api.applyInvoiceTaxExemption.mockRejectedValue(new Error('Network lost'))
    show()
    await fill()
    await userEvent.click(screen.getByRole('button', { name: 'Update invoice' }))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Certificate or supporting reference (optional)')).toBeDisabled()
    const first = api.applyInvoiceTaxExemption.mock.calls[0]
    await userEvent.click(screen.getByRole('button', { name: 'Update invoice' }))
    expect(api.applyInvoiceTaxExemption.mock.calls[1]).toEqual(first)
  })
  it('disables apply for pending or ineligible invoices with the server reason', () => {
    const value = summary()
    value.tax_exemption!.can_apply = false
    value.tax_exemption!.unavailable_reason = 'Resolve the pending payment first.'
    show(value)
    expect(screen.getByRole('switch', { name: 'Sales tax exemption' })).toBeDisabled()
    expect(screen.getByText('Resolve the pending payment first.')).toBeInTheDocument()
  })
  it('allows retry after temporary invoice contention without a version change', async () => {
    const failure = new AxiosError('Busy')
    failure.response = { status: 409, data: { error: { code: 'invoice_busy', message: 'Invoice is busy. Retry.', retryable: true } }, statusText: 'Conflict', headers: {}, config: {} as never }
    api.applyInvoiceTaxExemption.mockRejectedValue(failure)
    show()
    await fill()
    await userEvent.click(screen.getByRole('button', { name: 'Update invoice' }))
    await screen.findByText('Invoice is busy. Retry.')
    expect(screen.getByRole('button', { name: 'Update invoice' })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: 'Update invoice' }))
    expect(api.applyInvoiceTaxExemption).toHaveBeenCalledTimes(2)
  })
  it('blocks stale-version resubmission until a refreshed version arrives', async () => {
    const failure = new AxiosError('Stale')
    failure.response = { status: 409, data: { error: { code: 'stale_settlement_version', message: 'Refresh the invoice.', current_version: 2 } }, statusText: 'Conflict', headers: {}, config: {} as never }
    api.applyInvoiceTaxExemption.mockRejectedValue(failure)
    show()
    await fill()
    await userEvent.click(screen.getByRole('button', { name: 'Update invoice' }))
    await screen.findByText('Refresh the invoice.')
    expect(screen.getByRole('button', { name: 'Update invoice' })).toBeDisabled()
  })
  it('displays applied evidence and offers no repeated reduction', () => {
    const value = summary()
    value.tax_exemption = { ...value.tax_exemption!, applied: true, can_apply: false, reason: 'Qualifying exemption', support_reference: 'CERT-001' }
    show(value)
    expect(screen.getByText('Tax exemption applied')).toBeInTheDocument()
    expect(screen.getByText('Reference: CERT-001')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
