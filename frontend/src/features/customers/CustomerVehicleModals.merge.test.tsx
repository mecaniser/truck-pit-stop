import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Customer, Vehicle } from '@/types'
import CustomerVehicleModals, { type CustomerVehicleModalsHandle } from './CustomerVehicleModals'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: {} }) }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const truck = { id: 'original', customer_id: 'company', vin: '', unit_number: '077', make: '', model: '' } as Vehicle
const original = { ...truck, customer_name: 'Test fleet', repair_order_count: 2, appointment_count: 0, inspection_count: 0, incident_count: 0 }
const other = { ...original, id: 'other', vin: '1FUJGLDR9CSBP8777', repair_order_count: 9 }

function setup(basis = 'unit_number', candidates = [other], previewFails = false) {
  const preview = { canonical: original, duplicate: other, recommended_canonical_id: 'other', match_basis: basis, match_value: basis === 'vin' ? other.vin : '077' }
  api.get.mockImplementation((url: string) => {
    if (url.endsWith('/duplicate-candidates')) return Promise.resolve({ data: candidates })
    if (url.includes('/merge-preview/')) return previewFails ? Promise.reject(new Error('Unsafe pair')) : Promise.resolve({ data: preview })
    return Promise.resolve({ data: [] })
  })
  api.post.mockResolvedValue({ data: { canonical_vehicle_id: 'other', moved: {} } })
  const controlsRef = { current: null as CustomerVehicleModalsHandle | null }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(<QueryClientProvider client={client}><CustomerVehicleModals customer={{ id: 'company' } as Customer} selectedVehicleInPanel={truck} controlsRef={controlsRef} /></QueryClientProvider>)
  act(() => controlsRef.current!.openMerge())
}

afterEach(() => vi.clearAllMocks())

describe('customer truck duplicate merge', () => {
  it.each(['unit_number', 'vin'])('confirms and submits the server match basis %s', async (basis) => {
    setup(basis)
    const checkbox = await screen.findByRole('checkbox')
    expect(api.get).toHaveBeenCalledWith('/vehicles/original/duplicate-candidates', { params: { include_unit_matches: true } })
    expect(screen.getByText(/I verified both records/)).toHaveTextContent(basis === 'vin' ? 'with VIN' : 'with unit number')
    const button = screen.getByRole('button', { name: 'Merge trucks' })
    expect(button).toBeDisabled()
    const counts = screen.getByText('What will move').parentElement!
    expect(within(counts).getByText('2')).toBeInTheDocument()
    expect(within(counts).queryByText('9')).not.toBeInTheDocument()
    fireEvent.click(checkbox)
    fireEvent.click(button)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/vehicles/other/merge', {
      duplicate_vehicle_id: 'original',
      ...(basis === 'vin' ? { confirm_vin: other.vin } : { confirm_unit_number: '077' }),
    }))
  })

  it('explains an empty list without suggesting a blank VIN match', async () => {
    setup('unit_number', [])
    expect(await screen.findByText(/No eligible duplicate found/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Merge trucks' })).toBeDisabled()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
  })

  it('blocks a pair rejected by the server', async () => {
    setup('unit_number', [other], true)
    expect(await screen.findByText(/This pair cannot be safely merged/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Merge trucks' })).toBeDisabled()
    expect(api.post).not.toHaveBeenCalled()
  })
})
