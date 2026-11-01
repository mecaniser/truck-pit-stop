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
    ['paid', '534.41', '0.00', 'Paid in full'],
    ['partially_paid', '100.00', '434.41', 'Partially paid'],
    ['unpaid', '0.00', '534.41', 'Unpaid'],
  ] as const)('shows %s imported payment evidence separately from work state', async (status, completed, remaining, label) => {
    render(<ImportedBillingDetails billing={{ ...paid, payment_status: status, recorded_completed_amount: completed, recorded_remaining_amount: remaining }} />)
    expect(screen.getByText(label)).toBeVisible()
    if (remaining === '0.00') expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    else expect(screen.getByText(importedMoney(remaining))).toBeVisible()
    expect(screen.queryByText('Imported ETS records · QuickBooks not checked')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Imported ETS records · QuickBooks not checked')).toBeVisible()
    expect(screen.getAllByText(importedMoney(completed)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(importedMoney(remaining)).length).toBeGreaterThan(0)
  })
  it.each([
    ['paid', false, 'healthy', 'Paid in ETS'],
    ['paid', true, 'warning', 'Review needed'],
    ['partially_paid', false, 'warning', 'Partially paid in ETS'],
    ['unpaid', false, 'warning', 'Unpaid in ETS'],
    ['unverified', false, 'warning', 'Payment unverified'],
  ] as const)('uses accessible %s severity with review=%s', (status, review, severity, description) => {
    render(<ImportedBillingDetails billing={{ ...paid, payment_status: status, review_required: review }} />)
    const indicator = screen.getByRole('button', { name: 'ETS billing details' })
    expect(indicator).toHaveAttribute('data-severity', severity)
    expect(indicator.getAttribute('aria-description')).toContain(description)
  })
  it.each([null, 'invalid', '1.00'])('does not mark a paid invoice healthy with an unsupported remaining balance %s', remaining => {
    render(<ImportedBillingDetails billing={{ ...paid, recorded_remaining_amount: remaining }} />)
    expect(screen.getByRole('button', { name: 'ETS billing details' })).toHaveAttribute('data-severity', 'warning')
  })
  it('calls an unknown remaining amount unavailable rather than implying debt', async () => {
    render(<ImportedBillingDetails billing={{ ...paid, recorded_remaining_amount: null }} />)
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Balance unavailable')).toBeVisible()
    expect(screen.queryByText('Payment remaining')).not.toBeInTheDocument()
  })
  it.each(['total_amount', 'recorded_completed_amount'] as const)('does not show healthy when %s is missing', field => {
    render(<ImportedBillingDetails billing={{ ...paid, [field]: null }} />)
    expect(screen.getByRole('button', { name: 'ETS billing details' })).toHaveAttribute('data-severity', 'warning')
    expect(screen.getByRole('button', { name: 'ETS billing details' }).getAttribute('aria-description')).toContain('Payment details unavailable')
  })
  it('shows a warning heading and specific identity conflict explanation even for a paid invoice', async () => {
    render(<ImportedBillingDetails billing={{ ...paid, review_required: true, review_reasons: ['shared_job_identity_conflict'] }} />)
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Review needed')).toHaveAttribute('data-severity', 'warning')
    expect(screen.getByText('Related operations have different customer or vehicle identities. Shared billing needs review.')).toBeVisible()
    expect(screen.queryByText('Payment verified')).not.toBeInTheDocument()
  })
  it('shows a healthy payment heading in the opened details', async () => {
    render(<ImportedBillingDetails billing={paid} />)
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Payment verified')).toHaveAttribute('data-severity', 'healthy')
  })
  it('keeps unknown total as the only unavailable summary until details open', async () => {
    get.mockResolvedValue({ data: { ...paid, invoice_id: null, total_amount: null, payment_status: 'unverified', recorded_completed_amount: null, recorded_remaining_amount: null, review_required: true } })
    renderQuery()
    await waitFor(() => expect(get).toHaveBeenCalledOnce())
    expect(screen.getAllByText('Unavailable')).toHaveLength(1)
    expect(screen.queryByText('Payment unverified')).not.toBeInTheDocument()
    expect(screen.queryByText('Remaining')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Payment unverified')).toBeVisible()
  })
  it('keeps the shared whole-job explanation inside one tooltip', async () => {
    render(<ImportedBillingDetails billing={{ ...paid, shared_invoice: true, invoice_repair_order_number: 'ETS-9001-123-2' }} />)
    expect(screen.queryByText(/Shared invoice for the whole job/)).not.toBeInTheDocument()
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText(/Shared invoice for the whole job.*ETS-9001-123-2/)).toBeVisible()
  })
  it('does not expose stale remaining amounts when status is unverified', () => {
    render(<ImportedBillingDetails billing={{ ...paid, payment_status: 'unverified' }} />)
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ETS billing details' })).toHaveAttribute('data-severity', 'warning')
  })
  it('labels an observed source snapshot without claiming QuickBooks reconciliation', async () => {
    get.mockResolvedValue({ data: { ...paid, evidence_basis: 'ets_source_snapshot', observed_at: '2026-10-18T20:00:00Z' } })
    renderQuery()
    await screen.findByText('Paid in full')
    expect(screen.queryByText('ETS source snapshot · QuickBooks not checked')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('ETS source snapshot · QuickBooks not checked')).toBeVisible()
    expect(document.querySelector('time')).toHaveAttribute('datetime', '2026-10-18T20:00:00Z')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('shows review separately from the supported imported payment state', async () => {
    render(<ImportedBillingDetails billing={{ ...paid, payment_status: 'unpaid', recorded_completed_amount: '0.00', recorded_remaining_amount: '534.41', review_required: true }} />)
    expect(screen.getByText('Unpaid')).toBeVisible()
    expect(screen.queryByText('Review needed')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('Review needed')).toBeVisible()
    expect(screen.queryByText('Paid in full')).not.toBeInTheDocument()
  })
  it('does not replace missing amounts with zero', async () => {
    render(<ImportedBillingDetails />)
    expect(screen.queryByText('Payment unverified')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ETS billing details' })).toHaveAttribute('data-severity', 'warning')
    await userEvent.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getAllByText('Unavailable')).toHaveLength(3)
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
    expect(screen.queryByText('ETS invoice on file · no new invoice')).not.toBeInTheDocument()
    expect(screen.queryByText('Remaining')).not.toBeInTheDocument()
  })
  it('fetches the read-only scoped endpoint and holds on error', async () => {
    get.mockRejectedValue(new Error('503'))
    renderQuery()
    expect(await screen.findByRole('alert')).toHaveTextContent('Billing unavailable')
    expect(screen.queryByText('Payment unverified')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ETS billing details' })).toHaveAttribute('data-severity', 'warning')
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
    expect(get).toHaveBeenCalledWith('/repair-orders/order-1/imported-billing', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })
  it('does not reuse the previous order or session payment state', async () => {
    get.mockResolvedValueOnce({ data: paid }).mockImplementation(() => new Promise(() => {}))
    const view = renderQuery()
    await screen.findByText('Paid in full')
    view.changeOrder('order-2')
    expect(screen.queryByText('Paid in full')).not.toBeInTheDocument()
    expect(screen.queryByText('$534.41')).not.toBeInTheDocument()
    expect(screen.queryByText('Payment unverified')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ETS billing details' })).toHaveAttribute('data-severity', 'warning')
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    act(() => useAuthStore.setState({ authSessionEpoch: 2 }))
    await waitFor(() => expect(get).toHaveBeenCalledTimes(3))
  })
  it.each(['0', '000.00', null, '-1.00', '1junk'])('hides zero or invalid inline balance %s', remaining => {
    render(<ImportedBillingDetails billing={{ ...paid, recorded_remaining_amount: remaining }} />)
    expect(screen.queryByText(/Balance due/)).not.toBeInTheDocument()
  })
  it('shows exact positive balance without numeric coercion', () => {
    render(<ImportedBillingDetails billing={{ ...paid, payment_status: 'unpaid', recorded_remaining_amount: '9007199254740993.01' }} />)
    expect(screen.getByText('$9,007,199,254,740,993.01')).toBeVisible()
    expect(screen.getByText(/Balance due/)).toBeVisible()
  })
  it('opens on hover, closes on pointer exit, and opens on keyboard focus', async () => {
    const user = userEvent.setup()
    render(<><button>Before</button><ImportedBillingDetails billing={paid} /></>)
    const trigger = screen.getByRole('button', { name: 'ETS billing details' })
    await user.hover(trigger)
    expect(screen.getByRole('tooltip')).toBeVisible()
    expect(trigger).toHaveAttribute('aria-describedby', screen.getByRole('tooltip').id)
    await user.unhover(trigger)
    await waitFor(() => expect(screen.queryByRole('tooltip')).not.toBeInTheDocument())
    await user.tab()
    await user.tab()
    expect(trigger).toHaveFocus()
    expect(screen.getByRole('tooltip')).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
  it('toggles with touch and dismisses on outside touch', async () => {
    const user = userEvent.setup()
    render(<><button>Outside</button><ImportedBillingDetails billing={paid} /></>)
    const trigger = screen.getByRole('button', { name: 'ETS billing details' })
    const tap = async (target: HTMLElement) => user.pointer([{ keys: '[TouchA>]', target }, { keys: '[/TouchA]' }])
    await tap(trigger)
    expect(screen.getByRole('tooltip')).toBeVisible()
    await tap(trigger)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    await tap(trigger)
    await tap(screen.getByRole('button', { name: 'Outside' }))
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
  it('does not fetch for a native order', () => {
    renderQuery('native-order', false)
    expect(get).not.toHaveBeenCalled()
  })
  it('rejects incompatible source evidence', async () => {
    get.mockResolvedValue({ data: { ...paid, source: 'native' } })
    renderQuery()
    await screen.findByRole('alert')
    expect(screen.queryByText('Paid in full')).not.toBeInTheDocument()
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
