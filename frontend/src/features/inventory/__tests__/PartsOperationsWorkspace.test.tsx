import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import fixture from '../../../../../backend/tests/fixtures/db038_parts_operations.json'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner' }))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, post: apiMocks.post } }))
vi.mock('@/stores/authStore', () => ({ useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: authState.role } }) }))

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
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/parts-operations/summary') return Promise.resolve({ data: { low_stock_count: 2, open_purchase_order_count: 0 } })
    if (url === '/parts-operations/demand') return Promise.resolve({ data: { items: [oilFilter], total: 1, skip: 0, limit: 100, has_more: false } })
    if (url === '/inventory') return Promise.resolve({ data: { items: inventory, total: inventory.length, skip: 0, limit: 100, has_more: false } })
    if (url === '/parts-operations/purchase-orders' || url === '/parts-operations/returns' || url === '/parts-operations/cores' || url === '/parts-operations/activity') return Promise.resolve({ data: { items: [], total: 0, skip: 0, limit: 100, has_more: false } })
    throw new Error(`Unexpected GET ${url}`)
  })
}

describe('DB-038 Parts Operations workspace', () => {
  afterEach(() => { apiMocks.get.mockReset(); apiMocks.post.mockReset(); authState.role = 'garage_owner' })
  it('falls back to the existing catalog only when the server says the feature is unavailable', async () => { apiMocks.get.mockRejectedValue(Object.assign(new Error('off'), { response: { status: 404 } })); renderGate(); expect(await screen.findByText('Legacy inventory catalog')).toBeInTheDocument() })
  it('keeps a transient server failure visible instead of silently simulating an enabled feature', async () => { apiMocks.get.mockRejectedValue(Object.assign(new Error('offline'), { response: { status: 503 } })); renderGate(); expect(await screen.findByRole('alert')).toHaveTextContent('temporarily unavailable'); expect(screen.queryByText('Legacy inventory catalog')).not.toBeInTheDocument() })
  it('uses frozen demand evidence, deep-links to the canonical repair order, and posts an idempotent PO draft', async () => {
    installFixture(); const user = userEvent.setup(); renderGate()
    expect(await screen.findByRole('heading', { name: 'Supply, stock & custody' })).toBeInTheDocument()
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
  it('renders canonical part images with a neutral decorative fallback in demand and inventory', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()

    const demandRow = await screen.findByRole('button', { name: /Oil filter/i })
    expect(demandRow.querySelector('img')).toHaveAttribute('src', 'https://images.example.test/air-filter.png')
    expect(demandRow).toHaveAccessibleName(/Oil filter/)

    await user.click(screen.getByRole('tab', { name: 'Inventory' }))
    const airFilter = screen.getByRole('button', { name: /Air filter/i })
    expect(airFilter.querySelector('img')).toHaveAttribute('alt', '')
    const broken = screen.getByRole('button', { name: /Brake shoe/i })
    fireEvent.error(broken.querySelector('img')!)
    expect(within(broken).getByTestId('part-thumbnail-fallback')).toBeInTheDocument()
    expect(within(screen.getByRole('button', { name: /Coolant/i })).getByTestId('part-thumbnail-fallback')).toBeInTheDocument()
  })
  it('filters and stably sorts inventory while clearing hidden selection and offering one reset path', async () => {
    installInventoryControlsFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('tab', { name: 'Inventory' }))

    const rows = () => screen.queryAllByRole('button').filter((button) => button.hasAttribute('data-parts-row'))
    const names = () => rows().map((row) => row.textContent)
    expect(screen.getByText('5 inventory items')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All stock' })).toHaveAttribute('aria-pressed', 'true')

    await user.click(screen.getByRole('button', { name: 'Needs reorder' }))
    expect(screen.getByText('2 of 5 inventory items')).toBeInTheDocument()
    expect(names().join(' ')).toContain('Air filter')
    expect(names().join(' ')).toContain('Brake shoe')
    expect(names().join(' ')).not.toContain('Temporary catalog item')
    expect(names().join(' ')).not.toContain('Retired empty item')

    await user.click(screen.getByRole('button', { name: 'Out of stock' }))
    expect(screen.getByText('2 of 5 inventory items')).toBeInTheDocument()
    expect(names().join(' ')).toContain('Retired empty item')
    await user.click(screen.getByRole('button', { name: 'In stock' }))
    expect(rows()).toHaveLength(1)
    expect(names()[0]).toContain('Coolant')

    await user.click(screen.getByRole('button', { name: 'All stock' }))
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'low-stock')
    expect(names()[0]).toContain('Air filter')
    expect(names()[1]).toContain('Retired empty item')
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'high-stock')
    expect(names()[0]).toContain('Coolant')
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'name-desc')
    expect(names()[0]).toContain('Temporary catalog item')
    await user.selectOptions(screen.getByLabelText('Sort inventory'), 'name-asc')
    expect(names()[0]).toContain('Air filter')

    await user.click(screen.getByRole('button', { name: /Brake shoe/i }))
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Needs reorder')
    await user.click(screen.getByRole('button', { name: 'In stock' }))
    expect(screen.getByText('Select an inventory item to review stock and activity.')).toBeInTheDocument()
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('')

    await user.type(screen.getByLabelText('Search inventory'), 'Alpha Supply')
    expect(screen.getByText('0 of 5 inventory items')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset inventory view' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reset inventory view' }))
    expect(screen.getByText('5 inventory items')).toBeInTheDocument()
    expect(screen.getByLabelText('Search inventory')).toHaveValue('')
    expect(screen.getByLabelText('Sort inventory')).toHaveValue('catalog')
    expect(rows()[0]).toHaveAttribute('tabindex', '0')
  })
  it('clears demand selection and its draft form when search changes instead of carrying a quantity to another part', async () => {
    installDemandSelectionFixture()
    const user = userEvent.setup()
    renderGate()
    await user.click(await screen.findByRole('button', { name: /Engine oil Delo 10w30/i }))
    expect(screen.getByLabelText('Packages')).toHaveValue(9)
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Engine oil Delo 10w30 selected.')

    await user.clear(screen.getByLabelText('Search demand'))
    await user.type(screen.getByLabelText('Search demand'), 'Fuel Filter')
    expect(screen.getByText('Select a demand item to inspect its repair and replenishment sources.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create draft PO' })).not.toBeInTheDocument()
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('')

    await user.click(screen.getByRole('button', { name: /Fuel Filter Kit/i }))
    expect(screen.getByLabelText('Packages')).toHaveValue(3)
    expect(screen.getByTestId('parts-selection-status')).toHaveTextContent('Fuel Filter Kit selected.')
    await user.type(screen.getByLabelText('PO number'), 'PO-FUEL-001')
    await user.click(screen.getByRole('button', { name: 'Create draft PO' }))
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/parts-operations/purchase-orders', expect.objectContaining({ lines: [expect.objectContaining({ inventory_id: 'fuel-filter', ordered_quantity: 3 })] }), expect.anything()))
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
