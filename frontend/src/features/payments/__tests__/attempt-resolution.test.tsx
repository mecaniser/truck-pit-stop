import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AxiosError, AxiosHeaders } from 'axios'
import { useAuthStore } from '@/stores/authStore'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { AttemptResolutionDetail, AttemptResolutionResponse, ResolutionProjection } from '../attemptResolutionTypes'
import type { InvoiceSettlementSummary, PaymentAllocation, SettlementAccess } from '../types'

const requests = vi.hoisted(() => ({ resolve: vi.fn(), detail: vi.fn(), grant: vi.fn(), confirm: vi.fn(), create: vi.fn() }))
vi.mock('../attemptResolutionApi', async original => ({ ...await original<typeof import('../attemptResolutionApi')>(), resolvePaymentAttempt: requests.resolve, fetchAttemptResolutionDetail: requests.detail }))
vi.mock('@/lib/paymentStepUp', async original => ({ ...await original<typeof import('@/lib/paymentStepUp')>(), createPaymentStepUpGrant: requests.grant }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), confirmPaymentAttempt: requests.confirm, createPaymentAttempt: requests.create }))
import Controls from '../PaymentAttemptResolutionControls'
import SettlementSummaryCard from '../SettlementSummaryCard'

const summary: InvoiceSettlementSummary = { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, principal_total: '268.44', outstanding_balance: '268.44', active_pending_principal: '268.44', allocatable_balance: '0.00', state: 'payment_pending', version: 3 }
const access: SettlementAccess = { kind: 'authenticated', invoiceId: summary.invoice_id }
const noActions = { cancel_unsent: false, check_provider_status: false, request_review: false, release_with_terminal_evidence: false, record_late_receipt: false }
function projection(overrides: Partial<ResolutionProjection> = {}): ResolutionProjection {
  return { attempt_id: 'attempt-zelle', invoice_id: summary.invoice_id, attempt_version: 1, settlement_version: 3, rail: 'zelle', requested_principal: '168.44', currency: 'USD', attempt_state: 'pending', checkout_status: 'transfer_reported', reservation_amount: '168.44', can_retry: false, actions: { ...noActions, cancel_unsent: true }, block_reason: null, resolution_notice: null, review_status: 'none', ...overrides }
}
function allocation(resolution = projection()): PaymentAllocation {
  return { id: resolution.attempt_id, attempt_id: resolution.attempt_id, attempt_version: resolution.attempt_version, rail: resolution.rail, provider: resolution.rail === 'card' ? 'quickbooks_payments' : 'manual', principal_amount: resolution.requested_principal, applied_principal_amount: '0.00', card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: resolution.requested_principal, received_amount: null, unapplied_amount: '0.00', state: resolution.attempt_state, created_at: '2026-11-04T12:00:00Z', resolution }
}
const released: InvoiceSettlementSummary = { ...summary, version: 4, active_pending_principal: '100.00', allocatable_balance: '168.44', state: 'payment_pending' }
function cancelled(): AttemptResolutionResponse {
  return { attempt_id: 'attempt-zelle', invoice_id: summary.invoice_id, principal_amount: '168.44', card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: '168.44', rail: 'zelle', provider: 'manual', state: 'failed', expires_at: null, provider_configuration_version: 1, attempt_version: 2, settlement: released,
    resolution: projection({ attempt_version: 2, settlement_version: 4, attempt_state: 'failed', checkout_status: 'cancelled', reservation_amount: '0.00', can_retry: true, actions: noActions, resolution_notice: { kind: 'request_cancelled', message: 'Payment request canceled. No payment was recorded. You can try again.', resolved_at: '2026-11-04T12:01:00Z' } }) }
}
function detail(canSubmit = true): AttemptResolutionDetail {
  return { resolution: projection({ rail: 'card', checkout_status: 'review_required' }), binding: { provider: 'quickbooks_payments', provider_account_id: 'fictional-merchant', environment: 'sandbox', configuration_version: 1, provider_request_id: 'fictional-request', provider_reference: null, attempted_at: '2026-11-04T12:00:00Z', requested_principal: '168.44', provider_charge_amount: '168.44', currency: 'USD', evidence_context_sha256: 'a'.repeat(64) }, evidence_requirements: { can_submit_terminal_evidence: canSubmit, requires_provider_case: true, requires_document: false, allowed_kinds: ['provider_terminal_no_charge', 'provider_cancelled'], missing_binding_fields: canSubmit ? [] : ['environment'], message: 'Get provider support confirmation for this exact request.' }, history: [] }
}
function show(row = allocation(), audience: 'customer' | 'guest' | 'staff' = 'customer', route: SettlementAccess = access) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const onUpdated = vi.fn()
  const props = { allocation: row, summary, access: route, audience, onUpdated }
  return { ...render(<QueryClientProvider client={client}><Controls {...props} /></QueryClientProvider>), client, onUpdated }
}
async function assertUnsent() {
  await userEvent.click(screen.getByRole('button', { name: 'Payment not sent?' }))
  expect(screen.getByRole('button', { name: 'Cancel request', exact: true })).toBeDisabled()
  await userEvent.click(screen.getByRole('checkbox', { name: 'I have not sent this transfer.' }))
}
beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ authSessionEpoch: 0 })
  HTMLElement.prototype.scrollIntoView = vi.fn()
  requests.resolve.mockResolvedValue(cancelled())
  requests.detail.mockResolvedValue(detail())
  requests.grant.mockResolvedValue({ grant_token: 'fictional-one-time-grant' })
})

describe('Payment request resolution', () => {
  it.each(['customer', 'guest'] as const)('requires an explicit unsent assertion before %s cancellation', async audience => {
    const route = audience === 'guest' ? { kind: 'guest' as const, token: 'fictional-guest-token' } : access
    const { onUpdated } = show(allocation(), audience, route)
    await assertUnsent()
    expect(requests.resolve).not.toHaveBeenCalled()
    expect(screen.getByText(/does not cancel a bank transfer/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel request', exact: true }))
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(released))
    expect(requests.resolve).toHaveBeenCalledWith(route, 'attempt-zelle', expect.objectContaining({ action: 'cancel_unsent', transfer_not_sent_confirmed: true, expected_attempt_version: 1, expected_settlement_version: 3 }), expect.any(String), undefined)
    expect(requests.confirm).not.toHaveBeenCalled()
  })
  it('keeps a request when its confirmation is dismissed', async () => {
    show()
    await assertUnsent()
    await userEvent.click(screen.getByRole('button', { name: 'Keep request' }))
    expect(requests.resolve).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Payment not sent?' })).toHaveFocus()
  })
  it('requires a written staff reason and unsent confirmation', async () => {
    show(allocation(), 'staff')
    await userEvent.click(screen.getByRole('button', { name: 'Payment not sent?' }))
    await userEvent.click(screen.getByRole('checkbox', { name: /customer confirmed/ }))
    expect(screen.getByRole('button', { name: 'Cancel request', exact: true })).toBeDisabled()
    await userEvent.type(screen.getByRole('textbox', { name: 'Reason' }), 'Customer entered the wrong payment method.')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel request', exact: true }))
    expect(requests.resolve).toHaveBeenCalledTimes(1)
  })
  it('retries the identical uncertain cancellation without a second command key', async () => {
    requests.resolve.mockRejectedValueOnce(new Error('Connection lost')).mockResolvedValueOnce(cancelled())
    show()
    await assertUnsent()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel request', exact: true }))
    expect(await screen.findByRole('button', { name: 'Check again' })).toBeEnabled()
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Keep request' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Check again' }))
    expect(requests.resolve).toHaveBeenCalledTimes(2)
    expect(requests.resolve.mock.calls[0]).toEqual(requests.resolve.mock.calls[1])
  })
  it('never applies a late response after the authenticated session changes', async () => {
    let finish!: (result: AttemptResolutionResponse) => void
    requests.resolve.mockReturnValue(new Promise<AttemptResolutionResponse>(resolve => { finish = resolve }))
    const { onUpdated } = show()
    await assertUnsent()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel request', exact: true }))
    act(() => useAuthStore.setState({ authSessionEpoch: 1 }))
    await act(async () => finish(cancelled()))
    expect(onUpdated).not.toHaveBeenCalled()
  })
  it('never guesses cancellation or retry for an unknown card outcome', async () => {
    const unknown = projection({ rail: 'card', checkout_status: 'review_required', actions: { ...noActions, request_review: true }, block_reason: { code: 'provider_outcome_unknown', message: 'Contact the shop.' } })
    show(allocation(unknown))
    expect(screen.queryByRole('button', { name: 'Cancel checkout' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pay remaining' })).not.toBeInTheDocument()
    requests.resolve.mockResolvedValue({ ...cancelled(), rail: 'card', provider: 'quickbooks_payments', state: 'pending', settlement: summary, resolution: { ...unknown, review_status: 'requested' } })
    await userEvent.click(screen.getByRole('button', { name: 'Ask shop to review' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Shop review requested')
    expect(screen.queryByRole('button', { name: 'Ask shop to review' })).not.toBeInTheDocument()
  })
  it('cancels only a server-approved card checkout and never submits a charge', async () => {
    const card = projection({ rail: 'card', checkout_status: 'checkout_started' })
    const result = cancelled()
    requests.resolve.mockResolvedValue({ ...result, rail: 'card', provider: 'quickbooks_payments', resolution: { ...result.resolution, rail: 'card' } })
    const { onUpdated } = show(allocation(card))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel checkout' }))
    expect(requests.resolve).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel checkout', exact: true }))
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(released))
    expect(requests.resolve.mock.calls[0][2]).not.toHaveProperty('transfer_not_sent_confirmed')
    expect(requests.confirm).not.toHaveBeenCalled()
  })
  it('rejects a response for a different attempt without changing the invoice', async () => {
    const result = cancelled()
    requests.resolve.mockResolvedValue({ ...result, attempt_id: 'other-attempt' })
    const { onUpdated } = show()
    await assertUnsent()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel request', exact: true }))
    expect(await screen.findByRole('alert')).toHaveTextContent('newer payment update')
    expect(onUpdated).not.toHaveBeenCalled()
  })
  it('cancels a local EFS request without falsely asserting a Zelle transfer was not sent', async () => {
    const efs = { provider: 'EFS' as const, code_last4: '6789', status: 'awaiting_verification' as const, can_cancel: true, can_reveal: false, can_verify: false, can_reject: false, can_resolve_received_difference: false, difference_review: null }
    const result = cancelled()
    requests.resolve.mockResolvedValue({ ...result, rail: 'fleet_payment', provider: 'manual', resolution: { ...result.resolution, rail: 'fleet_payment' } })
    show({ ...allocation(projection({ rail: 'fleet_payment', checkout_status: 'verification_pending' })), efs })
    await userEvent.click(screen.getByRole('button', { name: 'Cancel EFS request', exact: true }))
    expect(screen.getByText(/not the EFS code/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /not sent/ })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel request', exact: true }))
    expect(requests.resolve.mock.calls[0][2]).toMatchObject({ action: 'cancel_unsent', reason: 'Customer canceled the EFS request.' })
    expect(requests.resolve.mock.calls[0][2]).not.toHaveProperty('transfer_not_sent_confirmed')
  })
  it('fails closed on an allocation from another invoice', () => {
    show(allocation(projection({ invoice_id: 'other-invoice' })))
    expect(screen.getByRole('alert')).toHaveTextContent('Payment details changed')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('does not offer any actions without server resolution metadata', () => {
    show({ ...allocation(), resolution: undefined })
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('refreshes a stale request without automatically resubmitting', async () => {
    const error = new AxiosError('Conflict')
    error.response = { status: 409, statusText: 'Conflict', headers: new AxiosHeaders(), config: { headers: new AxiosHeaders() }, data: { detail: { code: 'stale_attempt_version', message: 'This payment request changed. Refresh before continuing.' } } }
    requests.resolve.mockRejectedValue(error)
    const { client } = show()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    await assertUnsent()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel request', exact: true }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Refresh before continuing')
    expect(requests.resolve).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['invoice-settlement', 'authenticated', summary.invoice_id], exact: true })
  })
  it('gives staff a support path without allowing release of missing binding', async () => {
    const row = allocation(projection({ rail: 'card', checkout_status: 'review_required', actions: { ...noActions, request_review: true } }))
    requests.detail.mockResolvedValue(detail(false))
    show(row, 'staff')
    await userEvent.click(screen.getByRole('button', { name: 'Review payment outcome' }))
    expect(await screen.findByText('Get provider support confirmation for this exact request.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Verify and release request' })).not.toBeInTheDocument()
  })
  it('uses server binding and a distinct one-time grant for evidence-based release', async () => {
    const row = allocation(projection({ rail: 'card', checkout_status: 'review_required', actions: { ...noActions, release_with_terminal_evidence: true } }))
    show(row, 'staff')
    await userEvent.click(screen.getByRole('button', { name: 'Review payment outcome' }))
    await screen.findByRole('button', { name: 'No charge can complete' })
    expect(screen.getByRole('button', { name: 'Verify and release request' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'No charge can complete' }))
    fireEvent.change(screen.getByLabelText('Provider case reference'), { target: { value: 'CASE-FICTIONAL-1' } })
    fireEvent.change(screen.getByLabelText('Evidence reference'), { target: { value: 'Provider support confirmation CASE-FICTIONAL-1' } })
    fireEvent.change(screen.getByLabelText('Provider confirmation'), { target: { value: 'Provider confirmed this exact merchant request was never accepted and cannot complete.' } })
    fireEvent.change(screen.getByLabelText('Reason for release'), { target: { value: 'Verified terminal support confirmation.' } })
    fireEvent.change(screen.getByLabelText('Your password'), { target: { value: 'fictional-test-only' } })
    await userEvent.click(screen.getByRole('button', { name: 'Verify and release request' }))
    await waitFor(() => expect(requests.resolve).toHaveBeenCalledTimes(1))
    expect(requests.grant).toHaveBeenCalledWith('fictional-test-only', 'payments.attempts.resolve')
    const command = requests.resolve.mock.calls[0][2]
    expect(command.evidence).toMatchObject({ provider_account_id: 'fictional-merchant', environment: 'sandbox', provider_request_id: 'fictional-request', evidence_context_sha256: 'a'.repeat(64) })
    expect(command.evidence).not.toHaveProperty('requested_principal')
    expect(requests.resolve.mock.calls[0][4]).toBe('fictional-one-time-grant')
  })
  it('keeps active requests visible and canceled attempts under history', async () => {
    const client = new QueryClient()
    const past = allocation(cancelled().resolution)
    past.id = past.attempt_id = 'past-zelle'
    past.resolution = { ...past.resolution!, attempt_id: past.attempt_id }
    past.state = 'failed'
    render(<QueryClientProvider client={client}><SettlementSummaryCard streamlined audience="customer" summary={summary} allocations={[allocation(), past]} resolutionControls={{ access, audience: 'customer', onUpdated: vi.fn() }} /></QueryClientProvider>)
    expect(screen.getByRole('button', { name: 'Payment not sent?' })).toBeInTheDocument()
    expect(screen.queryByText('Request canceled')).not.toBeInTheDocument()
    const history = screen.getByRole('button', { name: 'Payment history (1)' })
    expect(history).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(history)
    expect(screen.getByText('Request canceled')).toBeInTheDocument()
    expect(screen.getByText('Canceled. No payment recorded.')).toBeInTheDocument()
    expect(requests.resolve).not.toHaveBeenCalled()
  })
  it('reveals an exact canceled history link and focuses its row', async () => {
    const past = allocation(cancelled().resolution)
    render(<SettlementSummaryCard streamlined audience="customer" summary={released} allocations={[past]} reviewAttemptId={past.attempt_id} />)
    await waitFor(() => expect(document.getElementById(`payment-request-${past.attempt_id}`)).toHaveFocus())
    expect(screen.getByRole('button', { name: 'Payment history (1)' })).toHaveAttribute('aria-expanded', 'true')
  })
  it('keeps a received payment in history without cancellation controls', async () => {
    const received = allocation(projection({ checkout_status: 'received', attempt_state: 'confirmed', actions: noActions }))
    received.state = 'confirmed'
    render(<QueryClientProvider client={new QueryClient()}><SettlementSummaryCard streamlined audience="customer" summary={released} allocations={[received]} resolutionControls={{ access, audience: 'customer', onUpdated: vi.fn() }} /></QueryClientProvider>)
    expect(screen.queryByRole('list', { name: 'Active payment requests' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Payment history (1)' }))
    expect(screen.getByText('Payment received')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel checkout' })).not.toBeInTheDocument()
  })
  it('announces a newly closed request while moving it into history', async () => {
    const props = { streamlined: true, audience: 'customer' as const, summary, allocations: [allocation()] }
    const { rerender } = render(<SettlementSummaryCard {...props} />)
    const closed = allocation(cancelled().resolution)
    closed.state = 'failed'
    rerender(<SettlementSummaryCard {...props} summary={released} allocations={[closed]} />)
    expect(await screen.findByRole('status')).toHaveTextContent('Request canceled.')
    expect(screen.getByRole('button', { name: 'Payment history (1)' })).toHaveFocus()
    expect(screen.queryByText('Request canceled')).not.toBeInTheDocument()
  })
  it('explains the next step while all payment amounts are reserved', () => {
    const card = allocation(projection({ rail: 'card', checkout_status: 'checkout_started' }))
    render(<QueryClientProvider client={new QueryClient()}><SettlementSummaryCard streamlined audience="customer" summary={summary} allocations={[card]} resolutionControls={{ access, audience: 'customer', onUpdated: vi.fn() }} /></QueryClientProvider>)
    expect(screen.getByRole('heading', { name: 'Payment options paused' })).toBeInTheDocument()
    expect(screen.getByText('Cancel this checkout to choose a payment method.')).toBeInTheDocument()
    expect(screen.queryByText('Don’t pay an amount in progress again.')).not.toBeInTheDocument()
  })
  it('makes waiting ownership clear without allowing another payment or cancellation', () => {
    const row = allocation(projection({ rail: 'card', checkout_status: 'review_required', actions: noActions, review_status: 'requested', block_reason: { code: 'provider_review_required', message: 'Review required.' } }))
    render(<QueryClientProvider client={new QueryClient()}><SettlementSummaryCard streamlined audience="customer" summary={summary} allocations={[row]} resolutionControls={{ access, audience: 'customer', onUpdated: vi.fn() }} /></QueryClientProvider>)
    expect(screen.getByRole('heading', { name: 'Waiting for confirmation' })).toBeInTheDocument()
    expect(screen.getByText('The shop will update this invoice. Don’t pay this amount again.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel checkout' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Choose payment method' })).not.toBeInTheDocument()
  })
  it('hands off to payment methods only after confirmed cancellation frees an amount', async () => {
    const props = { streamlined: true, audience: 'customer' as const, summary, allocations: [allocation()] }
    const { rerender } = render(<><SettlementSummaryCard {...props} /><h2 tabIndex={-1} id={`settlement-payment-${summary.invoice_id}`}>Payment method</h2></>)
    const closed = allocation(cancelled().resolution); closed.state = 'failed'
    rerender(<><SettlementSummaryCard {...props} summary={released} allocations={[closed]} /><h2 tabIndex={-1} id={`settlement-payment-${summary.invoice_id}`}>Payment method</h2></>)
    await userEvent.click(await screen.findByRole('button', { name: 'Choose payment method' }))
    expect(screen.getByRole('heading', { name: 'Payment method' })).toHaveFocus()
    expect(requests.resolve).not.toHaveBeenCalled()
    expect(requests.create).not.toHaveBeenCalled()
  })
  it('does not retain a cancellation success message after a newer payment update', async () => {
    const props = { streamlined: true, audience: 'customer' as const, summary, allocations: [allocation()] }
    const { rerender } = render(<SettlementSummaryCard {...props} />)
    const closed = allocation(cancelled().resolution); closed.state = 'failed'
    rerender(<SettlementSummaryCard {...props} summary={released} allocations={[closed]} />)
    expect(await screen.findByRole('status')).toHaveTextContent('Request canceled.')
    rerender(<SettlementSummaryCard {...props} summary={{ ...released, version: released.version + 1 }} allocations={[closed]} />)
    expect(screen.queryByText('Request canceled.')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Choose payment method' })).not.toBeInTheDocument()
  })
  it('keeps a historical review warning visible while canceled history is collapsed', () => {
    const terminal = allocation(cancelled().resolution)
    terminal.state = 'failed'
    terminal.resolution = { ...terminal.resolution!, can_retry: false, block_reason: { code: 'legacy_projection_review_required', message: 'Review this transfer.' } }
    render(<SettlementSummaryCard streamlined audience="customer" summary={released} allocations={[terminal]} />)
    expect(screen.getByRole('status')).toHaveTextContent('The shop needs to review an earlier payment before you try again.')
    expect(screen.getByRole('button', { name: 'Payment history (1)' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('button', { name: 'Choose payment method' })).not.toBeInTheDocument()
  })
  it('preserves a canceled legacy request that still requires shop review', () => {
    const terminal = cancelled().resolution
    terminal.block_reason = { code: 'legacy_projection_review_required', message: 'The shop must review this transfer before another payment.' }
    terminal.resolution_notice!.message = 'Payment request canceled. The shop must review this transfer before another payment.'
    show(allocation(terminal))
    expect(screen.getByRole('status')).toHaveTextContent('The shop must review this transfer')
    expect(screen.queryByText('Canceled. No payment recorded.')).not.toBeInTheDocument()
  })
  it('opens payment choices after cancellation without creating a new payment', async () => {
    const terminal = allocation(cancelled().resolution)
    const client = new QueryClient()
    const props = { access, summary: released, allocation: terminal, audience: 'customer' as const, onUpdated: vi.fn() }
    render(<QueryClientProvider client={client}><h2 tabIndex={-1} id={`settlement-payment-${summary.invoice_id}`}>Payment method</h2><Controls {...props} /></QueryClientProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Pay remaining' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Payment method' })).toHaveFocus())
    expect(requests.resolve).not.toHaveBeenCalled()
  })
})
