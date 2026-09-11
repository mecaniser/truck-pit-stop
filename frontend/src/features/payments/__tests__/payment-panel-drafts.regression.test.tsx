import { useState } from 'react'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import InvoiceChargeControls from '../InvoiceChargeControls'
import SettlementPaymentPanel from '../SettlementPaymentPanel'
import PendingManualPaymentPanel from '../PendingManualPaymentPanel'
import type { InvoiceSettlementSummary, PaymentQuote, PaymentRail } from '../types'

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }))
afterEach(() => vi.unstubAllGlobals())

// Regression: ISSUE-001..004: partial amounts reset, opaque limits, negative
// amounts silently became positive, and evidence leaked between payment drafts.
// Found by /qa on 2026-09-11.
// Report: .gstack/qa-reports/qa-report-payment-panel-2026-09-11.md
const api = vi.hoisted(() => ({ fetchPaymentQuote: vi.fn(), adjustInvoiceCharges: vi.fn(), createPaymentAttempt: vi.fn(), confirmPaymentAttempt: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), ...api }))
const initial = (): InvoiceSettlementSummary => ({
  ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
  card_provider: 'quickbooks_payments', principal_total: '1160.49', allocatable_balance: '1160.49', outstanding_balance: '1160.49',
  allowed_actions: { create_attempt: true, confirm_cash: true, rails: ['card', 'zelle', 'check', 'ach', 'fleet_payment'] },
  breakdown: { subtotal: '1048.05', discount_amount: '0.00', shop_supplies_amount: '24.00', sales_tax_amount: '88.44', principal_total: '1160.49' },
  charge_controls: { tax_exempt: false, shop_supplies_enabled: true, card_fee_enabled: true, can_adjust: true, unavailable_reason: null, support_reference: null, original_shop_supplies_amount: '24.00', original_tax_amount: '88.44', original_card_fee_amount: '34.81' },
})
let active: InvoiceSettlementSummary
const quoteFor = (_id: string, rail: PaymentRail, amount: string, version: number): PaymentQuote => {
  const fee = rail === 'card' && active.charge_controls?.card_fee_enabled ? Math.round(Number(amount) * 3) / 100 : 0
  const tax = active.charge_controls?.tax_exempt ? 0 : Math.round(fee * 8.25) / 100
  return { settlement_version: version, rail, principal_amount: amount, card_fee_amount: fee.toFixed(2), card_fee_tax_amount: tax.toFixed(2), total_amount: (Number(amount) + fee + tax).toFixed(2) }
}
function show(audience: 'staff' | 'customer' | 'guest' = 'staff') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Harness() {
    const [summary, setSummary] = useState(active)
    const [blocked, setBlocked] = useState(false)
    const [cashSelected, selectCash] = useState(false)
    const payment = (controls?: Parameters<typeof SettlementPaymentPanel>[0]['chargeControls']) => <SettlementPaymentPanel
      access={audience === 'guest' ? { kind: 'guest', token: 'fixture-token' } : { kind: 'authenticated', invoiceId: summary.invoice_id }}
      summary={summary} audience={audience} tone="light" onUpdated={setSummary} chargeControls={controls}
      submissionBlockedReason={blocked ? 'Saving charges' : undefined}
      cashTender={audience === 'staff' ? { allowed: true, selected: cashSelected, pending: false, select: selectCash, confirmation: <button>Confirm full cash</button> } : undefined} />
    return <><output aria-label="Current invoice">{summary.invoice_id}</output><button onClick={() => { active = { ...active, version: active.version + 1 }; setSummary(active) }}>Version refresh</button>
      <button onClick={() => { active = { ...initial(), invoice_id: 'invoice-B' }; setSummary(active) }}>Another invoice</button>
      {audience === 'staff' ? <InvoiceChargeControls summary={summary} invoiceId={summary.invoice_id} onUpdated={setSummary} onEditingChange={setBlocked}>{payment}</InvoiceChargeControls> : payment()}
    </>
  }
  return render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>)
}
const amountInput = () => screen.getByRole('textbox', { name: 'Amount applied to invoice' })
const collect = () => within(screen.getByRole('region', { name: 'Payment breakdown' })).getByText('Amount to collect').nextElementSibling!
const proceed = () => screen.getByRole('button', { name: 'Continue to QBO Payments' })
async function enterPartial(value: string) {
  await userEvent.click(screen.getByRole('button', { name: 'Pay partial amount' }))
  await userEvent.clear(amountInput())
  if (value) await userEvent.type(amountInput(), value)
}

describe('Payment panel explicit drafts and fee refresh', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    active = initial()
    api.fetchPaymentQuote.mockImplementation(async (...args: Parameters<typeof quoteFor>) => quoteFor(...args))
    api.adjustInvoiceCharges.mockImplementation(async (_id, body) => {
      const supplies = body.shop_supplies_enabled ? 24 : 0
      const tax = body.tax_exempt ? 0 : Math.round((1048.05 + supplies) * (88.44 / 1072.05) * 100) / 100
      const total = (1048.05 + supplies + tax).toFixed(2)
      active = { ...active, version: active.version + 1, principal_total: total, outstanding_balance: total, allocatable_balance: total,
        breakdown: { ...active.breakdown!, shop_supplies_amount: supplies.toFixed(2), sales_tax_amount: tax.toFixed(2), principal_total: total },
        charge_controls: { ...active.charge_controls!, ...body },
      }
      return active
    })
  })

  it.each(['Shop supplies', 'Sales tax', 'Card processing fee'])('preserves500 and its exact submitted principal through %s off/on', async label => {
    show()
    await enterPartial('500')
    await waitFor(() => expect(proceed()).toBeEnabled())
    const input = amountInput()
    const row = screen.getByText('This payment toward invoice').parentElement
    for (const checked of ['false', 'true']) {
      await userEvent.click(screen.getByRole('switch', { name: label, exact: true }))
      await waitFor(() => expect(proceed()).toBeEnabled())
      expect(amountInput()).toBe(input)
      expect(input).toHaveValue('500.00')
      expect(row?.isConnected).toBe(true)
      expect(screen.getByRole('button', { name: 'Pay full balance' })).toBeVisible()
      expect(screen.getByRole('switch', { name: label, exact: true })).toHaveAttribute('aria-checked', checked)
      expect(api.fetchPaymentQuote).toHaveBeenLastCalledWith(active.invoice_id, 'card', '500.00', active.version)
    }
    api.createPaymentAttempt.mockResolvedValue({ state: 'confirmed', rail: 'card', principal_amount: '500.00', settlement: { ...active, version: active.version + 1, allocatable_balance: '660.49', outstanding_balance: '660.49' } })
    await userEvent.click(proceed())
    expect(api.createPaymentAttempt).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ amount: '500.00', expected_settlement_version: active.version }), expect.any(String))
    await screen.findByRole('button', { name: 'Pay partial amount' })
    expect(screen.queryByRole('textbox', { name: 'Amount applied to invoice' })).not.toBeInTheDocument()
  })

  it('full mode follows updated balance, but explicit full-sized partial does not silently shrink', async () => {
    show()
    await userEvent.click(screen.getByRole('switch', { name: 'Shop supplies', exact: true }))
    await waitFor(() => expect(proceed()).toBeEnabled())
    expect(api.fetchPaymentQuote).toHaveBeenLastCalledWith(active.invoice_id, 'card', '1134.51', active.version)
    await enterPartial('1134.51')
    await userEvent.click(screen.getByRole('switch', { name: 'Sales tax', exact: true }))
    await waitFor(() => expect(active.allocatable_balance).toBe('1048.05'))
    expect(amountInput()).toHaveValue('1134.51')
    expect(proceed()).toBeDisabled()
    expect(collect()).toHaveTextContent('—')
    await userEvent.click(screen.getByRole('button', { name: 'Pay full balance' }))
    await waitFor(() => expect(proceed()).toBeEnabled())
    expect(api.fetchPaymentQuote).toHaveBeenLastCalledWith(active.invoice_id, 'card', '1048.05', active.version)
  })

  it.each(['', '0', '6000', '1.234', '-50'])('retains invalid draft %j after a fee update and never authorizes payment', async value => {
    show()
    await enterPartial(value)
    await userEvent.click(screen.getByRole('switch', { name: 'Shop supplies', exact: true }))
    await waitFor(() => expect(screen.getByRole('switch', { name: 'Shop supplies', exact: true })).toBeEnabled())
    expect(amountInput()).toHaveValue(value === '0' || value === '6000' ? `${value}.00` : value)
    expect(proceed()).toBeDisabled()
    expect(collect()).toHaveTextContent('—')
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it.each(['0.01', '1160.49'])('accepts inclusive boundary %s and explains excessive amounts', async value => {
    show()
    await enterPartial(value)
    await waitFor(() => expect(proceed()).toBeEnabled())
    await userEvent.clear(amountInput())
    await userEvent.type(amountInput(), '6000')
    expect(screen.getByText('Enter at least $0.01 and no more than $1,160.49, the amount available to pay.')).toBeVisible()
    expect(amountInput()).toHaveAttribute('aria-invalid', 'true')
    expect(proceed()).toBeDisabled()
    expect(collect()).toHaveTextContent('—')
  })

  it('retains partial intent across version refresh, Zelle, cash full-only and return', async () => {
    show()
    await enterPartial('500')
    await userEvent.click(screen.getByRole('button', { name: 'Version refresh' }))
    expect(amountInput()).toHaveValue('500.00')
    await userEvent.click(screen.getByRole('radio', { name: 'Zelle', exact: true }))
    expect(amountInput()).toHaveValue('500.00')
    await userEvent.click(screen.getByRole('radio', { name: 'Cash', exact: true }))
    expect(screen.queryByRole('textbox', { name: 'Amount applied to invoice' })).not.toBeInTheDocument()
    await waitFor(() => expect(collect()).toHaveTextContent('$1,160.49'))
    await userEvent.click(screen.getByRole('radio', { name: 'QBO Payments', exact: true }))
    expect(amountInput()).toHaveValue('500.00')
    await waitFor(() => expect(collect()).toHaveTextContent('$516.24'))
  })

  it('blocks stale and failed quotes while preserving partial amount and retries the same amount', async () => {
    show()
    await enterPartial('500')
    await waitFor(() => expect(proceed()).toBeEnabled())
    let resolve!: (q: PaymentQuote) => void
    api.fetchPaymentQuote.mockReturnValue(new Promise<PaymentQuote>(yes => { resolve = yes }))
    await userEvent.click(screen.getByRole('switch', { name: 'Card processing fee', exact: true }))
    await waitFor(() => expect(api.fetchPaymentQuote).toHaveBeenLastCalledWith(active.invoice_id, 'card', '500.00', 2))
    expect(proceed()).toBeDisabled()
    expect(amountInput()).toHaveValue('500.00')
    await act(async () => resolve(quoteFor(active.invoice_id, 'card', '500.00', 1)))
    expect(proceed()).toBeDisabled()
    api.fetchPaymentQuote.mockRejectedValue(new Error('offline'))
    await userEvent.click(screen.getByRole('button', { name: 'Version refresh' }))
    await screen.findByRole('button', { name: 'Retry payment total' })
    expect(amountInput()).toHaveValue('500.00')
    api.fetchPaymentQuote.mockImplementation(async (...args: Parameters<typeof quoteFor>) => quoteFor(...args))
    await userEvent.click(screen.getByRole('button', { name: 'Retry payment total' }))
    await waitFor(() => expect(proceed()).toBeEnabled())
    expect(api.fetchPaymentQuote).toHaveBeenLastCalledWith(active.invoice_id, 'card', '500.00', 3)
  })

  it('keeps manual trace evidence scoped to tender and Fleet provider without losing amount', async () => {
    show()
    await enterPartial('500')
    await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Check', exact: true }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Check number' }), 'CHECK-123')
    await userEvent.type(screen.getByRole('textbox', { name: 'Verification note (optional)' }), 'check note')
    await userEvent.click(screen.getByRole('radio', { name: 'Zelle', exact: true }))
    expect(screen.getByRole('textbox', { name: 'Zelle transaction reference' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'Verification note (optional)' })).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Record Zelle' })).toBeDisabled()
    expect(amountInput()).toHaveValue('500.00')
    await userEvent.click(screen.getByRole('radio', { name: 'Fleet Check / Code', exact: true }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Instrument / code reference' }), 'EFS-123')
    await userEvent.type(screen.getByRole('textbox', { name: 'Approval reference (optional)' }), 'EFS-APPROVAL')
    await userEvent.click(screen.getByRole('button', { name: /^Fleet provider/ }))
    await userEvent.click(screen.getByRole('option', { name: 'Comchek' }))
    expect(screen.getByRole('textbox', { name: 'Instrument / code reference' })).toHaveValue('')
    expect(screen.getByRole('textbox', { name: 'Approval reference (optional)' })).toHaveValue('')
    expect(amountInput()).toHaveValue('500.00')
  })

  it.each(['staff', 'customer', 'guest'] as const)('does not reuse %s drafts on a different invoice with the same version and balance', async audience => {
    show(audience)
    if (audience === 'staff') await enterPartial('500')
    else { await userEvent.clear(amountInput()); await userEvent.type(amountInput(), '500') }
    await userEvent.click(screen.getByRole('radio', { name: /^Zelle/ }))
    if (audience !== 'staff') await userEvent.click(screen.getByRole('button', { name: 'Add transfer details (optional)' }))
    await userEvent.type(screen.getByRole('textbox', { name: /^Zelle transaction reference/ }), 'INVOICE-A-ONLY')
    await userEvent.click(screen.getByRole('button', { name: 'Another invoice' }))
    if (audience === 'staff') expect(screen.queryByRole('textbox', { name: 'Amount applied to invoice' })).not.toBeInTheDocument()
    else expect(amountInput()).toHaveValue('1160.49')
    await userEvent.click(screen.getByRole('radio', { name: /^Zelle/ }))
    if (audience !== 'staff') await userEvent.click(screen.getByRole('button', { name: 'Add transfer details (optional)' }))
    expect(screen.getByRole('textbox', { name: /^Zelle transaction reference/ })).toHaveValue('')
  })

  it.each(['zelle', 'fleet_payment'] as const)('freezes %s amount and evidence until preparation and confirmation finish', async rail => {
    show()
    await enterPartial('500')
    if (rail === 'fleet_payment') await userEvent.click(screen.getByRole('button', { name: 'More payment methods' }))
    await userEvent.click(screen.getByRole('radio', { name: rail === 'zelle' ? 'Zelle' : 'Fleet Check / Code', exact: true }))
    const reference = screen.getByRole('textbox', { name: rail === 'zelle' ? 'Zelle transaction reference' : 'Instrument / code reference' })
    await userEvent.type(reference, 'SUBMITTED-REF')
    await userEvent.type(screen.getByRole('textbox', { name: 'Verification note (optional)' }), 'Submitted note')
    let resolve!: (value: unknown) => void
    api.createPaymentAttempt.mockReturnValue(new Promise(yes => { resolve = yes }))
    const record = screen.getByRole('button', { name: rail === 'zelle' ? 'Record Zelle' : 'Record Fleet Check / Code' })
    await waitFor(() => expect(record).toBeEnabled())
    await userEvent.click(record)
    expect(amountInput()).toBeDisabled()
    expect(reference).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'Verification note (optional)' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'Sales tax', exact: true })).toBeDisabled()
    if (rail === 'fleet_payment') {
      expect(screen.getByRole('button', { name: /^Fleet provider/ })).toBeDisabled()
      expect(screen.getByRole('textbox', { name: 'Approval reference (optional)' })).toBeDisabled()
    }
    await userEvent.type(reference, 'CHANGED')
    const pending = { attempt_id: 'new-attempt', attempt_version: 1, state: 'pending', rail, principal_amount: '500.00', settlement: { ...active, version: 2, reserved_amount: '500.00', allocatable_balance: '660.49' } }
    await act(async () => resolve(pending))
    expect(screen.getByText('SUBMITTED-REF')).toBeVisible()
    api.confirmPaymentAttempt.mockReturnValue(new Promise(() => {}))
    await userEvent.click(screen.getByRole('button', { name: rail === 'zelle' ? 'Confirm Zelle received' : 'Confirm Fleet Check / Code received' }))
    expect(api.confirmPaymentAttempt).toHaveBeenCalledWith(expect.anything(), 'new-attempt', expect.objectContaining({ reference: 'SUBMITTED-REF', note: 'Submitted note', received_amount: '500.00' }), expect.any(String))
    expect(screen.getByRole('textbox', { name: /^Amount actually received/ })).toBeDisabled()
  })

  it.each(['create', 'confirm'])('ignores late %s completion in a different invoice panel', async stage => {
    show()
    const invoiceA = active
    await userEvent.click(screen.getByRole('radio', { name: 'Zelle', exact: true }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Zelle transaction reference' }), 'A-ONLY')
    const pending = { attempt_id: 'attempt-A', attempt_version: 1, state: 'pending', rail: 'zelle', principal_amount: '1160.49', settlement: { ...invoiceA, version: 2 } }
    let resolve!: (value: unknown) => void
    const delayed = new Promise(yes => { resolve = yes })
    api.createPaymentAttempt.mockReturnValue(stage === 'create' ? delayed : Promise.resolve(pending))
    api.confirmPaymentAttempt.mockReturnValue(delayed)
    const record = screen.getByRole('button', { name: 'Record Zelle' })
    await waitFor(() => expect(record).toBeEnabled())
    await userEvent.click(record)
    if (stage === 'confirm') await userEvent.click(await screen.findByRole('button', { name: 'Confirm Zelle received' }))
    await userEvent.click(screen.getByRole('button', { name: 'Another invoice' }))
    await act(async () => resolve({ ...pending, ...(stage === 'confirm' ? { state: 'confirmed' } : {}) }))
    expect(screen.getByLabelText('Current invoice')).toHaveTextContent('invoice-B')
    expect(screen.queryByText('A-ONLY')).not.toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'QBO Payments', exact: true })).toHaveAttribute('aria-checked', 'true')
  })

  it('applies the same negative-amount, pending-input and late-response safeguards to existing Zelle review', async () => {
    const fixture = DB048_SETTLEMENT_FIXTURES.pendingZelle500
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const updated = vi.fn()
    const ui = (invoiceId: string) => <QueryClientProvider client={client}><PendingManualPaymentPanel invoiceId={invoiceId}
      summary={{ ...fixture.summary, invoice_id: invoiceId, allowed_actions: { ...fixture.summary.allowed_actions, confirm_manual: true } }}
      allocations={[{ ...fixture.allocations[0], attempt_version: 3, sender_evidence: { reference: 'PORTAL-REF', note: 'Portal note' } }]}
      onUpdated={updated} /></QueryClientProvider>
    const view = render(ui('invoice-A'))
    const amount = screen.getByRole('textbox', { name: /^Amount actually received/ })
    await userEvent.clear(amount)
    await userEvent.type(amount, '-50')
    expect(amount).toHaveValue('-50')
    expect(screen.getByRole('button', { name: 'Confirm Zelle received' })).toBeDisabled()
    await userEvent.clear(amount)
    await userEvent.type(amount, '500')
    let resolve!: (value: unknown) => void
    api.confirmPaymentAttempt.mockReturnValue(new Promise(yes => { resolve = yes }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm Zelle received' }))
    for (const input of screen.getAllByRole('textbox')) expect(input).toBeDisabled()
    expect(api.confirmPaymentAttempt).toHaveBeenCalledWith({ kind: 'authenticated', invoiceId: 'invoice-A' }, fixture.allocations[0].attempt_id, expect.objectContaining({ received_amount: '500.00', reference: 'PORTAL-REF' }), expect.any(String))
    view.rerender(ui('invoice-B'))
    await act(async () => resolve({ settlement: { ...fixture.summary, invoice_id: 'invoice-A' } }))
    expect(updated).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Confirm Zelle received' })).toBeEnabled()
  })
})
