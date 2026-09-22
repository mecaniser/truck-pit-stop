import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  limits: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string, ...args: unknown[]) => url.endsWith('/discount-limits') ? apiMocks.limits() : apiMocks.get(url, ...args),
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

  const view = render(
    <QueryClientProvider client={queryClient}>
      <PriceBuilderPanel orderId="order-1" orderStatus="draft" canEdit {...props} />
    </QueryClientProvider>,
  )

  return {
    ...view,
    rerenderPanel(nextProps: Partial<ComponentProps<typeof PriceBuilderPanel>>) {
      view.rerender(
        <QueryClientProvider client={queryClient}>
          <PriceBuilderPanel orderId="order-1" orderStatus="draft" canEdit {...nextProps} />
        </QueryClientProvider>,
      )
    },
  }
}

describe('PriceBuilderPanel pending feedback', () => {
  beforeEach(() => {
    const capacity = { labor_discount_max: '10000', combined_discount_max: '20000', labor_discount_block_reason: null, order_discount_block_reason: null }
    apiMocks.limits.mockResolvedValue({ data: { current: capacity, stock: capacity, list: capacity } })
  })
  it('limits combined discounts to cost headroom and rechecks a stock-price draft', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const current = { labor_discount_max: '150', combined_discount_max: '450', labor_discount_block_reason: null, order_discount_block_reason: null }
    apiMocks.limits.mockResolvedValue({ data: { current, list: current, stock: { ...current, combined_discount_max: '150' } } })
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByText('Pricing', { exact: true }))
    await user.click(screen.getByRole('button', { name: 'Discounts & pricing' }))
    await screen.findByText('Available discount: labor $150.00 · order $450.00')
    await user.type(screen.getByRole('textbox', { name: 'Labor discount' }), '150')
    await user.type(screen.getByRole('textbox', { name: 'Order discount' }), '300')
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeEnabled()
    await user.clear(screen.getByRole('textbox', { name: 'Order discount' }))
    await user.type(screen.getByRole('textbox', { name: 'Order discount' }), '300.01')
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('Order discount is limited to $300.00')
    await user.click(screen.getByRole('radio', { name: 'Stock price' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Order discount is limited to $0.00')
    await user.clear(screen.getByRole('textbox', { name: 'Order discount' }))
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeEnabled()
    expect(apiMocks.patch).not.toHaveBeenCalled()
  })

  it('accepts an exact fractional-dollar boundary and retains drafts after a failed save', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const capacity = { labor_discount_max: '187.50', combined_discount_max: '198.89', labor_discount_block_reason: null, order_discount_block_reason: null }
    apiMocks.limits.mockResolvedValue({ data: { current: capacity, stock: capacity, list: capacity } })
    apiMocks.patch.mockRejectedValueOnce(new Error('Save failed'))
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByText('Pricing', { exact: true }))
    await user.click(screen.getByRole('button', { name: 'Discounts & pricing' }))
    await screen.findByText('Available discount: labor $187.50 · order $198.89')
    await user.type(screen.getByRole('textbox', { name: 'Labor discount' }), '187.50')
    await user.type(screen.getByRole('textbox', { name: 'Order discount' }), '11.39')
    const apply = screen.getByRole('button', { name: 'Apply', exact: true })
    expect(apply).toBeEnabled()
    const previousRequests = apiMocks.limits.mock.calls.length
    await user.click(apply)
    await waitFor(() => expect(apiMocks.limits.mock.calls.length).toBeGreaterThan(previousRequests))
    expect(screen.getByRole('textbox', { name: 'Labor discount' })).toHaveValue('187.50')
    expect(screen.getByRole('textbox', { name: 'Order discount' })).toHaveValue('11.39')
    expect(apply).toBeEnabled()
    await user.clear(screen.getByRole('textbox', { name: 'Order discount' }))
    await user.type(screen.getByRole('textbox', { name: 'Order discount' }), '11.40')
    expect(apply).toBeDisabled()
  })

  it('fails closed when cost limits cannot be loaded', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    apiMocks.limits.mockRejectedValue(new Error('Unavailable'))
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByText('Pricing', { exact: true }))
    await user.click(screen.getByRole('button', { name: 'Discounts & pricing' }))
    await screen.findByText('Discount limits could not be loaded. Reopen pricing to retry.')
    await user.click(screen.getByRole('radio', { name: 'Stock price' }))
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeDisabled()
    expect(apiMocks.patch).not.toHaveBeenCalled()
  })
  it.each(['Labor discount', 'Order discount'])('formats %s and saves an ungrouped decimal', async name => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    apiMocks.patch.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByText('Pricing', { exact: true }))
    await user.click(screen.getByRole('button', { name: 'Discounts & pricing' }))
    const input = screen.getByRole('textbox', { name })
    await user.type(input, '1234')
    expect(input).toHaveValue('1,234')
    await user.keyboard('{Home}{ArrowRight}9')
    expect(input).toHaveValue('19,234')
    await user.keyboard('{Backspace}')
    expect(input).toHaveValue('1,234')
    await user.tab()
    expect(input).toHaveValue('1,234.00')
    await user.clear(input)
    await user.paste('$1,234.50')
    expect(input).toHaveValue('1,234.50')
    expect(screen.getByText('Customer saves $1,234.50')).toBeInTheDocument()
    await user.type(input, '9')
    expect(input).toHaveValue('1,234.50')
    await user.click(screen.getByRole('button', { name: 'Apply', exact: true }))
    expect(apiMocks.patch).toHaveBeenCalledWith('/repair-orders/order-1/discounts', {
      labor_discount_amount: name === 'Labor discount' ? '1234.50' : '0',
      order_discount_amount: name === 'Order discount' ? '1234.50' : '0',
    })
  })
  it('selects a pricing segment without persisting until Apply', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByText('Pricing', { exact: true }))
    await user.click(screen.getByRole('button', { name: 'Discounts & pricing' }))
    const list = screen.getByRole('radio', { name: 'List price' })
    const stock = screen.getByRole('radio', { name: 'Stock price' })
    expect(stock).toHaveClass('absolute', 'inset-0', 'w-full', 'h-full')
    expect(list).toBeChecked()
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeDisabled()
    await user.pointer({ target: screen.getByText('Stock price', { exact: true }), keys: '[MouseLeft>]' })
    expect(stock).toHaveFocus()
    await user.pointer({ keys: '[/MouseLeft]' })
    expect(stock).toBeChecked()
    expect(stock).toHaveFocus()
    expect(list).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeEnabled()
    await user.click(screen.getByText('List price', { exact: true }))
    expect(list).toBeChecked()
    expect(list).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeDisabled()
    await user.click(stock)
    expect(stock).toBeChecked()
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeEnabled()
    await user.click(list)
    expect(list).toBeChecked()
    expect(screen.getByRole('button', { name: 'Apply', exact: true })).toBeDisabled()
    expect(apiMocks.post).not.toHaveBeenCalled()
    expect(apiMocks.patch).not.toHaveBeenCalled()
  })
  it.each(['0.00', '5.00'])('enables Apply only for changed discount amounts (saved %s)', async amount => {
    apiMocks.get.mockResolvedValue({ data: { ...emptySummary, labor_discount_amount: amount, order_discount_amount: amount } })
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByText('Pricing', { exact: true }))
    await user.click(screen.getByRole('button', { name: 'Discounts & pricing' }))
    const apply = screen.getByRole('button', { name: 'Apply', exact: true })
    expect(apply).toBeDisabled()
    for (const name of ['Labor discount', 'Order discount']) {
      const input = screen.getByRole('textbox', { name })
      await user.clear(input)
      await user.type(input, String(Number(amount)))
      expect(apply).toBeDisabled()
      await user.clear(input)
      await user.type(input, '7.00')
      expect(apply).toBeEnabled()
      await user.clear(input)
      if (Number(amount)) await user.type(input, amount)
      expect(apply).toBeDisabled()
    }
    await user.click(apply)
    expect(apiMocks.post).not.toHaveBeenCalled()
    expect(apiMocks.patch).not.toHaveBeenCalled()
  })
  it('applies either selected pricing mode and locks selection while saving', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getByText('Pricing', { exact: true }))
    for (const mode of ['stock', 'list'] as const) {
      let finishSave!: () => void
      apiMocks.patch.mockImplementationOnce(() => new Promise(resolve => {
        finishSave = () => resolve({ data: emptySummary })
      }))
      await user.click(screen.getByRole('button', { name: 'Discounts & pricing' }))
      await user.click(screen.getByText(mode === 'stock' ? 'Stock price' : 'List price', { exact: true }))
      await user.click(screen.getByRole('button', { name: 'Apply', exact: true }))
      expect(apiMocks.patch).toHaveBeenLastCalledWith('/repair-orders/order-1/discounts', { parts_pricing_mode: mode, labor_discount_amount: '0', order_discount_amount: '0' })
      expect(screen.getByRole('radio', { name: 'Stock price' })).toBeDisabled()
      expect(screen.getByRole('radio', { name: 'List price' })).toBeDisabled()
      expect(screen.getByRole('button', { name: /Applying…/ })).toBeDisabled()
      await act(async () => finishSave())
      await waitFor(() => expect(screen.queryByRole('radio')).not.toBeInTheDocument())
    }
    expect(apiMocks.patch).toHaveBeenCalledTimes(2)
    expect(apiMocks.post).not.toHaveBeenCalled()
  })
  it('shows only three quick picks without focusing search and keeps history collapsed', async () => {
    const parts = [1, 2, 3, 4].map(n => ({ inventory_id: `part-${n}`, name: `Part ${n}`, sku: `${n}`, stock_quantity: 10, unit_type: 'each', selling_price: '10' }))
    const labor = [1, 2, 3, 4].map(n => ({ id: `labor-${n}`, operation_name: `Labor ${n}`, normalized_hours: '1', usage_count: n }))
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? emptySummary : url.endsWith('/suggestions') ? { for_this_order: [], most_used: parts } : url === '/labor-book-time' ? labor : [] }))
    const user = userEvent.setup()
    const view = renderPanel()
    await user.click(screen.getByRole('button', { name: 'Part', exact: true }))
    expect(await screen.findByRole('button', { name: 'Add Part 3' })).toBeInTheDocument()
    expect(view.container.querySelector('.db-workspace-picker')).not.toHaveClass('overflow-y-auto')
    expect(screen.queryByRole('button', { name: 'Add Part 4' })).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Add part —/)).not.toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'Labor', exact: true }))
    expect(await screen.findByRole('button', { name: 'Add Labor 4' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add Labor 1' })).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Search labor book time/)).not.toHaveFocus()
    await user.click(screen.getByRole('button', { name: 'History', exact: true }))
    expect(screen.queryByText('No repair order history has been recorded yet.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Repair order history/ }))
    expect(screen.getByText('No repair order history has been recorded yet.')).toBeInTheDocument()
  })
  it('keeps secondary work flows on demand and vehicle details accessible from the header', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onToggleDangerActions = vi.fn()
    const user = userEvent.setup()
    const { container } = renderPanel({ vehicleUnit: '609', vehicleVin: 'TESTVIN609', onAddNote: vi.fn(), onToggleDangerActions })
    expect(screen.queryByRole('button', { name: 'Customer & Vehicle' })).not.toBeInTheDocument()
    expect(screen.queryByText('VIN: TESTVIN609')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /609/ }))
    expect(screen.getByText('VIN: TESTVIN609')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add note' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Notes/ }))
    expect(screen.getByRole('button', { name: 'Add note' })).toBeInTheDocument()
    const pricing = container.querySelector('details.db-workspace-pricing')!
    expect(pricing).not.toHaveAttribute('open')
    await user.click(screen.getByText('Pricing', { exact: true }))
    expect(pricing).toHaveAttribute('open')
    await user.click(screen.getByRole('button', { name: 'Order actions' }))
    expect(onToggleDangerActions).toHaveBeenCalledOnce()
  })
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

    view.rerenderPanel({ onQuoteAction, quoteActionLabel: 'Create estimate', quoteActionPending: true })
    view.rerenderPanel({ onQuoteAction, quoteActionLabel: 'Send estimate', quoteActionPending: false })
    await waitFor(() => {
      expect(view.container.querySelector('button[data-authorization-quote-action="true"]:focus')).toHaveTextContent('Send estimate')
    })
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

  it.each(['main', 'operation'])('offers a new part alongside similar results in the %s picker', async (picker) => {
    const matches = [
      { id: 'connector-1', name: 'Connector brass', sku: 'CB-1', stock_quantity: 12, unit_type: 'each', selling_price: '5.00' },
      { id: 'connector-2', name: 'Connector steel', sku: 'CS-1', stock_quantity: 8, unit_type: 'each', selling_price: '7.00' },
    ]
    apiMocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/price-build')) return Promise.resolve({ data: {
        ...emptySummary,
        lines: picker === 'operation' ? [{
          id: 'labor-1', repair_order_id: 'order-1', description: 'Initial inspection',
          hours: '1.00', hourly_rate: '100.00', total_cost: '100.00',
          line_type: 'manual', source_service_id: null,
        }] : [],
      } })
      if (url.endsWith('/parts/suggestions')) return Promise.resolve({ data: { for_this_order: [], most_used: [] } })
      if (url === '/inventory/typeahead') return Promise.resolve({ data: matches })
      return Promise.resolve({ data: [] })
    })
    const user = userEvent.setup()
    renderPanel()
    if (picker === 'operation') await user.click(await screen.findByRole('button', { name: /Initial inspection/ }))
    await user.click(await screen.findByRole('button', { name: picker === 'main' ? 'Part' : 'Add part to this operation', exact: true }))
    const search = await screen.findByPlaceholderText(picker === 'main' ? /add part/i : 'Search parts, or type a name to add a new one')
    await user.type(search, 'connector')
    for (const item of matches) expect(await screen.findByText(item.name)).toBeInTheDocument()
    const create = await screen.findByRole('button', { name: 'Add “connector” as a new part' })
    create.focus()
    await user.keyboard('{Enter}')
    const name = screen.getByPlaceholderText('Part name')
    expect(name).toHaveValue('connector')
    expect(name).toHaveFocus()
    await user.type(name, ' nylon')
    expect(name).toHaveValue('connector nylon')
    expect(apiMocks.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
    expect(screen.queryByPlaceholderText('Part name')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add “connector” as a new part' })).toBeInTheDocument()
    await user.clear(search)
    await user.type(search, 'unique hose')
    expect(await screen.findByRole('button', { name: 'Add “unique hose” as a new part' })).toBeInTheDocument()
    await user.clear(search)
    expect(screen.queryByRole('button', { name: /as a new part/ })).not.toBeInTheDocument()
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

  it('guides checked-in work through a keyboard-accessible footer without starting on assignment', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    const onAssignTechnician = vi.fn()
    const onOverrideTechnicianAssignment = vi.fn()
    const props = {
      technicianOptions: [{ mechanic_id: 'tech-1', mechanic_name: 'Mike Johnson', assigned_count: 0, in_progress_count: 0 }],
      onAssignTechnician,
      onOverrideTechnicianAssignment,
    }
    const view = renderPanel(props)
    const trigger = await screen.findByRole('button', { name: 'Start work…' })
    expect(screen.getByLabelText('Technician status')).toHaveTextContent('No technician assigned')
    expect(screen.queryByRole('button', { name: /^Assign technician/ })).not.toBeInTheDocument()
    trigger.focus()
    await user.keyboard('{Enter}')
    let options = screen.getByLabelText('Start work options')
    expect(within(options).getByText('They’ll be notified and can start work.')).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByLabelText('Start work options')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    await user.click(trigger)
    options = screen.getByLabelText('Start work options')
    await user.click(within(options).getByRole('button', { name: /Mike Johnson/ }))
    expect(onAssignTechnician).toHaveBeenCalledWith('tech-1')
    expect(onOverrideTechnicianAssignment).not.toHaveBeenCalled()
    view.rerenderPanel({ ...props, orderStatus: 'assigned', assignedTechnicianName: 'Mike Johnson', assignedTechnicianId: 'tech-1' })
    expect(screen.getByText('Waiting for Mike Johnson to start')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Start work…' })).not.toBeInTheDocument()
  })

  it('starts shop-managed work from the footer and shows the existing completion action afterward', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    const onOverrideTechnicianAssignment = vi.fn()
    const props = { onOverrideTechnicianAssignment, onAdminCompleteWork: vi.fn() }
    const view = renderPanel(props)
    await user.click(await screen.findByRole('button', { name: 'Start work…' }))
    await user.click(within(screen.getByLabelText('Start work options')).getByRole('button', { name: 'Start without a technician' }))
    expect(onOverrideTechnicianAssignment).toHaveBeenCalledTimes(1)
    view.rerenderPanel({ ...props, technicianOverridePending: true })
    expect(screen.getByRole('button', { name: 'Starting…' })).toBeDisabled()
    view.rerenderPanel({ ...props, orderStatus: 'in_progress' })
    expect(screen.getByText('Work in progress')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Mark Completed' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Start work…' })).not.toBeInTheDocument()
  })

  it('can retry a failed start and dismiss its panel by clicking outside', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    const props = { onOverrideTechnicianAssignment: vi.fn() }
    const view = renderPanel(props)
    await user.click(await screen.findByRole('button', { name: 'Start work…' }))
    await user.click(within(screen.getByLabelText('Start work options')).getByRole('button', { name: 'Start without a technician' }))
    view.rerenderPanel({ ...props, technicianOverridePending: true })
    view.rerenderPanel(props)
    await user.click(screen.getByRole('button', { name: 'Start work…' }))
    expect(screen.getByLabelText('Start work options')).toBeVisible()
    await user.click(screen.getByText('Checked in'))
    expect(screen.queryByLabelText('Start work options')).not.toBeInTheDocument()
  })

  it.each([
    { canEdit: false }, { isDeleted: true }, { isInternalOrder: true },
    { orderStatus: 'cancelled' as const }, { orderStatus: 'completed' as const },
    { orderStatus: 'pending_review' as const }, { orderStatus: 'in_progress' as const },
  ])('does not introduce a start action for an ineligible order: %j', async (props) => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    renderPanel({ onOverrideTechnicianAssignment: vi.fn(), ...props })
    expect(screen.queryByRole('button', { name: 'Start work…' })).not.toBeInTheDocument()
  })

  it('respects unavailable assignment capability and does not expose an absent override callback', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    const view = renderPanel({ onAssignTechnician: vi.fn() })
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Start work…' })).not.toBeInTheDocument()
    view.rerenderPanel({
      onAssignTechnician: vi.fn(),
      technicianOptions: [{ mechanic_id: 'tech-1', mechanic_name: 'Mike Johnson', assigned_count: 0, in_progress_count: 0 }],
    })
    await user.click(screen.getByRole('button', { name: 'Start work…' }))
    const options = screen.getByLabelText('Start work options')
    expect(within(options).queryByRole('button', { name: 'Start without a technician' })).not.toBeInTheDocument()
  })

  it('shows a passive assigned status and allows reassignment only from the footer', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    const onAssignTechnician = vi.fn()
    const props = {
      orderStatus: 'assigned', assignedTechnicianName: 'Mike Johnson', assignedTechnicianId: 'tech-1',
      technicianOptions: [
        { mechanic_id: 'tech-1', mechanic_name: 'Mike Johnson', assigned_count: 0, in_progress_count: 0 },
        { mechanic_id: 'tech-2', mechanic_name: 'Gregory Toronto', assigned_count: 0, in_progress_count: 0 },
      ],
      onAssignTechnician,
      onOverrideTechnicianAssignment: vi.fn(),
    }
    const view = renderPanel(props)
    expect(await screen.findByLabelText('Technician status')).toHaveTextContent('Technician: Mike Johnson')
    const trigger = screen.getByRole('button', { name: 'Change technician…' })
    await user.click(trigger)
    const options = screen.getByLabelText('Change technician options')
    expect(within(options).queryByRole('button', { name: /Mike Johnson/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start without a technician' })).not.toBeInTheDocument()
    await user.click(within(options).getByRole('button', { name: /Gregory Toronto/ }))
    expect(onAssignTechnician).toHaveBeenCalledWith('tech-2')
    view.rerenderPanel({ ...props, technicianAssignmentPending: true })
    expect(screen.getByRole('button', { name: 'Assigning…' })).toBeDisabled()
    view.rerenderPanel({ ...props, canEdit: false })
    expect(screen.queryByRole('button', { name: 'Change technician…' })).not.toBeInTheDocument()
  })

  it('retains read-only review history after finalization without assignment controls', async () => {
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? emptySummary : [] }))
    const user = userEvent.setup()
    renderPanel({ orderStatus: 'completed', canEdit: false, workflowInfo: {
      created_at: '2026-09-12T09:00:00Z',
      internal_notes: JSON.stringify({ reviews: [{ type: 'manager_review', notes: 'Road test passed', reviewed_by: 'Sam' }] }),
    } })
    await user.click(await screen.findByRole('button', { name: 'Quality review' }))
    expect(screen.getByText('Road test passed')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Assign technician…' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start work…' })).not.toBeInTheDocument()
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

    expect(await screen.findByLabelText('Technician status')).toHaveTextContent('Shop-managed · no technician')
    const disclosure = screen.getByRole('button', { name: 'Assign technician…' })
    expect(disclosure).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Mike Johnson')).not.toBeInTheDocument()

    await user.click(disclosure)

    expect(disclosure).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Mike Johnson')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start without a technician' })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(disclosure).toHaveFocus()

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
