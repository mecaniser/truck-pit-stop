import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner' }))
const brandingState = vi.hoisted(() => ({
  name: 'Truck Pit Stop Wisconsin',
  logoUrl: 'https://images.example.test/shop-logo.png' as string | null,
}))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, put: apiMocks.put } }))
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (state: { user: { role: string } }) => unknown) => selector({ user: { role: authState.role } }),
}))
vi.mock('@/hooks/useTenantBranding', () => ({
  default: () => ({ data: { name: brandingState.name, logo_url: brandingState.logoUrl } }),
}))

import PartsInventoryWorkspace, {
  PURCHASE_PREPARATION_KEY,
  type PartRecord,
} from '../PartsInventoryWorkspace'

const source = {
  source_id: 'source-1',
  supplier_id: 'supplier-1',
  supplier_name: 'Fleet Parts Co',
  supplier_part_number: 'FPC-ALT-42',
  is_preferred: true,
  minimum_order_quantity: 5,
  pack_quantity: 4,
  last_unit_cost: '12.50',
  lead_time_days: 2,
  is_active: true,
  updated_at: '2026-08-24T12:00:00Z',
} as const

const activePart: PartRecord = {
  id: 'part-active',
  sku: 'ALT-42',
  name: 'Alternator',
  description: 'Heavy-duty alternator',
  image_url: 'https://images.example.test/alternator.png',
  unit_type: 'each',
  location: 'A-12',
  available_packages: 3,
  needed_for_open_repairs: 2,
  reorder_level: 5,
  incoming_packages: 0,
  recommended_order_packages: 7,
  average_unit_cost: '13.25',
  is_archived: false,
  is_placeholder: false,
  preferred_source: source,
  supplier_sources: [source],
  repair_sources: [{ repair_order_id: 'repair-1', order_number: 'TPS-301', vehicle_display: '2020 Freightliner Cascadia', unit_number: '144', packages: 2 }],
  incoming_sources: [],
}

const brakePart: PartRecord = {
  ...activePart,
  id: 'part-brake',
  sku: 'BRK-9',
  name: 'Brake shoe kit',
  image_url: null,
  available_packages: 9,
  needed_for_open_repairs: 0,
  recommended_order_packages: 0,
  preferred_source: null,
  supplier_sources: [],
  repair_sources: [],
}

const archivedPart: PartRecord = {
  ...activePart,
  id: 'part-archived',
  sku: 'OLD-ALT',
  name: 'Archived alternator',
  is_archived: true,
}

function detail(part: PartRecord) {
  return {
    ...part,
    recent_receipts: [],
    recent_movements: [{
      id: `movement-${part.id}`,
      movement_type: 'manual_adjustment',
      quantity_delta: 1,
      balance_after: part.available_packages,
      wac_after: part.average_unit_cost,
      occurred_at: '2026-08-24T12:00:00Z',
    }],
  }
}

function page<T>(items: T[], overrides: Partial<{ total: number; skip: number; limit: number; has_more: boolean }> = {}) {
  return {
    items,
    total: overrides.total ?? items.length,
    skip: overrides.skip ?? 0,
    limit: overrides.limit ?? 50,
    has_more: overrides.has_more ?? false,
  }
}

function installApi() {
  apiMocks.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url === '/parts-operations/parts') {
      const params = config?.params || {}
      if (params.view === 'archived') return Promise.resolve({ data: page([archivedPart]) })
      if (params.search === 'brake') return Promise.resolve({ data: page([brakePart]) })
      if (params.skip === 50) return Promise.resolve({ data: page([brakePart], { total: 51, skip: 50 }) })
      return Promise.resolve({ data: page([activePart], { total: 51, has_more: true }) })
    }
    if (url.startsWith('/parts-operations/parts/')) {
      const id = url.split('/').at(-1)
      const part = id === archivedPart.id ? archivedPart : id === brakePart.id ? brakePart : activePart
      return Promise.resolve({ data: detail(part) })
    }
    if (url === '/parts-operations/activity') {
      return Promise.resolve({ data: page([{
        id: 'movement-1',
        inventory: { id: activePart.id, sku: activePart.sku, name: activePart.name },
        movement_type: 'manual_adjustment',
        quantity_delta: -1,
        balance_after: 2,
        wac_after: '13.25',
        source: { type: 'repair_order', id: 'repair-1', order_number: 'TPS-301' },
        occurred_at: '2026-08-24T12:00:00Z',
      }]) })
    }
    throw new Error(`Unexpected GET ${url}`)
  })
  apiMocks.put.mockResolvedValue({ data: detail(activePart) })
}

function renderWorkspace() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/dashboard/garage/inventory']}>
        <PartsInventoryWorkspace summary={{ low_stock_count: 7, open_purchase_order_count: 2 }} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DB-038 Parts & inventory workspace', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.put.mockReset()
    authState.role = 'garage_owner'
    brandingState.name = 'Truck Pit Stop Wisconsin'
    brandingState.logoUrl = 'https://images.example.test/shop-logo.png'
    window.sessionStorage.clear()
  })

  it('uses server pagination and sends the active catalog, search, and sort filters', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'active', sort: 'catalog', skip: 0, limit: 50, paginated: true },
    })

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByRole('heading', { name: 'Brake shoe kit' })
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'active', sort: 'catalog', skip: 50, limit: 50, paginated: true },
    })

    await user.type(screen.getByRole('searchbox', { name: 'Search parts' }), 'brake')
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'active', search: 'brake', sort: 'catalog', skip: 0, limit: 50, paginated: true },
    }))
  })

  it('keeps archived parts out of the default request and locks their stock and purchase actions', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.queryByText('Archived part. History stays available, but stock and purchasing actions are locked.')).not.toBeInTheDocument()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Catalog' }), 'archived')

    expect(await screen.findByRole('heading', { name: 'Archived alternator' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Archived part')
    expect(screen.queryByRole('button', { name: 'Adjust available stock' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change reorder point' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add to purchase list' })).not.toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'archived', sort: 'catalog', skip: 0, limit: 50, paginated: true },
    })
  })

  it('uses the part photo, then the shop logo, then an accessible no-image fallback', async () => {
    installApi()
    renderWorkspace()

    const partPhoto = await screen.findByRole('img', { name: 'Alternator part photo' })
    fireEvent.error(partPhoto)
    const logoFallback = await screen.findByRole('img', { name: 'Truck Pit Stop Wisconsin logo placeholder for Alternator' })
    fireEvent.error(logoFallback)
    expect(await screen.findByRole('img', { name: 'No image available for Alternator' })).toBeInTheDocument()
  })

  it('requires a reason for available-stock changes and submits the existing inventory contract', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: 'Adjust available stock' }))
    await user.clear(screen.getByRole('spinbutton', { name: 'Available packages' }))
    await user.type(screen.getByRole('spinbutton', { name: 'Available packages' }), '4')
    await user.click(screen.getByRole('button', { name: 'Save change' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Explain why available stock is changing.')
    expect(apiMocks.put).not.toHaveBeenCalled()

    await user.type(screen.getByRole('textbox', { name: 'Adjustment reason' }), 'Cycle count correction')
    await user.click(screen.getByRole('button', { name: 'Save change' }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith('/inventory/part-active', {
      stock_quantity: 4,
      stock_adjustment_reason: 'Cycle count correction',
    }))
  })

  it('keeps reception staff read-only without rendering fake disabled stock forms', async () => {
    authState.role = 'receptionist'
    installApi()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.getByText('You can view stock. Owners and admins can make changes.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjust available stock' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change reorder point' })).not.toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  it('adds the preferred supplier source to purchase preparation with minimum and pack rounding', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: 'Add to purchase list' }))

    expect(JSON.parse(window.sessionStorage.getItem(PURCHASE_PREPARATION_KEY) || '[]')).toEqual([{
      inventoryId: activePart.id,
      name: activePart.name,
      sku: activePart.sku,
      sourceId: source.source_id,
      supplierId: source.supplier_id,
      supplierName: source.supplier_name,
      supplierPartNumber: source.supplier_part_number,
      quantity: 8,
      unitCost: source.last_unit_cost,
      minimumOrderQuantity: source.minimum_order_quantity,
      packQuantity: source.pack_quantity,
    }])
    expect(screen.getByRole('status')).toHaveTextContent('Alternator added to the purchase preparation list.')
  })

  it('translates movement records into shop language without exposing raw movement or WAC terms', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: 'Movement' }))
    expect(await screen.findByText(/Manual stock adjustment · 2 available after change · Average cost \$13.25/)).toBeInTheDocument()
    expect(screen.queryByText(/manual_adjustment/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\bWAC\b/)).not.toBeInTheDocument()
  })
})
