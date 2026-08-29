import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { FormEvent, ReactNode } from 'react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
const authState = vi.hoisted(() => ({ role: 'garage_owner', id: 'user-1', tenant_id: 'tenant-1' }))
const brandingState = vi.hoisted(() => ({
  name: 'Truck Pit Stop Wisconsin',
  logoUrl: 'https://images.example.test/shop-logo.png' as string | null,
}))

vi.mock('@/lib/api', () => ({ default: { get: apiMocks.get, put: apiMocks.put, post: apiMocks.post, patch: apiMocks.patch, delete: apiMocks.delete } }))
vi.mock('@/stores/authStore', () => {
  const state = () => ({ user: { role: authState.role, id: authState.id, tenant_id: authState.tenant_id } })
  const useAuthStore = Object.assign((selector: (value: ReturnType<typeof state>) => unknown) => selector(state()), { getState: state })
  return { useAuthStore }
})
vi.mock('@/hooks/useTenantBranding', () => ({
  default: () => ({ data: { name: brandingState.name, logo_url: brandingState.logoUrl } }),
}))
vi.mock('@/components/SlidePanelForm', () => ({
  default: ({ isOpen, title, onClose, onSubmit, submitLabel, panelClassName, children }: { isOpen: boolean; title: string; onClose: () => void; onSubmit: (event: FormEvent) => void; submitLabel: string; panelClassName?: string; children: ReactNode }) => isOpen ? <div role="dialog" aria-label={title} className={panelClassName}><button type="button" onClick={onClose}>Close</button><form onSubmit={onSubmit}>{children}<button type="submit">{submitLabel}</button></form></div> : null,
}))

import PartsInventoryWorkspace, {
  purchasePreparationStorageKey,
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

const supplierPurchasing = {
  id: 'supplier-1',
  name: 'Fleet Parts Co',
  payment_terms: 'NET 30',
  default_lead_time_days: 9,
  minimum_order_amount: null,
  purchasing_notes: null,
  active_part_source_count: 1,
  open_purchase_order_count: 0,
  open_purchase_order_value: '0.00',
  last_receipt_at: null,
  on_time_order_count: 9,
  timed_order_count: 10,
  on_time_rate: '90',
}

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

const unassignedReorderPart: PartRecord = {
  ...brakePart,
  id: 'part-unassigned',
  sku: 'FILTER-UNASSIGNED',
  name: 'Fuel filter kit',
  available_packages: 0,
  reorder_level: 4,
  recommended_order_packages: 4,
}

const directionReorderPart: PartRecord = {
  ...unassignedReorderPart,
  id: 'part-direction',
  sku: 'BELT-DIRECTION',
  name: 'Belt tensioner',
}

const activityEvent = {
  id: 'event-1',
  inventory_id: activePart.id,
  category: 'stock',
  event_type: 'stock.adjusted',
  occurred_at: '2026-08-24T12:00:00Z',
  correlation_id: 'correlation-1',
  origin: 'live',
  inventory: { id: activePart.id, sku: activePart.sku, name: activePart.name },
  actor: { id: 'user-1', name: 'Alex Popescu' },
  reason: { code: 'count_correction', note: 'Cycle count correction' },
  before: { stock_quantity: 3 },
  after: { stock_quantity: 2 },
  stock: { physical_on_hand: 2, held_for_checkout: 0, available_to_sell: 2, delta: -1, wac: '13.25' },
  money: null,
  payment: null,
  source: { type: 'inventory_movement', id: 'movement-1', number: 'MOV-100', href: '/dashboard/garage/inventory?activity=movement-1' },
}

const lifecycleSummary = {
  inventory_id: activePart.id,
  as_of: '2026-08-24T12:00:00Z',
  repairs: { units_used: '4', repair_order_count: 2, last_used_at: '2026-08-23T12:00:00Z' },
  purchasing: { units_received: 8, receipt_count: 1, units_returned_to_vendor: 0, open_core_obligations: 0 },
  sales: { units_sold: 3, units_returned: 1, net_units: 2, gross_item_revenue: '39.75', discounts: '0.00', refunds: '13.25', net_item_revenue: '26.50', last_sold_at: '2026-08-24T11:00:00Z' },
  activity: { event_count: 12, last_event_at: '2026-08-24T12:00:00Z' },
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

function editableInventory(part: PartRecord) {
  return {
    id: part.id,
    sku: part.sku,
    name: part.name,
    description: part.description,
    category: 'Electrical',
    unit_type: part.unit_type,
    location: part.location,
    image_url: part.image_url,
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

function installApi(detailOverride?: ReturnType<typeof detail>) {
  apiMocks.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
    if (url === '/parts-operations/parts') {
      const params = config?.params || {}
      if (params.view === 'archived') return Promise.resolve({ data: page([archivedPart]) })
      if (params.search === 'brake') return Promise.resolve({ data: page([brakePart]) })
      if (params.skip === 50) return Promise.resolve({ data: page([brakePart], { total: 51, skip: 50 }) })
      return Promise.resolve({ data: page([activePart], { total: 51, has_more: true }) })
    }
    if (url.endsWith('/lifecycle-summary')) return Promise.resolve({ data: lifecycleSummary })
    if (url.startsWith('/parts-operations/parts/')) {
      const id = url.split('/').at(-1)
      const part = id === archivedPart.id ? archivedPart : id === brakePart.id ? brakePart : activePart
      return Promise.resolve({ data: detailOverride?.id === part.id ? detailOverride : detail(part) })
    }
    if (url.startsWith('/inventory/')) {
      const id = url.split('/').at(-1)
      const part = id === archivedPart.id ? archivedPart : id === brakePart.id ? brakePart : activePart
      return Promise.resolve({ data: editableInventory(part) })
    }
    if (url.startsWith('/parts-operations/suppliers/')) return Promise.resolve({ data: supplierPurchasing })
    if (url === '/suppliers') return Promise.resolve({ data: page([{ id: 'supplier-2', name: 'AutoZone' }]) })
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
    if (url === '/parts-operations/activity-events') return Promise.resolve({ data: { items: [activityEvent], next_cursor: null } })
    throw new Error(`Unexpected GET ${url}`)
  })
  apiMocks.put.mockResolvedValue({ data: detail(activePart) })
  apiMocks.post.mockResolvedValue({ data: activePart })
  apiMocks.patch.mockResolvedValue({ data: source })
  apiMocks.delete.mockResolvedValue({ data: null })
}

function renderWorkspace(summary: { needs_reorder_count?: number; low_stock_count: number; open_purchase_order_count: number } = { needs_reorder_count: 5, low_stock_count: 7, open_purchase_order_count: 2 }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/dashboard/garage/inventory']}>
        <PartsInventoryWorkspace summary={summary} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DB-038 Parts & inventory workspace', () => {
  afterEach(() => {
    apiMocks.get.mockReset()
    apiMocks.put.mockReset()
    apiMocks.post.mockReset()
    apiMocks.patch.mockReset()
    apiMocks.delete.mockReset()
    authState.role = 'garage_owner'
    brandingState.name = 'Truck Pit Stop Wisconsin'
    brandingState.logoUrl = 'https://images.example.test/shop-logo.png'
    window.sessionStorage.clear()
  })

  it('appends explicit 50-row server pages and resets the loaded sequence when search changes', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'active', sort: 'catalog', direction: 'asc', skip: 0, limit: 50, paginated: true },
    })
    expect(screen.getByText('Showing 1 of 51')).toBeInTheDocument()
    const ledger = screen.getByRole('table', { name: '51 matching parts' })
    const naturalEnd = screen.getByText('Showing 1 of 51').closest('.db-parts-workbench__load-more')
    expect(naturalEnd).not.toBeNull()
    expect(ledger.lastElementChild).toBe(naturalEnd)

    await user.click(screen.getByRole('button', { name: 'Load 50 more' }))
    expect(await screen.findByText('Showing 2 of 51')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: '51 matching parts' }).querySelectorAll('.db-parts-workbench__row')).toHaveLength(2)
    expect(screen.getByText('Brake shoe kit')).toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'active', sort: 'catalog', direction: 'asc', skip: 50, limit: 50, paginated: true },
    })

    await user.type(screen.getByRole('searchbox', { name: 'Search parts' }), 'brake')
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'active', search: 'brake', sort: 'catalog', direction: 'asc', skip: 0, limit: 50, paginated: true },
    }))
    expect(await screen.findByText('Showing 1 of 1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load 50 more' })).not.toBeInTheDocument()

    await user.clear(screen.getByRole('searchbox', { name: 'Search parts' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenLastCalledWith('/parts-operations/parts', {
      params: { view: 'active', sort: 'catalog', direction: 'asc', skip: 0, limit: 50, paginated: true },
    }))
    expect(await screen.findByText('Showing 1 of 51')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load 50 more' })).toBeInTheDocument()
  })

  it('uses the actionable reorder summary with a temporary legacy fallback', async () => {
    installApi()
    const view = renderWorkspace({ low_stock_count: 7, open_purchase_order_count: 2 })
    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.getByRole('button', { name: /Needs reorder 7/ })).toBeInTheDocument()
    view.unmount()

    renderWorkspace({ needs_reorder_count: 5, low_stock_count: 695, open_purchase_order_count: 2 })
    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.getByRole('button', { name: /Needs reorder 5/ })).toBeInTheDocument()
    expect(screen.queryByText('695')).not.toBeInTheDocument()
  })

  it('uses the actionable recommendation for row status and keeps row actions outside table-cell semantics', async () => {
    const actionablePart: PartRecord = {
      ...brakePart,
      id: 'part-actionable-demand',
      sku: 'FAN-CLUTCH-1',
      name: 'Fan clutch',
      available_packages: 10,
      needed_for_open_repairs: 2,
      reorder_level: 0,
      recommended_order_packages: 2,
      preferred_source: source,
      supplier_sources: [source],
    }
    installApi()
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/parts-operations/parts') return Promise.resolve({ data: page([actionablePart]) })
      if (url === `/parts-operations/parts/${actionablePart.id}`) return Promise.resolve({ data: detail(actionablePart) })
      if (url.startsWith('/parts-operations/suppliers/')) return Promise.resolve({ data: supplierPurchasing })
      if (url === '/parts-operations/activity') return Promise.resolve({ data: page([], { total: 0, limit: 1 }) })
      throw new Error(`Unexpected GET ${url}`)
    })
    renderWorkspace({ needs_reorder_count: 1, low_stock_count: 1, open_purchase_order_count: 0 })

    await screen.findByRole('heading', { name: 'Fan clutch' })
    const openPart = screen.getByRole('button', { name: /Fan clutch.*FAN-CLUTCH-1/ })
    expect(openPart).toHaveAttribute('aria-controls', 'selected-part-inspector')
    expect(openPart).not.toHaveAttribute('role', 'cell')
    expect(openPart.closest('[role="cell"]')).toHaveClass('db-parts-workbench__part-cell')
    expect(screen.getAllByText('Needs reorder').length).toBeGreaterThan(0)
    expect(screen.getByRole('checkbox', { name: 'Select Fan clutch for purchase preparation' }).closest('label')).not.toBeNull()
  })

  it('keeps archived parts out of the default request and locks their stock and purchase actions', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.queryByText('Archived part. Activity stays available, but stock and purchasing actions are locked.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Archived parts' }))

    expect(await screen.findByRole('heading', { name: 'Archived alternator' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Archived part')
    expect(screen.queryByRole('button', { name: 'Adjust on-hand quantity' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit available quantity' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit reorder point' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add to purchase list' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Archived alternator/ })).not.toBeInTheDocument()
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'archived', sort: 'catalog', direction: 'asc', skip: 0, limit: 50, paginated: true },
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

  it('leads with selected-part identity and relocates stock and ordering actions to their contextual views', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    const selectedSurfaces = document.querySelectorAll('[data-selected-surface="true"]')
    expect(selectedSurfaces).toHaveLength(2)
    expect(selectedSurfaces[0]).toHaveClass('is-selected')
    expect(selectedSurfaces[1]).toHaveClass('db-parts-workbench__selected-action')
    // Edit now shares a controls group with the dismiss on the same label row.
    const editDetails = screen.getByRole('button', { name: 'Edit details' })
    expect(editDetails.parentElement).toHaveClass('db-parts-workbench__selected-controls')
    expect(editDetails.closest('.db-parts-workbench__selected-label-row')).not.toBeNull()
    expect(screen.getByRole('tabpanel', { name: 'Overview' })).toHaveTextContent('At a glance')
    expect(screen.queryByRole('button', { name: 'Add to purchase list' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjust on-hand quantity' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Open Purchasing/ })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Stock' }))
    const stock = screen.getByRole('tabpanel', { name: 'Stock' })
    expect(within(stock).getByRole('button', { name: 'Adjust on-hand quantity' })).toHaveClass('db-parts-workbench__stock-action')
    expect(within(stock).queryByRole('button', { name: 'Edit available quantity' })).not.toBeInTheDocument()
    expect(within(stock).getByRole('button', { name: 'Edit reorder point' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Ordering' }))
    const ordering = screen.getByRole('tabpanel', { name: 'Ordering' })
    expect(within(ordering).getByText('Replenishment recommended')).toBeInTheDocument()
    expect(within(ordering).getByRole('button', { name: 'Add to purchase list' })).toHaveClass('db-parts-workbench__action-primary')
    expect(within(ordering).getAllByRole('button', { name: /Open Purchasing/ })).toHaveLength(1)
    expect(within(ordering).getByRole('heading', { name: 'Purchase activity' })).toBeInTheDocument()
    expect(within(ordering).getByRole('heading', { name: 'Open purchase orders' }).parentElement).toHaveTextContent('None')
    expect(within(ordering).getByRole('heading', { name: 'Recent receipts' }).parentElement).toHaveTextContent('None')
    expect(within(ordering).getAllByText('None')).toHaveLength(2)
    expect(within(ordering).queryByText('No open purchase order includes this part.')).not.toBeInTheDocument()
    expect(within(ordering).queryByText('No receiving history has been recorded for this part.')).not.toBeInTheDocument()
    expect(document.querySelector('.db-parts-workbench__technical-line')).toHaveTextContent('51 TRACKED / 5 NEEDS REORDER / 2 OPEN PURCHASE ORDERS')
    expect(screen.getByRole('button', { name: /Needs reorder 5/ })).toBeInTheDocument()
    expect(screen.queryByText(/BELOW MIN/)).not.toBeInTheDocument()

    const workbench = document.querySelector('.db-parts-workbench')
    const body = workbench?.querySelector('.db-parts-workbench__body')
    expect(workbench?.querySelectorAll('.db-parts-workbench__view-count')).toHaveLength(2)
    expect(body?.children).toHaveLength(2)
    expect(body?.firstElementChild).toHaveClass('db-parts-workbench__ledger-workspace')
    expect(body?.lastElementChild).toHaveClass('db-parts-workbench__inspector')
    // Ledger controls live outside the bordered body, as a workbench-level
    // sibling that precedes it.
    const toolbar = workbench?.querySelector('.db-parts-workbench__toolbar')
    expect(toolbar?.parentElement).toHaveClass('db-parts-workbench')
    expect(toolbar?.nextElementSibling).toHaveClass('db-parts-workbench__body')
  })

  it('keeps manual purchase preparation available without visually escalating healthy stock', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.type(screen.getByRole('searchbox', { name: 'Search parts' }), 'brake')
    await screen.findByRole('heading', { name: 'Brake shoe kit' })
    await user.click(screen.getByRole('tab', { name: 'Ordering' }))

    const ordering = screen.getByRole('tabpanel', { name: 'Ordering' })
    expect(within(ordering).getByText('Stock is covered')).toBeInTheDocument()
    expect(within(ordering).getByText('No replenishment is recommended. Add it only to stage a manual review in Purchasing.')).toBeInTheDocument()
    expect(within(ordering).getByRole('button', { name: 'Add to purchase list' })).toHaveClass('db-parts-workbench__action-secondary')
    expect(within(ordering).getByRole('button', { name: 'Add to purchase list' })).not.toHaveClass('db-parts-workbench__action-primary')
  })

  it('restores the selected-part editor for identity, labels, location, and photo management', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: 'Edit details' }))
    const editor = await screen.findByRole('form', { name: 'Edit part details' })
    expect(apiMocks.get).toHaveBeenCalledWith('/inventory/part-active')
    expect(screen.queryByRole('button', { name: 'Close editor' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add to purchase list' })).not.toBeInTheDocument()
    expect(editor.parentElement).toHaveTextContent('Changes save immediately')
    expect(within(editor).getByRole('textbox', { name: 'Part name' })).toHaveValue('Alternator')
    expect(within(editor).getByRole('textbox', { name: 'SKU' })).toHaveValue('ALT-42')
    expect(within(editor).getByRole('textbox', { name: 'Category' })).toHaveValue('Electrical')
    expect(within(editor).getByRole('textbox', { name: 'Description' })).toHaveValue('Heavy-duty alternator')
    expect(within(editor).getByRole('textbox', { name: 'Bin location' })).toHaveValue('A-12')
    expect(within(editor).getByRole('textbox', { name: 'Unit label' })).toHaveValue('each')

    const name = within(editor).getByRole('textbox', { name: 'Part name' })
    const category = within(editor).getByRole('textbox', { name: 'Category' })
    const location = within(editor).getByRole('textbox', { name: 'Bin location' })
    await user.clear(name)
    await user.type(name, 'High-output alternator')
    await user.clear(category)
    await user.type(category, 'Charging')
    await user.clear(location)
    await user.type(location, 'B-07')
    await user.click(within(editor).getByRole('button', { name: 'Save details' }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith('/inventory/part-active', {
      name: 'High-output alternator',
      category: 'Charging',
      location: 'B-07',
    }))

    await user.click(screen.getByRole('button', { name: 'Edit details' }))
    const reopened = await screen.findByRole('form', { name: 'Edit part details' })
    expect(within(reopened).getByRole('button', { name: 'Save details' })).toBeDisabled()
    const file = new File(['photo'], 'alternator.webp', { type: 'image/webp' })
    const editorRegion = reopened.parentElement!
    const fileInput = editorRegion.querySelector<HTMLInputElement>('input[type="file"]')
    expect(fileInput).not.toBeNull()
    expect(fileInput).toHaveAttribute('hidden')
    await user.upload(fileInput!, file)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/inventory/part-active/photo', expect.any(FormData), {
      headers: { 'Content-Type': 'multipart/form-data' },
    }))
    expect((apiMocks.post.mock.calls.at(-1)?.[1] as FormData).get('image')).toBe(file)
    // Removing a photo is destructive, so the trash arms a confirmation rather
    // than deleting on the first click.
    await user.click(within(editorRegion).getByRole('button', { name: 'Remove photo' }))
    expect(apiMocks.delete).not.toHaveBeenCalled()
    expect(within(editorRegion).getByText('Remove this photo?')).toBeInTheDocument()

    await user.click(within(editorRegion).getByRole('button', { name: 'Keep photo' }))
    expect(apiMocks.delete).not.toHaveBeenCalled()

    await user.click(within(editorRegion).getByRole('button', { name: 'Remove photo' }))
    await user.click(within(editorRegion).getByRole('button', { name: 'Remove photo' }))
    await waitFor(() => expect(apiMocks.delete).toHaveBeenCalledWith('/inventory/part-active/photo'))
  })

  it('rejects invalid photo drafts before upload and closes the details draft with Escape', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: 'Edit details' }))
    const editor = await screen.findByRole('form', { name: 'Edit part details' })
    const fileInput = editor.parentElement!.querySelector<HTMLInputElement>('input[type="file"]')!
    await user.upload(fileInput, new File([], 'empty.png', { type: 'image/png' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose an image that is not empty.')
    expect(apiMocks.post).not.toHaveBeenCalled()

    const name = within(editor).getByRole('textbox', { name: 'Part name' })
    await user.type(name, ' updated')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('form', { name: 'Edit part details' })).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Edit details' })).toHaveFocus())
  })

  it('owns inspector detail with four keyboard-operable sections and resets new selections to Overview', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Overview', 'Stock', 'Ordering', 'Activity'])
    expect(tabs.filter((tab) => tab.getAttribute('aria-selected') === 'true')).toHaveLength(1)
    expect(screen.getByRole('tabpanel', { name: 'Overview' })).toBeInTheDocument()

    tabs[0].focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Stock' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'Stock' })).toHaveTextContent('Needed for open repairs')
    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'Activity' })).toHaveAttribute('aria-selected', 'true')
    const activityPanel = screen.getByRole('tabpanel', { name: 'Activity' })
    expect(await within(activityPanel).findByRole('heading', { name: 'Lifecycle summary' })).toBeInTheDocument()
    expect(await within(activityPanel).findByRole('heading', { name: 'Stock adjusted' })).toBeInTheDocument()

    await user.type(screen.getByRole('searchbox', { name: 'Search parts' }), 'brake')
    await screen.findByRole('heading', { name: 'Brake shoe kit' })
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'Overview' })).toHaveTextContent('No open repair is waiting on this part.')
  })

  it('renders one flat supplier relationship with source-first lead time and real delivery reliability', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    const heading = await screen.findByRole('heading', { name: 'Supplied by' })
    const section = heading.closest('.db-parts-workbench__supplier-section')
    expect(section).not.toBeNull()
    const relationship = section!.querySelector('.db-parts-workbench__supplier-relationship')
    expect(relationship).not.toBeNull()
    expect(within(section as HTMLElement).getByText('Fleet Parts Co')).toHaveClass('db-parts-workbench__supplier-name')
    expect(await within(section as HTMLElement).findByText(/NET 30 · Lead 2 days · Min 5 units · Pack size 4/)).toHaveClass('db-parts-workbench__supplier-meta')
    expect(await within(section as HTMLElement).findByLabelText('90% on-time delivery reliability')).toHaveTextContent('90%')
    expect(within(section as HTMLElement).getByText('Their part no.').closest('dl')).toBe(relationship!.querySelector('dl'))
    expect(relationship!.querySelectorAll(':scope > dl > div')).toHaveLength(3)
    expect(within(section as HTMLElement).getByText('Last receipt / purchase')).toBeInTheDocument()
    expect(within(section as HTMLElement).getByText('No receipt or purchase recorded')).toBeInTheDocument()

    await user.click(within(section as HTMLElement).getByRole('button', { name: 'Change preferred supplier' }))
    expect(screen.getByRole('tab', { name: 'Ordering' })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Ordering' })).toHaveFocus())
  })

  it('falls back to supplier lead time and never reports zero-percent reliability without timed orders', async () => {
    const fallbackSource = { ...source, lead_time_days: null }
    const fallbackPart = { ...activePart, preferred_source: fallbackSource, supplier_sources: [fallbackSource] }
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/parts-operations/activity') return Promise.resolve({ data: page([], { total: 1, limit: 1 }) })
      if (url === '/parts-operations/parts') return Promise.resolve({ data: page([fallbackPart]) })
      if (url === `/parts-operations/parts/${fallbackPart.id}`) return Promise.resolve({ data: detail(fallbackPart) })
      if (url.startsWith('/parts-operations/suppliers/')) return Promise.resolve({ data: { ...supplierPurchasing, default_lead_time_days: 6, timed_order_count: 0, on_time_order_count: 0, on_time_rate: '0' } })
      throw new Error(`Unexpected GET ${url}`)
    })
    renderWorkspace()

    const heading = await screen.findByRole('heading', { name: 'Supplied by' })
    const section = heading.closest('.db-parts-workbench__supplier-section') as HTMLElement
    expect(await within(section).findByText(/Lead 6 days/)).toBeInTheDocument()
    expect(await within(section).findByLabelText('Not enough delivery history')).toHaveTextContent('—')
    expect(within(section).queryByText('0%')).not.toBeInTheDocument()
  })

  it('separates supplier facts from the edit action and preserves pointer and keyboard focus modality', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Ordering' }))
    let sourceRecord = screen.getByRole('article', { name: 'Fleet Parts Co · Preferred' })
    expect(within(sourceRecord).getByText('Part no.')).toBeInTheDocument()
    expect(within(sourceRecord).getByText('FPC-ALT-42')).toBeInTheDocument()
    expect(within(sourceRecord).getByText('Pack')).toBeInTheDocument()
    expect(within(sourceRecord).getByText('Minimum')).toBeInTheDocument()
    expect(within(sourceRecord).getByText('Lead time')).toBeInTheDocument()
    expect(within(sourceRecord).getByText('2 days')).toBeInTheDocument()
    expect(within(sourceRecord).getByText('Last cost')).toBeInTheDocument()
    expect(within(sourceRecord).getByText('$12.50')).toBeInTheDocument()
    let sourceTrigger = within(sourceRecord).getByRole('button', { name: 'Edit Fleet Parts Co supplier source' })
    expect(sourceTrigger).toHaveTextContent('Edit source')
    expect(sourceTrigger).not.toBeDisabled()
    expect(sourceTrigger.parentElement).toBe(sourceRecord)

    fireEvent.click(sourceTrigger, { detail: 1 })
    let sourceForm = screen.getByRole('form', { name: 'Edit Fleet Parts Co supplier source' })
    const existingSourceField = within(sourceForm).getByRole('textbox', { name: 'Supplier part number' })
    expect(sourceForm).toHaveAttribute('data-focus-mode', 'pointer')
    await waitFor(() => expect(existingSourceField).toHaveFocus())
    expect(screen.queryByText('Edit source', { exact: true })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit Fleet Parts Co supplier source' })).not.toBeInTheDocument()
    fireEvent.keyDown(existingSourceField, { key: 'Tab' })
    expect(sourceForm).toHaveAttribute('data-focus-mode', 'keyboard')
    await user.click(within(sourceForm).getByRole('button', { name: 'Cancel' }))
    sourceRecord = await screen.findByRole('article', { name: 'Fleet Parts Co · Preferred' })
    sourceTrigger = within(sourceRecord).getByRole('button', { name: 'Edit Fleet Parts Co supplier source' })
    await waitFor(() => expect(sourceTrigger).toHaveFocus())

    sourceTrigger.focus()
    await user.keyboard('{Enter}')
    sourceForm = screen.getByRole('form', { name: 'Edit Fleet Parts Co supplier source' })
    expect(sourceForm).toHaveAttribute('data-focus-mode', 'keyboard')
    await waitFor(() => expect(within(sourceForm).getByRole('textbox', { name: 'Supplier part number' })).toHaveFocus())
    await user.click(within(sourceForm).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Edit Fleet Parts Co supplier source' })).toHaveFocus())

    const addSource = screen.getByRole('button', { name: 'Add supplier source' })
    fireEvent.click(addSource, { detail: 1 })
    let addForm = await screen.findByRole('form', { name: 'Add supplier source' })
    expect(addForm).toHaveAttribute('data-focus-mode', 'pointer')
    await waitFor(() => expect(within(addForm).getByRole('combobox', { name: 'Supplier' })).toHaveFocus())
    await user.click(within(addForm).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Add supplier source' })).toHaveFocus())

    screen.getByRole('button', { name: 'Add supplier source' }).focus()
    await user.keyboard('{Enter}')
    addForm = await screen.findByRole('form', { name: 'Add supplier source' })
    expect(addForm).toHaveAttribute('data-focus-mode', 'keyboard')
    await waitFor(() => expect(within(addForm).getByRole('combobox', { name: 'Supplier' })).toHaveFocus())
  })

  it('renders supplier truth without fake edit affordances for reception staff and archived parts', async () => {
    authState.role = 'receptionist'
    installApi()
    const user = userEvent.setup()
    const receptionistView = renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Ordering' }))
    expect(screen.getByText('Fleet Parts Co · Preferred')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit Fleet Parts Co supplier source' })).not.toBeInTheDocument()
    expect(screen.queryByText('Edit source', { exact: true })).not.toBeInTheDocument()
    expect(document.querySelector('.db-parts-workbench__source-row')?.tagName).toBe('ARTICLE')
    expect(screen.getByRole('article', { name: 'Fleet Parts Co · Preferred' })).toHaveTextContent('FPC-ALT-42')
    receptionistView.unmount()

    authState.role = 'garage_owner'
    installApi()
    renderWorkspace()
    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: 'Archived parts' }))
    await screen.findByRole('heading', { name: 'Archived alternator' })
    await user.click(screen.getByRole('tab', { name: 'Ordering' }))
    expect(screen.getByText('Fleet Parts Co · Preferred')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit Fleet Parts Co supplier source' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add supplier source' })).not.toBeInTheDocument()
    expect(screen.queryByText('Edit source', { exact: true })).not.toBeInTheDocument()
  })

  it('uses shop stock language and requires a reason for on-hand changes without changing the inventory contract', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(document.body).not.toHaveTextContent(/\b(?:packages|pkg)\b/i)
    expect(screen.getByText(/Pack size 4/)).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: 'Stock' }))
    await user.click(screen.getByRole('button', { name: 'Adjust on-hand quantity' }))
    const onHand = screen.getByRole('textbox', { name: 'On-hand quantity' })
    expect(screen.getByRole('form', { name: 'Edit available quantity' })).toBeInTheDocument()
    expect(onHand).toHaveValue('3')
    await user.click(screen.getByRole('button', { name: 'Decrease On-hand quantity' }))
    expect(onHand).toHaveValue('2')
    await user.click(screen.getByRole('button', { name: 'Increase On-hand quantity' }))
    expect(onHand).toHaveValue('3')
    await user.clear(onHand)
    await user.type(onHand, '4')
    await user.tab()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Explain why the on-hand quantity is changing.')
    expect(apiMocks.put).not.toHaveBeenCalled()

    await user.type(screen.getByRole('textbox', { name: 'Adjustment reason' }), 'Cycle count correction')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith('/inventory/part-active', {
      stock_quantity: 4,
      stock_adjustment_reason: 'Cycle count correction',
    }))
  })

  it('keeps one explicit physical on-hand editor entry point and steps reorder locally before saving', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Stock' }))
    const stock = screen.getByRole('tabpanel', { name: 'Stock' })
    expect(within(stock).getByText('Needed for open repairs')).toBeInTheDocument()
    expect(within(stock).getByText('Incoming')).toBeInTheDocument()
    expect(within(stock).queryByLabelText('Needed for open repairs')).not.toBeInTheDocument()
    expect(within(stock).queryByLabelText('Incoming')).not.toBeInTheDocument()
    expect(within(stock).queryByText('Adjust available')).not.toBeInTheDocument()
    expect(within(stock).queryByText('Change reorder point')).not.toBeInTheDocument()
    expect(stock.querySelector('.db-parts-workbench__actions')).not.toBeInTheDocument()
    expect(stock.querySelector('.db-parts-workbench__edit')).not.toBeInTheDocument()

    expect(within(stock).queryByRole('button', { name: 'Edit available quantity' })).not.toBeInTheDocument()
    const availableTrigger = within(stock).getByRole('button', { name: 'Adjust on-hand quantity' })
    expect(availableTrigger).toHaveTextContent('Adjust stock')
    await user.click(availableTrigger)
    const availableForm = within(stock).getByRole('form', { name: 'Edit available quantity' })
    expect(within(stock).getAllByRole('form', { name: 'Edit available quantity' })).toHaveLength(1)
    expect(within(stock).getAllByRole('textbox', { name: 'On-hand quantity' })).toHaveLength(1)
    expect(within(stock).queryByRole('button', { name: 'Edit reorder point' })).not.toBeInTheDocument()
    expect(availableForm.closest('.db-parts-workbench__fact')).toHaveTextContent('Physical on hand')
    expect(within(stock).getByText('Held for checkout')).toBeInTheDocument()
    expect(within(stock).getByText('Available to sell')).toBeInTheDocument()
    expect(availableForm.closest('.db-parts-workbench__fact')).toHaveClass('is-editing')
    expect(within(availableForm).queryByText('Cancel', { exact: true })).not.toBeInTheDocument()
    expect(within(availableForm).getByRole('button', { name: 'Save' })).toHaveTextContent('Save')
    await user.click(within(availableForm).getByRole('button', { name: 'Cancel available quantity edit' }))
    await waitFor(() => expect(within(stock).getByRole('button', { name: 'Adjust on-hand quantity' })).toHaveFocus())

    await user.click(screen.getByRole('button', { name: 'Adjust on-hand quantity' }))
    expect(within(stock).getAllByRole('textbox', { name: 'On-hand quantity' })).toHaveLength(1)
    expect(within(stock).getAllByRole('form', { name: 'Edit available quantity' })).toHaveLength(1)
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Adjust on-hand quantity' })).toHaveFocus())

    await user.click(within(stock).getByRole('button', { name: 'Edit reorder point' }))
    const reorder = within(stock).getByRole('textbox', { name: 'Reorder at' })
    expect(reorder).toHaveValue('5')
    expect(within(stock).queryByRole('textbox', { name: 'Adjustment reason' })).not.toBeInTheDocument()
    await user.click(within(stock).getByRole('button', { name: 'Decrease Reorder at' }))
    expect(reorder).toHaveValue('4')
    await user.click(within(stock).getByRole('button', { name: 'Increase Reorder at' }))
    expect(reorder).toHaveValue('5')
    await user.clear(reorder)
    await user.type(reorder, '6')
    await user.tab()
    await user.click(within(stock).getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(apiMocks.put).toHaveBeenCalledWith('/inventory/part-active', { reorder_level: 6 }))
    await waitFor(() => expect(within(stock).getByRole('button', { name: 'Edit reorder point' })).toHaveFocus())
  })

  it('keeps pointer-open steppers neutral while keyboard-open steppers retain focused editing and restore the invoker', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Stock' }))
    const shortcut = screen.getByRole('button', { name: 'Adjust on-hand quantity' })
    shortcut.focus()
    fireEvent.click(shortcut, { detail: 1 })
    const onHand = screen.getByRole('textbox', { name: 'On-hand quantity' })
    const pointerForm = onHand.closest('form')
    expect(pointerForm).toHaveAttribute('data-focus-mode', 'pointer')
    expect(onHand).toHaveFocus()
    expect(within(pointerForm!).getByText('units')).toBeInTheDocument()
    expect(within(pointerForm!).getByRole('tooltip', { name: 'Cancel available quantity edit' })).toBeInTheDocument()
    expect(within(pointerForm!).queryByText('Cancel', { exact: true })).not.toBeInTheDocument()
    await user.click(within(pointerForm!).getByRole('button', { name: 'Cancel available quantity edit' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Adjust on-hand quantity' })).toHaveFocus())

    const stock = screen.getByRole('tabpanel', { name: 'Stock' })
    const reorderTrigger = within(stock).getByRole('button', { name: 'Edit reorder point' })
    reorderTrigger.focus()
    await user.keyboard('{Enter}')
    const reorder = within(stock).getByRole('textbox', { name: 'Reorder at' })
    const keyboardForm = reorder.closest('form')
    expect(keyboardForm).toHaveAttribute('data-focus-mode', 'keyboard')
    expect(reorder).toHaveFocus()
    expect(within(keyboardForm!).getByText('units')).toBeInTheDocument()
    expect(within(keyboardForm!).getByRole('button', { name: 'Cancel reorder point edit' })).toBeInTheDocument()
    expect(within(keyboardForm!).getByRole('button', { name: 'Save' })).toHaveTextContent('Save')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(within(stock).getByRole('button', { name: 'Edit reorder point' })).toHaveFocus())
  })

  it('retains the inline stock draft and recovery error when the inventory update fails', async () => {
    installApi()
    apiMocks.put.mockRejectedValue({ response: { status: 422, data: { detail: 'Inventory update could not be saved.' } } })
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Stock' }))
    const stock = screen.getByRole('tabpanel', { name: 'Stock' })
    await user.click(within(stock).getByRole('button', { name: 'Edit reorder point' }))
    const reorder = within(stock).getByRole('textbox', { name: 'Reorder at' })
    await user.clear(reorder)
    await user.type(reorder, '9')
    await user.click(within(stock).getByRole('button', { name: 'Save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Inventory update could not be saved.')
    expect(within(stock).getByRole('form', { name: 'Edit reorder point' })).toBeInTheDocument()
    expect(reorder).toHaveValue('9')
  })

  it('keeps reception staff read-only without rendering fake disabled stock forms', async () => {
    authState.role = 'receptionist'
    installApi()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.getByText('You can view stock. Owners and admins can make changes.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjust on-hand quantity' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit available quantity' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit reorder point' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Select part' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /purchase preparation/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Selected parts actions' })).not.toBeInTheDocument()
  })

  it('adds the preferred supplier source to purchase preparation with minimum and pack rounding', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Ordering' }))
    await user.click(screen.getByRole('button', { name: 'Add to purchase list' }))

    expect(JSON.parse(window.sessionStorage.getItem(purchasePreparationStorageKey()) || '[]')).toEqual([{
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
      blockedReason: null,
    }])
    expect(screen.getByRole('status')).toHaveTextContent('1 part added to purchase preparation')
    const ordering = screen.getByRole('tabpanel', { name: 'Ordering' })
    expect(within(ordering).getByText('Prepared for purchasing')).toBeInTheDocument()
    expect(within(ordering).getByText('This part is staged for review in Purchasing.')).toBeInTheDocument()
    expect(within(ordering).queryByRole('button', { name: 'Add to purchase list' })).not.toBeInTheDocument()
    expect(within(ordering).getByRole('button', { name: 'View purchase list' })).toBeInTheDocument()
  })

  it('preserves populated purchase orders and receipts inside the compact activity group', async () => {
    installApi({
      ...detail(activePart),
      incoming_sources: [{ purchase_order_id: 'po-1', po_number: 'PO-1042', packages: 8, expected_at: '2026-09-02T12:00:00Z' }],
      recent_receipts: [{ receipt_id: 'receipt-1', receipt_number: 'RCV-2042', purchase_order_id: 'po-1', po_number: 'PO-1042', quantity: 4, unit_cost: '12.25', received_at: '2026-08-24T12:00:00Z' }],
    })
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Ordering' }))
    const ordering = screen.getByRole('tabpanel', { name: 'Ordering' })
    expect(within(ordering).getByRole('heading', { name: 'Purchase activity' })).toBeInTheDocument()
    const openOrders = within(ordering).getByRole('heading', { name: 'Open purchase orders' }).closest('section')!
    const recentReceipts = within(ordering).getByRole('heading', { name: 'Recent receipts' }).closest('section')!
    expect(within(openOrders).getByRole('button', { name: /PO-1042/ })).toHaveTextContent('8 units incoming')
    expect(within(recentReceipts).getByRole('button', { name: /RCV-2042/ })).toHaveTextContent('4 at $12.25')
    expect(within(ordering).queryByText('None')).not.toBeInTheDocument()
  })

  it('renders immutable inventory Activity with stock projections and source links', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.getByRole('button', { name: 'Activity' })).toBeInTheDocument()
    expect(apiMocks.get.mock.calls.filter(([url]) => url === '/parts-operations/activity-events')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Activity' }))
    expect(await screen.findByRole('heading', { name: 'Stock adjusted' })).toBeInTheDocument()
    const activityEvent = screen.getByRole('article', { name: 'Stock adjusted' })
    const onHandFact = within(activityEvent).getByText('On hand').closest('div')
    const heldFact = within(activityEvent).getByText('Held').closest('div')
    const availableFact = within(activityEvent).getByText('Available').closest('div')
    expect(within(onHandFact!).getByText('3')).toBeInTheDocument()
    expect(within(onHandFact!).getByText('2')).toBeInTheDocument()
    expect(within(heldFact!).getByText('0')).toBeInTheDocument()
    expect(within(availableFact!).getByText('2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /MOV-100/ })).toHaveAttribute('href', '/dashboard/garage/inventory?activity=movement-1')
    expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/activity-events', { params: { limit: 50 } })
    expect(screen.queryByText(/stock\.adjusted/)).not.toBeInTheDocument()
  })

  it('lets managers select an active non-reorder part without changing the detail row or exposing an ordinal column', async () => {
    installApi()
    apiMocks.get.mockImplementation((url: string) => {
      if (url === '/parts-operations/activity') return Promise.resolve({ data: page([], { total: 1, limit: 1 }) })
      if (url === '/parts-operations/parts') return Promise.resolve({ data: page([activePart, brakePart]) })
      if (url === `/parts-operations/parts/${activePart.id}`) return Promise.resolve({ data: detail(activePart) })
      if (url === `/parts-operations/parts/${brakePart.id}`) return Promise.resolve({ data: detail(brakePart) })
      if (url.startsWith('/parts-operations/suppliers/')) return Promise.resolve({ data: { id: 'supplier-1', name: 'Fleet Parts Co', payment_terms: 'NET 30' } })
      throw new Error(`Unexpected GET ${url}`)
    })
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('checkbox', { name: 'Select Brake shoe kit for purchase preparation' }))
    expect(screen.getByRole('checkbox', { name: 'Select Brake shoe kit for purchase preparation' })).toBeChecked()
    expect(screen.getByRole('heading', { name: 'Alternator' })).toBeInTheDocument()
    expect(document.querySelectorAll('[data-selected-surface="true"]')).toHaveLength(2)
    expect(screen.queryByRole('columnheader', { name: 'No' })).not.toBeInTheDocument()
    expect(document.querySelector('.db-parts-workbench__line-number')).not.toBeInTheDocument()
    expect(screen.getAllByRole('columnheader').map((header) => header.getAttribute('aria-label') || header.textContent)).toEqual([
      'Select part',
      'Part / Description',
      'Available',
      'Bin location',
      'Unit cost',
      'Preferred supplier',
      'Remarks',
    ])
    for (const removedHeader of ['Needed', 'Reorder', 'Incoming']) {
      expect(screen.queryByRole('columnheader', { name: removedHeader })).not.toBeInTheDocument()
    }
    expect(screen.getAllByRole('cell', { name: 'Bin A-12' }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('columnheader', { name: /Free|Committed/i })).not.toBeInTheDocument()
    const overview = screen.getByRole('tabpanel', { name: 'Overview' })
    expect(overview).toHaveTextContent('Unit cost')
    expect(overview).toHaveTextContent('Remarks')
    expect(overview).toHaveTextContent('Fleet Parts Co')
  })

  it('preselects only eligible loaded reorder rows and adds newly loaded eligible rows without implying unloaded selection', async () => {
    installApi()
    apiMocks.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/parts-operations/activity') return Promise.resolve({ data: page([], { total: 1, limit: 1 }) })
      if (url === '/parts-operations/parts' && config?.params?.attention === 'needs_reorder' && config.params.skip === 50) return Promise.resolve({ data: page([unassignedReorderPart], { total: 2, skip: 50 }) })
      if (url === '/parts-operations/parts' && config?.params?.attention === 'needs_reorder' && config.params.sort === 'name' && config.params.direction === 'desc') return Promise.resolve({ data: page([activePart, directionReorderPart], { total: 2 }) })
      if (url === '/parts-operations/parts' && config?.params?.attention === 'needs_reorder') return Promise.resolve({ data: page([activePart], { total: 2, has_more: true }) })
      if (url === '/parts-operations/parts') return Promise.resolve({ data: page([activePart]) })
      if (url === `/parts-operations/parts/${activePart.id}`) return Promise.resolve({ data: detail(activePart) })
      if (url === `/parts-operations/parts/${unassignedReorderPart.id}`) return Promise.resolve({ data: detail(unassignedReorderPart) })
      if (url.startsWith('/parts-operations/suppliers/')) return Promise.resolve({ data: { id: 'supplier-1', name: 'Fleet Parts Co', payment_terms: 'NET 30' } })
      throw new Error(`Unexpected GET ${url}`)
    })
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: /Needs reorder 5/ }))
    await waitFor(() => expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ })).toHaveLength(1))
    expect(screen.getByRole('button', { name: /Needs reorder 2/ })).toHaveAttribute('aria-current', 'page')
    expect(document.querySelector('.db-parts-workbench__technical-line')).toHaveTextContent('2 NEEDS REORDER')
    expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ }).every((control) => (control as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByText('1 part selected')).toBeInTheDocument()
    expect(screen.getByText('Showing 1 of 2')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Part / Description: sort ascending' }))
    await waitFor(() => expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ })).toHaveLength(1))
    expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ }).every((control) => (control as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByText('1 part selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Load 50 more' }))
    await waitFor(() => expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ })).toHaveLength(2))
    expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ }).every((control) => (control as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByText('2 parts selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Part / Description: sort descending' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: expect.objectContaining({ attention: 'needs_reorder', sort: 'name', direction: 'desc', skip: 0 }),
    }))
    expect(await screen.findByText('3 parts selected')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Select Belt tensioner for purchase preparation' })).toBeChecked()
    await user.click(within(screen.getByRole('region', { name: 'Selected parts actions' })).getByRole('button', { name: /Add to purchase list/ }))

    const prepared = JSON.parse(window.sessionStorage.getItem(purchasePreparationStorageKey()) || '[]')
    expect(prepared).toEqual(expect.arrayContaining([
      expect.objectContaining({ inventoryId: activePart.id, supplierId: source.supplier_id, blockedReason: null }),
      expect.objectContaining({ inventoryId: unassignedReorderPart.id, supplierId: null, blockedReason: 'supplier_source_required' }),
    ]))
  })

  it('switches density locally and restores the production Add Part validation and inventory payload', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    const toolbar = screen.getByRole('searchbox', { name: 'Search parts' }).closest('.db-parts-workbench__toolbar')
    expect(toolbar?.parentElement).toHaveClass('db-parts-workbench')
    expect(screen.queryByRole('dialog', { name: 'Sort parts' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Sort' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ledger options' })).not.toBeInTheDocument()
    const density = screen.getByRole('group', { name: 'Ledger density' })
    const comfortable = within(density).getByRole('button', { name: 'Comfortable' })
    const compact = within(density).getByRole('button', { name: 'Compact' })
    expect(comfortable).toHaveAttribute('aria-pressed', 'true')
    await user.click(compact)
    expect(compact).toHaveAttribute('aria-pressed', 'true')
    expect(document.querySelector('.db-parts-workbench__ledger')).toHaveClass('is-compact')

    await user.click(screen.getByRole('button', { name: 'Add Part' }))
    const addPartDialog = screen.getByRole('dialog', { name: 'Add Part' })
    expect(addPartDialog).toHaveClass('db-parts-workbench__add-panel')
    expect(within(addPartDialog).getByRole('group', { name: 'Part details' })).toBeInTheDocument()
    expect(within(addPartDialog).getByRole('group', { name: 'Stock' })).toBeInTheDocument()
    expect(within(addPartDialog).getByRole('group', { name: 'Pricing' })).toBeInTheDocument()
    expect(within(addPartDialog).getByRole('group', { name: 'Supplier' })).toBeInTheDocument()
    expect(addPartDialog.querySelector('input[type="number"]')).not.toBeInTheDocument()
    const onHand = within(addPartDialog).getByRole('textbox', { name: 'On-hand quantity' })
    const reorder = within(addPartDialog).getByRole('textbox', { name: 'Reorder level' })
    const cost = within(addPartDialog).getByRole('textbox', { name: 'Cost per unit' })
    const sellingPrice = within(addPartDialog).getByRole('textbox', { name: 'Selling price' })
    expect(onHand.closest('.db-parts-workbench__add-stepper')).toBeInTheDocument()
    expect(cost.closest('.db-parts-workbench__add-stepper')).toBeInTheDocument()
    await user.click(within(addPartDialog).getByRole('button', { name: 'Increase On-hand quantity' }))
    expect(onHand).toHaveValue('1')
    await user.click(within(addPartDialog).getByRole('button', { name: 'Decrease On-hand quantity' }))
    expect(onHand).toHaveValue('0')
    await user.clear(reorder)
    await user.type(reorder, '4')
    await user.tab()
    await user.clear(cost)
    await user.type(cost, '12.34')
    await user.tab()
    await user.clear(sellingPrice)
    await user.type(sellingPrice, '18.75')
    await user.tab()
    fireEvent.submit(addPartDialog.querySelector('form')!)
    expect(screen.getByRole('alert')).toHaveTextContent('Part name is required.')
    await user.type(screen.getByRole('textbox', { name: /Part name/ }), 'Air dryer cartridge')
    await user.type(screen.getByRole('textbox', { name: /SKU/ }), 'AIR-DRY-01')
    fireEvent.submit(addPartDialog.querySelector('form')!)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/inventory', expect.objectContaining({
      name: 'Air dryer cartridge', sku: 'AIR-DRY-01', stock_quantity: 0, reorder_level: 4, cost: 12.34, selling_price: 18.75, unit_type: 'each',
    })))
  })

  it('uses semantic desktop headers for every server sort and keeps compact fallback and Catalog reset equivalent', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    const checkbox = screen.getByRole('checkbox', { name: 'Select Alternator for purchase preparation' })
    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    await user.click(screen.getByRole('button', { name: 'Load 50 more' }))
    expect(await screen.findByText('Showing 2 of 51')).toBeInTheDocument()

    const scenarios = [
      { label: 'Part / Description', sort: 'name', first: 'asc', second: 'desc' },
      { label: 'Available', sort: 'available', first: 'asc', second: 'desc' },
      { label: 'Bin location', sort: 'location', first: 'asc', second: 'desc' },
      { label: 'Unit cost', sort: 'cost', first: 'desc', second: 'asc' },
      { label: 'Remarks', sort: 'reorder', first: 'desc', second: 'asc' },
    ] as const

    expect(screen.getAllByRole('columnheader').filter((header) => header.hasAttribute('aria-sort'))).toHaveLength(0)
    for (const [index, scenario] of scenarios.entries()) {
      const header = screen.getByRole('columnheader', { name: scenario.label })
      const firstAction = within(header).getByRole('button', { name: `${scenario.label}: sort ${scenario.first === 'asc' ? 'ascending' : 'descending'}` })
      firstAction.focus()
      if (index === 0) await user.keyboard('{Enter}')
      else await user.click(firstAction)
      await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
        params: expect.objectContaining({ sort: scenario.sort, direction: scenario.first, skip: 0 }),
      }))
      const activeHeader = screen.getByRole('columnheader', { name: scenario.label })
      expect(activeHeader).toHaveAttribute('aria-sort', scenario.first === 'asc' ? 'ascending' : 'descending')
      expect(screen.getAllByRole('columnheader').filter((candidate) => candidate.hasAttribute('aria-sort'))).toEqual([activeHeader])
      await waitFor(() => expect(within(screen.getByRole('columnheader', { name: scenario.label })).getByRole('button')).toHaveFocus())
      expect(screen.getByText('Showing 1 of 51')).toBeInTheDocument()
      expect(screen.queryByText('Brake shoe kit')).not.toBeInTheDocument()

      const secondAction = within(screen.getByRole('columnheader', { name: scenario.label })).getByRole('button', { name: `${scenario.label}: sort ${scenario.second === 'asc' ? 'ascending' : 'descending'}` })
      await user.click(secondAction)
      await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
        params: expect.objectContaining({ sort: scenario.sort, direction: scenario.second, skip: 0 }),
      }))
      expect(screen.getByRole('columnheader', { name: scenario.label })).toHaveAttribute('aria-sort', scenario.second === 'asc' ? 'ascending' : 'descending')
      expect(screen.getByText('1 part selected')).toBeInTheDocument()
    }

    expect(within(screen.getByRole('columnheader', { name: 'Preferred supplier' })).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ledger options' })).not.toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Ledger density' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reset to catalog order' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: expect.objectContaining({ sort: 'catalog', direction: 'asc', skip: 0 }),
    }))
    expect(screen.getAllByRole('columnheader').filter((header) => header.hasAttribute('aria-sort'))).toHaveLength(0)
    expect(screen.queryByRole('button', { name: 'Reset to catalog order' })).not.toBeInTheDocument()

    const sortTrigger = screen.getByRole('button', { name: 'Sort parts' })
    expect(sortTrigger).toHaveAttribute('aria-expanded', 'false')
    expect(sortTrigger).toHaveAttribute('aria-controls', 'parts-compact-sort-popover')
    await user.click(sortTrigger)
    const catalogReset = screen.getByRole('button', { name: 'Catalog order' })
    expect(catalogReset).toHaveFocus()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    const compactRadios = screen.getAllByRole('radio')
    expect(compactRadios).toHaveLength(10)
    const compactTabStops = compactRadios.filter((radio) => radio.tabIndex === 0)
    expect(compactTabStops).toHaveLength(1)
    expect(compactTabStops[0]).toHaveAttribute('aria-checked', 'false')
    compactTabStops[0].focus()
    await user.keyboard('{ArrowDown}')
    expect(compactRadios[1]).toHaveFocus()
    await user.keyboard('{Home}')
    expect(compactRadios[0]).toHaveFocus()
    await user.keyboard(' ')
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: expect.objectContaining({ sort: 'name', direction: 'asc', skip: 0 }),
    }))
    expect(sortTrigger).toHaveFocus()

    await user.click(sortTrigger)
    await user.click(screen.getByRole('radio', { name: 'Unit cost high to low' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: expect.objectContaining({ sort: 'cost', direction: 'desc', skip: 0 }),
    }))
    expect(screen.queryByRole('dialog', { name: 'Sort parts' })).not.toBeInTheDocument()
    expect(sortTrigger).toHaveFocus()

    await user.click(sortTrigger)
    await user.click(screen.getByRole('button', { name: 'Catalog order' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: expect.objectContaining({ sort: 'catalog', direction: 'asc', skip: 0 }),
    }))
    expect(screen.getAllByRole('columnheader').filter((header) => header.hasAttribute('aria-sort'))).toHaveLength(0)

    await user.click(sortTrigger)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Sort parts' })).not.toBeInTheDocument()
    expect(sortTrigger).toHaveFocus()

    await user.click(sortTrigger)
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('dialog', { name: 'Sort parts' })).not.toBeInTheDocument()
  })

  it('preserves the selected inspector and checked purchase IDs when sorting moves the row beyond page one', async () => {
    installApi()
    apiMocks.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/parts-operations/activity') return Promise.resolve({ data: page([], { total: 1, limit: 1 }) })
      if (url === '/parts-operations/parts') {
        if (config?.params?.sort === 'name') return Promise.resolve({ data: page([activePart], { total: 2 }) })
        return Promise.resolve({ data: page([activePart, brakePart], { total: 2 }) })
      }
      if (url === `/parts-operations/parts/${activePart.id}`) return Promise.resolve({ data: detail(activePart) })
      if (url === `/parts-operations/parts/${brakePart.id}`) return Promise.resolve({ data: detail(brakePart) })
      if (url.startsWith('/parts-operations/suppliers/')) return Promise.resolve({ data: supplierPurchasing })
      throw new Error(`Unexpected GET ${url}`)
    })
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: /Brake shoe kit.*BRK-9/ }))
    await screen.findByRole('heading', { name: 'Brake shoe kit' })
    await user.click(screen.getByRole('checkbox', { name: 'Select Brake shoe kit for purchase preparation' }))

    await user.click(screen.getByRole('button', { name: 'Part / Description: sort ascending' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: expect.objectContaining({ sort: 'name', direction: 'asc', skip: 0 }),
    }))
    expect(screen.queryByRole('checkbox', { name: 'Select Brake shoe kit for purchase preparation' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Brake shoe kit' })).toBeInTheDocument()
    expect(screen.getByText('1 part selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Reset to catalog order' }))
    expect(await screen.findByRole('checkbox', { name: 'Select Brake shoe kit for purchase preparation' })).toBeChecked()
    expect(screen.getByRole('heading', { name: 'Brake shoe kit' })).toBeInTheDocument()
  })

  it('does not expose Add Part to reception staff', async () => {
    authState.role = 'receptionist'
    installApi()
    renderWorkspace()
    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.queryByRole('button', { name: 'Add Part' })).not.toBeInTheDocument()
  })
})
