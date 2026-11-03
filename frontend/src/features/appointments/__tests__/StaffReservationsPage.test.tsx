import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import StaffReservationsPage from '../StaffReservationsPage'
import type { BookingAccountingTask, BookingPrepaymentView, StaffBooking } from '../booking-fulfillment'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ appearance: { mode: 'dark' }, mode: 'dark' }) }))
const vehicle = { id: 'truck-a', unit_number: '12', make: 'Volvo', model: 'VNR', year: 2021, license_plate: 'ABC123' }
const order = { id: 'ro-a', customer_id: 'customer-a', vehicle_id: 'truck-a', order_number: 'RO-123', status: 'completed', description: 'Inspection completed', source: null, vehicle_unit_number: '12' }
function task(overrides: Partial<BookingAccountingTask> = {}): BookingAccountingTask {
  return { id: 'task-liability', object_kind: 'booking_receipt_liability', state: 'awaiting_manual_ack', version: 1, amount_minor: 26844, currency: 'usd', evidence_snapshot_sha256: 'proof-a', ...overrides }
}
function prepayment(overrides: Partial<BookingPrepaymentView> = {}): BookingPrepaymentView {
  return { appointment_id: 'booking-a', repair_order_id: 'ro-a', invoice_id: null, application_id: null, booking_version: 2, receipt: { id: 'receipt-a', version: 1, currency: 'usd', received_minor: 26844, refunded_minor: 0, applied_minor: 0, unapplied_minor: 26844 }, invoice_preview: { currency: 'usd', invoice_total_minor: 31402, allocatable_principal_minor: 31402, suggested_apply_minor: 26844, remaining_minor: 4558, invoice_economics_sha256: 'economics-a' }, accounting: { mode: 'external_manual', state: 'awaiting_manual_ack', export_hold: true, tasks: [task()] }, shop_timezone: 'America/New_York', customer: { id: 'customer-a', display_name: 'Alex Driver', company_name: 'Sample Fleet' }, vehicle, can_apply: true, ...overrides }
}
function appointment(view: BookingPrepaymentView | null = prepayment()): StaffBooking {
  return { id: 'booking-a', confirmation_number: 'BOOK-A', customer_id: 'customer-a', vehicle_id: view?.vehicle?.id || null, service_id: 'service-a', service_name: 'Inspection', scheduled_at: '2099-11-04T14:00:00Z', duration_minutes: 60, status: 'confirmed', price: '268.44', customer_notes: null, paid_at: '2026-11-03T12:00:00Z', created_at: '2026-11-03T12:00:00Z', booking_kind: 'reserve', booking_payment_version: 1, booking_payment_state: 'paid', prepayment: view }
}
let current: StaffBooking
function mount(selected = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[selected ? '/dashboard/visit-requests?view=reservations&appointment_id=booking-a' : '/dashboard/visit-requests?view=reservations']}><StaffReservationsPage/></MemoryRouter></QueryClientProvider>)
  return client
}
beforeEach(() => {
  mocks.get.mockReset(); mocks.post.mockReset()
  current = appointment()
  useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false, authProvider: 'legacy', authSessionEpoch: 1, user: { id: 'staff-a', tenant_id: 'tenant-a', customer_id: null, first_name: 'Staff', last_name: 'Owner', email: 'staff@example.test', role: 'garage_owner', is_active: true } })
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/appointments') return { data: [current] }
    if (url === '/appointments/booking-a') return { data: current }
    if (url === '/customers/customer-a') return { data: { id: 'customer-a', company_name: 'Sample Fleet', first_name: 'Alex', last_name: 'Driver' } }
    if (url === '/vehicles/truck-a') return { data: vehicle }
    if (url === '/repair-orders/ro-a') return { data: order }
    if (url === '/repair-orders') return { data: [order, { ...order, id: 'ro-foreign', customer_id: 'customer-other', order_number: 'RO-FOREIGN' }] }
    if (url === '/vehicles') return { data: [vehicle] }
    throw new Error(`Unexpected read ${url}`)
  })
})
async function openApplication() {
  const button = await screen.findByRole('button', { name: 'Review invoice & prepayment' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  const dialog = screen.getByRole('dialog', { name: 'Issue invoice and apply prepayment' })
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Confirm application' })).toBeEnabled())
  return dialog
}
describe('staff prepaid reservation operations', () => {
  it('discovers reservations using actual authorized customer and vehicle names without creating records', async () => {
    mount(false)
    expect(await screen.findByText('Sample Fleet')).toBeInTheDocument()
    expect(await screen.findByText('Unit #12 · 2021 Volvo · ABC123')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review reservation' })).toBeInTheDocument()
    expect(screen.queryByText('customer-a')).not.toBeInTheDocument()
    expect(screen.queryByText('truck-a')).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each(['missing capability', 'missing preview', 'zero suggestion'])('disables application when the server provides %s', async missing => {
    current = appointment(prepayment(missing === 'missing capability' ? { can_apply: undefined } : missing === 'missing preview' ? { invoice_preview: null } : { invoice_preview: { ...prepayment().invoice_preview!, suggested_apply_minor: 0 } }))
    mount()
    expect(await screen.findByRole('region', { name: 'Prepayment summary' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review invoice & prepayment' })).toBeDisabled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('confirms only the server-proposed amount and invoice economics with no second provider payment', async () => {
    mocks.post.mockImplementationOnce(async () => {
      current = appointment(prepayment({ invoice_id: 'invoice-a', application_id: 'application-a', booking_version: 3, can_apply: false, invoice_preview: null, receipt: { ...prepayment().receipt, version: 2, applied_minor: 26844, unapplied_minor: 0 } }))
      return { data: { ...current.prepayment } }
    })
    mount()
    const dialog = await openApplication()
    expect(within(dialog).getByText('Sample Fleet')).toBeInTheDocument()
    expect(within(dialog).getByText('Unit #12 · 2021 Volvo · ABC123')).toBeInTheDocument()
    expect(within(dialog).getByText('RO-123')).toBeInTheDocument()
    expect(within(dialog).getByText('$314.02')).toBeInTheDocument()
    expect(within(dialog).getByText('$268.44')).toBeInTheDocument()
    expect(within(dialog).getByText('$45.58')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm application' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/appointments/booking-a/issue-invoice-with-prepayment', { repair_order_id: 'ro-a', receipt_id: 'receipt-a', expected_booking_version: 2, expected_receipt_version: 1, expected_invoice_economics_sha256: 'economics-a', amount_minor: 26844, invoice_options: {}, accounting_mode: 'external_manual' }, { headers: { 'Idempotency-Key': expect.any(String) } }))
    expect(mocks.post.mock.calls.some(([url]) => /charge|payment-attempts|confirm-payment/.test(url))).toBe(false)
  })
  it('requires a refreshed explicit confirmation when authoritative invoice economics change', async () => {
    mocks.post.mockImplementationOnce(async () => {
      current = appointment(prepayment({ invoice_preview: { ...prepayment().invoice_preview!, invoice_total_minor: 35000, remaining_minor: 8156, invoice_economics_sha256: 'economics-b' } }))
      throw { response: { status: 409, data: { detail: { code: 'booking_invoice_economics_changed', message: 'Invoice total changed. Review the updated proposal.' } } } }
    })
    mount()
    const dialog = await openApplication()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm application' }))
    expect(await within(dialog).findByText('Updated invoice total · $350.00')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Confirm application' })).toBeDisabled()
    expect(mocks.post).toHaveBeenCalledTimes(1)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Use refreshed details' }))
    expect(within(dialog).getByText('$350.00')).toBeInTheDocument()
    expect(within(dialog).getByText('$81.56')).toBeInTheDocument()
    expect(mocks.post).toHaveBeenCalledTimes(1)
    mocks.post.mockResolvedValueOnce({ data: { appointment_id: 'booking-a', invoice_id: 'invoice-a', application_id: 'application-a', receipt: { id: 'receipt-a' } } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm application' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    expect(mocks.post.mock.calls[1][1].expected_invoice_economics_sha256).toBe('economics-b')
  })
  it('links an explicit repair order and separately reviewed intake vehicle without applying funds', async () => {
    current = appointment(prepayment({ repair_order_id: null, vehicle: null, can_apply: false, invoice_preview: null }))
    mocks.post.mockResolvedValueOnce({ data: { appointment_id: 'booking-a', repair_order_id: 'ro-a' } })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Link repair order' }))
    const dialog = screen.getByRole('dialog', { name: 'Link repair order' })
    const submit = within(dialog).getByRole('button', { name: 'Link repair order' })
    const picker = within(dialog).getByRole('combobox', { name: 'Booking repair order' })
    await waitFor(() => expect(picker).toBeEnabled())
    fireEvent.click(picker)
    expect(screen.queryByRole('option', { name: /RO-FOREIGN/ })).not.toBeInTheDocument()
    fireEvent.mouseDown(await screen.findByRole('option', { name: /RO-123/ }))
    fireEvent.change(within(dialog).getByLabelText('Reason for linking'), { target: { value: 'Actual intake reviewed with driver' } })
    expect(submit).toBeDisabled()
    const unitPicker = within(dialog).getByRole('combobox', { name: 'Booking intake vehicle' })
    await waitFor(() => expect(unitPicker).toBeEnabled())
    fireEvent.click(unitPicker)
    fireEvent.mouseDown(await screen.findByRole('option', { name: /Unit #12/ }))
    expect(mocks.post).not.toHaveBeenCalled()
    fireEvent.click(submit)
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/appointments/booking-a/repair-order-link', { repair_order_id: 'ro-a', expected_booking_version: 2, reason: 'Actual intake reviewed with driver', expected_vehicle_id: 'truck-a' }, { headers: { 'Idempotency-Key': expect.any(String) } }))
  })
  it.each([false, true])('records only the truthful bookkeeping assertions for the task (application=%s)', async application => {
    const tasks = application ? [task({ state: 'externally_reconciled' }), task({ id: 'task-application', object_kind: 'booking_receipt_application' })] : [task()]
    current = appointment(prepayment({ application_id: application ? 'application-a' : null, invoice_id: application ? 'invoice-a' : null, can_apply: false, accounting: { ...prepayment().accounting, tasks } }))
    mocks.post.mockResolvedValueOnce({ data: { appointment_id: 'booking-a', accounting: { state: 'externally_reconciled', export_hold: true } } })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Record external bookkeeping' }))
    const dialog = screen.getByRole('dialog', { name: 'Record external bookkeeping' })
    const submit = within(dialog).getByRole('button', { name: 'Save bookkeeping review' })
    fireEvent.change(within(dialog).getByLabelText('Evidence reference'), { target: { value: 'Journal 2026-1103' } })
    fireEvent.change(within(dialog).getByLabelText('External company reference'), { target: { value: 'Reviewed company reference' } })
    fireEvent.change(within(dialog).getByLabelText('Review note'), { target: { value: 'Entries verified against actual records' } })
    expect(submit).toBeDisabled()
    const receiptCheck = within(dialog).getByRole('checkbox', { name: 'Receipt liability entry completed' })
    expect(receiptCheck).not.toBeChecked()
    fireEvent.click(receiptCheck)
    if (application) {
      expect(submit).toBeDisabled()
      const applicationCheck = within(dialog).getByRole('checkbox', { name: 'Prepayment application to receivables completed' })
      expect(applicationCheck).not.toBeChecked()
      fireEvent.click(applicationCheck)
    } else expect(within(dialog).queryByRole('checkbox', { name: 'Prepayment application to receivables completed' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
    fireEvent.click(submit)
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`/appointments/booking-a/accounting-reviews/${application ? 'task-application' : 'task-liability'}/acknowledge`, { expected_version: 1, evidence_reference: 'Journal 2026-1103', external_company_reference: 'Reviewed company reference', receipt_liability_recorded: true, application_to_ar_recorded: application, review_note: 'Entries verified against actual records' }, { headers: { 'Idempotency-Key': expect.any(String) } }))
  })
  it('keeps bookkeeping acknowledgment unavailable to a receptionist', async () => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role: 'receptionist' } })
    mount()
    expect(await screen.findByRole('heading', { name: 'External bookkeeping' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Record external bookkeeping' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not offer application or linking for a cancelled reservation', async () => {
    current = { ...appointment(), status: 'cancelled' }
    mount()
    expect(await screen.findByText('Cancelled · payment on record')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review invoice & prepayment' })).toBeDisabled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('keeps an application draft but blocks its confirmation after a failed booking read', async () => {
    const client = mount()
    const dialog = await openApplication()
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => { if (url === '/appointments/booking-a') throw new Error('Unavailable'); return original(url) })
    await act(async () => { await client.refetchQueries({ queryKey: ['staff-reservation-detail'] }) })
    expect(await within(dialog).findByText('Previous proposal · refresh required')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Confirm application' })).toBeDisabled()
    expect(within(dialog).getByRole('button', { name: 'Refresh saved booking' })).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not offer application bookkeeping review before the receipt entry has been reviewed', async () => {
    current = appointment(prepayment({ application_id: 'application-a', invoice_id: 'invoice-a', can_apply: false, accounting: { ...prepayment().accounting, tasks: [task(), task({ id: 'task-application', object_kind: 'booking_receipt_application' })] } }))
    mount()
    expect(await screen.findByRole('heading', { name: 'External bookkeeping' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Record external bookkeeping' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Record external bookkeeping' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).queryByRole('checkbox', { name: 'Prepayment application to receivables completed' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each(['verified', 'pending', 'review_required', 'failed'])('checks only an existing QBO refund reference with truthful %s feedback', async state => {
    current = appointment(prepayment({ receipt: { ...prepayment().receipt, provider: 'quickbooks_payments' } }))
    mocks.post.mockResolvedValueOnce({ data: { ...current.prepayment, refund_verification: { state, refund_id: 'QBO opaque/refund?42' } } })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Verify existing refund' }))
    const dialog = screen.getByRole('dialog', { name: 'Verify existing refund' })
    expect(within(dialog).getByText('Check a refund already issued in QuickBooks.')).toBeInTheDocument()
    expect(within(dialog).queryByRole('spinbutton')).not.toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('QuickBooks refund reference'), { target: { value: 'QBO opaque/refund?42' } })
    expect(mocks.post).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify existing refund' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/appointments/booking-a/refund-verifications', { refund_id: 'QBO opaque/refund?42', expected_receipt_version: 1, expected_booking_version: 2 }, { headers: { 'Idempotency-Key': expect.any(String) } }))
    const feedback = state === 'verified' ? 'Existing refund verified' : state === 'pending' ? 'Refund verification pending. Verified amounts remain unchanged.' : state === 'failed' ? 'The existing refund could not be verified. Verified amounts remain unchanged.' : 'Refund needs review. Verified amounts remain unchanged.'
    expect(await screen.findByText(feedback)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Prepayment summary' })).toHaveTextContent('$268.44')
  })
  it.each(['stripe_connect', undefined, 'receptionist'])('does not offer existing QBO refund verification for %s', async scope => {
    current = appointment(prepayment({ receipt: { ...prepayment().receipt, provider: scope === 'receptionist' ? 'quickbooks_payments' : scope as 'stripe_connect' | undefined } }))
    if (scope === 'receptionist') useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role: 'receptionist' } })
    mount()
    await screen.findByRole('heading', { name: 'External bookkeeping' })
    expect(screen.queryByRole('button', { name: 'Verify existing refund' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('preserves an unknown refund reference and requires a successful saved read before an explicit retry', async () => {
    current = appointment(prepayment({ receipt: { ...prepayment().receipt, provider: 'quickbooks_payments' } }))
    mocks.post.mockRejectedValueOnce(new Error('Network interrupted'))
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Verify existing refund' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('QuickBooks refund reference'), { target: { value: 'existing-reference' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify existing refund' }))
    expect(await within(dialog).findByText(/Verification could not be completed/)).toBeInTheDocument()
    expect(within(dialog).getByLabelText('QuickBooks refund reference')).toHaveValue('existing-reference')
    expect(within(dialog).getByRole('button', { name: 'Verify existing refund' })).toBeDisabled()
    expect(mocks.post).toHaveBeenCalledTimes(1)
    current = appointment(prepayment({ booking_version: 3, receipt: { ...prepayment().receipt, version: 2, provider: 'quickbooks_payments' } }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Refresh saved reservation' }))
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Verify existing refund' })).toBeEnabled())
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(within(dialog).getByLabelText('QuickBooks refund reference')).toBeDisabled()
    mocks.post.mockResolvedValueOnce({ data: { ...current.prepayment, refund_verification: { state: 'pending', refund_id: 'existing-reference' } } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Verify existing refund' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    expect(mocks.post.mock.calls[1]).toEqual(mocks.post.mock.calls[0])
  })

  it('pauses prepayment application while refund verification is pending', async () => {
    current = appointment(prepayment({ refund_verification_pending: true, can_apply: true, receipt: { ...prepayment().receipt, provider: 'quickbooks_payments' } }))
    mount()
    await screen.findByRole('heading', { name: 'External bookkeeping' })
    expect(screen.getByRole('button', { name: 'Review invoice & prepayment' })).toBeDisabled()
    expect(screen.getByText(/Refund verification pending. The received/)).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('preserves known receipt amounts while an unknown unapplied balance requires review and blocks application', async () => {
    current = appointment(prepayment({ receipt: { ...prepayment().receipt, refunded_minor: 1200, applied_minor: 30000, unapplied_minor: null }, can_apply: true }))
    mount()
    const summary = await screen.findByRole('region', { name: 'Prepayment summary' })
    expect(within(summary).getByText('$268.44')).toBeInTheDocument()
    expect(within(summary).getByText('$12.00')).toBeInTheDocument()
    expect(within(summary).getByText('$300.00')).toBeInTheDocument()
    expect(within(summary).getByText('Unavailable')).toBeInTheDocument()
    expect(within(summary).queryByText('$0.00')).not.toBeInTheDocument()
    expect(within(summary).getByText('Unapplied prepayment needs review before funds can be applied.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Review invoice & prepayment' })).toBeDisabled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each(['needs_review', 'externally_reconciled'] as const)('does not offer bookkeeping acknowledgment for task state %s', async state => {
    current = appointment(prepayment({ accounting: { ...prepayment().accounting, tasks: [task({ state })] } }))
    mount()
    await screen.findByRole('heading', { name: 'External bookkeeping' })
    expect(screen.queryByRole('button', { name: 'Record external bookkeeping' })).not.toBeInTheDocument()
    if (state === 'needs_review') expect(screen.getByText(/Payment details changed · bookkeeping needs review/)).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('blocks an open acknowledgment when the saved task moves to review even without a version change', async () => {
    const client = mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Record external bookkeeping' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Evidence reference'), { target: { value: 'Actual journal reference' } })
    fireEvent.change(within(dialog).getByLabelText('External company reference'), { target: { value: 'Actual company' } })
    fireEvent.change(within(dialog).getByLabelText('Review note'), { target: { value: 'Reviewed records' } })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'Receipt liability entry completed' }))
    expect(within(dialog).getByRole('button', { name: 'Save bookkeeping review' })).toBeEnabled()
    current = appointment(prepayment({ accounting: { ...prepayment().accounting, tasks: [task({ state: 'needs_review' })] } }))
    await act(async () => { await client.refetchQueries({ queryKey: ['staff-reservation-detail'] }) })
    expect(await within(dialog).findByText('Payment details changed. Bookkeeping needs review before it can be recorded.')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Save bookkeeping review' })).toBeDisabled()
    expect(within(dialog).getByLabelText('Evidence reference')).toHaveValue('Actual journal reference')
    expect(mocks.post).not.toHaveBeenCalled()
  })

  it('distinguishes matching customer, vehicle and service reservations by their actual shop-local schedule', async () => {
    const first = { ...appointment(), scheduled_at: '2026-11-04T14:00:00Z' }
    const second = { ...appointment(), id: 'booking-b', scheduled_at: '2026-11-05T16:30:00Z', prepayment: { ...prepayment(), appointment_id: 'booking-b' } }
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => url === '/appointments' ? { data: [first, second] } : original(url))
    mount(false)
    const firstSchedule = await screen.findByText(/Scheduled · Nov 4, 2026.*9:00 AM EST/)
    const secondSchedule = screen.getByText(/Scheduled · Nov 5, 2026.*11:30 AM EST/)
    for (const schedule of [firstSchedule, secondSchedule]) {
      const card = schedule.closest('article')!
      expect(within(card).getByText('Inspection')).toBeInTheDocument()
      expect(within(card).getAllByRole('button')).toHaveLength(1)
      expect(within(card).getByRole('button', { name: 'Review reservation' })).toBeInTheDocument()
    }
    expect(firstSchedule.closest('article')).not.toBe(secondSchedule.closest('article'))
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each(['missing zone', 'invalid zone', 'invalid timestamp'])('shows unavailable scheduling when the server provides %s', async invalid => {
    current = { ...appointment(prepayment({ shop_timezone: invalid === 'missing zone' ? '' : invalid === 'invalid zone' ? 'Unknown/Shop' : 'America/New_York' })), scheduled_at: invalid === 'invalid timestamp' ? 'not-a-date' : '2026-11-04T14:00:00Z' }
    mount(false)
    expect(await screen.findByText('Scheduled · Unavailable')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Review reservation' })).toHaveLength(1)
    expect(mocks.post).not.toHaveBeenCalled()
  })

})
