import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import AppointmentsPage from '../AppointmentsPage'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
const base = { customer_id: 'customer-a', vehicle_id: 'truck-a', service_id: 'oil', service_name: 'Oil service', scheduled_at: '2099-11-04T14:00:00Z', duration_minutes: 60, status: 'pending', price: '123.45', confirmation_number: 'REFERENCE', created_at: '2026-11-03T12:00:00Z' }
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/portal/appointments?vehicle_id=truck-a']}><AppointmentsPage /></MemoryRouter></QueryClientProvider>)
  return client
}
beforeEach(() => {
  useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false, authProvider: 'legacy', authSessionEpoch: 1, user: { id: 'customer-user', tenant_id: 'tenant-a', customer_id: 'customer-a', first_name: 'Alex', last_name: 'Driver', email: 'alex@example.test', role: 'customer', is_active: true } })
  mocks.get.mockReset(); mocks.post.mockReset()
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/vehicles') return { data: [{ id: 'truck-a', unit_number: '12', make: 'Volvo' }] }
    if (url === '/appointments') return { data: [] }
    if (url === '/appointments/visit-requests') return { data: [] }
    throw new Error('Unexpected read')
  })
})
describe('portal reservations and unpaid requests', () => {
  it('loads every scoped request page and presents no invented price, exact time or payment action', async () => {
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string, config: { params?: { skip?: number }; signal?: AbortSignal }) => {
      if (url !== '/appointments/visit-requests') return original(url, config)
      return { data: { items: [{ id: config.params?.skip ? 'request-b' : 'request-a', booking_kind: 'request', request_reference: config.params?.skip ? 'VR-B' : 'VR-A', service_name: 'Inspection request', vehicle_id: 'truck-a', status: 'requested', preferred_date: config.params?.skip ? null : '2099-11-04' }], skip: config.params?.skip || 0, limit: 100, has_more: !config.params?.skip } }
    })
    mount()
    const section = await screen.findByRole('region', { name: 'Visit requests' })
    expect(await within(section).findByText('Request VR-B')).toBeInTheDocument()
    expect(within(section).getByText('Preferred date:')).toHaveTextContent('Nov 4, 2099')
    expect(within(section).getAllByText(/No start time is reserved/)).toHaveLength(2)
    expect(within(section).getAllByText('Unit #12 · Volvo')).toHaveLength(2)
    expect(within(section).queryByText(/\$|09:00|confirmed|paid/i)).not.toBeInTheDocument()
    expect(within(section).queryByRole('button', { name: /pay|confirm/i })).not.toBeInTheDocument()
    const reads = mocks.get.mock.calls.filter(([url]) => url === '/appointments/visit-requests')
    expect(reads).toHaveLength(2)
    expect(reads[0][1].signal).toBeInstanceOf(AbortSignal)
    expect(reads[1][1].signal).toBe(reads[0][1].signal)
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('uses server hold/payment states and keeps legacy confirmed appointment cancellation available', async () => {
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => url === '/appointments' ? { data: [
      { ...base, id: 'hold', booking_payment_state: 'unpaid_hold' },
      { ...base, id: 'expired', booking_payment_state: 'expired_unpaid' },
      { ...base, id: 'processing', booking_payment_state: 'payment_processing' },
      { ...base, id: 'review', booking_payment_state: 'payment_received_review' },
      { ...base, id: 'paid', status: 'confirmed', booking_payment_state: 'paid', receipt: { id: 'receipt-a' } },
      { ...base, id: 'legacy', status: 'confirmed', service_name: 'Legacy confirmed service' },
    ] } : original(url))
    mount()
    expect(await screen.findByText('Payment needed · time not confirmed')).toBeInTheDocument()
    expect(screen.getByText('Checkout expired')).toBeInTheDocument()
    expect(screen.getByText('Payment verification pending')).toBeInTheDocument()
    expect(screen.getByText('Payment received · shop review needed')).toBeInTheDocument()
    expect(screen.getByText('Confirmed · payment verified')).toBeInTheDocument()
    const processing = screen.getByText('Payment verification pending').closest('article')!
    expect(within(processing).getByRole('link', { name: 'Check reservation' })).toHaveAttribute('href', '/portal/book/oil?reservation_id=processing&vehicle_id=truck-a')
    for (const state of ['Checkout expired', 'Payment verification pending']) {
      const row = screen.getByText(state).closest('article')!
      expect(within(row).queryByRole('button', { name: /pay|cancel/i })).not.toBeInTheDocument()
      expect(within(row).queryByText(/^Confirmation /)).not.toBeInTheDocument()
    }
    const legacy = screen.getByText('Legacy confirmed service').closest('article')!
    expect(within(legacy).getByRole('button', { name: 'Cancel' })).toBeEnabled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('hides cached request rows after a failed refresh and offers a specific retry', async () => {
    let failed = false
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => {
      if (url !== '/appointments/visit-requests') return original(url)
      if (failed) throw new Error('Unavailable')
      return { data: [{ id: 'request-a', request_reference: 'VR-A', status: 'requested', service_name: 'Requested inspection' }] }
    })
    const client = mount()
    expect(await screen.findByText('Requested inspection')).toBeInTheDocument()
    failed = true
    await act(async () => { await client.refetchQueries({ queryKey: ['visit-requests', 'tenant-a', 'customer-a'] }) })
    expect(await screen.findByText('Visit requests couldn’t load.')).toBeInTheDocument()
    expect(screen.queryByText('Requested inspection')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try requests again' })).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
})
