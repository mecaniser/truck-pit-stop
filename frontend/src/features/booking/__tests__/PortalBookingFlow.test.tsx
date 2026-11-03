import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BookingPage from '../BookingPage'
import ServicesPage from '../../services/ServicesPage'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), user: { tenant_id: 'tenant-a', customer_id: 'customer-a', id: 'user-a' } }))
vi.mock('@/lib/api', () => ({ default: { get: mocks.get, post: mocks.post } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (select: (state: unknown) => unknown) => select({ user: mocks.user }) }))
const service = { id: 'oil', is_active: true, name: 'Oil and filter service', description: 'Scheduled maintenance', computed_total_price: '123.45', duration_minutes: 60, requires_vehicle: true, category_id: 'maintenance' }
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
    if (url === '/vehicles') return { data: [truck] }
    if (url === '/services/categories') return { data: [{ id: 'maintenance', name: 'Maintenance' }] }
    if (url === '/services') return { data: [service, { ...service, id: 'inactive', name: 'Hidden service', is_active: false }] }
    if (url === '/services/oil') return { data: service }
    if (url.startsWith('/appointments/available-slots')) return { data: [{ time: '09:00', starts_at: '2026-11-04T14:00:00Z', timezone: 'America/New_York', available: true }, { time: '10:00', starts_at: '2026-11-04T15:00:00Z', timezone: 'America/New_York', available: false }] }
    throw new Error(`Unexpected GET ${url}`)
  })
})
afterEach(cleanup)
describe('real portal service and booking journey', () => {
  it('uses catalog metadata and preserves scoped vehicle when choosing a real active service', async () => {
    mount('/portal/services?vehicle_id=truck-a')
    fireEvent.click(await screen.findByRole('button', { name: /Maintenance Oil changes/ }))
    expect(screen.queryByText('Hidden service')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Choose/ }))
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    expect(screen.getByTestId('location')).toHaveTextContent('/portal/book/oil?vehicle_id=truck-a')
    expect(screen.getAllByText(/Unit #123.*2021 Volvo.*ABC123/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/SOURCE MODEL/)).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('classifies title-case catalog names for every common need', async () => {
    const get = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => url === '/services' ? { data: [
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
  it('has named steps, actual available times, and notes before review with no write before explicit confirmation', async () => {
    mount()
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    fireEvent.click(await screen.findByRole('button', { name: '09:00' }))
    expect(screen.queryByRole('button', { name: '10:00' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Notes (optional)' }), { target: { value: 'Check a noise' } })
    fireEvent.click(screen.getByRole('button', { name: 'Review visit' }))
    expect(screen.getByRole('heading', { name: 'Review your visit' })).toBeInTheDocument()
    expect(screen.getByText('Check a noise')).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
    mocks.post.mockResolvedValue({ data: { id: 'appointment-a' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Continue to payment' }))
    await screen.findByRole('heading', { name: 'Payment' })
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.post).toHaveBeenCalledWith('/appointments', expect.objectContaining({ service_id: 'oil', vehicle_id: 'truck-a', customer_notes: 'Check a noise', scheduled_at: '2026-11-04T14:00:00Z' }))
  })
  it('skips the known single vehicle once and respects Back across a vehicle refetch', async () => {
    const client = mount('/portal/book/oil')
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    expect(screen.getByText('Unit #123 · 2021 Volvo · ABC123')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await screen.findByRole('heading', { name: 'Which vehicle?' })
    await client.refetchQueries({ queryKey: ['vehicles'] })
    expect(screen.getByRole('heading', { name: 'Which vehicle?' })).toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('rechecks availability on review and blocks a slot that became unavailable', async () => {
    let slotReads = 0
    const get = mocks.get.getMockImplementation()!
    mocks.get.mockImplementation(async (url: string) => {
      if (url.startsWith('/appointments/')) return { data: [{ time: '09:00', starts_at: '2026-11-04T14:00:00Z', timezone: 'America/New_York', available: ++slotReads === 1 }] }
      return get(url)
    })
    mount()
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
    mocks.get.mockImplementation(async (url: string) => ({ data: url === '/vehicles' ? [truck, { ...truck, id: 'truck-b' }] : service }))
    mount()
    await screen.findByRole('heading', { name: 'Which vehicle?' })
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.getAllByText('Details need review — contact the shop')).toHaveLength(2)
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('skips vehicle selection for a service that requires no vehicle and handles empty availability', async () => {
    mocks.get.mockImplementation(async (url: string) => ({ data: url === '/vehicles' ? [] : url.startsWith('/appointments/') ? [] : { ...service, requires_vehicle: false } }))
    mount('/portal/book/oil')
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    await screen.findByText('No available times for this date. Choose another date.')
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    expect(screen.queryByRole('heading', { name: 'Which vehicle?' })).not.toBeInTheDocument()
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not select the first vehicle when multiple authorized choices exist', async () => {
    mocks.get.mockImplementation(async (url: string) => ({ data: url === '/vehicles' ? [truck, { ...truck, id: 'truck-b', unit_number: '456' }] : service }))
    mount('/portal/book/oil')
    await screen.findByRole('heading', { name: 'Which vehicle?' })
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Unit #456/ }))
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Choose another service' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/portal/services?vehicle_id=truck-b')
    expect(mocks.post).not.toHaveBeenCalled()
  })
  it('does not force a scoped vehicle into a no-vehicle service request', async () => {
    mocks.get.mockImplementation(async (url: string) => ({ data: url === '/vehicles' ? [truck] : url.startsWith('/appointments/') ? [{ time: '09:00', starts_at: '2026-11-04T14:00:00Z', timezone: 'America/New_York', available: true }] : { ...service, requires_vehicle: false } }))
    mocks.post.mockResolvedValue({ data: { id: 'appointment-a' } })
    mount()
    fireEvent.click(await screen.findByRole('button', { name: '09:00' }))
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Review visit' }))
    expect(mocks.post).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Continue to payment' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Continue to payment' }))
    await screen.findByRole('heading', { name: 'Payment' })
    expect(mocks.post).toHaveBeenCalledWith('/appointments', expect.objectContaining({ vehicle_id: null }))
  })
  it('shows retry on slot failure and never manufactures availability', async () => {
    mocks.get.mockImplementation(async (url: string) => {
      if (url.startsWith('/appointments/')) throw new Error('Offline')
      return { data: url === '/vehicles' ? [truck] : service }
    })
    mount()
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
    await screen.findByRole('heading', { name: 'Choose a date and time' })
    expect(client.getQueryCache().getAll().map(query => query.queryKey)).toEqual(expect.arrayContaining([['vehicles', 'tenant-a', 'customer-a'], ['service', 'oil', 'tenant-a', 'customer-a']]))
  })
})
