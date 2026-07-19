import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: apiMocks.get,
    post: apiMocks.post,
    patch: apiMocks.patch,
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

function renderPanel(props: Partial<ComponentProps<typeof PriceBuilderPanel>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <PriceBuilderPanel orderId="order-1" orderStatus="draft" canEdit {...props} />
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
    apiMocks.patch.mockReset()
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

    expect(await screen.findByText('Searching inventory…')).toBeInTheDocument()
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

  it('keeps an insufficient-stock failure beside the part and retries only after an explicit override', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      if (url === '/repair-orders/order-1/parts/suggestions') return Promise.resolve({ data: { for_this_order: [], most_used: [] } })
      if (url === '/inventory/typeahead') {
        return Promise.resolve({
          data: [{
            id: 'part-1', name: 'Brake Pad', sku: 'BP-1', stock_quantity: 1,
            on_order_quantity: 0, unit_type: 'each', cost: '30.00', selling_price: '50.00',
          }],
        })
      }
      return Promise.resolve({ data: [] })
    })
    apiMocks.post.mockImplementation((url: string, body?: { allow_stock_shortage?: boolean }) => {
      if (url !== '/repair-orders/order-1/parts') return Promise.resolve({ data: {} })
      if (body?.allow_stock_shortage) return Promise.resolve({ data: {} })
      return Promise.reject({
        response: {
          data: {
            detail: {
              code: 'insufficient_stock',
              inventory_id: 'part-1',
              requested_quantity: '2',
              required_packages: 2,
              available_packages: 1,
              shortfall_packages: 1,
              can_override: true,
            },
          },
        },
      })
    })

    const user = userEvent.setup()
    renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Part' }))
    const search = await screen.findByPlaceholderText(/add part/i)
    await user.type(search, 'brake')
    await screen.findByRole('button', { name: 'Add Brake Pad' })

    await user.click(screen.getByRole('button', { name: /increase quantity for brake pad/i }))
    await user.click(screen.getByRole('button', { name: 'Add Brake Pad' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Inventory shows 1 ea; this order requests 2 ea.')
    await user.click(screen.getByRole('button', { name: 'Override & add' }))

    await waitFor(() => {
      expect(apiMocks.post).toHaveBeenLastCalledWith('/repair-orders/order-1/parts', expect.objectContaining({
        inventory_id: 'part-1',
        quantity: 2,
        allow_stock_shortage: true,
      }))
    })
  })

  it('keeps an existing part quantity visible when stock validation fails and supports an override retry', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') {
        return Promise.resolve({
          data: [{
            id: 'usage-1', repair_order_id: 'order-1', inventory_id: 'part-1',
            inventory_sku: 'BS-1', inventory_name: 'Brake Shoes', quantity: '5', unit_type: 'each',
            unit_price: '50.00', unit_cost: '30.00', list_price: '50.00', savings: '0.00',
            total_price: '250.00', source_service_id: null, source_line_id: null,
            created_at: '2026-07-19T00:00:00Z',
          }],
        })
      }
      return Promise.resolve({ data: [] })
    })
    apiMocks.patch.mockImplementation((url: string, body?: { allow_stock_shortage?: boolean }) => {
      if (url !== '/repair-orders/order-1/parts/usage-1') return Promise.resolve({ data: {} })
      if (body?.allow_stock_shortage) return Promise.resolve({ data: {} })
      return Promise.reject({
        response: {
          data: {
            detail: {
              code: 'insufficient_stock',
              inventory_id: 'part-1',
              requested_quantity: '6',
              required_packages: 6,
              available_packages: 5,
              shortfall_packages: 1,
              can_override: true,
            },
          },
        },
      })
    })

    const user = userEvent.setup()
    renderPanel()

    await screen.findByText('Brake Shoes')
    await user.click(screen.getByRole('button', { name: /increase quantity for brake shoes/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Inventory shows 5 ea; this order requests 6 ea.')
    expect(screen.getByRole('textbox', { name: 'Quantity for Brake Shoes' })).toHaveValue('6')

    await user.click(screen.getByRole('button', { name: 'Override & update' }))

    await waitFor(() => {
      expect(apiMocks.patch).toHaveBeenLastCalledWith('/repair-orders/order-1/parts/usage-1', expect.objectContaining({
        quantity: 6,
        allow_stock_shortage: true,
      }))
    })
  })

  it('collapses technician assignment after an admin override starts work', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })

    const user = userEvent.setup()
    const onAdminCompleteWork = vi.fn()
    renderPanel({
      orderStatus: 'in_progress',
      quoteIsApproved: true,
      technicianOptions: [
        { mechanic_id: 'tech-1', mechanic_name: 'Mike Johnson', assigned_count: 0, in_progress_count: 0 },
      ],
      onAssignTechnician: vi.fn(),
      onAdminCompleteWork,
    })

    const disclosure = await screen.findByRole('button', { name: 'Assign technician' })
    expect(disclosure).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Mike Johnson')).not.toBeInTheDocument()

    await user.click(disclosure)

    expect(disclosure).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Mike Johnson')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mark Completed' }))
    expect(screen.getByText('Mark work completed')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Mark completed' }))
    expect(onAdminCompleteWork).toHaveBeenCalledTimes(1)
  })
})
