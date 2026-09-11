import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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
    expect(screen.getByRole('button', { name: /Cash Full payment only Choose cash/ })).toBeEnabled()
    await userEvent.click(screen.getByText('Choose cash'))
    expect(screen.queryByLabelText('Amount applied to invoice')).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /^QuickBooks Payments/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Confirm .* cash received/ })).toBeEnabled()
    await userEvent.click(screen.getByText('Cancel'))
    expect(screen.getByRole('radio', { name: /^QuickBooks Payments/ })).toBeEnabled()
    expect(screen.getByRole('radio', { name: /^Zelle/ })).toBeEnabled()
    expect(paymentApi.confirmFullCashPayment).not.toHaveBeenCalled()
    expect(paymentApi.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('keeps noncash choices available when only cash is ineligible', () => {
    fixture.summary!.allowed_actions = { ...fixture.summary!.allowed_actions,
      confirm_cash: false, cash_unavailable_reason: 'Cash requires the full invoice with no existing payment activity.' }
    show()
    expect(screen.getByRole('button', { name: /Cash Full payment only Unavailable/ })).toBeDisabled()
    expect(screen.getByRole('radio', { name: /^QuickBooks Payments/ })).toBeEnabled()
    expect(screen.getByRole('radio', { name: /^ACH/ })).toBeEnabled()
  })
})
