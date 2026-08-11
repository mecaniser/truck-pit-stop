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

  it('keeps one selected-order header without duplicating Shop Work return controls', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })

    renderPanel({
      orderNumber: 'RO-1017',
      customerName: 'Northline Logistics',
    })

    const orderNumber = screen.getByText('#RO-1017')
    expect(orderNumber).toBeInTheDocument()
    expect(orderNumber).toHaveClass('!text-white')
    expect(screen.getByText('Northline Logistics')).toBeInTheDocument()
    expect(screen.queryByText('Selected repair order')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Return to/ })).not.toBeInTheDocument()
  })

  it('keeps the mobile estimate action outside the workflow scroller and keyboard operable', async () => {
    const onQuoteAction = vi.fn()
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') {
        return Promise.resolve({
          data: {
            ...emptySummary,
            labor_total: '100.00',
            total_cost: '100.00',
            lines: [{
              id: 'labor-1',
              repair_order_id: 'order-1',
              description: 'Initial inspection',
              hours: '1.00',
              hourly_rate: '100.00',
              total_cost: '100.00',
              mechanic_id: null,
              service_code: null,
              line_type: 'manual',
              provider: null,
              provider_operation_id: null,
              auto_recalc_enabled: false,
              source_service_id: null,
              vendor_name: null,
              vendor_cost: null,
              created_at: '2026-08-11T12:00:00Z',
            }],
          },
        })
      }
      return Promise.resolve({ data: [] })
    })

    const user = userEvent.setup()
    const view = renderPanel({ onQuoteAction, quoteActionLabel: 'Create estimate' })

    let actions: HTMLButtonElement[] = []
    await waitFor(() => {
      actions = [...view.container.querySelectorAll('button')]
        .filter((action) => action.textContent?.trim() === 'Create estimate')
      expect(actions).toHaveLength(2)
    })
    const mobileAction = actions.find((action) => action.parentElement?.classList.contains('sm:hidden'))
    const desktopAction = actions.find((action) => action.classList.contains('sm:inline-flex'))
    expect(mobileAction).toHaveClass('min-h-[44px]', 'w-full')
    expect(mobileAction?.parentElement).toHaveClass('sm:hidden')
    expect(desktopAction).toHaveClass('hidden', 'h-8', 'sm:inline-flex')

    await waitFor(() => expect(mobileAction).toBeEnabled())
    mobileAction?.focus()
    await user.keyboard('{Enter}')
    expect(onQuoteAction).toHaveBeenCalledTimes(1)
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
    const brakeShoes = {
      id: 'usage-1', repair_order_id: 'order-1', inventory_id: 'part-1',
      inventory_sku: 'BS-1', inventory_name: 'Brake Shoes', quantity: '5', unit_type: 'each',
      unit_price: '50.00', unit_cost: '30.00', list_price: '50.00', savings: '0.00',
      total_price: '250.00', source_service_id: null, source_line_id: null,
      created_at: '2026-07-19T00:00:00Z',
    }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') {
        return Promise.resolve({ data: { ...emptySummary, parts: [brakeShoes] } })
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

  it('shows Zelle confirmation actions and the non-card total for an invoiced internal fleet order', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })

    const onRecordPayment = vi.fn()
    const onVoidInvoice = vi.fn()
    const user = userEvent.setup()
    renderPanel({
      orderStatus: 'invoiced',
      isInternalOrder: true,
      onRecordPayment,
      onVoidInvoice,
      invoice: {
        id: 'invoice-1',
        tenant_id: 'tenant-1',
        repair_order_id: 'order-1',
        invoice_number: 'INV-1001',
        status: 'sent',
        subtotal: '12.50',
        shop_supplies_amount: '0.38',
        service_fee_amount: '0.37',
        tax_amount: '0.89',
        discount_amount: '0.00',
        total_amount: '14.14',
        due_date: null,
        paid_at: null,
        notes: null,
        pending_zelle_confirmation: true,
        created_at: '2026-07-22T00:00:00Z',
        updated_at: '2026-07-22T00:00:00Z',
      },
    })

    expect(await screen.findByText('$13.77')).toBeInTheDocument()
    const confirmButton = screen.getByRole('button', { name: 'Confirm Zelle payment' })
    expect(screen.queryByRole('button', { name: 'Void & revise' })).not.toBeInTheDocument()
    await user.click(confirmButton)
    expect(onRecordPayment).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: /Invoice INV-1001/i }))
    expect(screen.getByText('Zelle total')).toBeInTheDocument()
    expect(screen.queryByText('Card processing fee')).not.toBeInTheDocument()
  })

  it('hides the repair photos section on a finalized order when no photos are attached', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      if (url === '/repair-orders/order-1/photos') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })

    renderPanel({ orderStatus: 'paid' })

    await waitFor(() => {
      expect(apiMocks.get).toHaveBeenCalledWith(
        '/repair-orders/order-1/photos',
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      )
    })
    expect(screen.queryByText('Repair photos')).not.toBeInTheDocument()
    expect(screen.queryByText('No photos attached')).not.toBeInTheDocument()
  })

  it('keeps attached photos visible but read-only on a finalized order', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      if (url === '/repair-orders/order-1/photos') {
        return Promise.resolve({
          data: [{
            id: 'photo-1',
            repair_order_id: 'order-1',
            image_url: 'https://example.com/repair.jpg',
            caption: 'Completed brake repair',
            uploaded_at: '2026-07-24T12:00:00Z',
            uploader_name: 'Shop Admin',
          }],
        })
      }
      return Promise.resolve({ data: [] })
    })

    renderPanel({ orderStatus: 'invoiced' })

    expect(await screen.findByText('1 photo attached')).toBeInTheDocument()
    expect(screen.queryByText('Upload photo')).not.toBeInTheDocument()
  })

  it('uses one canonical finalize-and-invoice action for fleet orders in quality review', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/repair-orders/order-1/price-build') return Promise.resolve({ data: emptySummary })
      if (url === '/repair-orders/order-1/parts') return Promise.resolve({ data: [] })
      return Promise.resolve({ data: [] })
    })

    const onApproveCompletion = vi.fn()
    const user = userEvent.setup()
    renderPanel({
      orderStatus: 'pending_review',
      isInternalOrder: true,
      completionMode: true,
      onApproveCompletion,
    })

    expect(await screen.findByText(
      'Review the final work and approve to send the invoice to the fleet billing contact.',
    )).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark Completed' })).not.toBeInTheDocument()
    expect(screen.queryByText('Complete work order')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Operation' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Part' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Labor' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Finalize & Send Invoice' }))
    expect(onApproveCompletion).toHaveBeenCalledTimes(1)
  })
})
