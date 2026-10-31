import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import InvoicePaymentSummary from '../InvoicePaymentSummary'
import { currentInvoicePaymentSummary } from '@/lib/invoicePaymentPresentation'
import type { InvoiceSettlementSummary } from '@/features/payments/types'
import type { InvoicePaymentPresentation } from '@/types'
const base: InvoicePaymentPresentation = { state: 'partially_paid', applied_amount: '400.00', balance_due: '600.00', pending_amount: null, note: null, basis: 'settlement' }
describe('invoice payment versions', () => {
  it('distinguishes applied and outstanding amounts', () => {
    render(<InvoicePaymentSummary summary={base} />)
    expect(screen.getByRole('heading', { name: 'Partially paid' })).toBeInTheDocument()
    expect(screen.getByText('$400.00')).toBeInTheDocument()
    expect(screen.getByText('$600.00')).toBeInTheDocument()
  })
  it('keeps pending money separate from the balance', () => {
    render(<InvoicePaymentSummary summary={{...base,state:'payment_pending',applied_amount:'0.00',balance_due:'1000.00',pending_amount:'400.00'}} />)
    expect(screen.getByText('Awaiting confirmation')).toBeInTheDocument()
    expect(screen.getByText('$1,000.00')).toBeInTheDocument()
  })
  it('preserves unknown rather than displaying zero', () => {
    render(<InvoicePaymentSummary summary={{...base,state:'unknown',applied_amount:null,balance_due:null}} />)
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })
  it('does not claim a payable balance for cancelled invoices', () => {
    render(<InvoicePaymentSummary summary={{...base,state:'cancelled',applied_amount:null,balance_due:null}} />)
    expect(screen.queryByText('Balance due')).not.toBeInTheDocument()
  })
  it('labels verified cash receipts', () => {
    render(<InvoicePaymentSummary summary={{...base,state:'paid',basis:'cash_receipt',applied_amount:'252.70',balance_due:'0.00'}} />)
    expect(screen.getByText('Cash received')).toBeInTheDocument()
    expect(screen.getByText('$252.70')).toBeInTheDocument()
    expect(screen.getByText('$0.00')).toBeInTheDocument()
  })
})

 it('uses one current settlement authority after a payment refresh', () => {
   const current = { feature_enabled: true, outstanding_balance: '200.00', confirmed_principal: '800.00', active_pending_principal: '0.00' } as InvoiceSettlementSummary
   const chosen = currentInvoicePaymentSummary(base, current)!
   expect(chosen.balance_due).toBe('200.00')
   expect(chosen.applied_amount).toBe('800.00')
   expect(chosen.state).toBe('partially_paid')
 })

it('preserves fee disclosures and unknown historical tender when settlement refreshes', () => {
  const saved = { ...base, state: 'paid' as const, applied_amount: null, balance_due: '0.00', basis: 'status_only', note: 'Balance excludes optional card processing fees; final payment quote shows applicable fees.' }
  const settlement = { feature_enabled: true, outstanding_balance: '0.00', confirmed_principal: '1000.00', active_pending_principal: '0.00' } as InvoiceSettlementSummary
  const chosen = currentInvoicePaymentSummary(saved, settlement)!
  expect(chosen.applied_amount).toBeNull()
  expect(chosen.note).toContain('optional card processing fees')
})
