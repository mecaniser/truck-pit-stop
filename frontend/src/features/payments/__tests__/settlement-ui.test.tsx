import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError } from 'axios'

import { DB048_PROVIDER_READINESS, DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'

const paymentApi = vi.hoisted(() => ({
  createPaymentAttempt: vi.fn(),
  chargeQuickBooksPaymentAttempt: vi.fn(),
  confirmPaymentAttempt: vi.fn(),
  fetchCardProviderReadiness: vi.fn(),
  fetchCustomerCreditAging: vi.fn(),
  downloadCustomerCreditAging: vi.fn(),
  fetchAccountingReconciliation: vi.fn(),
  retryAccountingOperation: vi.fn(),
  fetchEligibleCustomerCredits: vi.fn(),
  applyEligibleCustomerCredit: vi.fn(),
  recordOverpaymentCreditConsent: vi.fn(),
  confirmManualRefund: vi.fn(),
  retryPaymentRefund: vi.fn(),
  authorizeEarlyVehicleRelease: vi.fn(),
  fetchSettlement: vi.fn(),
  updateCardProvider: vi.fn(),
}))

vi.mock('../api', async importOriginal => {
  const original = await importOriginal<typeof import('../api')>()
  return { ...original, ...paymentApi, createIdempotencyKey: () => 'test-idempotency-key' }
})

vi.mock('@/lib/stripe', () => ({ getStripeForAccount: vi.fn() }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import CardProviderSettingsCard from '../CardProviderSettingsCard'
import AccountingReconciliationPanel from '../AccountingReconciliationPanel'
import CustomerCreditAgingCard from '../CustomerCreditAgingCard'
import EarlyVehicleReleasePanel from '../EarlyVehicleReleasePanel'
import SettlementPaymentPanel from '../SettlementPaymentPanel'
import PendingManualPaymentPanel from '../PendingManualPaymentPanel'
import SettlementCreditPanel from '../SettlementCreditPanel'
import SettlementResolutionPanel from '../SettlementResolutionPanel'
import SettlementSummaryCard from '../SettlementSummaryCard'
import { isSettlementUnavailable } from '../api'
import { formatMoney, isValidPrincipalAmount, normalizeMoney } from '../money'

const renderWithQuery = (ui: React.ReactNode) => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('DB-048 exact money helpers', () => {
  it('normalizes cents without floating point arithmetic', () => {
    expect(normalizeMoney('334')).toBe('334.00')
    expect(normalizeMoney('334.1')).toBe('334.10')
    expect(normalizeMoney('334.009')).toBeNull()
    expect(formatMoney('1234567.89')).toBe('$1,234,567.89')
    expect(isValidPrincipalAmount('334.00', '334.00')).toBe(true)
    expect(isValidPrincipalAmount('334.01', '334.00')).toBe(false)
  })
})

describe('DB-048 compatibility fallback', () => {
  const responseError = (status: number, code: string, message: string) => {
    const error = new AxiosError(message)
    error.response = {
      status,
      statusText: 'Error',
      headers: {},
      config: error.config!,
      data: { error: { code, message, retryable: false } },
    }
    return error
  }

  it('falls back only for the default-off gate, not a structured inaccessible-invoice 404', () => {
    expect(isSettlementUnavailable(responseError(409, 'split_payments_disabled', 'Partial payments are disabled.'))).toBe(true)
    expect(isSettlementUnavailable(responseError(404, 'invoice_not_found', 'Invoice not found.'))).toBe(false)
  })
})

describe('SettlementSummaryCard', () => {
  it('separates confirmed, pending, and card-eligible remainder', () => {
    const fixture = DB048_SETTLEMENT_FIXTURES.pendingZelle500
    render(<SettlementSummaryCard summary={fixture.summary} allocations={fixture.allocations} tone="light" />)
    expect(screen.getByText('Payment pending')).toBeInTheDocument()
    expect(screen.getByText('Outstanding')).toBeInTheDocument()
    expect(screen.getByText('Available to pay')).toBeInTheDocument()
    expect(screen.getByText('$334.00')).toBeInTheDocument()
    expect(screen.getAllByText('$834.00')).toHaveLength(2)
    expect(screen.getAllByText('$500.00')).toHaveLength(2)
    expect(screen.getByText((_, node) => node?.textContent === 'Zelle · pending')).toBeInTheDocument()
  })

  it('shows refund resolution without calling excess revenue', () => {
    render(<SettlementSummaryCard summary={DB048_SETTLEMENT_FIXTURES.automaticRefundPending.summary} tone="light" />)
    expect(screen.getByText(/\$75.00 refund pending/i)).toBeInTheDocument()
    expect(screen.getByText(/overpayment resolution/i)).toBeInTheDocument()
  })
})

describe('SettlementPaymentPanel', () => {
  beforeEach(() => {
    paymentApi.createPaymentAttempt.mockReset()
    paymentApi.confirmPaymentAttempt.mockReset()
  })

  it('offers only backend-allowed customer rails and reserves an exact Zelle amount', async () => {
    const user = userEvent.setup()
    const fixture = DB048_SETTLEMENT_FIXTURES.pendingZelle500
    paymentApi.createPaymentAttempt.mockResolvedValue({
      attempt_id: 'attempt-zelle',
      invoice_id: fixture.summary.invoice_id,
      principal_amount: '334.00',
      card_fee_amount: '0.00',
      card_fee_tax_amount: '0.00',
      provider_charge_amount: '334.00',
      state: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      rail: 'zelle',
      provider: 'manual',
      provider_configuration_version: 2,
      attempt_version: 1,
      settlement: { ...fixture.summary, active_pending_principal: '834.00', allocatable_balance: '0.00', version: 3 },
    })
    renderWithQuery(
      <SettlementPaymentPanel
        access={{ kind: 'authenticated', invoiceId: fixture.summary.invoice_id }}
        summary={fixture.summary}
        audience="customer"
        tone="light"
        zelleRecipient={{ display: 'pay@example.com', memo: 'INV-48' }}
        onUpdated={vi.fn()}
      />,
    )
    expect(screen.queryByRole('radio', { name: /check/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: /ach/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: /zelle/i }))
    await user.click(screen.getByRole('button', { name: /reserve zelle amount/i }))
    expect(paymentApi.createPaymentAttempt).toHaveBeenCalledWith(
      { kind: 'authenticated', invoiceId: fixture.summary.invoice_id },
      expect.objectContaining({ amount: '334.00', rail: 'zelle', expected_settlement_version: 2 }),
      'test-idempotency-key',
    )
    expect(await screen.findByText('Zelle amount reserved')).toBeInTheDocument()
    expect(screen.getByText('pay@example.com')).toBeInTheDocument()
    expect(screen.getByText('INV-48')).toBeInTheDocument()
  })

  it('keeps the remaining balance payable after a partial Zelle reservation', async () => {
    const user = userEvent.setup()
    const summary = DB048_SETTLEMENT_FIXTURES.unpaid.summary
    paymentApi.createPaymentAttempt.mockResolvedValue({
      attempt_id: 'attempt-zelle-partial',
      invoice_id: summary.invoice_id,
      principal_amount: '500.00',
      card_fee_amount: '0.00',
      card_fee_tax_amount: '0.00',
      provider_charge_amount: '500.00',
      state: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      rail: 'zelle',
      provider: 'manual',
      provider_configuration_version: 2,
      attempt_version: 1,
      settlement: {
        ...summary,
        active_pending_principal: '500.00',
        allocatable_balance: '334.00',
        state: 'payment_pending',
        version: 2,
      },
    })

    function PartialZelleHarness() {
      const [current, setCurrent] = useState(summary)
      return (
        <SettlementPaymentPanel
          access={{ kind: 'authenticated', invoiceId: current.invoice_id }}
          summary={current}
          audience="customer"
          tone="light"
          zelleRecipient={{ display: 'pay@example.com', memo: 'INV-48' }}
          onUpdated={setCurrent}
        />
      )
    }

    renderWithQuery(<PartialZelleHarness />)
    await user.click(screen.getByRole('radio', { name: /zelle/i }))
    const amount = screen.getByLabelText(/amount applied/i)
    await user.clear(amount)
    await user.type(amount, '500')
    await user.click(screen.getByRole('button', { name: /reserve zelle amount/i }))

    const continueButton = await screen.findByRole('button', { name: /make another payment.*\$334\.00 available/i })
    await user.click(continueButton)
    expect(screen.getByRole('heading', { name: /choose an amount and tender/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/amount applied/i)).toHaveValue('334.00')
  })

  it('requires staff evidence and never offers cash or fleet payment', async () => {
    const user = userEvent.setup()
    const summary = {
      ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
      allowed_actions: { create_attempt: true, confirm_manual: true, rails: ['card', 'zelle', 'check', 'ach'] },
    }
    paymentApi.createPaymentAttempt.mockResolvedValue({
      attempt_id: 'attempt-check', invoice_id: summary.invoice_id, principal_amount: '200.00', card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: '200.00', rail: 'check', provider: 'manual', state: 'pending', expires_at: null, provider_configuration_version: 2, attempt_version: 1, settlement: summary,
    })
    paymentApi.confirmPaymentAttempt.mockResolvedValue({
      attempt_id: 'attempt-check', invoice_id: summary.invoice_id, principal_amount: '200.00', card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: '200.00', rail: 'check', provider: 'manual', state: 'confirmed', expires_at: null, provider_configuration_version: 2, attempt_version: 2, settlement: { ...summary, confirmed_principal: '200.00', outstanding_balance: '634.00', allocatable_balance: '634.00', state: 'partially_paid' },
    })
    renderWithQuery(<SettlementPaymentPanel access={{ kind: 'authenticated', invoiceId: summary.invoice_id }} summary={summary} audience="staff" tone="light" onUpdated={vi.fn()} />)
    expect(screen.queryByText(/cash/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/fleet/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('radio', { name: /check/i }))
    const submit = screen.getByRole('button', { name: /record check/i })
    expect(submit).toBeDisabled()
    const amount = screen.getByLabelText(/amount applied/i)
    await user.clear(amount)
    await user.type(amount, '200')
    await user.type(screen.getByLabelText(/check number/i), 'CHK-884')
    expect(submit).toBeEnabled()
    await user.click(submit)
    const confirm = await screen.findByRole('button', { name: /confirm check received/i })
    const received = screen.getByLabelText(/amount actually received/i)
    await user.clear(received)
    await user.type(received, '225')
    await user.click(confirm)
    expect(paymentApi.confirmPaymentAttempt).toHaveBeenCalledWith(
      { kind: 'authenticated', invoiceId: summary.invoice_id },
      'attempt-check',
      expect.objectContaining({ expected_attempt_version: 1, reference: 'CHK-884', received_amount: '225.00' }),
      'test-idempotency-key',
    )
  })

  it('routes a QuickBooks card attempt into direct Intuit tokenization', async () => {
    const user = userEvent.setup()
    const summary = {
      ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
      card_provider: 'quickbooks_payments' as const,
      card_provider_status: 'ready' as const,
      allowed_actions: { create_attempt: true, rails: ['card'] as const },
    }
    paymentApi.createPaymentAttempt.mockResolvedValue({
      attempt_id: 'attempt-qbp',
      invoice_id: summary.invoice_id,
      principal_amount: '834.00',
      card_fee_amount: '25.02',
      card_fee_tax_amount: '0.00',
      provider_charge_amount: '859.02',
      rail: 'card',
      provider: 'quickbooks_payments',
      state: 'pending',
      expires_at: null,
      provider_configuration_version: 3,
      attempt_version: 1,
      provider_token_url: 'https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens',
      settlement: summary,
    })
    renderWithQuery(
      <SettlementPaymentPanel
        access={{ kind: 'authenticated', invoiceId: summary.invoice_id }}
        summary={summary}
        audience="customer"
        tone="light"
        onUpdated={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /continue to quickbooks payments/i }))
    expect(await screen.findByRole('heading', { name: /complete secure card payment/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/name on card/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /pay \$859\.02 with card/i })).toBeInTheDocument()
  })

  it('keeps the QuickBooks form visible when the attempt reserves the full remaining balance', async () => {
    const user = userEvent.setup()
    const initial = {
      ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
      card_provider: 'quickbooks_payments' as const,
      card_provider_status: 'ready' as const,
      allowed_actions: { create_attempt: true, rails: ['card'] as const },
    }
    const reserved = {
      ...initial,
      active_pending_principal: initial.allocatable_balance,
      allocatable_balance: '0.00',
      state: 'payment_pending' as const,
      allowed_actions: { create_attempt: false, rails: [] as const },
    }
    paymentApi.createPaymentAttempt.mockResolvedValue({
      attempt_id: 'attempt-qbp-full-balance',
      invoice_id: initial.invoice_id,
      principal_amount: initial.allocatable_balance,
      card_fee_amount: '25.02',
      card_fee_tax_amount: '0.00',
      provider_charge_amount: '859.02',
      rail: 'card',
      provider: 'quickbooks_payments',
      state: 'pending',
      expires_at: null,
      provider_configuration_version: 3,
      attempt_version: 1,
      provider_token_url: 'https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens',
      settlement: reserved,
    })

    function FullBalanceHarness() {
      const [summary, setSummary] = useState(initial)
      return (
        <SettlementPaymentPanel
          access={{ kind: 'authenticated', invoiceId: summary.invoice_id }}
          summary={summary}
          audience="staff"
          tone="light"
          onUpdated={setSummary}
        />
      )
    }

    renderWithQuery(<FullBalanceHarness />)
    await user.click(screen.getByRole('button', { name: /continue to quickbooks payments/i }))
    expect(await screen.findByRole('heading', { name: /complete secure card payment/i })).toBeInTheDocument()
    expect(screen.queryByText(/no new payment can be started/i)).not.toBeInTheDocument()
  })
})

describe('PendingManualPaymentPanel', () => {
  it('confirms an existing customer Zelle reservation with independently verified received amount', async () => {
    const user = userEvent.setup()
    const fixture = DB048_SETTLEMENT_FIXTURES.pendingZelle500
    const allocation = { ...fixture.allocations[0], attempt_version: 3 }
    const summary = { ...fixture.summary, allowed_actions: { confirm_manual: true, create_attempt: true, rails: ['card', 'zelle', 'check', 'ach'] as const } }
    paymentApi.confirmPaymentAttempt.mockResolvedValue({
      attempt_id: allocation.attempt_id,
      invoice_id: summary.invoice_id,
      principal_amount: allocation.principal_amount,
      card_fee_amount: '0.00',
      card_fee_tax_amount: '0.00',
      provider_charge_amount: '525.00',
      rail: 'zelle',
      provider: 'manual',
      state: 'confirmed',
      expires_at: allocation.expires_at,
      provider_configuration_version: 2,
      attempt_version: 4,
      settlement: { ...summary, confirmed_principal: '500.00', active_pending_principal: '0.00', outstanding_balance: '334.00', allocatable_balance: '334.00', state: 'partially_paid' },
    })
    renderWithQuery(
      <PendingManualPaymentPanel
        invoiceId={summary.invoice_id}
        summary={summary}
        allocations={[allocation]}
        onUpdated={vi.fn()}
      />,
    )
    const amount = screen.getByLabelText(/amount actually received/i)
    await user.clear(amount)
    await user.type(amount, '525')
    await user.type(screen.getByLabelText(/transaction reference/i), 'ZELLE-525')
    await user.click(screen.getByRole('button', { name: /confirm zelle received/i }))
    expect(paymentApi.confirmPaymentAttempt).toHaveBeenCalledWith(
      { kind: 'authenticated', invoiceId: summary.invoice_id },
      allocation.attempt_id,
      expect.objectContaining({ expected_attempt_version: 3, received_amount: '525.00', reference: 'ZELLE-525' }),
      'test-idempotency-key',
    )
  })
})

describe('CardProviderSettingsCard', () => {
  it('does not switch routing until the scoped verification callback grants authorization', async () => {
    const user = userEvent.setup()
    const readiness = {
      ...DB048_PROVIDER_READINESS,
      quickbooks_payments: { approved: true, tenant_ready: true, status: 'ready' as const },
    }
    paymentApi.fetchCardProviderReadiness.mockResolvedValue(readiness)
    paymentApi.updateCardProvider.mockResolvedValue({ ...readiness, selected_provider: 'quickbooks_payments' })
    const requestVerification = vi.fn()
    renderWithQuery(<CardProviderSettingsCard requestVerification={requestVerification} />)
    await user.click(await screen.findByRole('radio', { name: /quickbooks payments/i }))
    await user.click(screen.getByRole('button', { name: /use quickbooks for new attempts/i }))
    expect(requestVerification).toHaveBeenCalledTimes(1)
    expect(paymentApi.updateCardProvider).not.toHaveBeenCalled()
    act(() => requestVerification.mock.calls[0][0]('scoped-manage-grant'))
    await waitFor(() => expect(paymentApi.updateCardProvider).toHaveBeenCalledWith(
      'quickbooks_payments', readiness, expect.any(String), 'scoped-manage-grant',
    ))
  })

  it('only offers ready providers and omits an unapproved alternative from routing', async () => {
    paymentApi.fetchCardProviderReadiness.mockResolvedValue(DB048_PROVIDER_READINESS)
    renderWithQuery(<CardProviderSettingsCard requestVerification={vi.fn()} />)
    expect(await screen.findByRole('radio', { name: /stripe connect/i })).toBeChecked()
    expect(screen.queryByRole('radio', { name: /quickbooks payments/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(1)
  })

  it('shows active QuickBooks first without offering unconfigured Stripe', async () => {
    paymentApi.fetchCardProviderReadiness.mockResolvedValue({
      ...DB048_PROVIDER_READINESS,
      selected_provider: 'quickbooks_payments',
      stripe_connect: { ...DB048_PROVIDER_READINESS.stripe_connect, status: 'not_configured' },
      quickbooks_payments: { approved: true, tenant_ready: true, status: 'ready' },
    })
    renderWithQuery(<CardProviderSettingsCard requestVerification={vi.fn()} />)
    const active = await screen.findByRole('radio', { name: /quickbooks payments active for invoice payments/i })
    expect(active).toBeChecked()
    expect(active).toHaveAttribute('data-state', 'active')
    expect(screen.queryByRole('radio', { name: /stripe/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /use .* for new attempts/i })).not.toBeInTheDocument()
  })

  it('retains a selected unavailable provider as a warning, never active green', async () => {
    paymentApi.fetchCardProviderReadiness.mockResolvedValue({
      ...DB048_PROVIDER_READINESS,
      selected_provider: 'quickbooks_payments',
    })
    renderWithQuery(<CardProviderSettingsCard requestVerification={vi.fn()} />)
    const selected = await screen.findByRole('radio', { name: /quickbooks payments/i })
    expect(selected).toBeChecked()
    expect(selected).toBeDisabled()
    expect(selected).toHaveAttribute('data-state', 'unavailable')
    expect(screen.getByText(/external intuit approval pending/i)).toBeInTheDocument()
    expect(screen.queryByText('Active for invoice payments')).not.toBeInTheDocument()
  })

  it('keeps the saved provider active while distinguishing unsaved selection', async () => {
    const user = userEvent.setup()
    paymentApi.fetchCardProviderReadiness.mockResolvedValue({
      ...DB048_PROVIDER_READINESS,
      quickbooks_payments: { approved: true, tenant_ready: true, status: 'ready' },
    })
    renderWithQuery(<CardProviderSettingsCard requestVerification={vi.fn()} />)
    await user.click(await screen.findByRole('radio', { name: /quickbooks payments/i }))
    expect(screen.getByRole('radio', { name: /quickbooks payments/i })).toHaveAttribute('data-state', 'pending')
    expect(screen.getByRole('radio', { name: /stripe connect/i })).toHaveAttribute('data-state', 'active')
    expect(screen.getByText('Selected — save to activate')).toBeInTheDocument()
  })

  it('does not imply activation when the feature is off or allow a read-only change', async () => {
    paymentApi.fetchCardProviderReadiness.mockResolvedValue({
      ...DB048_PROVIDER_READINESS,
      feature_enabled: false,
      allowed_actions: { configure_provider: false },
    })
    renderWithQuery(<CardProviderSettingsCard requestVerification={vi.fn()} />)
    const selected = await screen.findByRole('radio', { name: /stripe connect/i })
    expect(selected).toBeDisabled()
    expect(selected).not.toHaveAttribute('data-state', 'active')
    expect(screen.queryByText('Active for invoice payments')).not.toBeInTheDocument()
  })

  it('allows an approved payment-scoped sandbox connection to be selected', async () => {
    const user = userEvent.setup()
    paymentApi.fetchCardProviderReadiness.mockResolvedValue({
      ...DB048_PROVIDER_READINESS,
      quickbooks_payments: { approved: true, tenant_ready: true, status: 'ready' },
    })
    renderWithQuery(<CardProviderSettingsCard requestVerification={vi.fn()} />)
    const option = await screen.findByRole('radio', { name: /quickbooks payments/i })
    expect(option).toBeEnabled()
    await user.click(option)
    expect(screen.getByRole('button', { name: /use quickbooks for new attempts/i })).toBeEnabled()
  })
})

describe('CustomerCreditAgingCard', () => {
  it('keeps consented customer money separate from revenue and reports its age', async () => {
    paymentApi.fetchCustomerCreditAging.mockResolvedValue([
      {
        credit_id: 'credit-1',
        customer_id: 'customer-1',
        customer_name: 'North Star Logistics',
        origin_amount: '50.00',
        remaining_amount: '25.00',
        issued_at: '2026-07-01T12:00:00Z',
        age_days: 60,
        consent_channel: 'customer_portal',
        consent_note: 'Use on next repair',
        disposition: 'available',
      },
      {
        credit_id: 'credit-2',
        customer_id: 'customer-2',
        customer_name: 'Elis Logistics',
        origin_amount: '50.00',
        remaining_amount: '50.00',
        issued_at: '2026-08-10T12:00:00Z',
        age_days: 20,
        consent_channel: 'in_person',
        consent_note: 'Customer requested credit',
        disposition: 'available',
      },
    ])
    renderWithQuery(<CustomerCreditAgingCard />)
    expect(await screen.findByText('North Star Logistics')).toBeInTheDocument()
    expect(screen.getByText('$75.00')).toBeInTheDocument()
    expect(screen.getByText('60 days')).toBeInTheDocument()
    expect(screen.getByText(/not revenue and has no arbitrary expiration/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /export csv/i })).toBeEnabled()
  })
})

describe('AccountingReconciliationPanel', () => {
  it('keeps a locally recorded payment visible and lets an authorized manager retry only the failed accounting operation', async () => {
    const user = userEvent.setup()
    paymentApi.fetchAccountingReconciliation.mockResolvedValue({
      invoice_id: 'invoice-834',
      state: 'failed',
      pending_operations: 0,
      failed_operations: 1,
      synced_operations: 1,
      links: [
        { id: 'accounting-link-1', type: 'invoice_payment', state: 'failed', error: 'QuickBooks temporarily unavailable' },
      ],
    })
    paymentApi.retryAccountingOperation.mockResolvedValue({ operation_id: 'accounting-link-1', state: 'pending' })
    renderWithQuery(<AccountingReconciliationPanel invoiceId="invoice-834" canRetry />)
    expect(await screen.findByText(/DieselBridge payment remains recorded/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /retry sync/i }))
    expect(paymentApi.retryAccountingOperation).toHaveBeenCalledWith('accounting-link-1', 'test-idempotency-key')
  })
})

describe('EarlyVehicleReleasePanel', () => {
  it('requires an owner/admin reason and preserves the unpaid balance', async () => {
    const user = userEvent.setup()
    const summary = {
      ...DB048_SETTLEMENT_FIXTURES.futureCreditApplied.summary,
      allowed_actions: { authorize_early_release: true },
    }
    paymentApi.authorizeEarlyVehicleRelease.mockResolvedValue({
      ...summary,
      version: summary.version + 1,
    })
    renderWithQuery(
      <EarlyVehicleReleasePanel
        invoiceId={summary.invoice_id}
        summary={summary}
        onUpdated={vi.fn()}
      />,
    )
    expect(screen.getByText(/does not close the invoice or reduce QuickBooks A\/R/i)).toBeInTheDocument()
    const submit = screen.getByRole('button', { name: /authorize vehicle release/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/release reason/i), 'Fleet needs the truck for an emergency route.')
    await user.click(submit)
    expect(paymentApi.authorizeEarlyVehicleRelease).toHaveBeenCalledWith(
      summary.invoice_id,
      summary.version,
      'Fleet needs the truck for an emergency route.',
      'test-idempotency-key',
    )
  })
})

describe('Settlement credit and overpayment resolution', () => {
  it('applies only the currently payable amount from a consented same-customer credit', async () => {
    const user = userEvent.setup()
    const summary = {
      ...DB048_SETTLEMENT_FIXTURES.futureCreditApplied.summary,
      allocatable_balance: '25.00',
      allowed_actions: { apply_customer_credit: true, create_attempt: true, rails: ['card', 'zelle'] as const },
    }
    paymentApi.fetchEligibleCustomerCredits.mockResolvedValue([
      { credit_id: 'credit-50', origin_amount: '50.00', remaining_amount: '50.00', issued_at: '2026-08-01T12:00:00Z', consent_channel: 'customer_portal' },
    ])
    paymentApi.applyEligibleCustomerCredit.mockResolvedValue({ application_id: 'application-25', settlement: { ...summary, confirmed_principal: '125.00', outstanding_balance: '709.00', allocatable_balance: '0.00', state: 'partially_paid' } })
    renderWithQuery(<SettlementCreditPanel access={{ kind: 'authenticated', invoiceId: summary.invoice_id }} summary={summary} onUpdated={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: 'Apply $25.00' }))
    expect(paymentApi.applyEligibleCustomerCredit).toHaveBeenCalledWith(
      { kind: 'authenticated', invoiceId: summary.invoice_id },
      'credit-50',
      '25.00',
      summary.version,
      'test-idempotency-key',
    )
  })

  it('requires an external reference before a manager can confirm a manual overpayment refund', async () => {
    const user = userEvent.setup()
    const fixture = DB048_SETTLEMENT_FIXTURES.manualOverpaymentDecision
    paymentApi.confirmManualRefund.mockResolvedValue({ refund_id: 'refund-ach-50', state: 'succeeded' })
    paymentApi.fetchSettlement.mockResolvedValue({ ...fixture.summary, unapplied_credit: '0.00', refund_pending: '0.00', state: 'paid' })
    renderWithQuery(
      <SettlementResolutionPanel
        access={{ kind: 'authenticated', invoiceId: fixture.summary.invoice_id }}
        summary={fixture.summary}
        allocations={fixture.allocations}
        audience="staff"
        onUpdated={vi.fn()}
      />,
    )
    const confirm = screen.getByRole('button', { name: /confirm refund completed/i })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText(/refund transaction or check reference/i), 'REFUND-ACH-50')
    await user.click(confirm)
    expect(paymentApi.confirmManualRefund).toHaveBeenCalledWith('refund-ach-50', 'REFUND-ACH-50', 'test-idempotency-key')
  })

  it('queues a safe retry when an automatic card overpayment refund failed', async () => {
    const user = userEvent.setup()
    const fixture = DB048_SETTLEMENT_FIXTURES.automaticRefundPending
    const failedAllocation = {
      ...fixture.allocations[0],
      refund_state: 'failed',
    }
    paymentApi.retryPaymentRefund.mockResolvedValue({ refund_id: failedAllocation.refund_id, state: 'pending' })
    paymentApi.fetchSettlement.mockResolvedValue(fixture.summary)
    renderWithQuery(
      <SettlementResolutionPanel
        access={{ kind: 'authenticated', invoiceId: fixture.summary.invoice_id }}
        summary={{ ...fixture.summary, allowed_actions: { resolve_overpayment: true } }}
        allocations={[failedAllocation]}
        audience="staff"
        onUpdated={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /retry card refund/i }))
    expect(paymentApi.retryPaymentRefund).toHaveBeenCalledWith(failedAllocation.refund_id, 'test-idempotency-key')
  })

  it('records explicit per-event guest consent before retaining an overpayment as credit', async () => {
    const user = userEvent.setup()
    const fixture = DB048_SETTLEMENT_FIXTURES.manualOverpaymentDecision
    paymentApi.recordOverpaymentCreditConsent.mockResolvedValue({ credit_id: 'credit-ach-50', state: 'available', amount: '50.00' })
    paymentApi.fetchSettlement.mockResolvedValue({
      ...fixture.summary,
      unapplied_credit: '0.00',
      refund_pending: '0.00',
      state: 'paid',
    })
    renderWithQuery(
      <SettlementResolutionPanel
        access={{ kind: 'guest', token: 'signed-invoice-token', invoiceId: fixture.summary.invoice_id }}
        summary={fixture.summary}
        allocations={fixture.allocations}
        audience="guest"
        onUpdated={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /confirm refund completed/i })).not.toBeInTheDocument()
    await user.type(screen.getByLabelText(/customer consent note/i), 'Please keep this for my next repair.')
    await user.click(screen.getByRole('button', { name: /keep as customer credit/i }))
    expect(paymentApi.recordOverpaymentCreditConsent).toHaveBeenCalledWith(
      { kind: 'guest', token: 'signed-invoice-token', invoiceId: fixture.summary.invoice_id },
      'overpayment-ach-50',
      'guest_token',
      'Please keep this for my next repair.',
      'test-idempotency-key',
    )
  })

  it('renders every unresolved overpayment instead of collapsing them into one decision', () => {
    const fixture = DB048_SETTLEMENT_FIXTURES.manualOverpaymentDecision
    const second = {
      ...fixture.allocations[0],
      id: 'allocation-check-15',
      attempt_id: 'attempt-check-15',
      unapplied_amount: '15.00',
      overpayment_id: 'overpayment-check-15',
      refund_id: 'refund-check-15',
    }
    renderWithQuery(
      <SettlementResolutionPanel
        access={{ kind: 'authenticated', invoiceId: fixture.summary.invoice_id }}
        summary={fixture.summary}
        allocations={[...fixture.allocations, second]}
        audience="staff"
        onUpdated={vi.fn()}
      />,
    )
    expect(screen.getByRole('heading', { name: /resolve \$50\.00 customer overpayment/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /resolve \$15\.00 customer overpayment/i })).toBeInTheDocument()
  })

  it('shows a blocking credit-verification error instead of silently hiding the credit ledger', async () => {
    paymentApi.fetchEligibleCustomerCredits.mockRejectedValue(new Error('offline'))
    const summary = {
      ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
      allowed_actions: { apply_customer_credit: true },
    }
    renderWithQuery(
      <SettlementCreditPanel
        access={{ kind: 'authenticated', invoiceId: summary.invoice_id }}
        summary={summary}
        onUpdated={vi.fn()}
      />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(/customer credit could not be verified/i)
  })
})
