import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { InvoiceSettlementSummary } from '../types'

const fixture = vi.hoisted(() => ({ summary: null as InvoiceSettlementSummary | null }))
const paymentApi = vi.hoisted(() => ({ confirmFullCashPayment: vi.fn(), createPaymentAttempt: vi.fn(), fetchPaymentQuote: vi.fn() }))
vi.mock('../useInvoiceSettlement', () => ({
  useInvoiceSettlement: () => ({ data: fixture.summary, isLoading: false, error: null }),
  useInvoiceAllocations: () => ({ data: { items: [] } }),
}))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), ...paymentApi }))
vi.mock('../AccountingReconciliationPanel', () => ({ default: () => null }))
vi.mock('../PendingManualPaymentPanel', () => ({ default: () => null }))
vi.mock('../SettlementResolutionPanel', () => ({ default: () => null }))
vi.mock('../SettlementCreditPanel', () => ({ default: () => null }))
vi.mock('../EarlyVehicleReleasePanel', () => ({ default: () => null }))
vi.mock('@/lib/stripe', () => ({ getStripeForAccount: vi.fn() }))
import StaffSettlementDialog from '../StaffSettlementDialog'

const show = () => render(<QueryClientProvider client={new QueryClient()}>
  <StaffSettlementDialog invoiceId="invoice-834" invoiceNumber="Existing unpaid invoice" open onClose={vi.fn()} />
</QueryClientProvider>)

describe('Staff payment choice remains independent of historical export status', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
    fixture.summary = {
      ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
      card_provider: 'quickbooks_payments',
      accounting_sync_status: 'historical_export_hold',
      allowed_actions: { create_attempt: true, confirm_cash: true, rails: ['card', 'zelle', 'check', 'ach', 'fleet_payment'] },
    }
  })

  it('keeps tender selection available while editing exemption, but pauses financial submission', async () => {
    fixture.summary!.tax_exemption = { applied: false, can_apply: true, unavailable_reason: null,
      current_tax_amount: '20.12', removed_tax_amount: '0.00', exempt_principal_total: '204.50', reason: null, support_reference: null }
    show()
    await userEvent.click(screen.getByRole('switch', { name: 'Sales tax exemption' }))
    for (const tender of screen.getAllByRole('radio')) expect(tender).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Continue to QBO Payments' })).toBeDisabled()
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeDisabled()
    await userEvent.click(screen.getByRole('switch', { name: 'Sales tax exemption' }))
    for (const tender of screen.getAllByRole('radio')) expect(tender).toBeEnabled()
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeEnabled()
    expect(paymentApi.confirmFullCashPayment).not.toHaveBeenCalled()
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('offers cash alongside all admitted noncash choices, and restores them when cash is cancelled', async () => {
    show()
    for (const name of ['QBO Payments', 'Zelle', 'Cash']) {
      expect(screen.getByRole('radio', { name: new RegExp(`^${name}`) })).toBeEnabled()
    }
    const tenders = screen.getByRole('radiogroup', { name: 'Payment tender' })
    expect(within(tenders).getAllByRole('radio')).toHaveLength(3)
    expect(screen.queryByRole('radio', { name: /^Check/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    expect(screen.getByRole('radio', { name: 'Check' })).toBeEnabled()
    expect(screen.getByRole('radio', { name: 'ACH' })).toBeEnabled()
    expect(screen.getByRole('radio', { name: 'Fleet Check / Code' })).toBeEnabled()
    expect(screen.getByRole('radio', { name: 'Fleet Check / Code' })).toHaveTextContent(/^Fleet$/)
    expect(screen.getByRole('radio', { name: 'Fleet Check / Code' })).toHaveAttribute('title', 'Fleet Check / Code · EFS / MoneyCode, Comchek, T-Chek or other provider')
    const more = screen.getByRole('button', { name: 'More payment methods' })
    expect(tenders.compareDocumentPosition(more) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(more.compareDocumentPosition(screen.getByRole('button', { name: 'Pay partial amount' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await userEvent.keyboard('{Escape}')
    expect(within(tenders).getByRole('radio', { name: /Cash/ })).toBeEnabled()
    expect(screen.queryByRole('region', { name: 'Full cash payment' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: /Cash/ }))
    expect(screen.queryByLabelText('Amount applied to invoice')).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^QBO Payments/ })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('radio', { name: /^Cash/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeEnabled()
    await userEvent.click(screen.getByRole('radio', { name: /^QBO Payments/ }))
    expect(screen.queryByRole('button', { name: /Confirm .* cash received/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Amount applied to invoice')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pay partial amount' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^QBO Payments/ })).toBeEnabled()
    expect(screen.getByRole('radio', { name: /^Zelle/ })).toBeEnabled()
    expect(paymentApi.confirmFullCashPayment).not.toHaveBeenCalled()
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('keeps noncash choices available when only cash is ineligible', async () => {
    fixture.summary!.allowed_actions = { ...fixture.summary!.allowed_actions,
      confirm_cash: false, cash_unavailable_reason: 'Cash requires the full invoice with no existing payment activity.' }
    show()
    expect(screen.getByRole('radio', { name: /Cash/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /^QBO Payments/ })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    expect(screen.getByRole('radio', { name: 'ACH' })).toBeEnabled()
  })

  it('includes cash in arrow navigation without sending a payment', async () => {
    show()
    screen.getByRole('radio', { name: /^QBO Payments/ }).focus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(screen.getByRole('radio', { name: /^Cash/ })).toHaveFocus()
    expect(screen.getByRole('radio', { name: /^Cash/ })).toHaveAttribute('aria-checked', 'true')
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('radio', { name: /^QBO Payments/ })).toHaveFocus()
    expect(paymentApi.confirmFullCashPayment).not.toHaveBeenCalled()
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('keeps full-cash confirmation available inside the selector when noncash is blocked', async () => {
    fixture.summary!.allowed_actions = { confirm_cash: true, create_attempt: false, rails: [], payment_unavailable_reason: 'Review required.' }
    show()
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    expect(screen.getByRole('radio', { name: /^QBO Payments/ })).toBeDisabled()
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeEnabled()
    expect(screen.queryByLabelText('Amount applied to invoice')).not.toBeInTheDocument()
  })

  it('shows the authoritative breakdown and changes card fees to zero for noncard tenders without recording anything', async () => {
    fixture.summary!.breakdown = { subtotal: '800.00', discount_amount: '20.00', shop_supplies_amount: '20.00', sales_tax_amount: '34.00', principal_total: '834.00' }
    paymentApi.fetchPaymentQuote.mockImplementation(async (_id, rail, principal, version) => ({ settlement_version: version, rail, principal_amount: principal, card_fee_amount: rail === 'card' ? '25.02' : '0.00', card_fee_tax_amount: rail === 'card' ? '1.03' : '0.00', total_amount: rail === 'card' ? '860.05' : principal }))
    show()
    const breakdown = screen.getByRole('region', { name: 'Payment breakdown' })
    expect(within(breakdown).getByText('Services & parts')).toBeInTheDocument()
    expect(within(breakdown).getByText('Shop supplies')).toBeInTheDocument()
    expect(within(breakdown).getByText('Sales tax')).toBeInTheDocument()
    expect(within(breakdown).getByText('−$20.00')).toBeInTheDocument()
    await within(breakdown).findByText('$860.05')
    for (const tender of ['Zelle', 'Check', 'ACH', 'Cash']) {
      if (['Check', 'ACH'].includes(tender)) {
        if (screen.getByRole('button', { name: 'More payment methods' }).getAttribute('aria-expanded') === 'false') {
          await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
        }
        await userEvent.click(screen.getByRole('radio', { name: tender }))
      } else await userEvent.click(screen.getByRole('radio', { name: new RegExp(`^${tender}`) }))
      await waitFor(() => expect(within(breakdown).getByText('Amount to collect').nextElementSibling).toHaveTextContent('$834.00'))
      expect(within(breakdown).queryByText('Card processing fee')).not.toBeInTheDocument()
      expect(within(breakdown).queryByText('Tax on card fee')).not.toBeInTheDocument()
    }
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
    expect(paymentApi.confirmFullCashPayment).not.toHaveBeenCalled()
  })

  it('does not reuse a full-card quote while recalculating a partial payment or after quote failure', async () => {
    fixture.summary!.breakdown = { subtotal: '800.00', discount_amount: '0.00', shop_supplies_amount: '0.00', sales_tax_amount: '34.00', principal_total: '834.00' }
    paymentApi.fetchPaymentQuote.mockResolvedValueOnce({ settlement_version: 1, rail: 'card', principal_amount: '834.00', card_fee_amount: '25.02', card_fee_tax_amount: '1.03', total_amount: '860.05' })
    paymentApi.fetchPaymentQuote.mockRejectedValue(new Error('Offline'))
    show()
    await screen.findByText('$860.05')
    await userEvent.click(screen.getByRole('button', { name: 'Pay partial amount' }))
    const amount = screen.getByLabelText('Amount applied to invoice')
    await userEvent.clear(amount)
    await userEvent.type(amount, '100')
    await screen.findByText('Payment total could not be verified. Retry before continuing.')
    expect(screen.queryByText('$860.05')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue to QBO Payments' })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /^Zelle/ })).toBeEnabled()
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('prevents tender switching while cash confirmation is in flight', async () => {
    paymentApi.confirmFullCashPayment.mockReturnValue(new Promise(() => undefined))
    show()
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    for (const tender of screen.getAllByRole('radio')) expect(tender).toBeDisabled()
    expect(paymentApi.confirmFullCashPayment).toHaveBeenCalledTimes(1)
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it.each([
    ['Check', 'Check number'], ['ACH', 'Bank trace'], ['Fleet Check / Code', 'Instrument / code reference'],
  ])('hides %s on collapse without losing its draft or changing payment', async (method, referenceLabel) => {
    show()
    await userEvent.click(screen.getByRole('button', { name: 'Pay partial amount' }))
    await userEvent.clear(screen.getByLabelText('Amount applied to invoice'))
    await userEvent.type(screen.getByLabelText('Amount applied to invoice'), '50')
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    await userEvent.click(screen.getByRole('radio', { name: method, exact: true }))
    await userEvent.type(screen.getByLabelText(referenceLabel), 'SAVED-REF')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    expect(screen.queryByRole('radio', { name: method, exact: true })).not.toBeInTheDocument()
    expect(screen.getByLabelText(referenceLabel)).toHaveValue('SAVED-REF')
    expect(screen.getByLabelText('Amount applied to invoice')).toHaveValue('50.00')
    expect(screen.getByRole('radio', { name: 'QBO Payments' })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('radio', { name: 'QBO Payments' })).toHaveAttribute('aria-checked', 'false')
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    expect(screen.getAllByRole('radio')).toHaveLength(6)
    expect(screen.getByRole('radio', { name: method, exact: true })).toHaveAttribute('aria-checked', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    await userEvent.click(screen.getByRole('radio', { name: /^Zelle/ }))
    expect(screen.getAllByRole('radio')).toHaveLength(3)
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('hides duplicated unpaid metrics but retains meaningful paid and pending amounts', () => {
    const view = show()
    for (const label of ['Invoice total', 'Confirmed', 'Pending', 'Available to pay']) expect(screen.queryByText(label)).not.toBeInTheDocument()
    expect(screen.getByText('Balance due')).toBeInTheDocument()
    view.unmount()
    fixture.summary = { ...fixture.summary!, state: 'partially_paid_pending', confirmed_principal: '100.00', active_pending_principal: '50.00', outstanding_balance: '734.00', allocatable_balance: '684.00' }
    show()
    expect(screen.getByText('Paid toward invoice').nextElementSibling).toHaveTextContent('$100.00')
    expect(screen.getByText('Pending confirmation').nextElementSibling).toHaveTextContent('$50.00')
    expect(screen.getByText('Available to pay').nextElementSibling).toHaveTextContent('$684.00')
  })

  it('retains receipt identity when switching away and back after an uncertain response', async () => {
    paymentApi.confirmFullCashPayment.mockRejectedValue(new Error('Network unavailable'))
    show()
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    await screen.findByText('Cash confirmation was not verified. Retry to check the same receipt.')
    const firstKey = paymentApi.confirmFullCashPayment.mock.calls[0][2]
    await userEvent.click(screen.getByRole('radio', { name: /^QBO Payments/ }))
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    expect(paymentApi.confirmFullCashPayment.mock.calls[1][2]).toBe(firstKey)
    expect(screen.getByLabelText('Receipt note (optional)')).toBeDisabled()
  })
})
