import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { garageOwnerSession } from '@/test-fixtures/db035/staffSession'
import { useAuthStore } from '@/stores/authStore'
import { DB048_SETTLEMENT_FIXTURES } from '@/test-fixtures/db048/settlements'
import type { EfsAttemptResponse, EfsSubmissionSummary } from '../efsApi'
import type { InvoiceSettlementSummary, PaymentAllocation } from '../types'

const api = vi.hoisted(() => ({ submit: vi.fn(), reveal: vi.fn(), verify: vi.fn(), genericCreate: vi.fn(), genericConfirm: vi.fn(), grant: vi.fn() }))
vi.mock('../efsApi', async original => ({ ...await original<typeof import('../efsApi')>(), submitEfsCode: api.submit, revealEfsCode: api.reveal, verifyEfsCode: api.verify }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), createPaymentAttempt: api.genericCreate, confirmPaymentAttempt: api.genericConfirm }))
vi.mock('@/lib/paymentStepUp', async original => ({ ...await original<typeof import('@/lib/paymentStepUp')>(), createPaymentStepUpGrant: api.grant }))
vi.mock('@/lib/stripe', () => ({ getStripeForAccount: vi.fn() }))
import EfsSubmissionForm from '../EfsSubmissionForm'
import EfsReviewControls from '../EfsReviewControls'
import PendingManualPaymentPanel from '../PendingManualPaymentPanel'
import SettlementPaymentPanel from '../SettlementPaymentPanel'
import SettlementSummaryCard from '../SettlementSummaryCard'

const secret = '0123456789'
const summary: InvoiceSettlementSummary = { ...DB048_SETTLEMENT_FIXTURES.unpaid.summary, principal_total: '268.44', outstanding_balance: '268.44', allocatable_balance: '268.44', version: 2, allowed_actions: { create_attempt: true, confirm_manual: true, submit_efs: true, rails: ['card', 'zelle'] } }
const efs: EfsSubmissionSummary = { provider: 'EFS', code_last4: '6789', status: 'awaiting_verification', can_cancel: true, can_reveal: false, can_verify: false, can_reject: false, can_resolve_received_difference: false, difference_review: null }
const reserved: InvoiceSettlementSummary = { ...summary, version: 3, active_pending_principal: '100.00', allocatable_balance: '168.44', state: 'payment_pending' }
function response(): EfsAttemptResponse {
  return { attempt_id: 'fictional-efs', invoice_id: summary.invoice_id, principal_amount: '100.00', card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: '100.00', rail: 'fleet_payment', provider: 'manual', state: 'pending', expires_at: null, provider_configuration_version: 1, attempt_version: 1, settlement: reserved, efs }
}
const row: PaymentAllocation = { id: 'fictional-efs', attempt_id: 'fictional-efs', attempt_version: 1, rail: 'fleet_payment', provider: 'manual', state: 'pending', principal_amount: '100.00', applied_principal_amount: '0.00', card_fee_amount: '0.00', card_fee_tax_amount: '0.00', provider_charge_amount: '100.00', unapplied_amount: '0.00', created_at: '2026-11-04T12:00:00Z', efs: { ...efs, can_reveal: true, can_verify: true, can_reject: true } }
function wrap(node: React.ReactNode, client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })) {
  return { ...render(<QueryClientProvider client={client}>{node}</QueryClientProvider>), client }
}
function submitForm(guest = false) {
  const onUpdated = vi.fn()
  const access = guest ? { kind: 'guest' as const, token: 'fictional-access' } : { kind: 'authenticated' as const, invoiceId: summary.invoice_id }
  return { ...wrap(<EfsSubmissionForm access={access} summary={summary} amount="100.00" tone="dark" onUpdated={onUpdated} />), onUpdated, access }
}
async function reviewCode() {
  await userEvent.type(screen.getByLabelText('EFS MoneyCode', { exact: true }), secret)
  await userEvent.click(screen.getByRole('button', { name: 'Review EFS payment', exact: true }))
}
beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ authSessionEpoch: 0, user: garageOwnerSession, isAuthenticated: true })
  HTMLElement.prototype.scrollIntoView = vi.fn()
  api.grant.mockResolvedValue({ grant_token: 'fictional-efs-grant' })
  api.submit.mockResolvedValue(response())
  api.reveal.mockResolvedValue({ code: secret, last4: '6789' })
  api.verify.mockResolvedValue({ ...response(), state: 'confirmed', efs: { ...efs, status: 'received' }, settlement: { ...reserved, version: 4, active_pending_principal: '0.00', confirmed_principal: '100.00', outstanding_balance: '168.44' } })
})

describe('customer EFS code submission', () => {
  it.each([false, true])('reviews a masked code before an explicit submission (guest=%s)', async guest => {
    const { onUpdated, access, client } = submitForm(guest)
    await reviewCode()
    expect(screen.getByRole('heading', { name: 'Review EFS payment' })).toHaveFocus()
    expect(screen.getByText('Ending in 6789')).toBeInTheDocument()
    expect(screen.queryByText(secret)).not.toBeInTheDocument()
    expect(api.submit).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Submit for verification' }))
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(reserved))
    expect(api.submit).toHaveBeenCalledWith(access, { code: secret, amount: '100.00', expected_settlement_version: 2, submitted_for_verification: true }, expect.any(String))
    expect(screen.getByLabelText('EFS MoneyCode', { exact: true })).toHaveValue('')
    expect(JSON.stringify(client.getQueryCache().getAll().map(query => query.state.data))).not.toContain(secret)
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain(secret)
    expect(api.genericCreate).not.toHaveBeenCalled()
    expect(api.genericConfirm).not.toHaveBeenCalled()
  })
  it.each(['customer', 'guest'] as const)('keeps the available amount and focus when %s switches methods', async audience => {
    const access = audience === 'guest' ? { kind: 'guest' as const, token: 'fictional-access' } : { kind: 'authenticated' as const, invoiceId: reserved.invoice_id }
    wrap(<><SettlementSummaryCard audience="customer" streamlined hideAvailable summary={reserved} />
      <SettlementPaymentPanel access={access} summary={reserved} audience={audience} onUpdated={vi.fn()} /></>)
    expect(screen.getByText('Pending confirmation')).toBeInTheDocument()
    expect(screen.getByText('$100.00')).toBeInTheDocument()
    expect(screen.queryByText('Available to pay')).not.toBeInTheDocument()
    expect(screen.queryByText(/Up to/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pay in full', exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Partial payment' })).not.toHaveAttribute('aria-pressed')
    const amount = screen.getByLabelText('Payment amount')
    expect(amount).toHaveValue('168.44')
    await userEvent.click(screen.getByRole('button', { name: 'Partial payment', exact: true }))
    expect(amount).toHaveFocus()
    await userEvent.type(amount, '50.00')
    expect(screen.getByRole('button', { name: 'Use available' })).not.toHaveAttribute('aria-pressed')
    for (const method of ['Zelle', 'EFS', 'Card']) {
      const radio = screen.getByRole('radio', { name: method, exact: true })
      await userEvent.click(radio)
      expect(radio).toHaveFocus()
      expect(radio).toHaveAttribute('aria-checked', 'true')
      expect(amount).toHaveValue('50.00')
    }
    expect(api.submit).not.toHaveBeenCalled()
    expect(api.genericCreate).not.toHaveBeenCalled()
  })
  it.each(['customer', 'guest'] as const)('accepts currency drafts and rejects invalid %s input or paste without changing the prior amount', async audience => {
    const user = userEvent.setup()
    const access = audience === 'guest' ? { kind: 'guest' as const, token: 'fictional-access' } : { kind: 'authenticated' as const, invoiceId: summary.invoice_id }
    wrap(<SettlementPaymentPanel access={access} summary={summary} audience={audience} onUpdated={vi.fn()} />)
    const input = screen.getByRole('textbox', { name: 'Payment amount', exact: true })
    expect(input).toHaveAttribute('type', 'text')
    expect(input).toHaveAttribute('inputmode', 'decimal')
    await user.click(screen.getByRole('button', { name: 'Partial payment' }))
    expect(input).toHaveFocus()
    for (const valid of ['', '.', '0.', '.5', '12.', '12.3', '12.34']) {
      fireEvent.change(input, { target: { value: valid } })
      expect(input).toHaveValue(valid)
    }
    for (const invalid of ['a', '12abc34', '1e2', '1E2', '-12', '+12', '1.2.3', '12.345', '１２', ' 12', '$12']) {
      fireEvent.change(input, { target: { value: invalid } })
      expect(input).toHaveValue('12.34')
    }
    await user.click(input)
    await user.keyboard('{Control>}a{/Control}')
    await user.paste('12abc34')
    expect(input).toHaveValue('12.34')
    await user.keyboard('{Control>}a{/Control}')
    await user.paste('50.25')
    expect(input).toHaveValue('50.25')
    await user.keyboard('{End}abc+-eE.9')
    expect(input).toHaveValue('50.25')
    await user.click(screen.getByRole('button', { name: 'Pay full balance' }))
    expect(input).toHaveValue('268.44')
    expect(screen.getByRole('button', { name: 'Partial payment' })).toBeInTheDocument()
    expect(api.submit).not.toHaveBeenCalled()
    expect(api.genericCreate).not.toHaveBeenCalled()
  })
  it.each(['customer', 'guest'] as const)('shows one selected-method fee note for %s without changing the principal', async audience => {
    const access = audience === 'guest' ? { kind: 'guest' as const, token: 'fictional-access' } : { kind: 'authenticated' as const, invoiceId: summary.invoice_id }
    wrap(<SettlementPaymentPanel access={access} summary={summary} audience={audience} onUpdated={vi.fn()} />)
    const notes = ['Any processing fee is shown before payment.', 'No card processing fee.', 'No card fee. EFS account fees may apply.']
    for (const [index, method] of ['Card', 'Zelle', 'EFS'].entries()) {
      await userEvent.click(screen.getByRole('radio', { name: method, exact: true }))
      expect(screen.getAllByText(notes[index], { exact: true })).toHaveLength(1)
      for (const note of notes.filter((_, other) => other !== index)) expect(screen.queryByText(note, { exact: true })).not.toBeInTheDocument()
      expect(screen.queryByText('Card fees apply to card payments.')).not.toBeInTheDocument()
      expect(screen.getByLabelText('Payment amount')).toHaveValue('268.44')
    }
    expect(api.genericCreate).not.toHaveBeenCalled()
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('returns to the local draft without submitting a code', async () => {
    submitForm(); await reviewCode()
    await userEvent.click(screen.getByRole('button', { name: 'Edit details' }))
    expect(screen.getByLabelText('EFS MoneyCode', { exact: true })).toHaveValue(secret)
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('rejects non-ASCII and incomplete codes without an HTTP call', async () => {
    submitForm()
    for (const code of ['0123', '０１２３４５６７８９', '01234-6789', '123456789x']) {
      fireEvent.change(screen.getByLabelText('EFS MoneyCode', { exact: true }), { target: { value: code } })
      expect(screen.getByRole('button', { name: 'Review EFS payment' })).toBeDisabled()
    }
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('retries an uncertain submission using the same body and request key', async () => {
    api.submit.mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce(response())
    submitForm(); await reviewCode()
    await userEvent.click(screen.getByRole('button', { name: 'Submit for verification' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Check submission' }))
    expect(api.submit.mock.calls[1]).toEqual(api.submit.mock.calls[0])
  })
  it('clears the draft and ignores a late result after identity changes', async () => {
    let finish!: (value: EfsAttemptResponse) => void
    api.submit.mockReturnValue(new Promise<EfsAttemptResponse>(resolve => { finish = resolve }))
    const { onUpdated } = submitForm(); await reviewCode()
    await userEvent.click(screen.getByRole('button', { name: 'Submit for verification' }))
    act(() => useAuthStore.setState({ authSessionEpoch: 1 }))
    await act(async () => finish(response()))
    expect(onUpdated).not.toHaveBeenCalled()
    expect(screen.getByLabelText('EFS MoneyCode', { exact: true })).toHaveValue('')
  })
  it('rejects a response for another invoice without applying its balance', async () => {
    api.submit.mockResolvedValue({ ...response(), invoice_id: 'foreign-invoice' })
    const { onUpdated } = submitForm(); await reviewCode()
    await userEvent.click(screen.getByRole('button', { name: 'Submit for verification' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('needs checking')
    expect(onUpdated).not.toHaveBeenCalled()
  })
  it('allows the dedicated EFS path when card checkout is unavailable without enabling generic fleet attempts', async () => {
    const manualOnly = { ...summary, card_provider_status: 'not_ready' as const, allowed_actions: { create_attempt: false, submit_efs: true, rails: [] } }
    wrap(<SettlementPaymentPanel access={{ kind: 'authenticated', invoiceId: summary.invoice_id }} summary={manualOnly} audience="customer" onUpdated={vi.fn()} />)
    expect(screen.getByRole('radio', { name: /^EFS/ })).toBeEnabled()
    expect(screen.queryByRole('radio', { name: 'Card', exact: true })).not.toBeInTheDocument()
    expect(screen.getByLabelText('EFS MoneyCode', { exact: true })).toBeInTheDocument()
    expect(api.genericCreate).not.toHaveBeenCalled()
  })
  it('does not infer customer EFS permission from the staff fleet rail', () => {
    wrap(<SettlementPaymentPanel access={{ kind: 'authenticated', invoiceId: summary.invoice_id }} summary={{ ...summary, allowed_actions: { create_attempt: true, submit_efs: false, rails: ['card', 'zelle', 'fleet_payment'] } }} audience="customer" onUpdated={vi.fn()} />)
    expect(screen.queryByRole('radio', { name: 'EFS', exact: true })).not.toBeInTheDocument()
  })
  it('keeps EFS alongside Card and Zelle and submits the chosen partial amount through its protected API', async () => {
    wrap(<SettlementPaymentPanel access={{ kind: 'authenticated', invoiceId: summary.invoice_id }} summary={summary} audience="customer" onUpdated={vi.fn()} />)
    expect(screen.getByRole('radio', { name: 'Card', exact: true })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Zelle', exact: true })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: 'EFS', exact: true }))
    await userEvent.click(screen.getByRole('button', { name: 'Partial payment', exact: true }))
    await userEvent.type(screen.getByRole('textbox', { name: 'Payment amount', exact: true }), '100.00')
    await reviewCode()
    await userEvent.click(screen.getByRole('button', { name: 'Submit for verification' }))
    await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1))
    expect(api.submit.mock.calls[0][1].amount).toBe('100.00')
    expect(api.genericCreate).not.toHaveBeenCalled()
  })
})

describe('shop EFS verification', () => {
  it('reveals a code only after the explicit authorized action and can hide it again', async () => {
    wrap(<EfsReviewControls summary={reserved} allocation={row} tone="light" onUpdated={vi.fn()} />)
    expect(api.reveal).not.toHaveBeenCalled()
    expect(screen.queryByText(secret)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reveal EFS code' }))
    expect(await screen.findByText(secret)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Hide code' }))
    expect(screen.queryByText(secret)).not.toBeInTheDocument()
  })
  it('requires explicit merchant verification and a separate authorization reference', async () => {
    const onUpdated = vi.fn()
    wrap(<EfsReviewControls summary={reserved} allocation={row} tone="light" onUpdated={onUpdated} />)
    expect(screen.getByRole('button', { name: 'Record verified receipt' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Merchant authorization reference'), 'QA-AUTH-1')
    expect(screen.getByRole('button', { name: 'Record verified receipt' })).toBeDisabled()
    await userEvent.click(screen.getByRole('checkbox', { name: /I verified EFS authorization/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Record verified receipt' }))
    await waitFor(() => expect(onUpdated).toHaveBeenCalled())
    expect(api.verify.mock.calls[0][1]).toMatchObject({ action: 'confirm_received', expected_attempt_version: 1, expected_settlement_version: 3, received_amount: '100.00', merchant_authorized: true, authorization_reference: 'QA-AUTH-1' })
    expect(api.genericConfirm).not.toHaveBeenCalled()
  })
  it('requires a reason and no-receipt assertion for rejection', async () => {
    api.verify.mockResolvedValue({ ...response(), state: 'failed', efs: { ...efs, status: 'rejected' }, settlement: { ...summary, version: 4 } })
    wrap(<EfsReviewControls summary={reserved} allocation={row} tone="light" onUpdated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Reject request' }))
    expect(screen.getByRole('button', { name: 'Reject request' })).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Reason for rejection'), 'Code was declined.')
    await userEvent.click(screen.getByRole('checkbox', { name: 'No payment was received for this code.' }))
    await userEvent.click(screen.getByRole('button', { name: 'Reject request' }))
    expect(api.verify.mock.calls[0][1]).toMatchObject({ action: 'reject', reason: 'No funds received. Code was declined.' })
    expect(api.verify.mock.calls[0][1]).not.toHaveProperty('merchant_authorized')
  })
  it('ignores secret reveal results after switching identity', async () => {
    let finish!: (value: { code: string; last4: string }) => void
    api.reveal.mockReturnValue(new Promise(resolve => { finish = resolve }))
    wrap(<EfsReviewControls summary={reserved} allocation={row} tone="light" onUpdated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Reveal EFS code' }))
    act(() => useAuthStore.setState({ authSessionEpoch: 1 }))
    await act(async () => finish({ code: secret, last4: '6789' }))
    expect(screen.queryByText(secret)).not.toBeInTheDocument()
  })
  it('never offers generic manual confirmation for a protected EFS submission', () => {
    wrap(<PendingManualPaymentPanel invoiceId={summary.invoice_id} summary={reserved} allocations={[row]} onUpdated={vi.fn()} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('clears an already revealed code when payment authority is revoked without an epoch change', async () => {
    wrap(<EfsReviewControls summary={reserved} allocation={row} tone="light" onUpdated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Reveal EFS code' }))
    await screen.findByText(secret)
    act(() => useAuthStore.setState({ user: { ...garageOwnerSession, role: 'garage_admin', permissions: { payments: false } } }))
    expect(screen.queryByText(secret)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Record verified receipt' })).not.toBeInTheDocument()
  })
  it('records a genuine different amount for review rather than silently changing the requested amount', async () => {
    api.verify.mockResolvedValue({ ...response(), efs: { ...efs, status: 'review_required' }, settlement: { ...reserved, version: 4, payment_verification_required: true } })
    const onUpdated = vi.fn()
    wrap(<EfsReviewControls summary={reserved} allocation={row} tone="light" onUpdated={onUpdated} />)
    fireEvent.change(screen.getByLabelText('Amount received'), { target: { value: '150.00' } })
    await userEvent.type(screen.getByLabelText('Merchant authorization reference'), 'QA-AUTH-DIFF')
    await userEvent.click(screen.getByRole('checkbox', { name: /I verified EFS authorization/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Send difference for review' }))
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ payment_verification_required: true })))
    expect(api.verify.mock.calls[0][1].received_amount).toBe('150.00')
    expect(row.principal_amount).toBe('100.00')
  })
  it('keeps the authorized received-difference resolution reachable while other collection is paused', () => {
    const reviewRow = { ...row, efs: { ...row.efs!, status: 'review_required' as const, can_verify: false, can_reveal: false, can_reject: false, can_resolve_received_difference: true, difference_review: { observation_id: 'fictional-observation', requested_amount: '100.00', actual_received_amount: '150.00', currency: 'USD' as const, authorization_reference: 'QA-AUTH-DIFF' } } }
    wrap(<SettlementSummaryCard summary={{ ...reserved, payment_verification_required: true }} audience="staff" allocations={[reviewRow]} resolutionControls={{ access: { kind: 'authenticated', invoiceId: summary.invoice_id }, audience: 'staff', onUpdated: vi.fn() }} />)
    expect(screen.getByRole('button', { name: 'Record verified actual receipt' })).toBeDisabled()
    expect(screen.getByText('Review the received amount')).toBeInTheDocument()
    expect(api.genericConfirm).not.toHaveBeenCalled()
  })
  it('resolves only the immutable received observation using a distinct grant and stable uncertain retry', async () => {
    const reviewRow = { ...row, attempt_version: 2, efs: { ...row.efs!, status: 'review_required' as const, can_verify: false, can_reveal: false, can_reject: false, can_resolve_received_difference: true, difference_review: { observation_id: 'fictional-observation', requested_amount: '100.00', actual_received_amount: '150.00', currency: 'USD' as const, authorization_reference: 'QA-AUTH-DIFF' } } }
    api.verify.mockRejectedValueOnce(new Error('Lost response')).mockResolvedValueOnce({ ...response(), state: 'confirmed', efs: { ...efs, status: 'received' }, settlement: { ...reserved, version: 5, confirmed_principal: '150.00', outstanding_balance: '118.44', active_pending_principal: '0.00' } })
    const onUpdated = vi.fn()
    wrap(<EfsReviewControls summary={{ ...reserved, version: 4, payment_verification_required: true }} allocation={reviewRow} tone="light" onUpdated={onUpdated} />)
    expect(screen.getByText('$150.00', { exact: true })).toBeInTheDocument()
    expect(screen.queryByLabelText('Amount received')).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Reason for recording actual receipt'), 'Reviewed the actual merchant receipt.')
    await userEvent.type(screen.getByLabelText('Your password'), 'fictional-password')
    await userEvent.click(screen.getByRole('checkbox', { name: /Record the verified actual receipt/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Record verified actual receipt' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Check verification result' }))
    await waitFor(() => expect(onUpdated).toHaveBeenCalled())
    expect(api.grant).toHaveBeenCalledExactlyOnceWith('fictional-password', 'payments.efs.resolve_received_difference')
    expect(api.verify.mock.calls[0]).toEqual(api.verify.mock.calls[1])
    expect(api.verify.mock.calls[0][1]).toMatchObject({ action: 'resolve_received_difference', observation_id: 'fictional-observation', expected_attempt_version: 2, expected_settlement_version: 4 })
    expect(api.verify.mock.calls[0][1]).not.toHaveProperty('received_amount')
    expect(api.verify.mock.calls[0][1]).not.toHaveProperty('authorization_reference')
    expect(api.verify.mock.calls[0][3]).toBe('fictional-efs-grant')
  })

})
