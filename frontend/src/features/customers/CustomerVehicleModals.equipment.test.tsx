import { act, render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, it, expect, vi } from 'vitest'
import type { Customer, Vehicle } from '@/types'
import CustomerVehicleModals, { type CustomerVehicleModalsHandle } from './CustomerVehicleModals'

const api = vi.hoisted(() => ({ get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn(), put: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ accentColors: { 500: '#d97706' } }) }))

function mount() {
  const controls = { current: null as CustomerVehicleModalsHandle | null }
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <CustomerVehicleModals customer={{ id: 'ellis', company_name: 'Ellis Logistics' } as Customer} selectedVehicleInPanel={null} controlsRef={controls} />
  </QueryClientProvider>)
  return controls
}

describe('company equipment type', () => {
  it('creates a trailer under the selected company', async () => {
    api.post.mockResolvedValue({ data: { id: 'trailer' } })
    const controls = mount()
    act(() => controls.current!.openAdd())
    const type = await screen.findByLabelText('Equipment type')
    expect(type).toHaveValue('tractor')
    fireEvent.change(type, { target: { value: 'trailer' } })
    fireEvent.change(document.querySelector('input[name="make"]')!, { target: { value: 'Great Dane' } })
    fireEvent.change(document.querySelector('input[name="model"]')!, { target: { value: 'Dry Van' } })
    fireEvent.submit(type.closest('form')!)
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/customers/ellis/vehicles', expect.objectContaining({ equipment_type: 'trailer', make: 'Great Dane' })))
  })
  it('preserves an existing trailer when editing', async () => {
    api.put.mockResolvedValue({ data: { id: 'trailer', equipment_type: 'trailer' } })
    const controls = mount()
    act(() => controls.current!.openEdit({ id: 'trailer', equipment_type: 'trailer', make: 'Great Dane', model: 'Dry Van', unit_number: 'T1003130' } as Vehicle))
    const type = await screen.findByLabelText('Equipment type')
    expect(type).toHaveValue('trailer')
    fireEvent.submit(type.closest('form')!)
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/customers/ellis/vehicles/trailer', expect.objectContaining({ equipment_type: 'trailer', unit_number: 'T1003130' })))
  })
})
