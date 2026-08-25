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
  default: ({ isOpen, title, onClose, onSubmit, submitLabel, children }: { isOpen: boolean; title: string; onClose: () => void; onSubmit: (event: FormEvent) => void; submitLabel: string; children: ReactNode }) => isOpen ? <div role="dialog" aria-label={title}><button type="button" onClick={onClose}>Close</button><form onSubmit={onSubmit}>{children}<button type="submit">{submitLabel}</button></form></div> : null,
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
      params: { view: 'active', sort: 'catalog', skip: 0, limit: 50, paginated: true },
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
      params: { view: 'active', sort: 'catalog', skip: 50, limit: 50, paginated: true },
    })

    await user.type(screen.getByRole('searchbox', { name: 'Search parts' }), 'brake')
    await waitFor(() => expect(apiMocks.get).toHaveBeenCalledWith('/parts-operations/parts', {
      params: { view: 'active', search: 'brake', sort: 'catalog', skip: 0, limit: 50, paginated: true },
    }))
    expect(await screen.findByText('Showing 1 of 1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Load 50 more' })).not.toBeInTheDocument()

    await user.clear(screen.getByRole('searchbox', { name: 'Search parts' }))
    await waitFor(() => expect(apiMocks.get).toHaveBeenLastCalledWith('/parts-operations/parts', {
      params: { view: 'active', sort: 'catalog', skip: 0, limit: 50, paginated: true },
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

  it('keeps archived parts out of the default request and locks their stock and purchase actions', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.queryByText('Archived part. History stays available, but stock and purchasing actions are locked.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Archived parts' }))

    expect(await screen.findByRole('heading', { name: 'Archived alternator' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Archived part')
    expect(screen.queryByRole('button', { name: 'Adjust on-hand quantity' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit available quantity' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit reorder point' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add to purchase list' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Archived alternator/ })).not.toBeInTheDocument()
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

  it('binds the selected ledger row to the service-manual action block and keeps action roles distinct', async () => {
    installApi()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    const selectedSurfaces = document.querySelectorAll('[data-selected-surface="true"]')
    expect(selectedSurfaces).toHaveLength(2)
    expect(selectedSurfaces[0]).toHaveClass('is-selected')
    expect(selectedSurfaces[1]).toHaveClass('db-parts-workbench__selected-action')
    expect(screen.getByRole('button', { name: 'Add to purchase list' })).toHaveClass('db-parts-workbench__action-primary')
    expect(screen.getByRole('button', { name: 'Adjust on-hand quantity' })).toHaveClass('db-parts-workbench__action-secondary')
    expect(screen.getByRole('button', { name: /Open Purchasing/ })).toHaveClass('db-parts-workbench__action-tertiary')
    expect(document.querySelector('.db-parts-workbench__technical-line')).toHaveTextContent('51 TRACKED / 5 NEEDS REORDER / 2 OPEN PURCHASE ORDERS')
    expect(screen.getByRole('button', { name: /Needs reorder 5/ })).toBeInTheDocument()
    expect(screen.queryByText(/BELOW MIN/)).not.toBeInTheDocument()

    const workbench = document.querySelector('.db-parts-workbench')
    const body = workbench?.querySelector('.db-parts-workbench__body')
    expect(workbench?.querySelectorAll('.db-parts-workbench__view-count')).toHaveLength(3)
    expect(body?.children).toHaveLength(2)
    expect(body?.firstElementChild).toHaveClass('db-parts-workbench__ledger-workspace')
    expect(body?.lastElementChild).toHaveClass('db-parts-workbench__inspector')
    expect(workbench?.querySelector('.db-parts-workbench__toolbar')?.parentElement).toHaveClass('db-parts-workbench__ledger-workspace')
  })

  it('owns inspector detail with four keyboard-operable sections and resets new selections to Overview', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Overview', 'Stock', 'Ordering', 'History'])
    expect(tabs.filter((tab) => tab.getAttribute('aria-selected') === 'true')).toHaveLength(1)
    expect(screen.getByRole('tabpanel', { name: 'Overview' })).toBeInTheDocument()

    tabs[0].focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Stock' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'Stock' })).toHaveTextContent('Needed for open repairs')
    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'History' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'History' })).toHaveTextContent('Recent inventory changes')

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

  it('makes supplier rows explicit actions and preserves pointer and keyboard focus modality for existing and new sources', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('tab', { name: 'Ordering' }))
    let sourceTrigger = screen.getByRole('button', { name: 'Edit Fleet Parts Co supplier source' })
    expect(sourceTrigger).toHaveTextContent('Edit source')
    expect(sourceTrigger).not.toBeDisabled()

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
    sourceTrigger = await screen.findByRole('button', { name: 'Edit Fleet Parts Co supplier source' })
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
    expect(document.querySelector('.db-parts-workbench__source-row')?.tagName).toBe('DIV')
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

  it('opens the same single stock editor from both Available entry points and steps reorder locally before saving', async () => {
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

    const availableTrigger = within(stock).getByRole('button', { name: 'Edit available quantity' })
    expect(availableTrigger).toHaveAttribute('aria-describedby', expect.stringContaining('available-edit-tooltip'))
    expect(within(stock).getByRole('tooltip', { name: 'Edit available quantity' })).toBeInTheDocument()
    expect(availableTrigger.closest('.db-parts-workbench__fact')).toHaveTextContent('Available')
    await user.click(availableTrigger)
    const availableForm = within(stock).getByRole('form', { name: 'Edit available quantity' })
    expect(within(stock).getAllByRole('form', { name: 'Edit available quantity' })).toHaveLength(1)
    expect(within(stock).getAllByRole('textbox', { name: 'On-hand quantity' })).toHaveLength(1)
    expect(within(stock).queryByRole('button', { name: 'Edit reorder point' })).not.toBeInTheDocument()
    expect(availableForm.closest('.db-parts-workbench__fact')).toHaveTextContent('Available')
    expect(availableForm.closest('.db-parts-workbench__fact')).toHaveClass('is-editing')
    expect(within(availableForm).queryByText('Cancel', { exact: true })).not.toBeInTheDocument()
    expect(within(availableForm).getByRole('button', { name: 'Save' })).toHaveTextContent('Save')
    await user.click(within(availableForm).getByRole('button', { name: 'Cancel available quantity edit' }))
    await waitFor(() => expect(within(stock).getByRole('button', { name: 'Edit available quantity' })).toHaveFocus())

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

    await user.click(screen.getByRole('tab', { name: 'Stock' }))
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
  })

  it('translates movement records into shop language without exposing raw movement or WAC terms', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    await user.click(screen.getByRole('button', { name: /Movement/ }))
    expect(await screen.findByText(/Manual stock adjustment · 2 on hand after change · Average cost \$13.25/)).toBeInTheDocument()
    expect(screen.queryByText(/manual_adjustment/)).not.toBeInTheDocument()
    expect(screen.queryByText(/\bWAC\b/)).not.toBeInTheDocument()
  })

  it('lets managers select an active non-reorder part without changing the detail row or exposing an ordinal column', async () => {
    installApi()
    apiMocks.get.mockImplementation((url: string) => {
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
      'Description',
      'Available',
      'Bin location',
      'Average cost',
      'Preferred supplier',
      'Remarks',
    ])
    for (const removedHeader of ['Needed', 'Reorder', 'Incoming']) {
      expect(screen.queryByRole('columnheader', { name: removedHeader })).not.toBeInTheDocument()
    }
    expect(screen.getAllByRole('cell', { name: 'Bin A-12' }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('columnheader', { name: /Free|Committed/i })).not.toBeInTheDocument()
    const overview = screen.getByRole('tabpanel', { name: 'Overview' })
    expect(overview).toHaveTextContent('Average cost')
    expect(overview).toHaveTextContent('Remarks')
    expect(overview).toHaveTextContent('Fleet Parts Co')
  })

  it('preselects only eligible loaded reorder rows and adds newly loaded eligible rows without implying unloaded selection', async () => {
    installApi()
    apiMocks.get.mockImplementation((url: string, config?: { params?: Record<string, unknown> }) => {
      if (url === '/parts-operations/parts' && config?.params?.attention === 'needs_reorder' && config.params.skip === 50) return Promise.resolve({ data: page([unassignedReorderPart], { total: 2, skip: 50 }) })
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

    await user.click(screen.getByRole('button', { name: 'Ledger options' }))
    await user.click(screen.getByRole('button', { name: /^Sort / }))
    await user.click(screen.getByRole('option', { name: 'Name' }))
    await waitFor(() => expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ })).toHaveLength(1))
    expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ }).every((control) => (control as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByText('1 part selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Load 50 more' }))
    await waitFor(() => expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ })).toHaveLength(2))
    expect(screen.getAllByRole('checkbox', { name: /purchase preparation/ }).every((control) => (control as HTMLInputElement).checked)).toBe(true)
    expect(screen.getByText('2 parts selected')).toBeInTheDocument()
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
    expect(toolbar?.parentElement).toHaveClass('db-parts-workbench__ledger-workspace')
    expect(screen.queryByRole('dialog', { name: 'Ledger options' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Sort' })).not.toBeInTheDocument()
    const options = screen.getByRole('button', { name: 'Ledger options' })
    expect(options).toHaveAttribute('aria-expanded', 'false')
    expect(options).toHaveAttribute('aria-controls', 'parts-ledger-options-popover')
    await user.click(options)
    expect(options).toHaveAttribute('aria-expanded', 'true')
    await user.click(screen.getByRole('button', { name: 'Compact' }))
    expect(document.querySelector('.db-parts-workbench__ledger')).toHaveClass('is-compact')
    expect(screen.queryByRole('dialog', { name: 'Ledger options' })).not.toBeInTheDocument()
    expect(options).toHaveFocus()

    await user.click(screen.getByRole('button', { name: 'Add Part' }))
    const addPartDialog = screen.getByRole('dialog', { name: 'Add Part' })
    fireEvent.submit(addPartDialog.querySelector('form')!)
    expect(screen.getByRole('alert')).toHaveTextContent('Part name is required.')
    await user.type(screen.getByRole('textbox', { name: /Part name/ }), 'Air dryer cartridge')
    await user.type(screen.getByRole('textbox', { name: /SKU/ }), 'AIR-DRY-01')
    fireEvent.submit(addPartDialog.querySelector('form')!)
    await waitFor(() => expect(apiMocks.post).toHaveBeenCalledWith('/inventory', expect.objectContaining({
      name: 'Air dryer cartridge', sku: 'AIR-DRY-01', stock_quantity: 0, reorder_level: 0, cost: 0, selling_price: 0, unit_type: 'each',
    })))
  })

  it('keeps eligible selections through every sort and owns sort dismissal and keyboard focus', async () => {
    installApi()
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Alternator' })
    const checkbox = screen.getByRole('checkbox', { name: 'Select Alternator for purchase preparation' })
    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    const options = screen.getByRole('button', { name: 'Ledger options' })
    for (const sortName of ['Name', 'Available', 'Reorder urgency', 'Catalog order']) {
      await user.click(options)
      const sortTrigger = screen.getByRole('button', { name: /^Sort / })
      await user.click(sortTrigger)
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
      await user.click(screen.getByRole('option', { name: sortName }))
      await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Select Alternator for purchase preparation' })).toBeChecked())
      expect(screen.getByText('1 part selected')).toBeInTheDocument()
      expect(screen.queryByRole('dialog', { name: 'Ledger options' })).not.toBeInTheDocument()
      expect(options).toHaveFocus()
    }

    await user.click(options)
    const sortTrigger = screen.getByRole('button', { name: /^Sort / })
    sortTrigger.focus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('listbox', { name: 'Sort' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Catalog order' })).toHaveFocus()
    await user.keyboard('{End}')
    expect(screen.getByRole('option', { name: 'Reorder urgency' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Ledger options' })).not.toBeInTheDocument()
    expect(options).toHaveFocus()

    await user.click(options)
    expect(screen.getByRole('dialog', { name: 'Ledger options' })).toBeInTheDocument()
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('dialog', { name: 'Ledger options' })).not.toBeInTheDocument()
  })

  it('does not expose Add Part to reception staff', async () => {
    authState.role = 'receptionist'
    installApi()
    renderWorkspace()
    await screen.findByRole('heading', { name: 'Alternator' })
    expect(screen.queryByRole('button', { name: 'Add Part' })).not.toBeInTheDocument()
  })
})
