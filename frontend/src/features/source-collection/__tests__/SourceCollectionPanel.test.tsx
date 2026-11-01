import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ preview: vi.fn(), prepare: vi.fn(), activate: vi.fn() }))
vi.mock('../EtsReceiptTasks', () => ({ default: () => <div>Receipt reconciliation</div> }))
vi.mock('../BillingAccountPicker', () => ({ default: ({ onChange }: { onChange: (id: string) => void }) => <button onClick={() => onChange('portal-customer')}>Use existing DBN account</button> }))
vi.mock('../api', () => ({ previewSourceCollection: mocks.preview, prepareSourceCollection: mocks.prepare, activateSourceCollection: mocks.activate }))
import SourceCollectionPanel from '../SourceCollectionPanel'
import SourceCollectionSummary from '../SourceCollectionSummary'
import type { SourceCollectionSummary as Summary } from '../types'

const summary: Summary = {
  id: 'handoff', state: 'prepared', version: 1, source_invoice_number: '1687', source_service_number: '1821',
  original_issued_total: '1000.00', source_prior_allocated: '400.00', opening_principal: '600.00',
  native_invoice_id: null, balance_due: '600.00', native_confirmed_principal: '0.00', native_pending_principal: '0.00',
  source_observed_at: '2026-11-01T02:06:33Z', source_sync_state: 'current', accounting_state: 'external_reconciliation_pending', hold_reasons: [],
}
const preview = { eligibility: 'ready', hold_reasons: [], proposal: { source_invoice_number: '1687', opening_principal: '600.00', source_observed_at: summary.source_observed_at } }
beforeEach(() => vi.resetAllMocks())

describe('source debt collection review', () => {
  it('requires an explicit same-business review before preparing for a different portal account', async () => {
    const billTo = { required: true, source_customer_id: 'ets-customer', source_ets_customer_id: '97052', target_customer_id: 'portal-customer', source_legal_name: 'Example Fleet', target_legal_name: 'Example Fleet (DBN)', authorization_mode: null }
    mocks.preview.mockResolvedValue({ ...preview, eligibility: 'held', hold_reasons: ['bill_to_review_required'], bill_to_review: billTo })
    mocks.prepare.mockResolvedValue(summary)
    render(<SourceCollectionPanel sourceInvoiceId="source-1" customerId="ets-customer" />)
    fireEvent.click(screen.getByRole('button', { name: 'Choose billing account' }))
    fireEvent.click(screen.getByRole('button', { name: 'Use existing DBN account' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review collection' }))
    const prepare = await screen.findByRole('button', { name: 'Prepare collection copy' })
    expect(mocks.preview).toHaveBeenCalledWith('source-1', 'portal-customer')
    fireEvent.click(screen.getByRole('checkbox', { name: /DBN will collect/ }))
    expect(prepare).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: /These accounts represent the same legal business/ }))
    fireEvent.change(screen.getByLabelText('Confirmation reference'), { target: { value: 'Owner instruction November 1' } })
    fireEvent.change(screen.getByLabelText('Reason for linking these accounts'), { target: { value: 'Duplicate records for the same legal business' } })
    fireEvent.click(prepare)
    await screen.findByRole('button', { name: 'Create collection invoice' })
    expect(mocks.prepare.mock.calls[0][2]).toEqual({ mode: 'owner_same_legal_entity', source_customer_id: 'ets-customer', target_customer_id: 'portal-customer', attested_same_legal_entity: true, confirmation_reference: 'Owner instruction November 1', reason: 'Duplicate records for the same legal business' })
    expect(mocks.activate).not.toHaveBeenCalled()
  })

  it('does not let a billing review override a stale source balance', async () => {
    mocks.preview.mockResolvedValue({ ...preview, eligibility: 'held', hold_reasons: ['bill_to_review_required', 'source_stale'], bill_to_review: { required: true } })
    render(<SourceCollectionPanel sourceInvoiceId="source-1" customerId="ets-customer" />)
    fireEvent.click(screen.getByRole('button', { name: 'Review collection' }))
    await screen.findByText('Collection needs review')
    expect(screen.queryByRole('button', { name: 'Prepare collection copy' })).not.toBeInTheDocument()
    expect(mocks.prepare).not.toHaveBeenCalled()
  })

  it('requires primary collection acknowledgment and a separate activation; retains activation identity on uncertain retry', async () => {
    mocks.preview.mockResolvedValue(preview)
    mocks.prepare.mockResolvedValue(summary)
    mocks.activate.mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce({ handoff: { ...summary, state: 'active', native_invoice_id: 'native-1' } })
    render(<SourceCollectionPanel sourceInvoiceId="source-1" customerId="bill-to-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Review collection' }))
    const prepare = await screen.findByRole('button', { name: 'Prepare collection copy' })
    expect(prepare).toBeDisabled()
    expect(mocks.preview).toHaveBeenCalledWith('source-1', 'bill-to-1')
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(prepare)
    const activate = await screen.findByRole('button', { name: 'Create collection invoice' })
    expect(mocks.activate).not.toHaveBeenCalled()
    fireEvent.click(activate)
    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Create collection invoice' }))
    await screen.findByRole('link', { name: 'View invoice PDF' })
    expect(mocks.activate.mock.calls[0][2]).toBe(mocks.activate.mock.calls[1][2])
    expect(screen.queryByRole('button', { name: 'Create collection invoice' })).not.toBeInTheDocument()
  })

  it('never prepares a held source or invents a zero collectible amount', async () => {
    mocks.preview.mockResolvedValue({ eligibility: 'held', proposal: null, hold_reasons: ['source_stale'] })
    render(<SourceCollectionPanel sourceInvoiceId="source-1" customerId="bill-to-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Review collection' }))
    await screen.findByText('Collection needs review')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    expect(mocks.prepare).not.toHaveBeenCalled()
  })

  it('keeps a confirmed DBN payment distinct from the pending ETS update', () => {
    render(<SourceCollectionSummary summary={{ ...summary, state: 'closed', balance_due: '0.00', source_sync_state: 'ets_update_pending', native_confirmed_principal: '600.00' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Payment recorded in DBN · ETS update pending')
    expect(screen.getByText('Paid before transfer').nextElementSibling).toHaveTextContent('$400.00')
    expect(screen.queryByText(/Pay the remaining/)).not.toBeInTheDocument()
  })

  it('does not display linked-account payment details in restricted original history', () => {
    render(<SourceCollectionSummary summary={{ ...summary, is_source_history: true, restricted_history: true, native_invoice_id: 'other-account-invoice', balance_due: '0.00', native_confirmed_principal: '600.00', source_sync_state: 'ets_update_pending' }} originalInvoiceHref="/portal/invoices/other-account-invoice" />)
    expect(screen.getByRole('heading', { name: 'ETS invoice 1687 · historical record' })).toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    expect(screen.queryByText(/ETS update pending/)).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
