import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BookingPage from '../BookingPage'
import ServicesPage from '../../services/ServicesPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), user: { tenant_id: 'tenant-a', customer_id: 'customer-a', id: 'user-a' } }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (select: (state: unknown) => unknown) => select({ user: mocks.user }) }))
const service = { id: 'oil', is_active: true, name: 'Oil and filter service', description: 'Scheduled maintenance', computed_total_price: '123.45', duration_minutes: 60, requires_vehicle: true, category_id: 'maintenance' }
const capability = { available: true, provider: 'quickbooks_payments', token_url: 'https://sandbox.api.intuit.com/quickbooks/v4/payments/tokens', shop_timezone: 'America/New_York', currency: 'usd' }
const truck = { id: 'truck-a', unit_number: '123', make: 'Volvo', model: 'SOURCE MODEL', year: 2021, license_plate: 'ABC123' }
function Location() { const location = useLocation(); return <div data-testid="location">{location.pathname}{location.search}</div> }
function mount(url = '/portal/book/oil?vehicle_id=truck-a') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[url]}><Location /><Routes><Route path="/portal/book/:serviceId" element={<BookingPage />} /><Route path="/portal/services" element={<ServicesPage />} /></Routes></MemoryRouter></QueryClientProvider>)
  return client
}
beforeEach(() => {
  mocks.get.mockReset(); mocks.post.mockReset()
  mocks.get.mockImplementation(async (url: string) => {
    if (url === '/appointments/payment-capability') return { data: capability }
    if (url === '/appointments/appointment-a') return { data: { id: 'appointment-a', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', status: 'pending', price: '123.45', currency: 'usd', version: 1, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: 'unpaid_hold' } }
    if (url === '/vehicles') return { data: [truck] }
    if (url === '/services/categories') return { data: [{ id: 'maintenance', name: 'Maintenance' }] }
    if (url === '/services') return { data: [service, { ...service, id: 'inactive', name: 'Hidden service', is_active: false }] }
    if (url === '/services/oil') return { data: service }
    if (url.startsWith('/appointments/available-slots')) return { data: [{ time: '09:00', starts_at: '2026-11-04T14:00:00Z', timezone: 'America/New_York', available: true }, { time: '10:00', starts_at: '2026-11-04T15:00:00Z', timezone: 'America/New_York', available: false }] }
    throw new Error(`Unexpected GET ${url}`)
  })
})
async function reserve() {
  if (screen.queryByRole('heading', { name: 'Choose a date and time' }) || screen.queryByRole('heading', { name: 'Which vehicle?' })) return
  fireEvent.click(await screen.findByRole('button', { name: /^Reserve a time/ }))
}
afterEach(cleanup)
describe('real portal service and booking journey', () => {
  it('uses catalog metadata and preserves scoped vehicle when choosing a real active service', async () => {
    mount('/portal/services?vehicle_id=truck-a')
    fireEvent.click(await screen.findByRole('button', { name: /Maintenance Oil changes/ }))
    expect(screen.queryByText('Hidden service')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Choose/ }))
    await reserve()
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    expect(screen.getByTestId('location')).toHaveTextContent('/portal/book/oil?vehicle_id=truck-a')
    expect(screen.getAllByText(/Unit #123.*2021 Volvo.*ABC123/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/SOURCE MODEL/)).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('classifies title-case catalog names for every common need', async () => {
    const get = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/payment-capability' ? { data: capability } : url === '/services' ? { data: [
      { ...service, id: 'oil', name: 'Oil Change', description: null, category_id: null },
      { ...service, id: 'inspection', name: 'DOT Inspection', description: null, category_id: null },
      { ...service, id: 'brakes', name: 'Brake Repair', description: null, category_id: null },
      { ...service, id: 'diagnostic', name: 'Diagnostic Visit', description: null, category_id: null },
    ] } : get(url))
    mount('/portal/services')
    for (const [need, title] of [['Maintenance', 'Oil Change'], ['Inspection', 'DOT Inspection'], ['Brakes & tires', 'Brake Repair'], ['Something wrong', 'Diagnostic Visit']]) {
      fireEvent.click(await screen.findByRole('button', { name: new RegExp(`^${need}`) }))
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'All common needs' }))
    }
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('returns from service search to common needs with a cleared search field', async () => {
    mount('/portal/services')
    const search = await screen.findByRole('textbox', { name: 'Search services or describe a concern' })
    fireEvent.change(search, { target: { value: 'Oil' } })
    expect(screen.getByRole('heading', { name: 'Results for “Oil”' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'All common needs' }))
    expect(search).toHaveValue('')
    expect(screen.queryByRole('heading', { name: /Results for/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Maintenance Oil changes/ })).toBeInTheDocument()
  })
  it('keeps keyboard focus on the new step heading and stable through availability refetches', async () => {
    const user = userEvent.setup()
    const client = mount()
    await reserve()
    const dateHeading = await screen.findByRole('heading', { name: 'Choose a date and time' })
    // Choosing a booking path is explicit and focuses its first step.
    expect(dateHeading).toHaveFocus()
    await user.click(await screen.findByRole('button', { name: '09:00' }))
    screen.getByRole('button', { name: 'Continue' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('heading', { name: 'Anything the shop should know?' })).toHaveFocus()
    screen.getByRole('button', { name: 'Review visit' }).focus()
    await user.keyboard('{Enter}')
    const reviewHeading = screen.getByRole('heading', { name: 'Review your visit' })
    expect(reviewHeading).toHaveFocus()
    await client.refetchQueries({ queryKey: ['time-slots'] })
    expect(reviewHeading).toHaveFocus()
    screen.getByRole('button', { name: 'Back' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('heading', { name: 'Anything the shop should know?' })).toHaveFocus()
    screen.getByRole('button', { name: 'Back' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('heading', { name: 'Choose a date and time' })).toHaveFocus()
    screen.getByRole('button', { name: 'Back' }).focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('heading', { name: 'Which vehicle?' })).toHaveFocus()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('has named steps, actual available times, and notes before review with no write before explicit confirmation', async () => {
    mount()
    await reserve()
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    await reserve()
    fireEvent.click(await screen.findByRole('button', { name: '09:00' }))
    expect(screen.queryByRole('button', { name: '10:00' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Notes (optional)' }), { target: { value: 'Check a noise' } })
    fireEvent.click(screen.getByRole('button', { name: 'Review visit' }))
    expect(screen.getByRole('heading', { name: 'Review your visit' })).toBeInTheDocument()
    expect(screen.getByText('Check a noise')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
    mocks.post.mockResolvedValue({ data: { id: 'appointment-a', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', status: 'pending', price: '123.45', currency: 'usd', version: 1, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: 'unpaid_hold' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Continue to payment' }))
    await screen.findByRole('heading', { name: 'Payment' })
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.post).toHaveBeenCalledWith('/appointments', expect.objectContaining({ service_id: 'oil', vehicle_id: 'truck-a', customer_notes: 'Check a noise', scheduled_at: '2026-11-04T14:00:00Z', booking_kind: 'reserve' }), expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }))
  })
  it('skips the known single vehicle once and respects Back across a vehicle refetch', async () => {
    const client = mount('/portal/book/oil')
    await reserve()
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    expect(screen.getByText('Unit #123 · 2021 Volvo · ABC123')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await reserve()
    await screen.findByRole('heading', { name: 'Which vehicle?' })
    await client.refetchQueries({ queryKey: ['vehicles'] })
    expect(screen.getByRole('heading', { name: 'Which vehicle?' })).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('rechecks availability on review and blocks a slot that became unavailable', async () => {
    let slotReads = 0
    const get = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => {
    if (url === '/appointments/payment-capability') return { data: capability }
    if (url === '/appointments/appointment-a') return { data: { id: 'appointment-a', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', status: 'pending', price: '123.45', currency: 'usd', version: 1, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: 'unpaid_hold' } }
      if (url.startsWith('/appointments/')) return { data: [{ time: '09:00', starts_at: '2026-11-04T14:00:00Z', timezone: 'America/New_York', available: ++slotReads === 1 }] }
      return get(url)
    })
    mount()
    await reserve()
    fireEvent.click(await screen.findByRole('button', { name: '09:00' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review visit' }))
    await screen.findByText('This time is no longer available or couldn’t be verified. Choose an available time to continue.')
    expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Continue to payment' }))
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('rejects a foreign URL rather than selecting the authorized first vehicle', async () => {
    mount('/portal/book/oil?vehicle_id=foreign')
    expect(await screen.findByRole('heading', { name: 'Vehicle unavailable' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continue' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('blocks indistinguishable vehicle choices for review', async () => {
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/payment-capability' ? { data: capability } : ({ data: url === '/vehicles' ? [truck, { ...truck, id: 'truck-b' }] : service }))
    mount()
    await reserve()
    await screen.findByRole('heading', { name: 'Which vehicle?' })
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.getAllByText('Details need review — contact the shop')).toHaveLength(2)
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('skips vehicle selection for a service that requires no vehicle and handles empty availability', async () => {
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/payment-capability' ? { data: capability } : ({ data: url === '/vehicles' ? [] : url.startsWith('/appointments/') ? [] : { ...service, requires_vehicle: false } }))
    mount('/portal/book/oil')
    await reserve()
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    await screen.findByText('No available times for this date. Choose another date.')
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.queryByRole('heading', { name: 'Which vehicle?' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not select the first vehicle when multiple authorized choices exist', async () => {
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/payment-capability' ? { data: capability } : ({ data: url === '/vehicles' ? [truck, { ...truck, id: 'truck-b', unit_number: '456' }] : service }))
    mount('/portal/book/oil')
    await reserve()
    await screen.findByRole('heading', { name: 'Which vehicle?' })
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Unit #456/ }))
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Choose another service' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/portal/services?vehicle_id=truck-b')
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not force a scoped vehicle into a no-vehicle service request', async () => {
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/payment-capability' ? { data: capability } : url === '/appointments/appointment-a' ? { data: { id: 'appointment-a', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', status: 'pending', price: '123.45', currency: 'usd', version: 1, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: 'unpaid_hold' } } : ({ data: url === '/vehicles' ? [truck] : url.startsWith('/appointments/') ? [{ time: '09:00', starts_at: '2026-11-04T14:00:00Z', timezone: 'America/New_York', available: true }] : { ...service, requires_vehicle: false } }))
    mocks.post.mockResolvedValue({ data: { id: 'appointment-a', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', status: 'pending', price: '123.45', currency: 'usd', version: 1, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: 'unpaid_hold' } })
    mount()
    await reserve()
    fireEvent.click(await screen.findByRole('button', { name: '09:00' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review visit' }))
    expect(mocks.post).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Continue to payment' }))
    await screen.findByRole('heading', { name: 'Payment' })
    expect(mocks.post).toHaveBeenCalledWith('/appointments', expect.objectContaining({ vehicle_id: null }), expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }))
  })
  it('shows retry on slot failure and never manufactures availability', async () => {
    mocks.get.mockImplementation(async (url: string) => {
    if (url === '/appointments/payment-capability') return { data: capability }
    if (url === '/appointments/appointment-a') return { data: { id: 'appointment-a', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', status: 'pending', price: '123.45', currency: 'usd', version: 1, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: 'unpaid_hold' } }
      if (url.startsWith('/appointments/')) throw new Error('Offline')
      return { data: url === '/vehicles' ? [truck] : service }
    })
    mount()
    await reserve()
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    await screen.findByText('Available times couldn’t be loaded.')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('shows retry on read failure rather than an empty vehicle account', async () => {
    mocks.get.mockRejectedValue(new Error('Offline'))
    mount()
    expect(await screen.findByRole('heading', { name: 'Booking unavailable' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
    expect(screen.queryByText(/No vehicles registered/)).not.toBeInTheDocument()
  })
  it('keeps tenant/customer identity in cache keys and the existing invalidation roots', async () => {
    const client = mount()
    await reserve()
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    expect(client.getQueryCache().getAll().map(query => query.queryKey)).toEqual(expect.arrayContaining([['vehicles', 'tenant-a', 'customer-a'], ['service', 'oil', 'tenant-a', 'customer-a']]))
  })
})

describe('visit requests and the one-time booking choice', () => {
  it.each([
    ['paid', 'inactive service'], ['payment_processing', 'inactive service'],
    ['paid', 'missing service'], ['payment_processing', 'missing service'],
    ['paid', 'retired vehicle'], ['payment_processing', 'retired vehicle'],
    ['paid', 'vehicles unavailable'], ['payment_processing', 'vehicles unavailable'],
  ])('recovers a %s reservation despite %s without creating or paying again', async (paymentState, unavailable) => {
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => {
      if (url === '/appointments/retained') return { data: { id: 'retained', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', vehicle_id: 'truck-a', status: paymentState === 'paid' ? 'confirmed' : 'pending', price: '123.45', currency: 'usd', version: 2, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: paymentState, receipt: paymentState === 'paid' ? { id: 'verified-receipt' } : null } }
      if (url === '/services/oil' && unavailable === 'inactive service') return { data: { ...service, is_active: false } }
      if (url === '/services/oil' && unavailable === 'missing service') throw new Error('Service not found')
      if (url === '/vehicles' && unavailable === 'retired vehicle') return { data: [] }
      if (url === '/vehicles' && unavailable === 'vehicles unavailable') throw new Error('Vehicles unavailable')
      return original(url)
    })
    mount('/portal/book/oil?vehicle_id=truck-a&reservation_id=retained')
    expect(await screen.findByRole('heading', { name: paymentState === 'paid' ? 'Time reserved' : 'Payment verification pending' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Service unavailable|Vehicle unavailable|Booking unavailable/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Pay.*reserve/ })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('recovers an existing processing reservation from its URL without creating or charging again', async () => {
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/appointment-a' ? { data: { id: 'appointment-a', booking_kind: 'reserve', service_id: 'oil', customer_id: 'customer-a', status: 'pending', price: '123.45', currency: 'usd', version: 2, price_snapshot_sha256: 'hash', hold_expires_at: new Date(Date.now() + 900000).toISOString(), booking_payment_state: 'payment_processing' } } : original(url))
    mount('/portal/book/oil?vehicle_id=truck-a&reservation_id=appointment-a')
    expect(await screen.findByRole('heading', { name: 'Payment verification pending' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'How would you like to visit?' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Pay.*reserve/ })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('rejects reservation recovery for a different customer without falling back to new checkout', async () => {
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/foreign' ? { data: { id: 'foreign', booking_kind: 'reserve', service_id: 'oil', customer_id: 'foreign-customer' } } : original(url))
    mount('/portal/book/oil?reservation_id=foreign')
    expect(await screen.findByRole('heading', { name: 'Reservation unavailable' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Reserve a time/ })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('keeps the initial choice visible for a preselected vehicle and does not read slots', async () => {
    mount()
    expect(await screen.findByRole('heading', { name: 'How would you like to visit?' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Request a visit/ })).toBeEnabled()
    expect(mocks.get.mock.calls.some(([url]) => String(url).includes('available-slots'))).toBe(false)
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('sends an unpaid date-only request without any reservation, availability or payment call', async () => {
    mocks.post.mockResolvedValueOnce({ data: { id: 'request-a', booking_kind: 'request', request_reference: 'VR-123', status: 'requested', preferred_date: null } })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: /^Request a visit/ }))
    expect(screen.getByLabelText('Preferred visit date (optional)')).toHaveValue('')
    expect(screen.queryByText('Available times')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Notes (optional)' }), { target: { value: 'Please check a noise' } })
    fireEvent.click(screen.getByRole('button', { name: 'Review request' }))
    expect(screen.getByText('No payment now')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Continue to payment' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByRole('textbox', { name: 'Notes (optional)' })).toHaveValue('Please check a noise')
    fireEvent.click(screen.getByRole('button', { name: 'Review request' }))
    expect(screen.queryByRole('heading', { name: 'How would you like to visit?' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Send request' }))
    expect(await screen.findByRole('heading', { name: 'Visit request sent' })).toBeInTheDocument()
    expect(screen.getByText(/The shop will confirm availability. No start time is reserved./)).toBeInTheDocument()
    expect(mocks.post).toHaveBeenCalledExactlyOnceWith('/visit-requests', { service_id: 'oil', vehicle_id: 'truck-a', customer_notes: 'Please check a noise', preferred_date: null }, { headers: { 'Idempotency-Key': expect.any(String) } })
    expect(mocks.get.mock.calls.some(([url]) => String(url).includes('available-slots'))).toBe(false)
    expect(mocks.post.mock.calls.some(([url]) => String(url).includes('appointments'))).toBe(false)
  })
  it('allows requests when the selected payment provider is unavailable', async () => {
    const original = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => url === '/appointments/payment-capability' ? { data: { ...capability, available: false, message: 'Online payments unavailable.' } } : original(url))
    mount()
    expect(await screen.findByRole('button', { name: /^Reserve a time/ })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /^Request a visit/ }))
    expect(screen.getByRole('heading', { name: 'When would you prefer to visit?' })).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
})
