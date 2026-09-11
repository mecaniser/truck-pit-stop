import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { InvoiceSettlementSummary } from '../types'

const fixture = vi.hoisted(() => ({ summary: null as InvoiceSettlementSummary | null }))
const paymentApi = vi.hoisted(() => ({ confirmFullCashPayment: vi.fn(), createPaymentAttempt: vi.fn() }))
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
    fixture.summary = {
      ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
      card_provider: 'quickbooks_payments',
      accounting_sync_status: 'historical_export_hold',
      allowed_actions: { create_attempt: true, confirm_cash: true, rails: ['card', 'zelle', 'check', 'ach'] },
    }
  })

  it('offers cash alongside all admitted noncash choices, and restores them when cash is cancelled', async () => {
    show()
    for (const name of ['QuickBooks Payments', 'Zelle', 'Check', 'ACH']) {
      expect(screen.getByRole('radio', { name: new RegExp(`^${name}`) })).toBeEnabled()
    }
    const tenders = screen.getByRole('radiogroup', { name: 'Payment tender' })
    expect(within(tenders).getAllByRole('radio')).toHaveLength(5)
    expect(within(tenders).getByRole('radio', { name: /Cash Full payment only/ })).toBeEnabled()
    expect(screen.queryByRole('region', { name: 'Full cash payment' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: /Cash Full payment only/ }))
    expect(screen.queryByLabelText('Amount applied to invoice')).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^QuickBooks Payments/ })).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByRole('radio', { name: /^Cash/ })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeEnabled()
    await userEvent.click(screen.getByRole('radio', { name: /^QuickBooks Payments/ }))
    expect(screen.queryByRole('button', { name: /Confirm .* cash received/ })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Amount applied to invoice')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^QuickBooks Payments/ })).toBeEnabled()
    expect(screen.getByRole('radio', { name: /^Zelle/ })).toBeEnabled()
    expect(paymentApi.confirmFullCashPayment).not.toHaveBeenCalled()
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('keeps noncash choices available when only cash is ineligible', () => {
    fixture.summary!.allowed_actions = { ...fixture.summary!.allowed_actions,
      confirm_cash: false, cash_unavailable_reason: 'Cash requires the full invoice with no existing payment activity.' }
    show()
    expect(screen.getByRole('radio', { name: /Cash Full payment only/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /^QuickBooks Payments/ })).toBeEnabled()
    expect(screen.getByRole('radio', { name: /^ACH/ })).toBeEnabled()
  })

  it('includes cash in arrow navigation without sending a payment', async () => {
    show()
    screen.getByRole('radio', { name: /^QuickBooks Payments/ }).focus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(screen.getByRole('radio', { name: /^Cash/ })).toHaveFocus()
    expect(screen.getByRole('radio', { name: /^Cash/ })).toHaveAttribute('aria-checked', 'true')
    await userEvent.keyboard('{ArrowRight}')
    expect(screen.getByRole('radio', { name: /^QuickBooks Payments/ })).toHaveFocus()
    expect(paymentApi.confirmFullCashPayment).not.toHaveBeenCalled()
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('keeps full-cash confirmation available inside the selector when noncash is blocked', async () => {
    fixture.summary!.allowed_actions = { confirm_cash: true, create_attempt: false, rails: [], payment_unavailable_reason: 'Review required.' }
    show()
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeEnabled()
    expect(screen.queryByLabelText('Amount applied to invoice')).not.toBeInTheDocument()
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

  it('retains receipt identity when switching away and back after an uncertain response', async () => {
    paymentApi.confirmFullCashPayment.mockRejectedValue(new Error('Network unavailable'))
    show()
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    await screen.findByText('Cash confirmation was not verified. Retry to check the same receipt.')
    const firstKey = paymentApi.confirmFullCashPayment.mock.calls[0][2]
    await userEvent.click(screen.getByRole('radio', { name: /^QuickBooks Payments/ }))
    await userEvent.click(screen.getByRole('radio', { name: /^Cash/ }))
    await userEvent.click(screen.getByRole('button', { name: /Confirm .* cash received/ }))
    expect(paymentApi.confirmFullCashPayment.mock.calls[1][2]).toBe(firstKey)
    expect(screen.getByLabelText('Receipt note (optional)')).toBeDisabled()
  })
})
