import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import RepairOrdersPage from '../RepairOrdersPage'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('@/lib/api', () => ({ default: api }))
vi.mock('@/hooks/useWebSocket', () => ({ useWebSocket: vi.fn() }))
vi.mock('@/contexts/ThemeContext', () => ({ useTheme: () => ({ presentationVariant: 'new', accentColors: { 500: '#f59e0b' } }) }))

const order = {
  id: 'ets-order', tenant_id: 'tenant-139', customer_id: 'customer-139', vehicle_id: 'vehicle-139',
  source: 'easy_truck_shop_import', imported_invoice_total_amount: '534.41',
  order_number: 'ETS-7001-8002', status: 'completed', description: 'PM service',
  vehicle_make: 'VOLVO', vehicle_model: 'VNL', vehicle_year: 2021,
  customer_company_name: 'Imported shop customer', assigned_mechanic_id: null, is_internal: false,
  total_parts_cost: '489.52', total_labor_cost: '0.00', total_cost: '-150.00',
  created_at: '2026-10-13T12:00:00Z', updated_at: '2026-10-13T13:00:00Z', deleted_at: null,
}
const detail = {
  ...order,
  labor_items: [{ id: 'stale-labor', repair_order_id: order.id, description: 'STALE imported labor', hours: '1.25', hourly_rate: '120.00', total_cost: '0.00', mechanic_id: null, line_type: 'manual' }],
  parts_usage: [{ id: 'stale-part', repair_order_id: order.id, inventory_id: 'inventory-139', inventory_name: 'STALE imported part', inventory_sku: 'STALE-139', quantity: '1', unit_type: 'each', unit_price: '489.52', total_price: '489.52' }],
  history_events: [],
}
const sourceBilling = {
  source: 'easy_truck_shop_import', evidence_basis: 'ets_source_snapshot', reconciliation_status: 'not_checked',
  invoice_id: 'ets-invoice', invoice_number: 'ETSINV-9001', total_amount: '534.41',
  recorded_completed_amount: '534.41', recorded_remaining_amount: '0.00', payment_status: 'paid',
  observed_at: '2026-10-18T20:00:00Z', review_required: false, review_reasons: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  useAuthStore.setState({ user: { id: 'owner-139', tenant_id: 'tenant-139', role: 'garage_owner' } as NonNullable<ReturnType<typeof useAuthStore.getState>['user']>, authSessionEpoch: 139, logoutInProgress: false })
  api.get.mockImplementation(async (url: string) => {
    if (url === '/repair-orders') return { data: { items: [order], total: 1, has_more: false } }
    if (url.endsWith('/workspace')) return { data: order }
    if (url.endsWith('/detail')) return { data: detail }
    if (url.endsWith('/imported-billing')) return { data: sourceBilling }
    if (url.endsWith('/price-build')) return { data: { order_id: order.id, labor_total: '150.00', parts_total: '489.52', total_cost: '-150.00', lines: [{ id: 'line-139', description: 'PM service', hours: '1.25', hourly_rate: '120.00', total_cost: '0.00', line_type: 'manual' }], parts: [], warnings: [], pricing_locked: false, can_edit_work: false } }
    if (url.endsWith('/operations')) return { data: { items: [], summary: { tracked: 0, completed: 0, remaining: 0, legacy_untracked: 0 } } }
    if (url.endsWith('/checklist')) return { data: { items: [], total: 0, summary: { total: 0, required_remaining: 0 } } }
    if (url.endsWith('/history')) return { data: { revisions: [], events: [] } }
    if (url.startsWith('/quotes?')) return { data: null }
    if (url === '/repair-orders/recommended-work') return { data: { items: [], total: 0, skip: 0, limit: 25 } }
    return { data: [] }
  })
})
afterEach(() => { vi.unstubAllGlobals(); useAuthStore.setState({ user: null }) })

describe('imported repair-order billing page', () => {
  it.each([
    [true, false],
    [false, true],
    [undefined, false],
  ] as const)('uses full-filter imported metadata %s rather than the native-only loaded page', async (hasImportedOrders, showAggregate) => {
    const fallbackGet = api.get.getMockImplementation()!
    const nativeOrder = { ...order, id: 'native-order', order_number: 'RO-139-NATIVE', source: null, imported_invoice_total_amount: null, total_parts_cost: '123.00', total_labor_cost: '10.00', total_cost: '133.00' }
    api.get.mockImplementation(async (url: string) => {
      if (url === '/repair-orders') return { data: { items: [nativeOrder], total: 55, has_more: true } }
      if (url === '/repair-orders/value-summary') return { data: { order_count: 55, order_value: '99123.45', ...(hasImportedOrders === undefined ? {} : { has_imported_orders: hasImportedOrders }) } }
      return fallbackGet(url)
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><RepairOrdersPage /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByRole('button', { name: 'Open repair order RO-139-NATIVE', exact: true })).toBeVisible()
    await waitFor(() => expect(client.getQueriesData({ queryKey: ['repair-orders', 'value-summary'] }).some(([, value]) => (value as { order_count?: number } | undefined)?.order_count === 55)).toBe(true))
    expect(screen.getByText('$133.00')).toBeVisible()
    if (showAggregate) {
      expect(screen.getByText('$99,123.45')).toBeVisible()
      expect(screen.getByText('Filtered order value')).toBeInTheDocument()
    } else {
      expect(screen.queryByText('$99,123.45')).not.toBeInTheDocument()
      expect(screen.queryByText('Filtered order value')).not.toBeInTheDocument()
    }
  })

  it('passes shared invoice context to every related ledger row without showing an additive total', async () => {
    const shared = { ...sourceBilling, shared_invoice: true, payment_status: 'partially_paid', recorded_completed_amount: '100.00', recorded_remaining_amount: '434.41', invoice_repair_order_id: order.id, invoice_repair_order_number: order.order_number }
    const getDefault = api.get.getMockImplementation()!
    api.get.mockImplementation(async (url: string, ...args: unknown[]) => {
      if (url === '/repair-orders') return { data: { items: [
        { ...order, imported_billing: shared },
        { ...order, id: 'ets-sibling', order_number: 'ETS-7001-8002-2', imported_billing: shared },
      ], total: 2, has_more: false } }
      if (url.startsWith('/repair-orders/value-summary')) return { data: { order_count: 2, order_value: '1068.82', has_imported_orders: true } }
      return getDefault(url, ...args)
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><MemoryRouter><RepairOrdersPage /></MemoryRouter></QueryClientProvider>)
    for (const number of ['ETS-7001-8002', 'ETS-7001-8002-2']) {
      const row = await screen.findByRole('article', { name: `Repair order ${number}` })
      expect(within(row).getByText('Partially paid in ETS')).toBeVisible()
      expect(within(row).getByText('$434.41')).toBeVisible()
      expect(within(row).getByText('Shared ETS invoice')).toBeVisible()
    }
    expect(screen.queryByText('$1,068.82')).not.toBeInTheDocument()
    expect(screen.queryByText('Filtered order value')).not.toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    expect(api.patch).not.toHaveBeenCalled()
  })

  it('keeps legacy detail prices and editing controls absent after History loads full detail', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    const { container } = render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/?selected=ets-order']}><RepairOrdersPage /></MemoryRouter></QueryClientProvider>)
    const user = userEvent.setup()
    expect(await screen.findByText('Paid in ETS')).toBeVisible()
    await user.click(await screen.findByRole('button', { name: 'Repair order history', exact: true }))
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/repair-orders/ets-order/detail', expect.anything()))
    await waitFor(() => expect(client.getQueriesData({ queryKey: ['repair-order-detail', order.id] }).some(([, value]) => (value as typeof detail | undefined)?.labor_items?.length === 1)).toBe(true))

    expect(container.querySelector('.db-workspace-footer')).toHaveTextContent('$534.41')
    expect(screen.getByText('Paid in ETS')).toBeVisible()
    expect(screen.queryByText('ETS source snapshot · QuickBooks not checked')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'ETS billing details' }))
    expect(screen.getByText('ETS source snapshot · QuickBooks not checked')).toBeVisible()
    await user.keyboard('{Escape}')
    for (const stale of ['$489.52', '$-150.00', 'STALE imported labor', 'STALE imported part']) {
      expect(screen.queryByText(stale, { exact: true })).not.toBeInTheDocument()
    }
    for (const action of ['Create Invoice', 'Record payment', 'Remove part', 'Remove labor', 'Add labor', '+ Add part']) {
      expect(screen.queryByRole('button', { name: action, exact: true })).not.toBeInTheDocument()
    }
    expect(api.post).not.toHaveBeenCalled()
    expect(api.patch).not.toHaveBeenCalled()
    expect(api.delete).not.toHaveBeenCalled()
  })
})
