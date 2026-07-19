import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
  },
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

import PriceBuilderPanel from '../PriceBuilderPanel'

const emptySummary = {
  order_id: 'order-1',
  labor_total: '0.00',
  parts_total: '0.00',
  total_cost: '0.00',
  pricing_locked: false,
  lines: [],
  warnings: [],
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <PriceBuilderPanel orderId="order-1" orderStatus="draft" canEdit />
    </QueryClientProvider>,
  )
}

describe('PriceBuilderPanel pending feedback', () => {
  beforeAll(() => {
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
  })

  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
  })

  afterAll(() => {
    vi.unstubAllGlobals()
  })

  it('keeps the selected operation visibly pending while its request is still in flight', async () => {
    let resolveApply: (() => void) | undefined
    const pendingApply = new Promise<{ data: unknown }>((resolve) => {
      resolveApply = () => resolve({ data: {} })
    })

    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })
    apiMocks.post.mockImplementation((url: string) => {
      if (url.endsWith('/repair-ops/search')) {
        return Promise.resolve({
          data: {
            candidates: [{
              operation_id: 'brake-inspection',
              name: 'Brake Inspection',
              description: 'Inspect brake system',
              estimated_hours: '1.00',
              provider: 'manual',
            }],
            warnings: [],
          },
        })
      }
      if (url.endsWith('/repair-ops/apply')) return pendingApply
      return Promise.resolve({ data: {} })
    })

    const user = userEvent.setup()
    renderPanel()

    const search = await screen.findByPlaceholderText(/add operation/i)
    await user.type(search, 'brake')
    await screen.findByText('Brake Inspection')

    await user.click(screen.getByRole('button', { name: 'Apply operation' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Adding Brake Inspection' })).toBeDisabled()
    })
    expect(screen.getByText('Adding operation to work & labor…')).toBeInTheDocument()

    await act(async () => {
      resolveApply?.()
      await pendingApply
    })
  })

  it('shows a parts skeleton while searching and a spinner while adding the chosen part', async () => {
    let resolveInventory: (() => void) | undefined
    const pendingInventory = new Promise<{ data: unknown }>((resolve) => {
      resolveInventory = () => resolve({
        data: [{
          id: 'part-1', name: 'Brake Pad', sku: 'BP-1', stock_quantity: 12,
          on_order_quantity: 0, unit_type: 'each', cost: '30.00', selling_price: '50.00',
        }],
      })
    })
    let resolvePartAdd: (() => void) | undefined
    const pendingPartAdd = new Promise<{ data: unknown }>((resolve) => {
      resolvePartAdd = () => resolve({ data: {} })
    })

    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      if (url === '/repair-orders/order-1/parts/suggestions') return Promise.resolve({ data: { for_this_order: [], most_used: [] } })
      if (url === '/inventory/typeahead') return pendingInventory
      return Promise.resolve({ data: [] })
    })
    apiMocks.post.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/parts') return pendingPartAdd
      return Promise.resolve({ data: {} })
    })

    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Part' }))
    const search = await screen.findByPlaceholderText(/add part/i)
    await user.type(search, 'brake')

    expect(await screen.findByText('Searching in-stock parts…')).toBeInTheDocument()
    await act(async () => {
      resolveInventory?.()
      await pendingInventory
    })
    await user.click(await screen.findByRole('button', { name: 'Add Brake Pad' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Adding Brake Pad' })).toBeDisabled()
    })
    expect(screen.getByText('Adding part to work & labor…')).toBeInTheDocument()

    await act(async () => {
      resolvePartAdd?.()
      await pendingPartAdd
    })
  })
})
