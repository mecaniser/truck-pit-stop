import { useState } from 'react'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import InvoiceChargeControls from '../InvoiceChargeControls'
import SettlementPaymentPanel from '../SettlementPaymentPanel'
import type { InvoiceSettlementSummary, PaymentQuote } from '../types'

const api = vi.hoisted(() => ({ fetchPaymentQuote: vi.fn(), adjustInvoiceCharges: vi.fn(), createPaymentAttempt: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), ...api }))

const initial = (): InvoiceSettlementSummary => ({
  ...DB048_SETTLEMENT_FIXTURES.unpaid.summary,
  card_provider: 'quickbooks_payments',
  principal_total: '1160.49', allocatable_balance: '1160.49', outstanding_balance: '1160.49',
  breakdown: { subtotal: '1048.05', discount_amount: '0.00', shop_supplies_amount: '24.00', sales_tax_amount: '88.44', principal_total: '1160.49' },
  charge_controls: { tax_exempt: false, shop_supplies_enabled: true, card_fee_enabled: true, can_adjust: true, unavailable_reason: null, support_reference: null, original_shop_supplies_amount: '24.00', original_tax_amount: '88.44', original_card_fee_amount: '34.81' },
})
const originalQuote: PaymentQuote = { settlement_version: 1, rail: 'card', principal_amount: '1160.49', card_fee_amount: '34.81', card_fee_tax_amount: '2.87', total_amount: '1198.17' }
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function show() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Harness() {
    const [summary, setSummary] = useState(initial())
    const [editing, setEditing] = useState(false)
    return <><button onClick={() => setSummary({ ...initial(), invoice_id: 'another-invoice' })}>Another invoice</button>
      <InvoiceChargeControls summary={summary} invoiceId={summary.invoice_id} onUpdated={setSummary} onEditingChange={setEditing}>
        {chargeControls => <SettlementPaymentPanel access={{ kind: 'authenticated', invoiceId: summary.invoice_id }} summary={summary} audience="staff" tone="light" onUpdated={setSummary}
        submissionBlockedReason={editing ? 'Finish saving invoice changes before recording payment.' : undefined}
        chargeControls={chargeControls} />}
      </InvoiceChargeControls>
    </>
  }
  return render(<QueryClientProvider client={client}><Harness /></QueryClientProvider>)
}
const row = (label: string) => within(screen.getByRole('region', { name: 'Payment breakdown' })).getByText(label).parentElement!

describe('Stable invoice charge layout', () => {
  beforeEach(() => { vi.resetAllMocks(); api.fetchPaymentQuote.mockResolvedValue(originalQuote) })

  it.each(['Sales tax', 'Shop supplies', 'Card processing fee'])('keeps every breakdown row mounted through %s save and quote refresh', async label => {
    const save = deferred<InvoiceSettlementSummary>()
    const refresh = deferred<PaymentQuote>()
    api.adjustInvoiceCharges.mockReturnValue(save.promise)
    show()
    await screen.findByText('$1,198.17')
    const labels = ['Services & parts', 'Shop supplies', 'Sales tax', 'Card processing fee', 'Tax on card fee', 'Amount to collect']
    const rows = labels.map(row)
    const button = screen.getByRole('button', { name: 'Continue to QBO Payments' })
    expect(screen.queryByRole('region', { name: 'Invoice charges' })).not.toBeInTheDocument()
    const toggles = screen.getAllByRole('switch')
    for (const toggle of toggles) expect(row(toggle.getAttribute('aria-label')!)).toContainElement(toggle)
    await userEvent.click(screen.getByRole('switch', { name: label }))
    expect(button).toBeDisabled()
    expect(rows.every(node => node.isConnected)).toBe(true)
    expect(toggles.every(node => node.isConnected)).toBe(true)
    expect(screen.getByText('Updating invoice…')).toHaveClass('sr-only')
    api.fetchPaymentQuote.mockReturnValue(refresh.promise)
    const principal = label === 'Sales tax' ? '1072.05' : label === 'Shop supplies' ? '1134.51' : '1160.49'
    const fee = label === 'Card processing fee' ? '0.00' : label === 'Sales tax' ? '32.16' : '34.04'
    const feeTax = label === 'Shop supplies' ? '2.81' : '0.00'
    const total = label === 'Card processing fee' ? '1160.49' : label === 'Sales tax' ? '1104.21' : '1171.36'
    const next = { ...initial(), version: 2, principal_total: principal, allocatable_balance: principal, outstanding_balance: principal,
      breakdown: { ...initial().breakdown!, shop_supplies_amount: label === 'Shop supplies' ? '0.00' : '24.00', sales_tax_amount: label === 'Sales tax' ? '0.00' : label === 'Shop supplies' ? '86.46' : '88.44', principal_total: principal },
      charge_controls: { ...initial().charge_controls!, tax_exempt: label === 'Sales tax', shop_supplies_enabled: label !== 'Shop supplies', card_fee_enabled: label !== 'Card processing fee' },
    }
    await act(async () => save.resolve(next))
    await waitFor(() => expect(api.fetchPaymentQuote).toHaveBeenCalledWith(initial().invoice_id, 'card', principal, 2))
    expect(rows.every(node => node.isConnected)).toBe(true)
    expect(screen.getByText('$1,198.17')).toBeInTheDocument()
    expect(screen.queryByText('Invoice total before card fees')).not.toBeInTheDocument()
    expect(screen.queryByText('This payment toward invoice')).not.toBeInTheDocument()
    expect(button).toBeDisabled()
    await act(async () => refresh.resolve({ ...originalQuote, settlement_version: 2, principal_amount: principal, card_fee_amount: fee, card_fee_tax_amount: feeTax, total_amount: total }))
    await waitFor(() => expect(button).toBeEnabled())
    expect(rows.every(node => node.isConnected)).toBe(true)
    expect(row('Tax on card fee')).toHaveTextContent(`$${feeTax}`)
    expect(row('Amount to collect')).toHaveTextContent(`$${Number(total).toLocaleString('en-US', { minimumFractionDigits: 2 })}`)
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it('does not collapse an opened optional reference when tax exemption is turned off', async () => {
    api.adjustInvoiceCharges.mockImplementation(async (_id, body) => ({ ...initial(), version: body.expected_settlement_version + 1, charge_controls: { ...initial().charge_controls!, ...body } }))
    show()
    const toggle = screen.getByRole('switch', { name: 'Sales tax' })
    await userEvent.click(toggle)
    await waitFor(() => expect(toggle).toBeEnabled())
    await userEvent.click(screen.getByRole('button', { name: 'Add certificate/reference' }))
    const reference = screen.getByRole('textbox')
    await userEvent.click(toggle)
    await waitFor(() => expect(toggle).toBeEnabled())
    expect(reference).toBeInTheDocument()
    expect(reference).toBeDisabled()
    await userEvent.click(toggle)
    await waitFor(() => expect(reference).toBeEnabled())
    expect(screen.getByRole('textbox')).toBe(reference)
  })

  it('keeps payment blocked if the replacement quote fails', async () => {
    show()
    await screen.findByText('$1,198.17')
    api.fetchPaymentQuote.mockRejectedValue(new Error('Quote failed'))
    api.adjustInvoiceCharges.mockResolvedValue({ ...initial(), version: 2, charge_controls: { ...initial().charge_controls!, shop_supplies_enabled: false } })
    await userEvent.click(screen.getByRole('switch', { name: 'Shop supplies' }))
    await screen.findByRole('button', { name: 'Retry payment total' })
    expect(screen.getByRole('button', { name: 'Continue to QBO Payments' })).toBeDisabled()
    expect(row('Amount to collect')).toBeInTheDocument()
    expect(api.createPaymentAttempt).not.toHaveBeenCalled()
  })

  it.each(['Zelle', 'Another invoice'])('never displays the old quote for %s', async choice => {
    show()
    await screen.findByText('$1,198.17')
    api.fetchPaymentQuote.mockReturnValue(new Promise(() => undefined))
    await userEvent.click(screen.getByRole(choice === 'Zelle' ? 'radio' : 'button', { name: choice }))
    expect(screen.queryByText('$1,198.17')).not.toBeInTheDocument()
    expect(row('Amount to collect')).toHaveTextContent('—')
  })
})
