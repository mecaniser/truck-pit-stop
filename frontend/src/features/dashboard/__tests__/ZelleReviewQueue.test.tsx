import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { User } from '@/types'
import { useAuthStore } from '@/stores/authStore'
import ZelleReviewQueue from '../ZelleReviewQueue'
import { useZelleReviewQueue, type ZelleReviewRow } from '../useZelleReviewQueue'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), dialog: vi.fn(), legacy: vi.fn(), open: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock('@/features/payments/StaffSettlementDialog', () => ({ default: (props: { invoiceId: string; invoiceNumber: string; reviewAttemptId?: string; onClose: () => void }) => { mocks.dialog(props); return <div role="dialog" aria-label={`Review invoice ${props.invoiceNumber}`}><button onClick={props.onClose}>Close review</button></div> } }))
function resolution(overrides: Partial<NonNullable<ZelleReviewRow['resolution']>> = {}): NonNullable<ZelleReviewRow['resolution']> {
  return { attempt_id: 'attempt-1687', invoice_id: 'native-copy-1687', attempt_version: 2, settlement_version: 3, rail: 'zelle', requested_principal: '168.44', currency: 'USD', attempt_state: 'pending', checkout_status: 'transfer_reported', reservation_amount: '168.44', can_retry: false, actions: { cancel_unsent: false, check_provider_status: false, request_review: false, release_with_terminal_evidence: false, record_late_receipt: false }, block_reason: null, resolution_notice: null, review_status: 'none', ...overrides }
}
function row(overrides: Partial<ZelleReviewRow> = {}): ZelleReviewRow {
  const result: ZelleReviewRow = { kind: 'canonical_zelle_attempt', rail: 'zelle', resolution: null, invoice_id: 'native-copy-1687', repair_order_id: 'archived-source-ro', display_invoice_number: 'TPS-1687', customer_id: 'reviewed-payer', customer_display_name: 'Actual Billed Fleet', principal_amount: '168.44', attempt_id: 'attempt-1687', settlement_id: 'settlement-1687', settlement_version: 3, created_at: '2026-11-04T12:00:00Z', reported_at: '2026-11-04T12:00:00Z', report_status: 'explicit_report', review_mode: 'canonical_attempt', can_confirm: true, ...overrides }
  if (result.kind !== 'legacy_zelle_submission' && overrides.resolution === undefined) result.resolution = resolution({ attempt_id: result.attempt_id!, invoice_id: result.invoice_id, rail: result.rail, requested_principal: result.principal_amount })
  return result
}
function Harness({ compact = false }: { compact?: boolean }) {
  const queue = useZelleReviewQueue()
  return <ZelleReviewQueue queue={queue} compact={compact} onOpenQueue={mocks.open} onOpenLegacy={mocks.legacy}/>
}
function show(compact = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><Harness compact={compact}/></QueryClientProvider>)
  return client
}
beforeEach(() => {
  vi.clearAllMocks()
  mocks.get.mockReset()
  mocks.get.mockResolvedValue({ data: { rows: [row()], next_cursor: null } })
  useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false, authProvider: 'legacy', authSessionEpoch: 1, user: { id: 'owner-a', tenant_id: 'tenant-a', role: 'garage_owner', is_active: true, permissions: { payments: true } } as User })
})
describe('durable staff Zelle payment review', () => {
  it('opens exact invoice settlement for the reported partial amount, including an archived source order', async () => {
    show()
    expect(await screen.findByText('Actual Billed Fleet')).toBeInTheDocument()
    expect(screen.getByText('Invoice TPS-1687')).toBeInTheDocument()
    expect(screen.getByText('$168.44')).toBeInTheDocument()
    expect(screen.queryByText('$268.44')).not.toBeInTheDocument()
    expect(screen.getByText('Customer reported transfer sent')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Review Zelle request for invoice TPS-1687' }))
    expect(screen.getByRole('dialog', { name: 'Review invoice TPS-1687' })).toBeInTheDocument()
    expect(mocks.dialog.mock.lastCall?.[0]).toMatchObject({ invoiceId: 'native-copy-1687', invoiceNumber: 'TPS-1687', reviewAttemptId: 'attempt-1687' })
    expect(mocks.legacy).not.toHaveBeenCalled()
    expect(mocks.get.mock.calls.every(([url]) => url === '/payments/attempt-review-queue')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Close review' }))
    expect(screen.getByRole('heading', { name: 'Payment review' })).toHaveFocus()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('opens the exact protected EFS request without using generic manual confirmation', async () => {
    mocks.get.mockResolvedValue({ data: { rows: [row({ kind: 'canonical_efs_attempt', rail: 'fleet_payment', provider_label: 'EFS', can_confirm: false, resolution: resolution({ rail: 'fleet_payment', checkout_status: 'verification_pending' }), efs: { provider: 'EFS', code_last4: '6789', status: 'awaiting_verification', can_cancel: true, can_reveal: true, can_verify: true, can_reject: true, can_resolve_received_difference: false, difference_review: null } })], next_cursor: null } })
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Review EFS request for invoice TPS-1687' }))
    expect(mocks.dialog.mock.lastCall?.[0]).toMatchObject({ invoiceId: 'native-copy-1687', reviewAttemptId: 'attempt-1687' })
    expect(screen.getByText('EFS code awaiting verification')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('loads every cursor page read-only and deduplicates an exact repeated attempt', async () => {
    mocks.get.mockResolvedValueOnce({ data: { rows: [row()], next_cursor: 'cursor-next' } }).mockResolvedValueOnce({ data: { rows: [row(), row({ invoice_id: 'invoice-b', display_invoice_number: 'TPS-42', attempt_id: 'attempt-b', principal_amount: '20.00' })], next_cursor: null } })
    show()
    expect(await screen.findByText('Invoice TPS-42')).toBeInTheDocument()
    expect(screen.getAllByText('Invoice TPS-1687')).toHaveLength(1)
    expect(mocks.get).toHaveBeenNthCalledWith(2, '/payments/attempt-review-queue', expect.objectContaining({ params: { limit: 100, cursor: 'cursor-next' }, signal: expect.any(AbortSignal) }))
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('keeps historical unverified requests visible without claiming a transfer was sent', async () => {
    mocks.get.mockResolvedValue({ data: { rows: [row({ report_status: 'unverified_request', reported_at: null })], next_cursor: null } })
    show()
    expect(await screen.findByText('Payment request awaiting review')).toBeInTheDocument()
    expect(screen.queryByText(/transfer sent/i)).not.toBeInTheDocument()
    expect(screen.getByText('$168.44')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('keeps a legacy-only submission on its separately labeled existing review path', async () => {
    mocks.get.mockResolvedValue({ data: { rows: [row({ kind: 'legacy_zelle_submission', review_mode: 'legacy_invoice', report_status: 'legacy_report', attempt_id: null })], next_cursor: null } })
    show()
    expect(await screen.findByText('Invoice amount')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review Zelle report for invoice TPS-1687' }))
    expect(screen.getByText('Reported transfer')).toBeInTheDocument()
    expect(screen.queryByText(/legacy/i)).not.toBeInTheDocument()
    expect(mocks.legacy).toHaveBeenCalledExactlyOnceWith('archived-source-ro')
    expect(mocks.dialog).not.toHaveBeenCalled()
  })
  it('leaves nonconfirmable requests read-only', async () => {
    mocks.get.mockResolvedValue({ data: { rows: [row({ can_confirm: false })], next_cursor: null } })
    show()
    expect(await screen.findByText('Review unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Review Zelle/ })).not.toBeInTheDocument()
    expect(mocks.dialog).not.toHaveBeenCalled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('uses one compact discovery entry and opens the existing Closeout queue', async () => {
    show(true)
    expect(await screen.findByText('1 payment request awaiting review')).toBeInTheDocument()
    expect(screen.queryByText('Invoice TPS-1687')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review payments' }))
    expect(mocks.open).toHaveBeenCalledOnce()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not turn a failed read into an empty queue and retries read-only', async () => {
    mocks.get.mockRejectedValueOnce(new Error('Unavailable'))
    show()
    expect(await screen.findByRole('alert')).toHaveTextContent('Payment requests couldn’t load')
    expect(screen.queryByText('No payment requests awaiting review.')).not.toBeInTheDocument()
    mocks.get.mockResolvedValue({ data: { rows: [row()], next_cursor: null } })
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Invoice TPS-1687')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not silently accept a repeated cursor as a complete queue', async () => {
    mocks.get.mockResolvedValue({ data: { rows: [row()], next_cursor: 'repeated' } })
    show()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByText('Invoice TPS-1687')).not.toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledTimes(2)
  })
  it.each(['customer', 'fleet_manager', 'driver', 'mechanic', 'garage_admin', 'receptionist'] as const)('does not read or expose queue data to ungranted %s', async role => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role, permissions: {} } })
    show()
    expect(screen.queryByRole('heading', { name: 'Payment review' })).not.toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalled()
  })
  it.each(['garage_owner', 'garage_admin'] as const)('allows the existing payment authority for %s', async role => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role, permissions: role === 'garage_owner' ? {} : { payments: true } } })
    show()
    expect(await screen.findByText('Invoice TPS-1687')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review Zelle request for invoice TPS-1687' })).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each(['receptionist', 'super_admin', 'mechanic', 'customer', 'fleet_manager', 'driver'] as const)('denies %s even with a payments flag', role => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role, permissions: { payments: true } } })
    show()
    expect(screen.queryByRole('heading', { name: 'Payment review' })).not.toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalled()
  })
  it('unmounts an open invoice review on authorization loss', async () => {
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Review Zelle request for invoice TPS-1687' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    act(() => useAuthStore.setState({ logoutInProgress: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Actual Billed Fleet')).not.toBeInTheDocument()
  })
  it('pauses a warm queue on failed refresh instead of preserving a confirm action', async () => {
    const client = show()
    await screen.findByText('Invoice TPS-1687')
    mocks.get.mockRejectedValue(new Error('Unavailable'))
    await act(async () => { await client.refetchQueries({ queryKey: ['zelle-review-queue'] }) })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Review Zelle/ })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
})


describe('combined card and Zelle staff discovery', () => {
  it.each(['checkout_started', 'verification_pending', 'review_required'] as const)('opens a card %s for exact invoice review without manual-receipt authority', async status => {
    mocks.get.mockResolvedValue({ data: { rows: [row({ kind: 'canonical_card_attempt', rail: 'card', can_confirm: false, reported_at: null, report_status: 'unverified_request', resolution: resolution({ rail: 'card', checkout_status: status, review_status: status === 'review_required' ? 'requested' : 'none' }) })], next_cursor: null } })
    show()
    const label = status === 'checkout_started' ? 'Card checkout started' : status === 'verification_pending' ? 'Card verification pending' : 'Card payment needs review'
    expect(await screen.findByText(label)).toBeInTheDocument()
    expect(screen.queryByText(/transfer sent|payment received|Zelle/i)).not.toBeInTheDocument()
    expect(screen.getByText('$168.44')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review card request for invoice TPS-1687' }))
    expect(mocks.dialog.mock.lastCall?.[0]).toMatchObject({ invoiceId: 'native-copy-1687', invoiceNumber: 'TPS-1687', reviewAttemptId: 'attempt-1687' })
    expect(mocks.legacy).not.toHaveBeenCalled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('uses one combined queue for card, Zelle and genuine invoice reports', async () => {
    mocks.get.mockResolvedValue({ data: { rows: [row({ kind: 'canonical_card_attempt', rail: 'card', can_confirm: false, resolution: resolution({ rail: 'card', checkout_status: 'review_required' }) }), row({ invoice_id: 'invoice-zelle', attempt_id: 'attempt-zelle', display_invoice_number: 'TPS-42' }), row({ kind: 'legacy_zelle_submission', invoice_id: 'invoice-report', attempt_id: null, resolution: null, review_mode: 'legacy_invoice', display_invoice_number: 'TPS-43', report_status: 'legacy_report' })], next_cursor: null } })
    show()
    expect(await screen.findByText('Card payment needs review')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { name: 'Payment review' })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Review card request for invoice TPS-1687' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review Zelle request for invoice TPS-42' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review Zelle report for invoice TPS-43' })).toBeInTheDocument()
    expect(mocks.get).toHaveBeenCalledTimes(1)
    expect(mocks.get.mock.calls[0][0]).toBe('/payments/attempt-review-queue')
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each(['missing', 'wrong invoice', 'wrong attempt', 'wrong rail'] as const)('leaves a card with %s resolution data read-only', async invalid => {
    const projection = invalid === 'missing' ? null : resolution({ rail: invalid === 'wrong rail' ? 'zelle' : 'card', invoice_id: invalid === 'wrong invoice' ? 'different-invoice' : 'native-copy-1687', attempt_id: invalid === 'wrong attempt' ? 'different-attempt' : 'attempt-1687', checkout_status: 'review_required' })
    mocks.get.mockResolvedValue({ data: { rows: [row({ kind: 'canonical_card_attempt', rail: 'card', can_confirm: true, resolution: projection })], next_cursor: null } })
    show()
    expect(await screen.findByText('Payment details unavailable')).toBeInTheDocument()
    expect(screen.getByText('Review unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Review card/ })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not request another cursor page after logout while a page is still in flight', async () => {
    let complete!: (result: { data: { rows: ZelleReviewRow[]; next_cursor: string } }) => void
    mocks.get.mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
    show()
    expect(mocks.get).toHaveBeenCalledTimes(1)
    const signal = mocks.get.mock.calls[0][1].signal as AbortSignal
    act(() => useAuthStore.setState({ logoutInProgress: true }))
    expect(signal.aborted).toBe(true)
    await act(async () => { complete({ data: { rows: [row()], next_cursor: 'later-page' } }) })
    expect(mocks.get).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Actual Billed Fleet')).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
})


describe('exact selected payment request', () => {
  it('opens the chosen attempt when two requests belong to the same invoice', async () => {
    mocks.get.mockResolvedValue({ data: { rows: [row(), row({ attempt_id: 'second-attempt', principal_amount: '20.00' })], next_cursor: null } })
    show()
    const reviews = await screen.findAllByRole('button', { name: 'Review Zelle request for invoice TPS-1687' })
    expect(reviews).toHaveLength(2)
    fireEvent.click(reviews[1])
    expect(mocks.dialog.mock.lastCall?.[0]).toMatchObject({ invoiceId: 'native-copy-1687', reviewAttemptId: 'second-attempt', invoiceNumber: 'TPS-1687' })
    expect(mocks.post).not.toHaveBeenCalled()
    expect(mocks.legacy).not.toHaveBeenCalled()
  })
})
