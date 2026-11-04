import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import VisitRequestsPage, { VisitRequestsEntry } from '../VisitRequestsPage'
import type { StaffVisitRequest } from '../visit-requests'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ appearance: { mode: 'dark' }, mode: 'dark' }) }))
function request(overrides: Partial<StaffVisitRequest> = {}): StaffVisitRequest {
  return { id: 'request-a', request_reference: 'VR-A', status: 'requested', version: 1, customer: { id: 'customer-a', display_name: 'Alex Driver', company_name: 'Sample Fleet', email: 'alex@example.test', phone: null }, service: { id: 'service-a', name: 'Inspection' }, vehicle: { id: 'truck-a', unit_number: '12', make: 'Volvo', model: 'Source model', year: 2021, license_plate: 'ABC123' }, preferred_date: '2099-11-04', accepted_arrival_date: null, customer_notes: 'Check an air leak', internal_review_note: 'Staff context', created_at: '2026-11-03T12:00:00Z', reviewed_at: null, can_review: true, ...overrides }
}
function mount(entry = false, url = '/dashboard/visit-requests') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}>{entry ? <VisitRequestsEntry/> : <VisitRequestsPage/>}</MemoryRouter></QueryClientProvider>)
  return client
}
beforeEach(() => {
  mocks.get.mockReset(); mocks.post.mockReset()
  useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false, authProvider: 'legacy', authSessionEpoch: 1, user: { id: 'staff-a', tenant_id: 'tenant-a', customer_id: null, email: 'staff@example.test', first_name: 'Staff', last_name: 'Owner', role: 'garage_owner', is_active: true } })
  mocks.get.mockResolvedValue({ data: [request()] })
})
describe('staff visit request review', () => {
  it('switches familiar request/reservation context tabs without a new primary navigation or writes', async () => {
    mocks.get.mockImplementation(async (url: string) => {
      if (url === '/appointments') return { data: [{ id: 'booking-a', customer_id: 'customer-a', vehicle_id: 'truck-a', service_name: 'Reserved inspection', booking_payment_state: 'paid', status: 'confirmed' }] }
      if (url === '/customers/customer-a') return { data: { id: 'customer-a', company_name: 'Reservation Fleet' } }
      if (url === '/vehicles/truck-a') return { data: request().vehicle }
      return { data: [request()] }
    })
    mount()
    const navigation = screen.getByRole('navigation', { name: 'Service visit sections' })
    expect(within(navigation).getAllByRole('link')).toHaveLength(2)
    fireEvent.click(within(navigation).getByRole('link', { name: 'Reservations' }))
    expect(await screen.findByText('Reservation Fleet')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Reservations' })).toBeInTheDocument()
    fireEvent.click(within(navigation).getByRole('link', { name: 'Requests', exact: true }))
    expect(await screen.findByText('Check an air leak')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('shows actual customer, vehicle, service and notes with complete pagination and a pending count', async () => {
    mocks.get.mockImplementation(async (_url: string, config: { params: { skip: number } }) => ({ data: { items: [request({ id: config.params.skip ? 'request-b' : 'request-a', status: config.params.skip ? 'accepted' : 'requested' })], skip: config.params.skip, limit: 100, has_more: !config.params.skip } }))
    mount(true)
    expect(await screen.findByText('1 request awaiting review')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review visits' })).toHaveAttribute('href', '/dashboard/visit-requests')
    expect(mocks.get).toHaveBeenCalledTimes(2)
    expect(mocks.get.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal)
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('accepts an arrival date explicitly without creating an appointment, payment or notification', async () => {
    mocks.post.mockResolvedValueOnce({ data: { request: request({ status: 'accepted', version: 2, accepted_arrival_date: '2099-11-05' }) } })
    mount()
    expect(await screen.findByText('Sample Fleet')).toBeInTheDocument()
    expect(screen.getByText('Alex Driver')).toBeInTheDocument()
    expect(screen.getByText('Unit #12 · 2021 Volvo · ABC123')).toBeInTheDocument()
    expect(screen.getByText('Check an air leak')).toBeInTheDocument()
    expect(screen.getByText(/Staff context/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Accept visit' }))
    const dialog = await screen.findByRole('dialog', { name: 'Accept visit' })
    expect(within(dialog).getByText('No guaranteed start time. The shop will start as availability allows.')).toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('Arrival date'), { target: { value: '2099-11-05' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept visit' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/appointments/visit-requests/request-a/accept', { expected_version: 1, arrival_date: '2099-11-05' }, { headers: { 'Idempotency-Key': expect.any(String) } }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
  it.each([['Start review', 'review', 'availability_review'], ['Decline', 'decline', 'declined']] as const)('performs the explicit %s action with its version and staff note', async (label, action, status) => {
    mocks.post.mockResolvedValueOnce({ data: { request: request({ status, version: 2 }) } })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: label, exact: true }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Staff note (optional)'), { target: { value: 'Customer preference reviewed' } })
    fireEvent.click(within(dialog).getByRole('button', { name: action === 'review' ? 'Start review' : 'Decline visit request' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith(`/appointments/visit-requests/request-a/${action}`, { expected_version: 1, internal_note: 'Customer preference reviewed' }, { headers: { 'Idempotency-Key': expect.any(String) } }))
  })
  it('preserves a stale draft, refreshes the saved version and never automatically replays the action', async () => {
    let latest = false
    mocks.get.mockImplementation(async () => ({ data: [request({ version: latest ? 2 : 1, status: latest ? 'availability_review' : 'requested' })] }))
    mocks.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: { code: 'visit_request_version_conflict' } } } })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Accept visit' }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Arrival date'), { target: { value: '2099-11-06' } })
    fireEvent.change(within(dialog).getByLabelText('Staff note (optional)'), { target: { value: 'Afternoon intake discussed' } })
    latest = true
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept visit' }))
    expect(await within(dialog).findByText('Saved state: Shop is reviewing')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Arrival date')).toHaveValue('2099-11-06')
    expect(within(dialog).getByLabelText('Staff note (optional)')).toHaveValue('Afternoon intake discussed')
    expect(within(dialog).getByRole('button', { name: 'Accept visit' })).toBeDisabled()
    expect(mocks.post).toHaveBeenCalledTimes(1)
    const firstKey = mocks.post.mock.calls[0][2].headers['Idempotency-Key']
    fireEvent.click(within(dialog).getByRole('button', { name: 'Keep draft and review again' }))
    expect(mocks.post).toHaveBeenCalledTimes(1)
    mocks.post.mockResolvedValueOnce({ data: { request: request({ status: 'accepted', version: 3 }) } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Accept visit' }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2))
    expect(mocks.post.mock.calls[1][1]).toEqual({ expected_version: 2, arrival_date: '2099-11-06', internal_note: 'Afternoon intake discussed' })
    expect(mocks.post.mock.calls[1][2].headers['Idempotency-Key']).not.toBe(firstKey)
  })
  it('forbids unsupported staff roles without loading the queue', () => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, role: 'mechanic' } })
    mount()
    expect(screen.getByRole('heading', { name: 'Visit requests unavailable' })).toBeInTheDocument()
    expect(mocks.get).not.toHaveBeenCalled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('drops an open action draft when the staff account changes', async () => {
    mount()
    fireEvent.click(await screen.findByRole('button', { name: 'Accept visit' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await act(async () => { useAuthStore.setState({ authSessionEpoch: 2, user: { ...useAuthStore.getState().user!, id: 'staff-b', tenant_id: 'tenant-b' } }) })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not display a failed queue read as zero pending requests', async () => {
    mocks.get.mockRejectedValue(new Error('Unavailable'))
    mount(true)
    expect(await screen.findByText('Requests couldn’t load')).toBeInTheDocument()
    expect(screen.queryByText('0 requests awaiting review')).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each([false, true])('records check-in only against an explicit exact intake selection (vehicleless=%s)', async vehicleless => {
    mocks.get.mockImplementation(async (url: string) => {
      if (url === '/appointments/visit-requests') return { data: [request({ status: 'accepted', can_review: false, can_accept: true, can_fulfill: true, accepted_arrival_date: '2099-11-04', vehicle: vehicleless ? null : request().vehicle })] }
      if (url === '/repair-orders') return { data: [{ id: 'ro-a', customer_id: 'customer-a', vehicle_id: 'truck-a', order_number: 'RO-123', status: 'in_progress', source: null, description: 'Actual intake' }, { id: 'ro-foreign', customer_id: 'customer-other', vehicle_id: 'truck-a', order_number: 'RO-FOREIGN', status: 'in_progress' }] }
      if (url === '/vehicles') return { data: [request().vehicle] }
      throw new Error('Unexpected read')
    })
    mocks.post.mockResolvedValueOnce({ data: { request: request({ status: 'fulfilled', version: 2 }) } })
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'All requests' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Record check-in' }))
    const dialog = screen.getByRole('dialog', { name: 'Record check-in' })
    const submit = within(dialog).getByRole('button', { name: 'Record check-in' })
    expect(submit).toBeDisabled()
    const orderPicker = within(dialog).getByRole('combobox', { name: 'Intake repair order' })
    await waitFor(() => expect(orderPicker).toBeEnabled())
    fireEvent.click(orderPicker)
    fireEvent.mouseDown(await screen.findByRole('option', { name: /RO-123/ }))
    expect(screen.queryByRole('option', { name: /RO-FOREIGN/ })).not.toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('Staff note (reason for check-in)'), { target: { value: 'Driver arrived and intake verified' } })
    if (vehicleless) {
      expect(submit).toBeDisabled()
      const vehiclePicker = within(dialog).getByRole('combobox', { name: 'Vehicle reviewed at intake' })
      await waitFor(() => expect(vehiclePicker).toBeEnabled())
      fireEvent.click(vehiclePicker)
      fireEvent.mouseDown(await screen.findByRole('option', { name: /Unit #12/ }))
    }
    expect(submit).toBeEnabled()
    expect(mocks.post).not.toHaveBeenCalled()
    fireEvent.click(submit)
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/appointments/visit-requests/request-a/fulfill', { expected_version: 1, repair_order_id: 'ro-a', reason: 'Driver arrived and intake verified', ...(vehicleless ? { expected_vehicle_id: 'truck-a' } : {}) }, { headers: { 'Idempotency-Key': expect.any(String) } }))
    expect(mocks.post.mock.calls.some(([url]) => /payment|charge|invoice|repair-orders/.test(url))).toBe(false)
  })
  it('requires a reason before amending an already accepted arrival date', async () => {
    mocks.get.mockResolvedValue({ data: [request({ status: 'accepted', can_review: false, can_accept: true, version: 7, accepted_arrival_date: '2099-11-05' })] })
    mocks.post.mockResolvedValueOnce({ data: { request: request({ status: 'accepted', version: 8, accepted_arrival_date: '2099-11-06' }) } })
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'All requests' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Change arrival date' }))
    const dialog = screen.getByRole('dialog', { name: 'Change arrival date' })
    const submit = within(dialog).getByRole('button', { name: 'Change arrival date' })
    expect(within(dialog).getByLabelText('Arrival date')).toHaveValue('2099-11-05')
    fireEvent.change(within(dialog).getByLabelText('Arrival date'), { target: { value: '2099-11-06' } })
    expect(submit).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('Staff note (reason for change)'), { target: { value: 'Customer requested the following day' } })
    fireEvent.click(submit)
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/appointments/visit-requests/request-a/accept', { expected_version: 7, arrival_date: '2099-11-06', internal_note: 'Customer requested the following day' }, { headers: { 'Idempotency-Key': expect.any(String) } }))
    expect(dialog.querySelector('input[type=datetime-local]')).toBeNull()
  })
})
