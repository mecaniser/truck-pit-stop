import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
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

describe('Schedule PM day load', () => {
  afterEach(() => vi.clearAllMocks())

  it('shows which days already have trucks booked for PM', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url.includes('pm-day-load')) {
        return Promise.resolve({ data: [{ day: '2026-11-20', count: 2, units: ['412', '118'] }] })
      }
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
    await user.click(screen.getByRole('button', { name: /choose date/i }))
    const dialog = screen.getByRole('dialog', { name: /next pm due date/i })
    const busy = await within(dialog).findByRole('button', { name: /Nov 20, 2026.*2 PMs scheduled/ })
    expect(busy).toHaveTextContent('2')
  })
})

describe('Schedule PM shop load request', () => {
  afterEach(() => vi.clearAllMocks())

  it('asks for booked repair work as well as PMs', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url.includes('pm-day-load')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <SchedulePMModal truck={truck} onClose={vi.fn()} onDone={vi.fn()} />
      </QueryClientProvider>,
    )
    await waitFor(() => {
      const call = apiMocks.get.mock.calls.find((c) => String(c[0]).includes('pm-day-load'))
      expect(call?.[1]?.params?.include_repair_orders).toBe(true)
    })
  })
})

describe('Schedule PM offers a service day', () => {
  afterEach(() => vi.clearAllMocks())

  it('defaults the due date to the shop PM day, not a mid-week date', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url.includes('pm-day-load')) return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <SchedulePMModal truck={truck} onClose={vi.fn()} onDone={vi.fn()} />
      </QueryClientProvider>,
    )
    const field = screen.getByLabelText(/next pm due date/i) as HTMLInputElement
    await waitFor(() => expect(field.value).toMatch(/^\d{4}-\d{2}-\d{2}$/))
    // Saturday: the only day the shop performs PM work.
    expect(new Date(`${field.value}T12:00:00Z`).getUTCDay()).toBe(6)
  })

  it('keeps the offered date on a service day when the mileage target changes', async () => {
    apiMocks.get.mockImplementation(() => Promise.resolve({ data: [] }))
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={client}>
        <SchedulePMModal truck={truck} onClose={vi.fn()} onDone={vi.fn()} />
      </QueryClientProvider>,
    )
    const miles = screen.getByLabelText(/next pm at odometer/i)
    await user.clear(miles)
    await user.type(miles, '610000')
    const field = screen.getByLabelText(/next pm due date/i) as HTMLInputElement
    await waitFor(() => expect(new Date(`${field.value}T12:00:00Z`).getUTCDay()).toBe(6))
  })
})
