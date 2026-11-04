import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import type { VisitRequestResult } from '@/features/booking/booking-contract'
import CustomerVisitRequestCard from '../CustomerVisitRequestCard'
const mocks = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: { post: mocks.post } }))
function request(overrides: Partial<VisitRequestResult> = {}): VisitRequestResult {
  return { id: 'request-a', booking_kind: 'request', request_reference: 'VR-A', status: 'accepted', version: 2, service_name: 'Inspection', preferred_date: '2099-11-03', accepted_arrival_date: '2099-11-04', customer_notes: 'Check an air leak', ...overrides }
}
function mount(row = request()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><CustomerVisitRequestCard request={row} vehicleLabel="Unit #12 · 2021 Volvo"/></QueryClientProvider>)
  return client
}
beforeEach(() => {
  mocks.post.mockReset()
  useAuthStore.setState({ isAuthenticated: true, logoutInProgress: false, authProvider: 'legacy', authSessionEpoch: 1, user: { id: 'customer-user', tenant_id: 'tenant-a', customer_id: 'customer-a', email: 'customer@example.test', first_name: 'Alex', last_name: 'Driver', role: 'customer', is_active: true } })
})
describe('customer visit request states', () => {
  it('shows an accepted calendar date without a reserved time, price or payment promise', () => {
    const row = { ...request(), internal_review_note: 'STAFF ONLY NOTE' }
    mount(row)
    expect(screen.getByRole('heading', { name: 'Visit accepted' })).toBeInTheDocument()
    expect(screen.getByText('Nov 4, 2099')).toHaveAttribute('datetime', '2099-11-04')
    expect(screen.getByText(/The shop will start as availability allows/)).toHaveTextContent('Arrive on Nov 4, 2099.')
    expect(screen.getByText('Unit #12 · 2021 Volvo')).toBeInTheDocument()
    expect(screen.queryByText('STAFF ONLY NOTE')).not.toBeInTheDocument()
    expect(screen.queryByText(/\$|09:00|^Paid$|^Confirmed$|^Reserved$/)).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it.each([['declined', 'Request declined'], ['withdrawn', 'Request withdrawn'], ['fulfilled', 'Visit checked in']] as const)('shows %s without a reserved/paid badge or withdrawal action', (status, label) => {
    mount(request({ status, accepted_arrival_date: null }))
    expect(screen.getByRole('heading', { name: label })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Withdraw request' })).not.toBeInTheDocument()
    expect(screen.queryByText(/\$|09:00|^Paid$|^Confirmed$|^Reserved$/)).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('withdraws only after explicit confirmation with the server version and a stable action key', async () => {
    mocks.post.mockResolvedValueOnce({ data: { request: request({ status: 'withdrawn', version: 3 }) } })
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw request' }))
    expect(mocks.post).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Withdraw', exact: true }))
    await waitFor(() => expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/appointments/visit-requests/request-a/withdraw', { expected_version: 2 }, { headers: { 'Idempotency-Key': expect.any(String) } }))
    expect(mocks.post.mock.calls.some(([url]) => /payment|cancel|charge/.test(url))).toBe(false)
  })
})
