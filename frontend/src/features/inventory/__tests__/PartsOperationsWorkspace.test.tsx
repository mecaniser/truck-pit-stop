import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import fixture from '../../../../../backend/tests/fixtures/db038_parts_operations.json'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner' }))
const brandingState = vi.hoisted(() => ({ name: 'Truck Pit Stop Wisconsin', logoUrl: 'https://images.example.test/tenant-logo.png' as string | null }))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, post: apiMocks.post, put: apiMocks.put } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: authState.role } }) }))
vi.mock('@/hooks/useTenantBranding', () => ({ default: () => ({ data: { name: brandingState.name, logo_url: brandingState.logoUrl } }) }))

import { PartsOperationsGate } from '../PartsOperationsWorkspace'

const oilFilter = fixture.read_contract.expected_oil_filter_demand
const inventoryItem = { ...fixture.inventory[0], tenant_id: fixture.tenant_ids.primary, description: null, category: 'Filters', core_charge: '0.00', selling_price: '20.00', supplier_name: 'Fleet Parts Co', supplier_contact: null, image_url: null, location: 'A-01', is_placeholder: false, created_at: fixture.frozen_at, updated_at: fixture.frozen_at } as const

function LocationProbe() { return <output data-testid="location">{useLocation().pathname}{useLocation().search}</output> }
function renderGate() { const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/dashboard/garage/inventory']}><PartsOperationsGate legacy={<p>Legacy inventory catalog</p>} /><LocationProbe /></MemoryRouter></QueryClientProvider>) }

function installFixture() {
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 1, open_purchase_order_count: 1 } })
    if (url === '/parts-operations/demand') return Promise.resolve({ data: { items: [oilFilter], total: 1, skip: 0, limit: 100, has_more: false } })
    if (url === '/inventory') return Promise.resolve({ data: { items: [inventoryItem], total: 1, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/purchase-orders') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    throw new Error(`Unexpected GET ${url}`)
  })
  apiMocks.post.mockResolvedValue({ data: { id: 'po-created' } })
}

function installLargeFixture() {
  const demand = Array.from({ length: 100 }, (_, index) => ({
    ...oilFilter,
    inventory_id: `demand-${index + 1}`,
    sku: `DB-FILTER-${String(index + 1).padStart(3, '0')}`,
    name: `Fleet filter ${index + 1}`,
    state: index === 99 ? 'unlinked' : 'open',
    repair_shortage_packages: index % 2 === 0 ? 2 : 0,
    shelf_replenishment_packages: index % 2 === 0 ? 0 : 1,
    preferred_supplier: index === 99 ? null : oilFilter.preferred_supplier,
  }))
  const inventory = Array.from({ length: 100 }, (_, index) => ({
    ...inventoryItem,
    id: `inventory-${index + 1}`,
    sku: `DB-INVENTORY-${String(index + 1).padStart(3, '0')}`,
    name: `Fleet filter ${index + 1}`,
  }))
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 50, open_purchase_order_count: 4 } })
    if (url === '/parts-operations/demand') return Promise.resolve({ data: { items: demand, total: demand.length, skip: 0, limit: 100, has_more: false } })
    if (url === '/inventory') return Promise.resolve({ data: { items: inventory, total: inventory.length, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/purchase-orders') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    throw new Error(`Unexpected GET ${url}`)
  })
}

function installDemandSelectionFixture() {
  const engineOil = { ...oilFilter, inventory_id: 'engine-oil', sku: 'ENG-OIL-10W30', name: 'Engine oil Delo 10w30', recommended_order_packages: 9 }
  const fuelFilter = { ...oilFilter, inventory_id: 'fuel-filter', sku: 'FUEL-FILTER-KIT', name: 'Fuel Filter Kit', recommended_order_packages: 3 }
  const inventory = [
    { ...inventoryItem, id: engineOil.inventory_id, name: engineOil.name, sku: engineOil.sku },
    { ...inventoryItem, id: fuelFilter.inventory_id, name: fuelFilter.name, sku: fuelFilter.sku },
  ]
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 2, open_purchase_order_count: 0 } })
    if (url === '/parts-operations/demand') return Promise.resolve({ data: { items: [engineOil, fuelFilter], total: 2, skip: 0, limit: 100, has_more: false } })
    if (url === '/inventory') return Promise.resolve({ data: { items: inventory, total: inventory.length, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/purchase-orders') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    throw new Error(`Unexpected GET ${url}`)
  })
  apiMocks.post.mockResolvedValue({ data: { id: 'po-created' } })
}

function installInventoryControlsFixture() {
  const inventory = [
    { ...inventoryItem, id: oilFilter.inventory_id, sku: 'AIR-000', name: 'Air filter', stock_quantity: 0, reorder_level: 2, supplier_name: 'Alpha Supply', location: 'A-01', image_url: 'https://images.example.test/air-filter.png', ets_retired_at: null },
    { ...inventoryItem, id: 'brake-shoe', sku: 'BRK-200', name: 'Brake shoe', stock_quantity: 2, reorder_level: 5, supplier_name: 'Beta Supply', location: 'B-02', image_url: 'https://images.example.test/broken.png', ets_retired_at: null },
    { ...inventoryItem, id: 'coolant', sku: 'CLT-900', name: 'Coolant', stock_quantity: 10, reorder_level: 3, supplier_name: 'Gamma Supply', location: 'C-03', image_url: null, ets_retired_at: null },
    { ...inventoryItem, id: 'placeholder', sku: 'TMP-100', name: 'Temporary catalog item', stock_quantity: 1, reorder_level: 8, supplier_name: null, location: null, image_url: null, is_placeholder: true, ets_retired_at: null },
    { ...inventoryItem, id: 'retired-empty', sku: 'RET-000', name: 'Retired empty item', stock_quantity: 0, reorder_level: 4, supplier_name: 'Archive Supply', location: 'R-01', image_url: null, ets_retired_at: fixture.frozen_at },
  ]
  const demand = inventory.slice(0, 3).map((item) => ({ ...oilFilter, inventory_id: item.id, sku: item.sku, name: item.name }))
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 2, open_purchase_order_count: 0 } })
    if (url === '/parts-operations/demand') return Promise.resolve({ data: { items: demand, total: demand.length, skip: 0, limit: 100, has_more: false } })
    if (url === '/inventory') return Promise.resolve({ data: { items: inventory, total: inventory.length, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/purchase-orders' || url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    throw new Error(`Unexpected GET ${url}`)
  })
}

function installSelectionLifecycleFixture() {
  const engineOil = { ...oilFilter, inventory_id: 'engine-oil', sku: 'ENG-OIL-10W30', name: 'Engine oil Delo 10w30', recommended_order_packages: 9 }
  const fuelFilter = { ...oilFilter, inventory_id: 'fuel-filter', sku: 'FUEL-FILTER-KIT', name: 'Fuel Filter Kit', recommended_order_packages: 3 }
  const inventory = [
    { ...inventoryItem, id: engineOil.inventory_id, name: engineOil.name, sku: engineOil.sku, stock_quantity: 4, reorder_level: 6 },
    { ...inventoryItem, id: fuelFilter.inventory_id, name: fuelFilter.name, sku: fuelFilter.sku, stock_quantity: 8, reorder_level: 3 },
  ]
  const purchaseOrders = [
    { id: 'po-first', po_number: 'PO-FIRST', supplier_id: fixture.ids.supplier, supplier: oilFilter.preferred_supplier, status: 'submitted', version: 1, expected_at: null, line_count: 1, ordered_quantity: 9, received_quantity: 0, remaining_quantity: 9, created_at: fixture.frozen_at },
    { id: 'po-second', po_number: 'PO-SECOND', supplier_id: fixture.ids.supplier, supplier: oilFilter.preferred_supplier, status: 'draft', version: 1, expected_at: null, line_count: 1, ordered_quantity: 3, received_quantity: 0, remaining_quantity: 3, created_at: fixture.frozen_at },
  ]
  const purchaseOrderDetails = Object.fromEntries(purchaseOrders.map((po) => [po.id, { ...po, notes: null, lines: [{ id: `${po.id}-line`, inventory_id: engineOil.inventory_id, sku: engineOil.sku, description: engineOil.name, unit_type: engineOil.unit_type, unit_cost: '20.00', ordered_quantity: po.ordered_quantity, received_quantity: 0 }] }]))
  const returns = [
    { id: 'return-first', return_number: 'RET-FIRST', supplier_id: fixture.ids.supplier, supplier: oilFilter.preferred_supplier, kind: 'stock', status: 'submitted', version: 1, line_count: 1, total_quantity: 1, expected_credit_total: '20.00', reverses_return_id: null, created_at: fixture.frozen_at },
    { id: 'return-second', return_number: 'RET-SECOND', supplier_id: fixture.ids.supplier, supplier: oilFilter.preferred_supplier, kind: 'stock', status: 'draft', version: 1, line_count: 1, total_quantity: 2, expected_credit_total: '40.00', reverses_return_id: null, created_at: fixture.frozen_at },
  ]
  const returnDetails = Object.fromEntries(returns.map((row) => [row.id, { ...row, reason: 'Supplier return', notes: null, lines: [{ id: `${row.id}-line`, inventory: { id: engineOil.inventory_id, sku: engineOil.sku, name: engineOil.name }, quantity: row.total_quantity, expected_credit: row.expected_credit_total, actual_credit: null, source: { type: 'receipt', id: 'receipt-source' } }] }]))
  const cores = [
    { id: 'core-first', inventory_id: engineOil.inventory_id, inventory: { id: engineOil.inventory_id, sku: engineOil.sku, name: 'Engine oil core' }, supplier_id: fixture.ids.supplier, supplier: oilFilter.preferred_supplier, quantity: 1, status: 'on_hand', version: 1, unit_core_value: '20.00', source: { repair_order_id: fixture.ids.repair_order, order_number: 'TPS-000301' }, created_at: fixture.frozen_at },
    { id: 'core-second', inventory_id: fuelFilter.inventory_id, inventory: { id: fuelFilter.inventory_id, sku: fuelFilter.sku, name: 'Fuel filter core' }, supplier_id: fixture.ids.supplier, supplier: oilFilter.preferred_supplier, quantity: 1, status: 'expected', version: 1, unit_core_value: '15.00', source: { repair_order_id: fixture.ids.repair_order, order_number: 'TPS-000302' }, created_at: fixture.frozen_at },
  ]
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 1, open_purchase_order_count: 2 } })
    if (url === '/parts-operations/demand') return Promise.resolve({ data: { items: [engineOil, fuelFilter], total: 2, skip: 0, limit: 100, has_more: false } })
    if (url === '/inventory') return Promise.resolve({ data: { items: inventory, total: 2, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/purchase-orders') return Promise.resolve({ data: { items: purchaseOrders, total: 2, skip: 0, limit: 100, has_more: false } })
    if (url.startsWith('/parts-operations/purchase-orders/')) return Promise.resolve({ data: purchaseOrderDetails[url.split('/').at(-1)!] })
    if (url === '/parts-operations/returns') return Promise.resolve({ data: { items: returns, total: 2, skip: 0, limit: 100, has_more: false } })
    if (url.startsWith('/parts-operations/returns/')) return Promise.resolve({ data: returnDetails[url.split('/').at(-1)!] })
    if (url === '/parts-operations/cores') return Promise.resolve({ data: { items: cores, total: 2, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    throw new Error(`Unexpected GET ${url}`)
  })
}

describe('DB-038 Parts Operations workspace', () => {
  afterEach(() => { apiMocks.get.mockReset(); apiMocks.post.mockReset(); apiMocks.put.mockReset(); authState.role = 'garage_owner'; brandingState.name = 'Truck Pit Stop Wisconsin'; brandingState.logoUrl = 'https://images.example.test/tenant-logo.png' })
  it('falls back to the existing catalog only when the server says the feature is unavailable', async () => { apiMocks.get.mockRejectedValue(Object.assign(new Error('off'), { response: { status: 404 } })); renderGate(); expect(await screen.findByText('Legacy inventory catalog')).toBeInTheDocument() })
  it('keeps a transient server failure visible instead of silently simulating an enabled feature', async () => { apiMocks.get.mockRejectedValue(Object.assign(new Error('offline'), { response: { status: 503 } })); renderGate(); expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable'); expect(screen.queryByText('Legacy inventory catalog')).not.toBeInTheDocument() })
  it('uses frozen demand evidence, deep-links to the canonical repair order, and posts an idempotent PO draft', async () => {
    installFixture(); const user = userEvent.setup(); renderGate()
    expect(await screen.findByRole('heading', { name: 'Parts & inventory' })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Oil filter/i }))
    await user.click(await screen.findByRole('button', { name: /Repair order TPS-000301/i })); expect(screen.getByTestId('location')).toHaveTextContent('/dashboard/repair-orders?selected=30000000-0000-4000-8000-000000000301')
    await user.type(screen.getByLabelText('PO number'), 'PO-000302'); await user.click(screen.getByRole('button', { name: 'Create draft PO' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/purchase-orders', expect.objectContaining({ supplier_id: fixture.ids.supplier, lines: [expect.objectContaining({ inventory_id: fixture.ids.oil_filter, ordered_quantity: 3 })] }), expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.stringMatching(/^po-create-/) }) })))
  })
  it('keeps reception staff read-only while exposing the same demand evidence', async () => { authState.role = 'receptionist'; installFixture(); const user = userEvent.setup(); renderGate(); await user.click(await screen.findByRole('button', { name: /Oil filter/i })); expect(screen.getByText(/Read-only access/)).toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Create draft PO' })).not.toBeInTheDocument() })
  it('uses one composed search shell for both demand and inventory', async () => {
    installFixture()
    const user = userEvent.setup()
    renderGate()

    const demandSearch = await screen.findByRole('searchbox', { name: 'Search demand' })
    expect(demandSearch.closest('label')).toHaveClass('db-parts-operations__search')
    expect(demandSearch.closest('label')?.querySelectorAll('input')).toHaveLength(1)

    await user.click(screen.getByRole('tab', { name: 'Inventory' }))
    const inventorySearch = screen.getByRole('searchbox', { name: 'Search inventory' })
    expect(inventorySearch.closest('label')).toHaveClass('db-parts-operations__search')
    expect(inventorySearch.closest('label')?.querySelectorAll('input')).toHaveLength(1)
  })
  it('loads only the active work area and makes the reorder summary actionable', async () => {
    installFixture()
    const user = userEvent.setup()
    renderGate()
    await screen.findByRole('searchbox', { name: 'Search demand' })
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/demand', expect.anything())
    expect(apiMocks.get).toHaveBeenCalledWith('/inventory', expect.anything())
    expect(apiMocks.get).not.toHaveBeenCalledWith('/parts-operations/purchase-orders', expect.anything())
    expect(apiMocks.get).not.toHaveBeenCalledWith('/parts-operations/returns', expect.anything())
    expect(apiMocks.get).not.toHaveBeenCalledWith('/parts-operations/activity', expect.anything())

    await user.click(screen.getByRole('button', { name: /Need reorder/ }))
    expect(screen.getByRole('tab', { name: 'Inventory' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByRole('button', { name: 'Needs reorder' })).toHaveAttribute('aria-pressed', 'true')
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/activity', expect.anything())
  })
  it('renders large inventories in bounded 50-row chunks', async () => {
    installLargeFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    await screen.findByText('100 active parts')
    const rows = () => screen.queryAllByRole('button').filter((button) => button.hasAttribute('data-parts-row'))
    expect(rows()).toHaveLength(50)
    await user.click(screen.getByRole('button', { name: 'Show 50 more parts' }))
    expect(rows()).toHaveLength(100)
    expect(screen.queryByRole('button', { name: /Show .* more parts/ })).not.toBeInTheDocument()
  })
  it('separates quantity, reorder, and cost changes while keeping the selected row', async () => {
    installInventoryControlsFixture()
    let resolveSave!: (value: unknown) => void
    apiMocks.put.mockImplementation(() => new Promise((resolve) => { resolveSave = resolve }))
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    const selectedRow = screen.getByRole('button', { name: /Air filter/i })
    expect(selectedRow).toHaveAttribute('aria-current', 'true')
    expect(screen.getByText(/Unit not set/)).toBeInTheDocument()
    expect(screen.queryByText(/undefined/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Adjust quantities' }))
    await user.clear(screen.getByLabelText('Available now')); await user.type(screen.getByLabelText('Available now'), '7')
    await user.clear(screen.getByLabelText('Incoming quantity')); await user.type(screen.getByLabelText('Incoming quantity'), '4')
    expect(screen.getByLabelText('Available now')).toHaveValue(7)
    await user.type(await screen.findByLabelText('Adjustment reason'), 'Cycle count correction')
    const save = screen.getByRole('button', { name: 'Save quantities' })
    await user.dblClick(save)
    expect(apiMocks.put).toHaveBeenCalledTimes(1)
    expect(apiMocks.put).toHaveBeenCalledWith(`/inventory/${oilFilter.inventory_id}`, {
      stock_quantity: 7,
      on_order_quantity: 4,
      stock_adjustment_reason: 'Cycle count correction',
    })
    expect(save).toBeDisabled()
    resolveSave({ data: { ...inventoryItem, id: oilFilter.inventory_id, name: 'Air filter', sku: 'AIR-000', stock_quantity: 7, on_order_quantity: 4 } })
    expect(await screen.findByRole('button', { name: 'Change reorder point' })).toBeInTheDocument()
    apiMocks.put.mockResolvedValue({ data: { ...inventoryItem, id: oilFilter.inventory_id, name: 'Air filter', sku: 'AIR-000', stock_quantity: 7, on_order_quantity: 4, reorder_level: 6 } })
    await user.click(screen.getByRole('button', { name: 'Change reorder point' }))
    await user.clear(screen.getByLabelText('Reorder point')); await user.type(screen.getByLabelText('Reorder point'), '6')
    await user.click(screen.getByRole('button', { name: 'Save reorder point' }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenLastCalledWith(`/inventory/${oilFilter.inventory_id}`, { reorder_level: 6 }))
    apiMocks.put.mockResolvedValue({ data: { ...inventoryItem, id: oilFilter.inventory_id, name: 'Air filter', sku: 'AIR-000', stock_quantity: 7, on_order_quantity: 4, reorder_level: 6, cost: '24.50' } })
    await user.click(await screen.findByRole('button', { name: 'Update average cost' }))
    await user.clear(screen.getByLabelText('Average unit cost')); await user.type(screen.getByLabelText('Average unit cost'), '24.50')
    await user.click(screen.getByRole('button', { name: 'Save average cost' }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenLastCalledWith(`/inventory/${oilFilter.inventory_id}`, { cost: 24.5 }))
    expect(screen.getByRole('button', { name: /Air filter/i })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('heading', { name: 'Air filter' })).toBeInTheDocument()
    const controls = screen.getByRole('heading', { name: 'Stock details' }).closest('section')!
    expect(within(controls).getByText('7')).toBeInTheDocument()
    expect(within(controls).getByText('4')).toBeInTheDocument()
    expect(within(controls).getByText('6')).toBeInTheDocument()
    expect(within(controls).getByText('$24.50')).toBeInTheDocument()
    expect(screen.getByText('Stock details saved for Air filter.')).toBeInTheDocument()
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Air filter stock details saved')
  })
  it('requires a reason only when available stock changes and sends only changed quantity fields', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    await user.click(screen.getByRole('button', { name: 'Adjust quantities' }))
    await user.clear(screen.getByLabelText('Available now')); await user.type(screen.getByLabelText('Available now'), '1')
    await user.click(screen.getByRole('button', { name: 'Save quantities' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Adjustment reason is required')
    expect(apiMocks.put).not.toHaveBeenCalled()

    await user.clear(screen.getByLabelText('Available now')); await user.type(screen.getByLabelText('Available now'), '0')
    expect(screen.getByLabelText('Adjustment reason')).not.toBeRequired()
    expect(screen.getByText('Required only when available stock changes.')).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Incoming quantity')); await user.type(screen.getByLabelText('Incoming quantity'), '5')
    apiMocks.put.mockResolvedValue({ data: { ...inventoryItem, id: oilFilter.inventory_id, name: 'Air filter', sku: 'AIR-000', stock_quantity: 0, on_order_quantity: 5 } })
    await user.click(screen.getByRole('button', { name: 'Save quantities' }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith(`/inventory/${oilFilter.inventory_id}`, { on_order_quantity: 5 }))
  })
  it('rejects empty, nonnumeric, and negative inventory values without a request', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    await user.click(screen.getByRole('button', { name: 'Adjust quantities' }))
    await user.clear(screen.getByLabelText('Incoming quantity'))
    await user.click(screen.getByRole('button', { name: 'Save quantities' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Incoming quantity must be a whole number')
    await user.type(screen.getByLabelText('Incoming quantity'), '-1')
    await user.click(screen.getByRole('button', { name: 'Save quantities' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Incoming quantity must be a whole number')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Update average cost' }))
    await user.clear(screen.getByLabelText('Average unit cost'))
    await user.click(screen.getByRole('button', { name: 'Save average cost' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Average unit cost must be a currency value')
    expect(apiMocks.put).not.toHaveBeenCalled()
  })
  it.each([
    ['permission response', Object.assign(new Error('forbidden'), { response: { status: 403, data: { detail: 'Inventory controls require shop-owner access.' } } }), 'Only owners and admins can change stock details.'],
    ['validation response', Object.assign(new Error('invalid'), { response: { status: 422, data: { detail: [{ msg: 'Adjustment reason is too short.' }] } } }), 'Adjustment reason is too short.'],
    ['network failure', new Error('Network unavailable'), 'Network unavailable'],
  ])('retains the draft after a recoverable %s', async (_label, failure, expected) => {
    installInventoryControlsFixture()
    apiMocks.put.mockRejectedValue(failure)
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    await user.click(screen.getByRole('button', { name: 'Change reorder point' }))
    await user.clear(screen.getByLabelText('Reorder point')); await user.type(screen.getByLabelText('Reorder point'), '9')
    await user.click(screen.getByRole('button', { name: 'Save reorder point' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(expected)
    expect(screen.getByLabelText('Reorder point')).toHaveValue(9)
    expect(screen.getByRole('button', { name: 'Save reorder point' })).toBeInTheDocument()
  })
  it('shows read-only inventory controls to non-manager roles without a fake disabled form', async () => {
    authState.role = 'receptionist'
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    expect(screen.getByText('You can view stock details. Owners and admins can make changes.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjust quantities' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Available now')).not.toBeInTheDocument()
  })
  it('discards the local inventory draft on selection change and Cancel restores saved values', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    await user.click(screen.getByRole('button', { name: 'Adjust quantities' }))
    await user.clear(screen.getByLabelText('Available now')); await user.type(screen.getByLabelText('Available now'), '12')
    await user.click(screen.getByRole('button', { name: /Brake shoe/i }))
    await user.click(screen.getByRole('button', { name: 'Adjust quantities' }))
    expect(screen.getByLabelText('Available now')).toHaveValue(2)
    await user.clear(screen.getByLabelText('Available now')); await user.type(screen.getByLabelText('Available now'), '8')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Adjust quantities' }))
    expect(screen.getByLabelText('Available now')).toHaveValue(2)
    await user.click(screen.getByRole('button', { name: /Air filter/i }))
    await user.click(screen.getByRole('button', { name: 'Adjust quantities' }))
    expect(screen.getByLabelText('Available now')).toHaveValue(0)
  })
  it('renders canonical photos then tenant-logo placeholders in demand and inventory rows and selected detail', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()

    const demandAir = await screen.findByRole('button', { name: /Air filter/i })
    expect(demandAir.querySelector('img')).toHaveAttribute('src', 'https://images.example.test/air-filter.png')
    expect(demandAir).toHaveAccessibleName(/Air filter/)
    await user.click(demandAir)
    expect(screen.getByRole('img', { name: 'Air filter part photo' })).toHaveAttribute('src', 'https://images.example.test/air-filter.png')

    const demandCoolant = screen.getByRole('button', { name: /Coolant/i })
    expect(demandCoolant.querySelector('img')).toHaveAttribute('src', brandingState.logoUrl)
    expect(demandCoolant.querySelector('img')).toHaveAttribute('alt', '')
    await user.click(demandCoolant)
    expect(screen.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Coolant' })).toHaveAttribute('src', brandingState.logoUrl)

    const demandBrake = screen.getByRole('button', { name: /Brake shoe/i })
    fireEvent.error(demandBrake.querySelector('img')!)
    expect(demandBrake.querySelector('img')).toHaveAttribute('src', brandingState.logoUrl)
    await user.click(demandBrake)
    const demandBrokenPhoto = screen.getByRole('img', { name: 'Brake shoe part photo' })
    fireEvent.error(demandBrokenPhoto)
    expect(screen.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Brake shoe' })).toHaveAttribute('src', brandingState.logoUrl)

    await user.click(screen.getByRole('tab', { name: 'Inventory' }))
    const airFilter = screen.getByRole('button', { name: /Air filter/i })
    expect(airFilter.querySelector('img')).toHaveAttribute('alt', '')
    await user.click(airFilter)
    expect(screen.getByRole('img', { name: 'Air filter part photo' })).toBeInTheDocument()
    const broken = screen.getByRole('button', { name: /Brake shoe/i })
    fireEvent.error(broken.querySelector('img')!)
    expect(broken.querySelector('img')).toHaveAttribute('src', brandingState.logoUrl)
    const coolant = screen.getByRole('button', { name: /Coolant/i })
    expect(coolant.querySelector('img')).toHaveAttribute('src', brandingState.logoUrl)
    await user.click(coolant)
    expect(screen.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Coolant' })).toBeInTheDocument()
  })
  it('terminates broken part and company-logo fallbacks at the neutral icon without retry loops', async () => {
    brandingState.logoUrl = 'https://images.example.test/broken-logo.png'
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()

    const demandBrake = await screen.findByRole('button', { name: /Brake shoe/i })
    fireEvent.error(demandBrake.querySelector('img')!)
    expect(demandBrake.querySelector('img')).toHaveAttribute('src', brandingState.logoUrl)
    fireEvent.error(demandBrake.querySelector('img')!)
    expect(within(demandBrake).getByTestId('part-thumbnail-fallback')).toBeInTheDocument()
    expect(demandBrake.querySelector('img')).not.toBeInTheDocument()
    await user.click(demandBrake)
    fireEvent.error(screen.getByRole('img', { name: 'Brake shoe part photo' }))
    fireEvent.error(screen.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Brake shoe' }))
    expect(screen.getByRole('img', { name: 'No image available for Brake shoe' })).toContainElement(screen.getByTestId('part-detail-fallback'))

    await user.click(screen.getByRole('tab', { name: 'Inventory' }))
    const inventoryBrake = screen.getByRole('button', { name: /Brake shoe/i })
    fireEvent.error(inventoryBrake.querySelector('img')!)
    fireEvent.error(inventoryBrake.querySelector('img')!)
    expect(within(inventoryBrake).getByTestId('part-thumbnail-fallback')).toBeInTheDocument()
    const inventoryCoolant = screen.getByRole('button', { name: /Coolant/i })
    fireEvent.error(inventoryCoolant.querySelector('img')!)
    expect(within(inventoryCoolant).getByTestId('part-thumbnail-fallback')).toBeInTheDocument()
    await user.click(inventoryCoolant)
    fireEvent.error(screen.getByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Coolant' }))
    expect(screen.getByRole('img', { name: 'No image available for Coolant' })).toContainElement(screen.getByTestId('part-detail-fallback'))
  })
  it('filters and stably sorts inventory while re-homing hidden selection and offering one reset path', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))

    const rows = () => screen.queryAllByRole('button').filter((button) => button.hasAttribute('data-parts-row'))
    const names = () => rows().map((row) => row.textContent)
    expect(screen.getByText('4 active parts')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All active' })).toHaveAttribute('aria-pressed', 'true')
    expect(names().join(' ')).not.toContain('Retired empty item')

    await user.click(screen.getByRole('button', { name: 'Needs reorder' }))
    expect(screen.getByText('2 of 4 active parts')).toBeInTheDocument()
    expect(names().join(' ')).toContain('Air filter')
    expect(names().join(' ')).toContain('Brake shoe')
    expect(names().join(' ')).not.toContain('Temporary catalog item')
    expect(names().join(' ')).not.toContain('Retired empty item')

    await user.click(screen.getByRole('button', { name: 'Out of stock' }))
    expect(screen.getByText('1 of 4 active parts')).toBeInTheDocument()
    expect(names().join(' ')).not.toContain('Retired empty item')
    await user.click(screen.getByRole('button', { name: 'In stock' }))
    expect(rows()).toHaveLength(1)
    expect(names()[0]).toContain('Coolant')

    await user.click(screen.getByRole('button', { name: 'All active' }))
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'low-stock')
    expect(names()[0]).toContain('Air filter')
    expect(names()[1]).toContain('Brake shoe')
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'high-stock')
    expect(names()[0]).toContain('Coolant')
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'name-desc')
    expect(names()[0]).toContain('Temporary catalog item')
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'name-asc')
    expect(names()[0]).toContain('Air filter')

    await user.click(screen.getByRole('button', { name: 'Archived' }))
    expect(screen.getByText('1 archived part')).toBeInTheDocument()
    expect(names().join(' ')).toContain('Retired empty item')
    expect(screen.getByText(/Archived part/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjust quantities' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'All active' }))

    await user.click(screen.getByRole('button', { name: /Brake shoe/i }))
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Needs reorder')
    await user.click(screen.getByRole('button', { name: 'In stock' }))
    expect(screen.getByRole('button', { name: /Coolant/i })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('heading', { name: 'Coolant' })).toBeInTheDocument()
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Coolant selected')

    await user.type(screen.getByLabelText('Search inventory'), 'Alpha Supply')
    expect(screen.getByText('0 of 4 active parts')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear search and filters' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear search and filters' }))
    expect(screen.getByText('4 active parts')).toBeInTheDocument()
    expect(screen.getByLabelText('Search inventory')).toHaveValue('')
    expect(screen.getByLabelText('Sort inventory')).toHaveValue('name-asc')
    expect(rows()[0]).toHaveAttribute('tabindex', '0')
    expect(rows()[0]).toHaveAttribute('aria-current', 'true')
  })
  it('re-homes demand selection and atomically resets its draft form when search changes', async () => {
    installDemandSelectionFixture()
    const user = userEvent.setup()
    renderGate()
    const engineOil = await screen.findByRole('button', { name: /Engine oil Delo 10w30/i })
    expect(engineOil).toHaveAttribute('aria-current', 'true')
    expect(screen.getByLabelText('Packages')).toHaveValue(9)
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Engine oil Delo 10w30 selected.')

    await user.clear(screen.getByLabelText('Search demand'))
    await user.type(screen.getByLabelText('Search demand'), 'Fuel Filter')
    expect(screen.getByRole('button', { name: /Fuel Filter Kit/i })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByLabelText('Packages')).toHaveValue(3)
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Fuel Filter Kit selected.')
    await user.type(screen.getByLabelText('PO number'), 'PO-FUEL-001')
    await user.click(screen.getByRole('button', { name: 'Create draft PO' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/purchase-orders', expect.objectContaining({ lines: [expect.objectContaining({ inventory_id: 'fuel-filter', ordered_quantity: 3 })] }), expect.anything()))
  })
  it('explicitly selects the first visible row on every master tab and return/core activation', async () => {
    installSelectionLifecycleFixture()
    const user = userEvent.setup()
    renderGate()
    const rows = () => screen.queryAllByRole('button').filter((button) => button.hasAttribute('data-parts-row'))
    const expectSingleCurrentRow = (name: RegExp) => {
      const visibleRows = rows()
      const current = visibleRows.filter((row) => row.getAttribute('aria-current') === 'true')
      const tabStops = visibleRows.filter((row) => row.getAttribute('tabindex') === '0')
      expect(current).toHaveLength(1)
      expect(tabStops).toHaveLength(1)
      expect(current[0]).toBe(tabStops[0])
      expect(current[0]).toHaveAccessibleName(name)
    }

    await screen.findByRole('button', { name: /Engine oil Delo 10w30/i })
    expectSingleCurrentRow(/Engine oil Delo 10w30/i)
    expect(screen.getByLabelText('Packages')).toHaveValue(9)
    await user.click(screen.getByRole('button', { name: /Fuel Filter Kit/i }))
    expectSingleCurrentRow(/Fuel Filter Kit/i)
    await user.click(screen.getByRole('tab', { name: 'Inventory' }))
    expectSingleCurrentRow(/Engine oil Delo 10w30/i)
    await user.click(screen.getByRole('tab', { name: 'Demand' }))
    expectSingleCurrentRow(/Engine oil Delo 10w30/i)
    expect(screen.getByLabelText('Packages')).toHaveValue(9)

    await user.click(screen.getByRole('tab', { name: 'Purchase orders' }))
    expectSingleCurrentRow(/PO-FIRST/i)
    expect(await screen.findByRole('heading', { name: 'PO-FIRST' })).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/purchase-orders/po-first')

    await user.click(screen.getByRole('tab', { name: 'Returns & cores' }))
    expectSingleCurrentRow(/RET-FIRST/i)
    expect(await screen.findByRole('heading', { name: 'RET-FIRST' })).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/returns/return-first')
    await user.click(screen.getByRole('tab', { name: 'Cores' }))
    expectSingleCurrentRow(/Engine oil core/i)
    expect(screen.getByRole('heading', { name: 'Engine oil core' })).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Returns' }))
    expectSingleCurrentRow(/RET-FIRST/i)
    await user.click(screen.getByRole('tab', { name: 'Activity' }))
    expect(rows()).toHaveLength(0)
  })
  it('preserves a visible inventory selection through every sort order', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))
    const brake = screen.getByRole('button', { name: /Brake shoe/i })
    await user.click(brake)
    for (const sort of ['low-stock', 'high-stock', 'name-desc', 'name-asc']) {
      await user.selectOptions(screen.getByLabelText('Sort inventory'), sort)
      const selected = screen.getByRole('button', { name: /Brake shoe/i })
      expect(selected).toHaveAttribute('aria-current', 'true')
      expect(selected).toHaveAttribute('tabindex', '0')
    }
  })
  it('keeps one keyboard-operable primary selection and nests return/core selection only inside its panel', async () => {
    installFixture()
    const user = userEvent.setup()
    renderGate()
    expect(screen.queryByRole('list', { name: 'Parts operations workflow' })).not.toBeInTheDocument()
    const primaryTablist = await screen.findByRole('tablist', { name: 'Parts Operations areas' })
    const selectedPrimary = () => within(primaryTablist).getAllByRole('tab').filter((tab) => tab.getAttribute('aria-selected') === 'true')
    const demand = await screen.findByRole('tab', { name: 'Demand' })
    expect(selectedPrimary()).toEqual([demand])
    demand.focus()
    await user.keyboard('{ArrowRight}')
    const inventory = screen.getByRole('tab', { name: 'Inventory' })
    expect(inventory).toHaveAttribute('aria-selected', 'true')
    expect(inventory).toHaveFocus()
    expect(selectedPrimary()).toEqual([inventory])
    expect(screen.getByRole('tabpanel', { name: 'Inventory' })).toBeInTheDocument()
    await user.click(within(primaryTablist).getByRole('tab', { name: 'Returns & cores' }))
    expect(selectedPrimary()).toHaveLength(1)
    const custodyTablist = screen.getByRole('tablist', { name: 'Return and core custody view' })
    const selectedCustody = () => within(custodyTablist).getAllByRole('tab').filter((tab) => tab.getAttribute('aria-selected') === 'true')
    expect(selectedCustody()).toHaveLength(1)
    within(custodyTablist).getByRole('tab', { name: 'Returns' }).focus()
    await user.keyboard('{ArrowRight}')
    expect(selectedCustody()).toHaveLength(1)
  })
  it('keeps 100 loaded demand rows searchable, triageable, focusable, and selection-announced', async () => {
    installLargeFixture()
    const user = userEvent.setup()
    renderGate()
    expect(await screen.findByText('100 demand items')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Unlinked' }))
    expect(screen.getByRole('region', { name: 'Demand results, 1 shown of 100' })).toHaveAttribute('tabindex', '0')
    await user.click(screen.getByRole('button', { name: /Fleet filter 100/i }))
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Fleet filter 100 selected.')
    await user.click(screen.getByRole('button', { name: 'All demand' }))
    await user.type(screen.getByLabelText('Search demand'), 'Fleet filter 100')
    expect(screen.getByText('1 of 100 demand items')).toBeInTheDocument()
  })
  it('loads every advertised server page before applying demand search and roves large result focus', async () => {
    const first = Array.from({ length: 100 }, (_, index) => ({ ...oilFilter, inventory_id: `page-one-${index}`, name: `Page one ${index}` }))
    const last = { ...oilFilter, inventory_id: 'page-two-last', name: 'Page two last' }
    apiMocks.get.mockImplementation((url: string, config?: { params?: { skip?: number } }) => {
      if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 101, open_purchase_order_count: 0 } })
      if (url === '/parts-operations/demand') return Promise.resolve({ data: config?.params?.skip === 100 ? { items: [last], total: 101, skip: 100, limit: 100, has_more: false } : { items: first, total: 101, skip: 0, limit: 100, has_more: true } })
      if (url === '/inventory') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
      if (url === '/parts-operations/purchase-orders' || url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
      throw new Error(`Unexpected GET ${url}`)
    })
    const user = userEvent.setup()
    renderGate()
    expect(await screen.findByText('101 demand items')).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/demand', expect.objectContaining({ params: expect.objectContaining({ skip: 100, limit: 100, paginated: true }) }))
    const [firstRow, secondRow] = screen.getAllByRole('button').filter((button) => button.hasAttribute('data-parts-row'))
    firstRow.focus()
    await user.keyboard('{ArrowDown}')
    expect(firstRow).toHaveAttribute('tabindex', '-1')
    expect(secondRow).toHaveAttribute('tabindex', '0')
    expect(secondRow).toHaveFocus()
    await user.type(screen.getByLabelText('Search demand'), 'Page two last')
    const row = screen.getByRole('button', { name: /Page two last/i })
    expect(row).toHaveAttribute('tabindex', '0')
    row.focus()
    await user.keyboard('{Home}')
    expect(row).toHaveFocus()
  })
  it('keeps a mutation single-flight and reuses its idempotency key when the same attempt is retried', async () => {
    installFixture()
    let rejectFirst!: (reason: Error) => void
    apiMocks.post.mockImplementationOnce(() => new Promise((_, reject) => { rejectFirst = reject })).mockResolvedValueOnce({ data: { id: 'po-created' } })
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('button', { name: /Oil filter/i }))
    await user.type(screen.getByLabelText('PO number'), 'PO-RETRY-001')
    const create = screen.getByRole('button', { name: 'Create draft PO' })
    await user.dblClick(create)
    expect(apiMocks.post).toHaveBeenCalledTimes(1)
    expect(create).toBeDisabled()
    rejectFirst(Object.assign(new Error('temporary'), { response: { status: 503 } }))
    expect(await screen.findByRole('alert')).toHaveTextContent('temporary')
    await user.click(create)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledTimes(2))
    const firstKey = apiMocks.post.mock.calls[0][2].headers['Idempotency-Key']
    expect(apiMocks.post.mock.calls[1][2].headers['Idempotency-Key']).toBe(firstKey)
  })
  it('keeps an active-panel failure explicit and lets its retry restore only that panel', async () => {
    let demandCalls = 0
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 1, open_purchase_order_count: 0 } })
      if (url === '/parts-operations/demand') { demandCalls += 1; return demandCalls === 1 ? Promise.reject(new Error('offline')) : Promise.resolve({ data: { items: [oilFilter], total: 1, skip: 0, limit: 100, has_more: false } }) }
      if (url === '/inventory' || url === '/parts-operations/purchase-orders' || url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
      throw new Error(`Unexpected GET ${url}`)
    })
    const user = userEvent.setup()
    renderGate()
    expect(await screen.findByRole('alert')).toHaveTextContent('Demand could not be loaded')
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('button', { name: /Oil filter/i })).toBeInTheDocument()
  })
})
