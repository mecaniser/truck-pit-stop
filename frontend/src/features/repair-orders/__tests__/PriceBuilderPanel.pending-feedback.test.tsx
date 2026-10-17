import { quote, price } from '@/features/parts-pricing/__tests__/fixtures'
import { orderMaintenance, program, work } from '@/features/maintenance/__tests__/fixtures'
import type { ResolveRequest } from '@/features/parts-pricing/contract'
import { useAuthStore } from '@/stores/authStore'
import type { User } from '@/types'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  limits: vi.fn(),
  resolve: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string, ...args: unknown[]) => url.endsWith('/operations') ? Promise.resolve({ data: { items: [], summary: { tracked: 0, completed: 0, remaining: 0, legacy_untracked: 0 }, order_status: 'draft', is_order_lead: false } }) : url.endsWith('/checklist') ? Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, summary: { total: 0, completed: 0, required: 0, required_remaining: 0 }, can_update: true } }) : url.endsWith('/discount-limits') ? apiMocks.limits() : apiMocks.get(url, ...args),
    post: (url: string, body: ResolveRequest, ...args: unknown[]) => url === '/parts-pricing/resolve' ? apiMocks.resolve(body) : apiMocks.post(url, body, ...args),
    patch: apiMocks.patch,
    delete: apiMocks.delete,
  },
}))

vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ appearance: { mode: 'dark' }, accentColors: { 500: '#d86a15' } }) }))

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
  it.each([['garage_owner', 'shop'], ['fleet_manager', 'fleet']] as const)('matches maintenance read and removal presentation for %s', async (role, channel) => {
    useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role } as User, authSessionEpoch: 1, logoutInProgress: false })
    apiMocks.get.mockImplementation(async (url: string, config?: { params?: { channel?: string } }) => {
      if (url.endsWith('/maintenance')) { if (config?.params?.channel !== channel) throw new Error('422: exact maintenance channel is required'); return { data: orderMaintenance([program('program-1', { work: work() })]) } }
      return { data: { ...emptySummary, can_edit_work: true, lines: [{ id: 'labor-1', description: 'Saved maintenance', hours: '1.00', hourly_rate: '100.00', total_cost: '100.00', line_type: 'manual', source_service_id: null }], parts: [] } }
    })
    apiMocks.delete.mockResolvedValue({ data: {} }); const user = userEvent.setup(); renderPanel(); await user.click(await screen.findByRole('button', { name: /^Saved maintenance/ })); await user.click(screen.getByRole('button', { name: 'Remove', exact: true })); const dialog = await screen.findByRole('dialog', { name: 'Remove work' }); expect(dialog).toHaveTextContent('Oil service'); await user.click(within(dialog).getByRole('button', { name: 'Remove work' }))
    await waitFor(() => expect(apiMocks.delete).toHaveBeenCalledWith('/repair-orders/order-1/price-build/lines/labor-1', { params: { pricing_presentation: channel, expected_maintenance_fingerprint: 'review-1' } })); expect(apiMocks.get).toHaveBeenCalledWith('/repair-orders/order-1/maintenance', expect.objectContaining({ params: { channel } }))
  })
  beforeEach(() => {
    apiMocks.resolve.mockReset().mockImplementation((body: ResolveRequest) => Promise.resolve({ data: quote({ plan: body.plan, required: false }) }))
    useAuthStore.setState({ user: { id: 'user-1', tenant_id: 'tenant-1', role: 'garage_owner' } as User, authSessionEpoch: 1, logoutInProgress: false })
    const capacity = { labor_discount_max: '10000', combined_discount_max: '20000', labor_discount_block_reason: null, order_discount_block_reason: null }
    apiMocks.limits.mockResolvedValue({ data: { current: capacity, stock: capacity, list: capacity } })
  })
  it('keeps recovery notices in the work scroller with the footer outside that content', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const { container } = renderPanel({ workspaceNotice: <div role="status" aria-label="Unfinished service attachment">Service pending<button>Retry remaining</button><button>Keep current work</button></div> })
    const notice = await screen.findByRole('status', { name: 'Unfinished service attachment' })
    const scroll = notice.closest('.db-workspace-scroll')
    expect(scroll).not.toBeNull()
    const footer = container.querySelector('.db-workspace-footer')
    expect(footer).not.toBeNull()
    expect(scroll).not.toContainElement(footer as HTMLElement)
    expect(within(notice).getByRole('button', { name: 'Retry remaining' })).toBeEnabled()
    expect(within(notice).getByRole('button', { name: 'Keep current work' })).toBeEnabled()
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
  it('shows only three quick picks without focusing search and opens history in one click', async () => {
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
    apiMocks.delete.mockReset()
  })

  afterAll(() => {
    vi.unstubAllGlobals()
  })

  it('opens truck details in an anchored popover and returns keyboard focus to the truck', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    const { container } = renderPanel({ vehicleUnit: '609', vehicleVin: 'TESTVIN609', customerName: 'Carrier' })
    const trigger = screen.getByRole('button', { name: '609' })
    await user.click(trigger)
    const panel = screen.getByLabelText('Truck and customer details')
    expect(panel).toHaveTextContent('VIN: TESTVIN609')
    expect(container.querySelector('.db-workspace-body')).not.toContainElement(panel)
    expect(screen.getByRole('heading', { name: 'Truck and customer' })).toHaveFocus()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByLabelText('Truck and customer details')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
  })

  it('opens vehicle history from the truck header without leaving an open popover', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onOpenVehicleHistory = vi.fn()
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', onOpenVehicleHistory })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'View vehicle history' }))
    expect(onOpenVehicleHistory).toHaveBeenCalledOnce()
    await waitFor(() => expect(screen.queryByLabelText('Truck and customer details')).not.toBeInTheDocument())
  })

  it('saves only changed intake fields and clears the carried-reading flag', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onSaveIntake = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', mileageIn: 123, mileageOut: 130, poNumber: 'PO-1', mileageInCarried: true, onSaveIntake })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.clear(screen.getByRole('textbox', { name: 'Mileage in' }))
    await user.type(screen.getByRole('textbox', { name: 'Mileage in' }), '125')
    await user.click(screen.getByRole('button', { name: 'Save intake' }))
    expect(onSaveIntake).toHaveBeenCalledExactlyOnceWith({ mileage_in: 125, mileage_in_carried: false })
  })

  it('clears a PO without overwriting unchanged mileage', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onSaveIntake = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', mileageIn: 123, poNumber: 'PO-1', onSaveIntake })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.clear(screen.getByRole('textbox', { name: 'PO number' }))
    await user.click(screen.getByRole('button', { name: 'Save intake' }))
    expect(onSaveIntake).toHaveBeenCalledExactlyOnceWith({ po_number: null })
  })

  it.each(['-1', '1.5', '1e6', '2147483648'])('rejects invalid intake mileage %s without a write', async (value) => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onSaveIntake = vi.fn()
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', onSaveIntake })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.type(screen.getByRole('textbox', { name: 'Mileage in' }), value)
    await user.click(screen.getByRole('button', { name: 'Save intake' }))
    expect(screen.getByRole('alert')).toHaveTextContent('whole number')
    expect(onSaveIntake).not.toHaveBeenCalled()
  })

  it('retains the intake draft after a save failure and allows retry', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onSaveIntake = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', onSaveIntake })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.type(screen.getByRole('textbox', { name: 'PO number' }), 'PO-123')
    await user.click(screen.getByRole('button', { name: 'Save intake' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save intake')
    expect(screen.getByRole('textbox', { name: 'PO number' })).toHaveValue('PO-123')
    await user.click(screen.getByRole('button', { name: 'Save intake' }))
    expect(onSaveIntake).toHaveBeenCalledTimes(2)
  })

  it('discards an intake draft on Escape without saving and returns focus', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onSaveIntake = vi.fn()
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', poNumber: 'Original', onSaveIntake })
    const trigger = screen.getByRole('button', { name: '609' })
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.type(screen.getByRole('textbox', { name: 'PO number' }), ' draft')
    await user.keyboard('{Escape}')
    expect(trigger).toHaveFocus()
    expect(onSaveIntake).not.toHaveBeenCalled()
    await user.click(trigger)
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    expect(screen.getByRole('textbox', { name: 'PO number' })).toHaveValue('Original')
  })

  it.each([{ canEdit: false }, { orderStatus: 'completed' as const }, { isDeleted: true }])('hides the intake editor on read-only orders %j', async (props) => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', onSaveIntake: vi.fn(), ...props })
    await user.click(screen.getByRole('button', { name: '609' }))
    expect(screen.queryByRole('button', { name: 'Edit intake' })).not.toBeInTheDocument()
  })

  it('does not resubmit intake while the first save is pending', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    let resolveSave!: () => void
    const onSaveIntake = vi.fn(() => new Promise<void>(resolve => { resolveSave = resolve }))
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', onSaveIntake })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.type(screen.getByRole('textbox', { name: 'Mileage out' }), '0')
    await user.dblClick(screen.getByRole('button', { name: 'Save intake' }))
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'Mileage out' })).toBeDisabled()
    expect(onSaveIntake).toHaveBeenCalledExactlyOnceWith({ mileage_out: 0 })
    await act(async () => resolveSave())
  })

  it('clears mileage explicitly and cancels without changing the order', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onSaveIntake = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', mileageIn: 123, mileageOut: 124, onSaveIntake })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.clear(screen.getByRole('textbox', { name: 'Mileage in' }))
    await user.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
    expect(onSaveIntake).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    expect(screen.getByRole('textbox', { name: 'Mileage in' })).toHaveValue('123')
    await user.clear(screen.getByRole('textbox', { name: 'Mileage in' }))
    await user.clear(screen.getByRole('textbox', { name: 'Mileage out' }))
    await user.click(screen.getByRole('button', { name: 'Save intake' }))
    expect(onSaveIntake).toHaveBeenCalledExactlyOnceWith({ mileage_in: null, mileage_in_carried: false, mileage_out: null })
  })

  it('sends no intake request for an unchanged draft', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const onSaveIntake = vi.fn()
    const user = userEvent.setup()
    renderPanel({ vehicleUnit: '609', mileageIn: 123, poNumber: 'PO-1', onSaveIntake })
    await user.click(screen.getByRole('button', { name: '609' }))
    await user.click(screen.getByRole('button', { name: 'Edit intake' }))
    await user.click(screen.getByRole('button', { name: 'Save intake' }))
    expect(onSaveIntake).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Edit intake' })).toBeInTheDocument()
  })

  it('shows held work and its readable reason instead of active work', async () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const user = userEvent.setup()
    const { container } = renderPanel({ orderStatus: 'in_progress', workflowInfo: { created_at: '2026-10-12', hold_reason: 'waiting_for_parts' } })
    expect(container.querySelector('.db-job-stage')).toHaveTextContent('On hold')
    expect(screen.getByText('On hold · Waiting for parts')).toHaveAttribute('role', 'status')
    expect(screen.queryByText('Work in progress')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'On hold' }))
    expect(screen.getByText('Waiting for parts')).toBeVisible()
  })

  it('does not label completed work as held when an old reason remains', () => {
    apiMocks.get.mockResolvedValue({ data: emptySummary })
    const { container } = renderPanel({ orderStatus: 'completed', workflowInfo: { created_at: '2026-10-12', hold_reason: 'waiting_for_parts' } })
    expect(container.querySelector('.db-job-stage')).toHaveTextContent('completed')
    expect(screen.queryByRole('button', { name: 'On hold' })).not.toBeInTheDocument()
  })

  it.each(['0.00', '2.50'])('only allocates a Savings column when a part has savings (%s)', async (savings) => {
    const part = {
      id: 'usage-1', repair_order_id: 'order-1', inventory_id: 'part-1', inventory_sku: 'BS-1', inventory_name: 'Brake Shoes',
      quantity: '1', unit_type: 'each', unit_price: '50', total_price: '50', savings, source_service_id: null, source_line_id: null,
    }
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? { ...emptySummary, parts: [part] } : [] }))
    renderPanel()
    await screen.findByText('Brake Shoes')
    expect(screen.getByRole('textbox', { name: 'Quantity for Brake Shoes' })).toHaveValue('1')
    if (savings === '0.00') expect(screen.queryByRole('columnheader', { name: 'Savings' })).not.toBeInTheDocument()
    else expect(screen.getByRole('columnheader', { name: 'Savings' })).toBeInTheDocument()
  })

  it('dismisses part pricing without saving and preserves explicit price application', async () => {
    const part = {
      pricing: { ...price, pricing_version: 2 },
      id: 'usage-1', repair_order_id: 'order-1', inventory_id: 'part-1', inventory_sku: 'BS-1', inventory_name: 'Brake Shoes',
      quantity: '1', unit_type: 'each', unit_price: '50', total_price: '50', savings: '0', source_service_id: null, source_line_id: null,
    }
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? { ...emptySummary, parts: [part] } : [] }))
    apiMocks.patch.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    renderPanel()
    const trigger = await screen.findByRole('button', { name: '$50.00' })
    await user.click(trigger)
    await user.clear(screen.getByRole('textbox', { name: 'Customer price' }))
    await user.type(screen.getByRole('textbox', { name: 'Customer price' }), '42')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByLabelText('Part pricing for Brake Shoes')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
    expect(apiMocks.patch).not.toHaveBeenCalled()
    await user.click(trigger)
    expect(screen.getByRole('textbox', { name: 'Customer price' })).toHaveValue('50.00')
    await user.clear(screen.getByRole('textbox', { name: 'Customer price' }))
    await user.type(screen.getByRole('textbox', { name: 'Customer price' }), '45')
    await user.type(screen.getByRole('textbox', { name: 'Override reason' }), 'Customer agreement')
    await user.click(screen.getByRole('button', { name: 'Apply', exact: true }))
    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledWith('/repair-orders/order-1/parts/usage-1', { unit_price: '45.00', price_action: 'manual', price_override_reason: 'Customer agreement', expected_pricing_version: 2 }))
    await waitFor(() => expect(screen.queryByLabelText('Part pricing for Brake Shoes')).not.toBeInTheDocument())
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

  it('reviews a bundled operation, retains its search on cancel, and requires acceptance of a changed quote', async () => {
    const serviceId = 'service-1'
    const plan = { kind: 'service_apply' as const, service_id: serviceId, quantity: '1' }
    const bundleQuote = (fingerprint: string, amount: string) => {
      const result = quote({ fingerprint, total: amount })
      return { ...result, plan_kind: 'service_apply', lines: result.lines.map(line => ({ ...line, source_service_id: serviceId, source_component_id: 'component-1' })) }
    }
    apiMocks.resolve.mockResolvedValue({ data: bundleQuote('bundle-old', '15.00') })
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? emptySummary : [] }))
    let writes = 0
    apiMocks.post.mockImplementation((url: string) => {
      if (url.endsWith('/repair-ops/search')) return Promise.resolve({ data: { candidates: [{ operation_id: `service:${serviceId}`, name: 'Filter service bundle', estimated_hours: '0.25', provider: 'service_catalog' }], warnings: [] } })
      if (url.endsWith('/flat-service')) {
        writes += 1
        if (writes === 1) return Promise.reject({ response: { status: 409, data: { detail: { code: 'pricing_preview_changed', message: 'Service price changed.', preview: bundleQuote('bundle-fresh', '19.00') } } } })
        return Promise.resolve({ data: emptySummary })
      }
      throw new Error(`Unexpected POST ${url}`)
    })
    const user = userEvent.setup(); renderPanel()
    const search = await screen.findByPlaceholderText(/add operation/i)
    await user.type(search, 'filter service')
    await user.click(await screen.findByRole('button', { name: 'Apply operation' }))
    expect(await screen.findByRole('dialog', { name: 'Review parts pricing' })).toHaveTextContent('$15.00')
    expect(writes).toBe(0)
    await user.click(screen.getByRole('button', { name: 'Cancel', exact: true }))
    expect(search).toHaveValue('filter service')
    expect(writes).toBe(0)
    await user.click(screen.getByRole('button', { name: 'Apply operation' }))
    await user.click(await screen.findByRole('button', { name: 'Confirm price' }))
    const changed = await screen.findByRole('dialog', { name: 'Review changed price' })
    expect(changed).toHaveTextContent('$19.00')
    expect(changed).toHaveTextContent('Previously $15.00')
    expect(writes).toBe(1)
    await user.click(within(changed).getByRole('button', { name: 'Accept new price' }))
    await waitFor(() => expect(search).toHaveValue(''))
    expect(apiMocks.resolve).toHaveBeenCalledWith({ context: { kind: 'repair_order', repair_order_id: 'order-1' }, plan })
    const calls = apiMocks.post.mock.calls.filter(([url]) => url.endsWith('/flat-service'))
    expect(calls).toHaveLength(2)
    expect(calls[0][1]).toEqual({ service_id: serviceId, quantity: 1, pricing_preview_fingerprint: 'bundle-old', pricing_presentation: 'shop' })
    expect(calls[1][1]).toEqual({ service_id: serviceId, quantity: 1, pricing_preview_fingerprint: 'bundle-fresh', pricing_presentation: 'shop' })
    expect(calls[1][2].headers['Idempotency-Key']).not.toBe(calls[0][2].headers['Idempotency-Key'])
    expect(apiMocks.post.mock.calls.some(([url]) => url.endsWith('/repair-ops/apply'))).toBe(false)
  })

  it('persists manually entered labor duration through the optimistic pricing rollup', async () => {
    apiMocks.get.mockImplementation((url: string) => {
      if (url.endsWith('/price-build')) return Promise.resolve({ data: {
        ...emptySummary,
        lines: [{ id: 'labor-1', repair_order_id: 'order-1', description: 'Duration test', hours: '1.00', hourly_rate: '100.00', total_cost: '100.00', line_type: 'manual', source_service_id: null }],
      } })
      return Promise.resolve({ data: [] })
    })
    apiMocks.patch.mockResolvedValue({ data: {} })
    const user = userEvent.setup()
    renderPanel()
    await user.click(await screen.findByRole('button', { name: /Duration test/ }))
    const duration = screen.getByRole('textbox', { name: 'Labor duration', exact: true })
    await user.click(duration)
    await user.keyboard('1:20{Enter}')
    await waitFor(() => expect(apiMocks.patch).toHaveBeenCalledWith('/repair-orders/order-1/price-build/lines/labor-1', { hours: 1.33 }))
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
      }), expect.objectContaining({ headers: { 'Idempotency-Key': expect.any(String) } }))
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
    expect(await screen.findByLabelText('Technician status')).toHaveTextContent('Mike Johnson')
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

  it('requires fresh completion confirmation when switching orders through a recommendation link', async () => {
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? emptySummary : [] }))
    const user = userEvent.setup()
    const props = { orderStatus: 'in_progress' as const, quoteIsApproved: true, onAdminCompleteWork: vi.fn() }
    const view = renderPanel(props)
    await user.click(await screen.findByRole('button', { name: 'Mark Completed' }))
    expect(screen.getByText('Mark work completed')).toBeInTheDocument()
    view.rerenderPanel({ ...props, orderId: 'order-2' })
    expect(screen.queryByText('Mark work completed')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark Completed' })).toBeEnabled()
    expect(props.onAdminCompleteWork).not.toHaveBeenCalled()
  })

  it('keeps the primary invoice action visible and secondary actions reachable on phones with paid and pending guards', async () => {
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? emptySummary : [] }))
    const compact = vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
      matches: query.includes('max-width'), media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
    const onRecordPayment = vi.fn()
    const onResendInvoice = vi.fn()
    const onVoidInvoice = vi.fn()
    const invoice = {
      id: 'invoice-1', tenant_id: 'tenant-1', repair_order_id: 'order-1', invoice_number: 'INV-1001',
      status: 'sent' as const, subtotal: '100', tax_amount: '0', discount_amount: '0', total_amount: '100',
      due_date: null, paid_at: null, notes: null, created_at: '2026-10-12T00:00:00Z', updated_at: '2026-10-12T00:00:00Z',
    }
    const props = { orderStatus: 'invoiced' as const, invoice, onRecordPayment, onResendInvoice, onVoidInvoice }
    const view = renderPanel(props)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Record payment' }))
    expect(screen.queryByRole('button', { name: 'Resend invoice' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Repair order actions', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Resend invoice' }))
    await user.click(screen.getByRole('button', { name: 'Repair order actions', exact: true }))
    await user.click(screen.getByRole('button', { name: 'Void & revise' }))
    expect(onRecordPayment).toHaveBeenCalledOnce()
    expect(onResendInvoice).toHaveBeenCalledOnce()
    expect(onVoidInvoice).toHaveBeenCalledOnce()
    view.rerenderPanel({ ...props, invoiceActionPending: true })
    expect(screen.getByRole('button', { name: 'Record payment' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Repair order actions', exact: true }))
    expect(screen.getByRole('button', { name: 'Resend invoice' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Void & revise' })).toBeDisabled()
    view.rerenderPanel({ ...props, orderStatus: 'paid', invoice: { ...invoice, status: 'paid', paid_at: '2026-10-12T12:00:00Z' } })
    expect(screen.queryByRole('button', { name: 'Record payment' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Void & revise' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resend copy' })).toBeEnabled()
    compact.mockRestore()
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

  it('keeps secondary panels mutually exclusive, preserves note drafts, and resets on order navigation', async () => {
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/price-build') ? emptySummary : [],
    }))
    const user = userEvent.setup()
    const onAddNote = vi.fn()
    const onRecommendedServicesOpenChange = vi.fn()
    const view = renderPanel({ onAddNote, onRecommendedServicesOpenChange })
    const recommended = screen.getByRole('button', { name: /Recommended Services/ })
    const notes = screen.getByRole('button', { name: /^Notes/ })
    const photos = await screen.findByRole('button', { name: 'Photos No photos attached' })
    const pills = [recommended, notes, photos]
    for (const selected of [recommended, notes, photos, notes, recommended, photos]) {
      await user.click(selected)
      for (const pill of pills) expect(pill).toHaveAttribute('aria-expanded', String(pill === selected))
      expect(onRecommendedServicesOpenChange).toHaveBeenLastCalledWith(selected === recommended)
    }
    await user.click(photos)
    for (const pill of pills) expect(pill).toHaveAttribute('aria-expanded', 'false')
    await user.click(notes)
    await user.click(screen.getByRole('button', { name: 'Add note', exact: true }))
    const draft = screen.getByPlaceholderText('Note for the shop — never shown to the customer…')
    await user.type(draft, 'Keep this draft')
    await user.click(photos)
    expect(screen.queryByDisplayValue('Keep this draft')).not.toBeInTheDocument()
    await user.click(notes)
    expect(screen.getByDisplayValue('Keep this draft')).toBeVisible()
    notes.focus()
    await user.keyboard('{Enter}')
    expect(notes).toHaveAttribute('aria-expanded', 'false')
    await user.click(photos)
    view.rerenderPanel({ orderId: 'order-2', onAddNote, onRecommendedServicesOpenChange })
    for (const pill of pills) expect(pill).toHaveAttribute('aria-expanded', 'false')
  })

  it.each([0, 1, 2, 12])('shows only the count for %i photos in both disclosure states', async (count) => {
    const photos = Array.from({ length: count }, (_, index) => ({
      id: `photo-${index}`, repair_order_id: 'order-1',
      image_url: `https://example.com/repair-${index}.jpg`,
      caption: `Repair detail ${index}`, uploaded_at: '2026-10-01T12:00:00Z',
      uploader_name: 'Shop Admin',
    }))
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({
      data: url.endsWith('/price-build') ? emptySummary : url.endsWith('/photos') ? photos : [],
    }))
    const user = userEvent.setup()
    renderPanel()
    const trigger = await screen.findByRole('button', { name: count ? `Photos ${count} photo${count === 1 ? '' : 's'} attached` : 'Photos No photos attached' })
    const assertTrigger = (expanded: boolean) => {
      expect(trigger).toHaveAttribute('aria-expanded', String(expanded))
      const countLabel = within(trigger).getByText(String(count), { exact: true })
      expect(countLabel).toBeVisible()
      expect(countLabel).toHaveClass('inline-flex', 'items-center', 'justify-center', 'align-baseline', 'normal-nums')
      expect(countLabel).not.toHaveClass('tabular-nums')
      expect(countLabel.parentElement).toHaveTextContent(`Photos${count}`)
      expect(countLabel.parentElement?.parentElement).toHaveClass('text-sm', 'font-semibold')
      if (count > 0) expect(countLabel).toHaveClass('h-5', 'min-w-5', 'rounded-full', 'ring-emerald-300', 'bg-emerald-50')
      else expect(countLabel).not.toHaveClass('ring-emerald-300')
      expect(within(trigger).queryByRole('img')).not.toBeInTheDocument()
      expect(trigger).toHaveClass('whitespace-nowrap', 'shrink-0')
    }
    assertTrigger(false)
    await user.click(trigger)
    assertTrigger(true)
    for (const photo of photos) expect(screen.getByRole('img', { name: photo.caption })).toBeVisible()
    await user.click(trigger)
    assertTrigger(false)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
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

  it.each([
    ['invoiced', 'Invoiced'],
    ['paid', 'Paid'],
    ['completed', 'Work complete'],
    ['cancelled', 'Cancelled'],
  ] as const)('keeps the %s footer canonical while invoice detail is absent', async (orderStatus, label) => {
    apiMocks.get.mockImplementation((url: string) => Promise.resolve({ data: url.endsWith('/price-build') ? emptySummary : [] }))

    const { container } = renderPanel({ orderStatus })
    const footer = container.querySelector('.db-workspace-footer') as HTMLElement

    expect(within(footer).getByText(label)).toHaveAttribute('role', 'status')
    expect(within(footer).queryByText('Work order open')).not.toBeInTheDocument()
    await waitFor(() => expect(within(footer).getByText('$0.00')).toBeVisible())
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
