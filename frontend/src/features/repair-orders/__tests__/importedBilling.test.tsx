import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types'
import { ImportedBillingDetails } from '../ImportedBillingDetails'
import { importedMoney, useImportedBilling, type ImportedBilling } from '../importedBilling'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ default: { get } }))
const paid: ImportedBilling = {
  source: 'easy_truck_shop_import', evidence_basis: 'imported_records', reconciliation_status: 'not_checked',
  invoice_id: 'ets-invoice', total_amount: '534.41', recorded_completed_amount: '534.41', recorded_remaining_amount: '0.00',
  payment_status: 'paid', review_required: false, review_reasons: [],
}
function BillingQuery({ id, enabled = true }: { id: string; enabled?: boolean }) {
  const query = useImportedBilling(id, enabled)
  return <><p>{importedMoney(query.isError ? null : query.data?.total_amount)}</p><ImportedBillingDetails billing={query.data} failed={query.isError} /></>
}
function renderQuery(id = 'order-1', enabled = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(<QueryClientProvider client={client}><BillingQuery id={id} enabled={enabled} /></QueryClientProvider>)
  return { ...view, changeOrder(next: string) { view.rerender(<QueryClientProvider client={client}><BillingQuery id={next} /></QueryClientProvider>) } }
}
describe('Imported ETS billing', () => {
  beforeEach(() => {
    get.mockReset()
    useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role: 'garage_owner' } as User, authSessionEpoch: 1, logoutInProgress: false })
  })
  it.each([
    ['paid', '534.41', '0.00', 'Paid in ETS'],
    ['partially_paid', '100.00', '434.41', 'Partially paid in ETS'],
    ['unpaid', '0.00', '534.41', 'Unpaid in ETS'],
  ] as const)('shows %s imported payment evidence separately from work state', async (status, completed, remaining, label) => {
    render(<ImportedBillingDetails billing={{ ...paid, payment_status: status, recorded_completed_amount: completed, recorded_remaining_amount: remaining }} />)
    expect(screen.getByText(label)).toBeVisible()
    expect(screen.queryByText('Imported ETS records · QuickBooks not checked')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Imported ETS records · QuickBooks not checked')).toBeVisible()
    expect(screen.getAllByText(importedMoney(completed)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(importedMoney(remaining)).length).toBeGreaterThan(0)
  })
  it('labels an observed source snapshot without claiming QuickBooks reconciliation', async () => {
    get.mockResolvedValue({ data: { ...paid, evidence_basis: 'ets_source_snapshot', observed_at: '2026-10-18T20:00:00Z' } })
    renderQuery()
    await screen.findByText('Paid in ETS')
    expect(screen.queryByText('ETS source snapshot · QuickBooks not checked')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('ETS source snapshot · QuickBooks not checked')).toBeVisible()
    expect(document.querySelector('time')).toHaveAttribute('datetime', '2026-10-18T20:00:00Z')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('shows review separately from the supported imported payment state', async () => {
    render(<ImportedBillingDetails billing={{ ...paid, payment_status: 'unpaid', recorded_completed_amount: '0.00', recorded_remaining_amount: '534.41', review_required: true }} />)
    expect(screen.getByText('Unpaid in ETS')).toBeVisible()
    expect(screen.queryByText('Review needed')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Review needed')).toBeVisible()
    expect(screen.queryByText('Paid in ETS')).not.toBeInTheDocument()
  })
  it('does not replace missing amounts with zero', async () => {
    render(<ImportedBillingDetails />)
    expect(screen.getByText('Payment unverified')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getAllByText('Unavailable')).toHaveLength(2)
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })
  it('opens by keyboard and dismisses with Escape or an outside click', async () => {
    const user = userEvent.setup()
    render(<><button>Outside</button><ImportedBillingDetails billing={paid} /></>)
    const trigger = screen.getByRole('button', { name: 'ETS billing details' })
    trigger.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByText('ETS invoice on file · no new invoice')).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByText('ETS invoice on file · no new invoice')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: 'Outside' }))
    expect(screen.queryByText('Remaining')).not.toBeInTheDocument()
  })
  it('fetches the read-only scoped endpoint and holds on error', async () => {
    get.mockRejectedValue(new Error('503'))
    renderQuery()
    expect(await screen.findByRole('alert')).toHaveTextContent('Billing unavailable')
    expect(screen.getByText('Payment unverified')).toBeVisible()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/repair-orders/order-1/imported-billing', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })
  it('does not reuse the previous order or session payment state', async () => {
    get.mockResolvedValueOnce({ data: paid }).mockImplementation(() => new Promise(() => {}))
    const view = renderQuery()
    await screen.findByText('Paid in ETS')
    view.changeOrder('order-2')
    expect(screen.queryByText('Paid in ETS')).not.toBeInTheDocument()
    expect(screen.queryByText('$534.41')).not.toBeInTheDocument()
    expect(screen.getByText('Payment unverified')).toBeVisible()
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    act(() => useAuthStore.setState({ authSessionEpoch: 2 }))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3))
  })
  it('does not fetch for a native order', () => {
    renderQuery('native-order', false)
    expect(get).not.toHaveBeenCalled()
  })
  it('rejects incompatible source evidence', async () => {
    get.mockResolvedValue({ data: { ...paid, source: 'native' } })
    renderQuery()
    await screen.findByRole('alert')
    expect(screen.queryByText('Paid in ETS')).not.toBeInTheDocument()
  })
  it.each([
    ['9007199254740993.01', '$9,007,199,254,740,993.01'],
    ['000150.5', '$150.50'],
    ['0', '$0.00'],
  ])('formats exact decimal cents %s', (value, expected) => {
    expect(importedMoney(value)).toBe(expected)
  })

  it.each([null, undefined, '', '-150.00', 'NaN', '0junk', 'Infinity'])('holds invalid money %s', value => {
    expect(importedMoney(value)).toBe('Unavailable')
  })
})
