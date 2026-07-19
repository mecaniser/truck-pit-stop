import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
  },
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

vi.mock('@/contexts/ThemeContext', () => ({
  useTheme: () => ({ accentColors: { primary: '#2563eb' } }),
}))

import RepairOrdersPage from '../RepairOrdersPage'

function renderPage(initialEntries: string[] = ['/']) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <RepairOrdersPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('RepairOrdersPage request cancellation', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
  })

  it('aborts an in-flight repair-order page request when the page unmounts', async () => {
    let resolveRequest: (() => void) | undefined
    const pendingRequest = new Promise<{ data: { items: []; total: number; has_more: boolean } }>((resolve) => {
      resolveRequest = () => resolve({ data: { items: [], total: 0, has_more: false } })
    })

    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') return pendingRequest
      return Promise.resolve({ data: url === '/dashboard/stats' ? { mechanic_workload: [] } : { labor_rate: 100 } })
    })

    const { unmount } = renderPage()

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith('/repair-orders', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    })

    const [, config] = apiMocks.get.mock.calls.find(([url]) => url === '/repair-orders')!
    const signal = config.signal as AbortSignal
    expect(signal.aborted).toBe(false)

    unmount()

    await waitFor(() => expect(signal.aborted).toBe(true))
    resolveRequest?.()
  })

  it('shows the selected company trucks as model-and-unit cards', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders') {
        return Promise.resolve({ data: { items: [], total: 0, has_more: false } })
      }
      if (url === '/customers/typeahead') {
        return Promise.resolve({
          data: [{
            id: 'customer-1', first_name: 'Elis', last_name: 'Logistics', company_name: 'ELIS LOGISTICS LLC',
            email: 'dispatch@elis.example', phone: null,
          }],
        })
      }
      if (url === '/vehicles/typeahead') {
        return Promise.resolve({
          data: [{
            id: 'vehicle-1', customer_id: 'customer-1', make: 'Freightliner', model: 'Cascadia',
            year: 2022, unit_number: '204', license_plate: 'ELIS-204', vin: 'VIN204',
          }],
        })
      }
      if (url === '/services/typeahead') return Promise.resolve({ data: [] })
      if (url === '/dashboard/stats') return Promise.resolve({ data: { mechanic_workload: [] } })
      return Promise.resolve({ data: { labor_rate: 100 } })
    })

    renderPage(['/?new=true'])

    await screen.findByRole('heading', { name: 'New Repair Order' })
    fireEvent.click(await screen.findByRole('button', { name: /choose a customer/i }))
    fireEvent.mouseDown(await screen.findByText('ELIS LOGISTICS LLC'))

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith('/vehicles/typeahead', expect.objectContaining({
        params: expect.objectContaining({ customer_id: 'customer-1', limit: 50 }),
      }))
    })
    expect(await screen.findByText('Available trucks')).toBeInTheDocument()
    expect(screen.getByText('Unit 204')).toBeInTheDocument()
    expect(screen.getByText('Freightliner Cascadia')).toBeInTheDocument()
  })
})
