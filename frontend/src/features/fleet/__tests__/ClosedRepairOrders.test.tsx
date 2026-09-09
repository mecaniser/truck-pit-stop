import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ClosedRepairOrders from '../ClosedRepairOrders'
import type { BoardTruck } from '../types'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: mocks }))
const trucks = [{ id: 'truck-1', unit_number: '609' }] as BoardTruck[]
function mount() {
  const open = vi.fn()
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ClosedRepairOrders trucks={trucks} onOpenRepairOrder={open} /></QueryClientProvider>)
  return open
}
describe('Closed repair order history', () => {
  beforeEach(() => mocks.get.mockReset())
  it('loads only the selected truck, excludes inspections, and opens the repair record', async () => {
    mocks.get.mockResolvedValue({ data: [
      { id: 'ro-1', kind: 'Repair', summary: 'Replace steering tire', date: '2026-09-01' },
      { id: 'inspection-1', kind: 'Inspection', summary: 'Weekly inspection' },
    ] })
    const open = mount()
    expect(mocks.get).not.toHaveBeenCalled()
    await userEvent.selectOptions(screen.getByLabelText('Truck'), 'truck-1')
    await userEvent.click(await screen.findByRole('button', { name: /Replace steering tire/ }))
    expect(mocks.get).toHaveBeenCalledWith('/fleet/trucks/truck-1/history')
    expect(screen.queryByText('Weekly inspection')).not.toBeInTheDocument()
    expect(open).toHaveBeenCalledWith('ro-1')
  })
  it('distinguishes a failed history request from an empty list and allows retry', async () => {
    mocks.get.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ data: [] })
    mount()
    await userEvent.selectOptions(screen.getByLabelText('Truck'), 'truck-1')
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No closed repair orders in this truck’s recent service history.')).toBeInTheDocument()
  })
})
