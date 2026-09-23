import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { BoardTruck } from '../types'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, post: apiMocks.post } }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import { SchedulePMModal } from '../FleetModals'

const truck: BoardTruck = {
  id: 'truck-603',
  unit_number: '603',
  display_unit_number: 'Elis Logistics LLC (DBN) 603',
  year: 2021,
  make: 'Volvo',
  model: 'VNL',
  vin: '4V4NC9EH0MN000603',
  plate: 'WI-603',
  status: 'yard',
  odometer: 600_000,
  pm_interval_miles: 25_000,
  moving: false,
  open_work_order_count: 0,
  open_incident_count: 0,
}

function renderModal() {
  apiMocks.get.mockImplementation((url: string) => {
    if (url.includes('/relationships')) return Promise.resolve({ data: [] })
    if (url.includes('pm-service-catalog')) return Promise.resolve({ data: [] })
    return Promise.resolve({ data: [] })
  })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const user = userEvent.setup()
  render(
    <QueryClientProvider client={client}>
      <SchedulePMModal truck={truck} onClose={vi.fn()} onDone={vi.fn()} />
    </QueryClientProvider>,
  )
  return { user }
}

describe('Schedule PM due date', () => {
  afterEach(() => vi.clearAllMocks())

  /* The due date previously used <input type="date">, whose calendar is drawn
     by the browser. On the dark fleet panel that popup is dark-on-dark and
     unreadable, and no app CSS can reach it. The field must use the app's own
     picker so the appearance tokens apply. */
  it('offers the app calendar instead of the browser date popup', async () => {
    const { user } = renderModal()
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    expect(screen.getByRole('dialog', { name: /next pm due date/i })).toBeInTheDocument()
  })

  it('does not leave a native date input on the due date field', () => {
    renderModal()
    const field = screen.getByLabelText(/next pm due date/i)
    expect(field).not.toHaveAttribute('type', 'date')
  })

  it('picking a day in the calendar overrides the mileage estimate', async () => {
    const { user } = renderModal()
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const calendar = within(screen.getByRole('dialog', { name: /next pm due date/i }))
    await user.click(calendar.getByRole('button', { name: /^Nov 20, 2026$/ }))
    expect(screen.getByLabelText(/next pm due date/i)).toHaveValue('2026-11-20')
    expect(screen.getByText(/overrides the mileage estimate/i)).toBeInTheDocument()
  })
})
