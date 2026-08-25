/* eslint-disable react-refresh/only-export-components -- Session-scoped purchase preparation is shared with Purchasing. */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Archive, ArrowDown, ArrowRight, ArrowUp, Boxes, ChevronsUpDown, History, MapPin, Package, Pencil, Plus, Search, ShoppingCart, X } from 'lucide-react'

import api from '@/lib/api'
import useTenantBranding from '@/hooks/useTenantBranding'
import { useAuthStore } from '@/stores/authStore'
import SlidePanelForm from '@/components/SlidePanelForm'
import QuantityStepper from '@/components/QuantityStepper'

type Page<T> = { items: T[]; total: number; skip: number; limit: number; has_more: boolean }
type Summary = { needs_reorder_count?: number; low_stock_count?: number; open_purchase_order_count: number }
type WorkspaceView = 'parts' | 'reorder' | 'movement'
type CatalogView = 'active' | 'archived'
type PartSort = 'catalog' | 'name' | 'available' | 'location' | 'cost' | 'reorder'
type SortDirection = 'asc' | 'desc'
type StockFilter = 'all' | 'below_min' | 'out_of_stock'
type LedgerDensity = 'comfortable' | 'compact'
type InspectorView = 'overview' | 'stock' | 'ordering' | 'history'

const FIRST_SORT_DIRECTION: Record<PartSort, SortDirection> = {
  catalog: 'asc',
  name: 'asc',
  available: 'asc',
  location: 'asc',
  cost: 'desc',
  reorder: 'desc',
}

const COMPACT_SORT_OPTIONS: Array<{ sort: Exclude<PartSort, 'catalog'>; direction: SortDirection; label: string }> = [
  { sort: 'name', direction: 'asc', label: 'Part name A–Z' },
  { sort: 'name', direction: 'desc', label: 'Part name Z–A' },
  { sort: 'available', direction: 'asc', label: 'Available low to high' },
  { sort: 'available', direction: 'desc', label: 'Available high to low' },
  { sort: 'location', direction: 'asc', label: 'Bin location A–Z' },
  { sort: 'location', direction: 'desc', label: 'Bin location Z–A' },
  { sort: 'cost', direction: 'desc', label: 'Average cost high to low' },
  { sort: 'cost', direction: 'asc', label: 'Average cost low to high' },
  { sort: 'reorder', direction: 'desc', label: 'Reorder urgency high to low' },
  { sort: 'reorder', direction: 'asc', label: 'Reorder urgency low to high' },
]

const INSPECTOR_VIEWS: Array<{ id: InspectorView; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'stock', label: 'Stock' },
  { id: 'ordering', label: 'Ordering' },
  { id: 'history', label: 'History' },
]

export type SupplierSource = {
  source_id: string
  supplier_id: string
  supplier_name: string | null
  supplier_part_number: string | null
  is_preferred: boolean
  minimum_order_quantity: number
  pack_quantity: number
  last_unit_cost: string | null
  lead_time_days: number | null
  is_active: boolean
  updated_at: string | null
}

export type PartRecord = {
  id: string
  sku: string
  name: string
  description: string | null
  image_url: string | null
  unit_type: string | null
  location: string | null
  available_packages: number
  needed_for_open_repairs: number
  reorder_level: number
  incoming_packages: number
  recommended_order_packages: number
  average_unit_cost: string
  is_archived: boolean
  is_placeholder: boolean
  preferred_source: SupplierSource | null
  supplier_sources: SupplierSource[]
  repair_sources: Array<{
    repair_order_id: string
    order_number: string
    vehicle_display: string
    unit_number: string | null
    packages: number
  }>
  incoming_sources: Array<{
    purchase_order_id: string
    po_number: string
    packages: number
    expected_at: string | null
  }>
}

type PartDetail = PartRecord & {
  recent_receipts: Array<{ receipt_id: string; receipt_number: string; purchase_order_id: string; po_number: string; quantity: number; unit_cost: string; received_at: string }>
  recent_movements: Array<{ id: string; movement_type: string; quantity_delta: number; balance_after: number; wac_after: string | null; occurred_at: string }>
}

type Movement = {
  id: string
  inventory: { id: string; sku: string; name: string } | null
  movement_type: string
  quantity_delta: number
  balance_after: number
  wac_after: string | null
  source: { type: string; id: string; order_number?: string; receipt_number?: string; return_number?: string } | null
  occurred_at: string
}

type SupplierOption = { id: string; name: string }

type SupplierPurchasing = {
  id: string
  name: string
  payment_terms: string | null
  default_lead_time_days: number | null
  minimum_order_amount: string | null
  purchasing_notes: string | null
  active_part_source_count: number
  open_purchase_order_count: number
  open_purchase_order_value: string
  last_receipt_at: string | null
  on_time_order_count: number
  timed_order_count: number
  on_time_rate: string | null
}

export type PurchasePreparationLine = {
  inventoryId: string
  name: string
  sku: string
  sourceId: string | null
  supplierId: string | null
  supplierName: string | null
  supplierPartNumber: string | null
  quantity: number
  unitCost: string
  minimumOrderQuantity: number
  packQuantity: number
  blockedReason: 'supplier_source_required' | null
}

export const PURCHASE_PREPARATION_KEY = 'dieselbridge:db038:purchase-preparation:v1'

export function purchasePreparationStorageKey() {
  const user = useAuthStore.getState().user
  return `${PURCHASE_PREPARATION_KEY}:${user?.tenant_id || 'no-tenant'}:${user?.id || 'no-user'}`
}

export function readPurchasePreparation(): PurchasePreparationLine[] {
  if (typeof window === 'undefined') return []
  try {
    const value = JSON.parse(window.sessionStorage.getItem(purchasePreparationStorageKey()) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export function writePurchasePreparation(lines: PurchasePreparationLine[]) {
  window.sessionStorage.setItem(purchasePreparationStorageKey(), JSON.stringify(lines))
  window.dispatchEvent(new Event('db038:purchase-preparation'))
}

function canManage(role: string | undefined) {
  return role === 'garage_owner' || role === 'garage_admin'
}

function errorMessage(error: unknown) {
  const candidate = error as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  if (candidate.response?.status === 409) return 'This part changed elsewhere. Refresh the details and try again.'
  const detail = candidate.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => (item as { msg?: string }).msg).filter(Boolean).join(' ')
  return candidate.message || 'The change could not be completed.'
}

function movementLabel(value: string) {
  const labels: Record<string, string> = {
    migration_opening_balance: 'Starting inventory',
    legacy_inventory_opening: 'Starting inventory',
    manual_adjustment: 'Manual stock adjustment',
    legacy_direct_receipt: 'Stock received',
    repair_reservation: 'Reserved for a repair',
    repair_release: 'Returned from a repair',
    po_receipt: 'Purchase order received',
    core_recovery: 'Core recovered',
    vendor_return: 'Returned to supplier',
    core_return: 'Core returned to supplier',
    vendor_return_reversal: 'Supplier return reversed',
    core_return_reversal: 'Core return reversed',
  }
  return labels[value] || value.split('_').join(' ')
}

function formatDate(value: string | null) {
  if (!value) return 'Date not set'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value))
}

function roundOrderQuantity(part: PartRecord, source: SupplierSource) {
  const minimum = Math.max(1, part.recommended_order_packages, source.minimum_order_quantity)
  const packQuantity = Math.max(1, source.pack_quantity)
  return Math.ceil(minimum / packQuantity) * packQuantity
}

function partRemark(part: PartRecord) {
  if (part.is_archived) return 'Archived'
  if (part.is_placeholder) return 'Placeholder'
  if (part.available_packages < part.needed_for_open_repairs) return `Short ${part.needed_for_open_repairs - part.available_packages}`
  if (!part.preferred_source && part.recommended_order_packages > 0) return 'Supplier needed'
  if (part.available_packages <= part.reorder_level) return 'Needs reorder'
  if (part.incoming_packages > 0) return 'Incoming'
  return '—'
}

function isManuallySelectable(part: PartRecord) {
  return !part.is_archived && !part.is_placeholder
}

function isReorderEligible(part: PartRecord) {
  return isManuallySelectable(part) && part.recommended_order_packages > 0
}

function toPreparationLine(part: PartRecord): PurchasePreparationLine {
  const source = part.preferred_source
  return {
    inventoryId: part.id,
    name: part.name,
    sku: part.sku,
    sourceId: source?.source_id || null,
    supplierId: source?.supplier_id || null,
    supplierName: source?.supplier_name || null,
    supplierPartNumber: source?.supplier_part_number || null,
    quantity: source ? roundOrderQuantity(part, source) : Math.max(1, part.recommended_order_packages),
    unitCost: source?.last_unit_cost || part.average_unit_cost,
    minimumOrderQuantity: source?.minimum_order_quantity || 1,
    packQuantity: source?.pack_quantity || 1,
    blockedReason: source ? null : 'supplier_source_required',
  }
}

function PartPhoto({ part, logoUrl, companyName, detail = false }: { part: Pick<PartRecord, 'name' | 'image_url'>; logoUrl: string | null; companyName: string | null; detail?: boolean }) {
  const [source, setSource] = useState<'part' | 'company' | 'icon'>(() => part.image_url ? 'part' : logoUrl ? 'company' : 'icon')
  const src = source === 'part' ? part.image_url : source === 'company' ? logoUrl : null
  const fail = () => setSource((current) => current === 'part' && logoUrl && logoUrl !== part.image_url ? 'company' : 'icon')
  if (!src || source === 'icon') return <span className={`db-parts-workbench__photo ${detail ? 'is-detail' : ''}`} role={detail ? 'img' : undefined} aria-label={detail ? `No image available for ${part.name}` : undefined} aria-hidden={detail ? undefined : 'true'}><Package aria-hidden="true" /></span>
  return <span className={`db-parts-workbench__photo ${detail ? 'is-detail' : ''} ${source === 'company' ? 'is-company' : ''}`} aria-hidden={detail ? undefined : 'true'}><img src={src} alt={detail ? source === 'part' ? `${part.name} part photo` : `${companyName || 'Shop'} logo placeholder for ${part.name}` : ''} onError={fail} loading={detail ? 'eager' : 'lazy'} /></span>
}

export function PartsInventoryGate({ legacy }: { legacy: ReactNode }) {
  const role = useAuthStore((state) => state.user?.role)
  const mayRead = role === 'garage_owner' || role === 'garage_admin' || role === 'receptionist'
  const availability = useQuery<Summary>({
    queryKey: ['parts-operations', 'summary'],
    queryFn: async () => (await api.get('/parts-operations/summary')).data,
    enabled: mayRead,
    retry: false,
    staleTime: 60_000,
  })
  if (!mayRead) return <>{legacy}</>
  if (availability.isPending) return <div className="db-parts-workbench__gate" role="status">Opening Parts & inventory…</div>
  if (availability.isError) {
    const status = (availability.error as { response?: { status?: number } }).response?.status
    if (status === 403 || status === 404) return <>{legacy}</>
    return <div className="db-parts-workbench__gate" role="alert">Parts & inventory is temporarily unavailable. Refresh to use the existing catalog.</div>
  }
  return <PartsInventoryWorkspace summary={availability.data} />
}

export default function PartsInventoryWorkspace({ summary }: { summary: Summary }) {
  const role = useAuthStore((state) => state.user?.role)
  const manage = canManage(role)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: branding } = useTenantBranding()
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>('parts')
  const [catalogView, setCatalogView] = useState<CatalogView>('active')
  const [sort, setSort] = useState<PartSort>('catalog')
  const [direction, setDirection] = useState<SortDirection>('asc')
  const [stockFilter, setStockFilter] = useState<StockFilter>('all')
  const [density, setDensity] = useState<LedgerDensity>('comfortable')
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [partsSequence, setPartsSequence] = useState(0)
  const [movementSkip, setMovementSkip] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checkedParts, setCheckedParts] = useState<Map<string, PartRecord>>(() => new Map())
  const [allPartsCount, setAllPartsCount] = useState<number | null>(null)
  const [addPartOpen, setAddPartOpen] = useState(false)
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)
  const [compactSortOpen, setCompactSortOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const compactSortMenu = useRef<HTMLDivElement>(null)
  const compactSortTrigger = useRef<HTMLButtonElement>(null)
  const compactCatalogReset = useRef<HTMLButtonElement>(null)
  const compactSortRefs = useRef<Array<HTMLButtonElement | null>>([])
  const headerSortFocus = useRef<Exclude<PartSort, 'catalog'> | null>(null)
  const selectionMembership = useRef('')
  const reorderPreselection = useRef<{ context: string; pages: Set<string> }>({ context: '', pages: new Set() })

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const nextSearch = search.trim()
      if (debouncedSearch !== nextSearch) {
        setDebouncedSearch(nextSearch)
        setPartsSequence((current) => current + 1)
        setCheckedParts(new Map())
      }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [debouncedSearch, search])

  const partParams = useMemo(() => ({
    view: catalogView,
    ...(workspaceView === 'reorder' || stockFilter === 'below_min' ? { attention: 'needs_reorder' } : {}),
    ...(workspaceView !== 'reorder' && stockFilter === 'out_of_stock' ? { attention: 'out_of_stock' } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    sort,
    direction,
    limit: 50,
    paginated: true,
  }), [catalogView, debouncedSearch, direction, sort, stockFilter, workspaceView])

  const partsQuery = useInfiniteQuery({
    queryKey: ['parts-operations', 'parts', partParams, partsSequence],
    queryFn: async ({ pageParam }): Promise<Page<PartRecord>> => (await api.get('/parts-operations/parts', { params: { ...partParams, skip: pageParam } })).data,
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.skip + lastPage.limit : undefined,
    enabled: workspaceView !== 'movement',
    retry: false,
  })
  const movementQuery = useQuery<Page<Movement>>({
    queryKey: ['parts-operations', 'movement', 'page', movementSkip],
    queryFn: async () => (await api.get('/parts-operations/activity', { params: { paginated: true, skip: movementSkip, limit: 50 } })).data,
    enabled: workspaceView === 'movement',
    retry: false,
  })
  const movementCountQuery = useQuery<Page<Movement>>({
    queryKey: ['parts-operations', 'movement', 'count'],
    queryFn: async () => (await api.get('/parts-operations/activity', { params: { paginated: true, skip: 0, limit: 1 } })).data,
    retry: false,
    staleTime: 60_000,
  })
  const detailQuery = useQuery<PartDetail>({
    queryKey: ['parts-operations', 'part', selectedId],
    queryFn: async () => (await api.get(`/parts-operations/parts/${selectedId}`)).data,
    enabled: workspaceView !== 'movement' && Boolean(selectedId),
    retry: false,
  })
  const parts = useMemo(() => {
    const byId = new Map<string, PartRecord>()
    partsQuery.data?.pages.forEach((page) => page.items.forEach((part) => byId.set(part.id, part)))
    return Array.from(byId.values())
  }, [partsQuery.data?.pages])
  const firstPartsPage = partsQuery.data?.pages[0]
  const partsPage = useMemo<Page<PartRecord> | undefined>(() => firstPartsPage ? {
    items: parts,
    total: firstPartsPage.total,
    skip: 0,
    limit: firstPartsPage.limit,
    has_more: Boolean(partsQuery.hasNextPage),
  } : undefined, [firstPartsPage, parts, partsQuery.hasNextPage])
  const preselectionContext = `${workspaceView}:${catalogView}:${stockFilter}:${debouncedSearch}`

  useEffect(() => {
    if (workspaceView === 'parts' && catalogView === 'active' && stockFilter === 'all' && !debouncedSearch && firstPartsPage) {
      setAllPartsCount(firstPartsPage.total)
    }
  }, [catalogView, debouncedSearch, firstPartsPage, stockFilter, workspaceView])

  useEffect(() => {
    if (workspaceView === 'movement' || !firstPartsPage) return
    const membershipChanged = selectionMembership.current !== preselectionContext
    if (!selectionMembership.current || membershipChanged) {
      selectionMembership.current = preselectionContext
      if (!parts.length) { setSelectedId(null); return }
      if (!selectedId || !parts.some((part) => part.id === selectedId)) setSelectedId(parts[0].id)
      return
    }
    if (!selectedId && parts.length) setSelectedId(parts[0].id)
  }, [firstPartsPage, parts, preselectionContext, selectedId, workspaceView])

  useEffect(() => {
    if (workspaceView !== 'reorder' || !partsQuery.data) return
    if (reorderPreselection.current.context !== preselectionContext) {
      reorderPreselection.current = { context: preselectionContext, pages: new Set() }
      setCheckedParts(new Map())
    }
    const unseenPages = partsQuery.data.pages.filter((page) => !reorderPreselection.current.pages.has(`${sort}:${direction}:${page.skip}`))
    if (!unseenPages.length) return
    unseenPages.forEach((page) => reorderPreselection.current.pages.add(`${sort}:${direction}:${page.skip}`))
    setCheckedParts((current) => {
      const next = new Map(current)
      unseenPages.forEach((page) => page.items.filter(isReorderEligible).forEach((part) => next.set(part.id, part)))
      return next
    })
  }, [direction, partsQuery.data, preselectionContext, sort, workspaceView])

  useEffect(() => {
    if (!compactSortOpen) return
    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (compactSortMenu.current?.contains(event.target as Node)) return
      setCompactSortOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsidePointer)
    return () => document.removeEventListener('pointerdown', closeOnOutsidePointer)
  }, [compactSortOpen])

  useLayoutEffect(() => {
    if (!compactSortOpen) return
    compactCatalogReset.current?.focus({ preventScroll: true })
  }, [compactSortOpen])

  useLayoutEffect(() => {
    if (!headerSortFocus.current || partsQuery.isLoading) return
    const field = headerSortFocus.current
    const control = document.querySelector<HTMLButtonElement>(`[data-parts-sort-field='${field}']`)
    control?.focus({ preventScroll: true })
    headerSortFocus.current = null
  }, [partsQuery.data, partsQuery.isLoading])

  const closeCompactSort = (restoreFocus: boolean) => {
    setCompactSortOpen(false)
    if (restoreFocus) compactSortTrigger.current?.focus({ preventScroll: true })
  }

  const chooseSort = (nextSort: PartSort, nextDirection: SortDirection, closeMenu = false) => {
    if (nextSort !== sort || nextDirection !== direction) {
      setSort(nextSort)
      setDirection(nextDirection)
      setPartsSequence((current) => current + 1)
    }
    if (closeMenu) closeCompactSort(true)
  }

  const toggleHeaderSort = (nextSort: Exclude<PartSort, 'catalog'>) => {
    const nextDirection = sort === nextSort ? direction === 'asc' ? 'desc' : 'asc' : FIRST_SORT_DIRECTION[nextSort]
    headerSortFocus.current = nextSort
    chooseSort(nextSort, nextDirection)
  }

  const chooseDensity = (nextDensity: LedgerDensity) => {
    setDensity(nextDensity)
  }

  const moveCompactSortFocus = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (index + 1) % COMPACT_SORT_OPTIONS.length
    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (index - 1 + COMPACT_SORT_OPTIONS.length) % COMPACT_SORT_OPTIONS.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = COMPACT_SORT_OPTIONS.length - 1
    if (nextIndex === null) return
    event.preventDefault()
    compactSortRefs.current[nextIndex]?.focus()
  }

  const selectView = (view: WorkspaceView) => {
    setWorkspaceView(view)
    setPartsSequence((current) => current + 1)
    setMovementSkip(0)
    setMobileDetailOpen(false)
    setCheckedParts(new Map())
    reorderPreselection.current = { context: '', pages: new Set() }
    if (view === 'reorder') {
      setCatalogView('active')
      setStockFilter('all')
    }
  }

  const toggleChecked = (part: PartRecord, checked: boolean) => {
    setCheckedParts((current) => {
      const next = new Map(current)
      if (checked && isManuallySelectable(part)) next.set(part.id, part)
      else next.delete(part.id)
      return next
    })
  }

  const prepareParts = (selected: PartRecord[], openPurchasing = false) => {
    const eligible = selected.filter(isManuallySelectable)
    if (!eligible.length) { setError('Select at least one active catalog part.'); return }
    const byInventory = new Map(readPurchasePreparation().map((line) => [line.inventoryId, line]))
    eligible.forEach((part) => byInventory.set(part.id, toPreparationLine(part)))
    writePurchasePreparation(Array.from(byInventory.values()))
    const blocked = eligible.filter((part) => !part.preferred_source).length
    setNotice(`${eligible.length} ${eligible.length === 1 ? 'part' : 'parts'} added to purchase preparation${blocked ? ` · ${blocked} still ${blocked === 1 ? 'needs' : 'need'} a supplier source` : ''}.`)
    if (openPurchasing) navigate('/dashboard/garage/purchasing?view=orders')
  }

  const addToPreparation = (part: PartRecord) => prepareParts([part])

  const prepareChecked = () => prepareParts(Array.from(checkedParts.values()), true)

  const clearChecked = () => setCheckedParts(new Map())

  const needsReorderCount = workspaceView === 'reorder' && firstPartsPage
    ? firstPartsPage.total
    : summary.needs_reorder_count ?? summary.low_stock_count ?? 0
  const movementCount = movementCountQuery.data?.total ?? null

  const updatePart = async (part: PartDetail, patch: Record<string, unknown>) => {
    setError(null)
    try {
      await api.put(`/inventory/${part.id}`, patch)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'parts'] }),
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'part', part.id] }),
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'movement'] }),
      ])
      setNotice(`${part.name} stock setting saved.`)
    } catch (cause) {
      setError(errorMessage(cause))
      throw cause
    }
  }

  return <section className="db-parts-workbench" aria-labelledby="parts-workbench-title">
    <header className="db-parts-workbench__header">
      <div><h1 id="parts-workbench-title">Parts</h1><p className="db-parts-workbench__technical-line">{allPartsCount ?? firstPartsPage?.total ?? '—'} TRACKED / <em>{needsReorderCount} NEEDS REORDER</em> / {summary.open_purchase_order_count} OPEN PURCHASE ORDERS</p></div>
      <div className="db-parts-workbench__summary" aria-label="Parts summary">
        {manage && <button className="db-parts-workbench__add-part" type="button" onClick={() => setAddPartOpen(true)}><Plus aria-hidden="true" />Add Part</button>}
      </div>
    </header>

    <nav className="db-parts-workbench__views" aria-label="Parts and inventory views">
      <button type="button" aria-current={workspaceView === 'parts' ? 'page' : undefined} onClick={() => selectView('parts')}><Boxes aria-hidden="true" />All parts <span className="db-parts-workbench__view-count">{allPartsCount ?? '—'}</span></button>
      <button type="button" aria-current={workspaceView === 'reorder' ? 'page' : undefined} onClick={() => selectView('reorder')}><ShoppingCart aria-hidden="true" />Needs reorder <span className="db-parts-workbench__view-count">{needsReorderCount}</span></button>
      <button type="button" aria-current={workspaceView === 'movement' ? 'page' : undefined} onClick={() => selectView('movement')}><History aria-hidden="true" />Movement <span className="db-parts-workbench__view-count">{movementCount ?? '—'}</span></button>
    </nav>

    {notice && <div className="db-parts-workbench__notice" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice(null)}>Dismiss</button></div>}
    {error && <div className="db-parts-workbench__error" role="alert"><span>{error}</span><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}

    {workspaceView === 'movement'
      ? <MovementLedger page={movementQuery.data} loading={movementQuery.isLoading} failed={movementQuery.isError} onRetry={() => void movementQuery.refetch()} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} onPage={setMovementSkip} />
      : <div className={`db-parts-workbench__body is-${density}${mobileDetailOpen ? ' is-mobile-detail' : ''}`}>
        <div className="db-parts-workbench__ledger-workspace">
          <div className="db-parts-workbench__toolbar">
            <label className="db-parts-workbench__search"><Search aria-hidden="true" /><span className="sr-only">Search parts</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search part, SKU, supplier, source number, or bin" /></label>
            <div className="db-parts-workbench__filters" role="group" aria-label="Stock filter">
              <button type="button" aria-pressed={stockFilter === 'all'} onClick={() => { setStockFilter('all'); setPartsSequence((current) => current + 1); setCheckedParts(new Map()) }}>All</button>
              <button type="button" aria-pressed={stockFilter === 'below_min'} onClick={() => { setStockFilter('below_min'); setPartsSequence((current) => current + 1); setCheckedParts(new Map()) }}>Needs reorder</button>
              <button type="button" aria-pressed={stockFilter === 'out_of_stock'} onClick={() => { setStockFilter('out_of_stock'); setPartsSequence((current) => current + 1); setCheckedParts(new Map()) }}>Out of stock</button>
            </div>
            <button className="db-parts-workbench__archive-link" type="button" onClick={() => { setCatalogView(catalogView === 'active' ? 'archived' : 'active'); setPartsSequence((current) => current + 1); setCheckedParts(new Map()) }} disabled={workspaceView === 'reorder'}><Archive aria-hidden="true" />{catalogView === 'active' ? 'Archived parts' : 'Back to active parts'}</button>
            <div className="db-parts-workbench__density" role="group" aria-label="Ledger density">
              <button type="button" aria-pressed={density === 'comfortable'} onClick={() => chooseDensity('comfortable')}>Comfortable</button>
              <button type="button" aria-pressed={density === 'compact'} onClick={() => chooseDensity('compact')}>Compact</button>
            </div>
            {sort !== 'catalog' && <button className="db-parts-workbench__catalog-reset is-desktop" type="button" aria-label="Reset to catalog order" onClick={() => chooseSort('catalog', 'asc')}>Catalog order</button>}
            <div ref={compactSortMenu} className="db-parts-workbench__compact-sort-menu" onKeyDown={(event) => {
              if (event.key !== 'Escape' || !compactSortOpen) return
              event.preventDefault()
              event.stopPropagation()
              closeCompactSort(true)
            }}>
              <button ref={compactSortTrigger} type="button" aria-label="Sort parts" aria-expanded={compactSortOpen} aria-controls="parts-compact-sort-popover" onClick={() => {
                setCompactSortOpen((current) => !current)
              }}><ChevronsUpDown aria-hidden="true" /><span>Sort</span></button>
              {compactSortOpen && <div id="parts-compact-sort-popover" className="db-parts-workbench__compact-sort-popover" role="dialog" aria-label="Sort parts">
                <div className="db-parts-workbench__compact-sort-row">
                  <span id="parts-ledger-sort-label">Sort</span>
                  <div className="db-parts-workbench__sort-controls">
                    <button ref={compactCatalogReset} className="db-parts-workbench__catalog-reset" type="button" aria-pressed={sort === 'catalog'} onClick={() => chooseSort('catalog', 'asc', true)}>Catalog order</button>
                    <div className="db-parts-workbench__compact-sort" role="radiogroup" aria-labelledby="parts-ledger-sort-label">
                      {COMPACT_SORT_OPTIONS.map((option, index) => {
                        const selected = sort === option.sort && direction === option.direction
                        const hasSelectedCompactSort = COMPACT_SORT_OPTIONS.some((candidate) => sort === candidate.sort && direction === candidate.direction)
                        return <button key={`${option.sort}-${option.direction}`} ref={(node) => { compactSortRefs.current[index] = node }} type="button" role="radio" aria-checked={selected} tabIndex={selected || !hasSelectedCompactSort && index === 0 ? 0 : -1} onKeyDown={(event) => moveCompactSortFocus(event, index)} onClick={() => chooseSort(option.sort, option.direction, true)}>{option.label}</button>
                      })}
                    </div>
                  </div>
                </div>
              </div>}
            </div>
          </div>
          {manage && checkedParts.size > 0 && <div className="db-parts-workbench__bulk" role="region" aria-label="Selected parts actions">
            <strong>{checkedParts.size} {checkedParts.size === 1 ? 'part' : 'parts'} selected</strong>
            <div><button type="button" onClick={clearChecked}>Clear selection</button><button type="button" onClick={prepareChecked}>Add to purchase list<ArrowRight aria-hidden="true" /></button></div>
          </div>}
          <PartLedger page={partsPage} loading={partsQuery.isLoading} loadingMore={partsQuery.isFetchingNextPage} failed={partsQuery.isError && !partsQuery.data} manage={manage} selectedId={selectedId} checkedIds={new Set(checkedParts.keys())} density={density} sort={sort} direction={direction} logoUrl={branding?.logo_url || null} companyName={branding?.name || null} onSort={toggleHeaderSort} onCheck={toggleChecked} onSelect={(id) => { setSelectedId(id); setMobileDetailOpen(true) }} onRetry={() => void partsQuery.refetch()} onLoadMore={() => void partsQuery.fetchNextPage()} />
        </div>
        <PartInspector part={detailQuery.data} loading={detailQuery.isLoading} failed={detailQuery.isError} manage={manage} logoUrl={branding?.logo_url || null} companyName={branding?.name || null} onBack={() => setMobileDetailOpen(false)} onRetry={() => void detailQuery.refetch()} onAdjust={updatePart} onPrepare={addToPreparation} onPurchasing={() => navigate('/dashboard/garage/purchasing')} onOpenPurchaseOrder={(id) => navigate(`/dashboard/garage/purchasing?view=orders&purchase_order=${encodeURIComponent(id)}`)} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} />
      </div>}
    {addPartOpen && <AddPartDrawer isOpen onClose={() => setAddPartOpen(false)} onCreated={async (partName) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'parts'] }),
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'summary'] }),
      ])
      setNotice(`${partName} added to the parts catalog.`)
      setAddPartOpen(false)
    }} />}
  </section>
}

function SortableColumnHeader({ label, columnClass, field, sort, direction, onSort }: { label: string; columnClass: string; field: Exclude<PartSort, 'catalog'>; sort: PartSort; direction: SortDirection; onSort: (field: Exclude<PartSort, 'catalog'>) => void }) {
  const active = sort === field
  const nextDirection = active ? direction === 'asc' ? 'desc' : 'asc' : FIRST_SORT_DIRECTION[field]
  return <span className={`${columnClass} is-sortable`} role="columnheader" aria-sort={active ? direction === 'asc' ? 'ascending' : 'descending' : undefined}>
    <button type="button" data-parts-sort-field={field} aria-label={`${label}: sort ${nextDirection === 'asc' ? 'ascending' : 'descending'}`} onClick={() => onSort(field)}>
      <span>{label}</span>
      {active ? direction === 'asc' ? <ArrowUp aria-hidden="true" /> : <ArrowDown aria-hidden="true" /> : <ChevronsUpDown aria-hidden="true" />}
    </button>
  </span>
}

function PartLedger({ page, loading, loadingMore, failed, manage, selectedId, checkedIds, density, sort, direction, logoUrl, companyName, onSort, onCheck, onSelect, onRetry, onLoadMore }: { page?: Page<PartRecord>; loading: boolean; loadingMore: boolean; failed: boolean; manage: boolean; selectedId: string | null; checkedIds: Set<string>; density: LedgerDensity; sort: PartSort; direction: SortDirection; logoUrl: string | null; companyName: string | null; onSort: (field: Exclude<PartSort, 'catalog'>) => void; onCheck: (part: PartRecord, checked: boolean) => void; onSelect: (id: string) => void; onRetry: () => void; onLoadMore: () => void }) {
  if (loading) return <div className="db-parts-workbench__state" role="status">Loading parts…</div>
  if (failed) return <div className="db-parts-workbench__state" role="alert">Parts could not be loaded.<button type="button" onClick={onRetry}>Retry</button></div>
  if (!page?.items.length) return <div className="db-parts-workbench__state"><strong>No parts match this view.</strong><span>Change the search or catalog filter to see more.</span></div>
  return <div className={`db-parts-workbench__ledger is-${density}${manage ? '' : ' is-read-only'}`} role="table" aria-label={`${page.total} matching parts`}>
    <div className="db-parts-workbench__table-head" role="row">
      {manage && <span role="columnheader" aria-label="Select part" />}
      <SortableColumnHeader label="Part / Description" columnClass="is-description" field="name" sort={sort} direction={direction} onSort={onSort} />
      <SortableColumnHeader label="Available" columnClass="is-available" field="available" sort={sort} direction={direction} onSort={onSort} />
      <SortableColumnHeader label="Bin location" columnClass="is-bin" field="location" sort={sort} direction={direction} onSort={onSort} />
      <SortableColumnHeader label="Average cost" columnClass="is-cost" field="cost" sort={sort} direction={direction} onSort={onSort} />
      <span className="is-supplier" role="columnheader">Preferred supplier</span>
      <SortableColumnHeader label="Remarks / Status" columnClass="is-remarks" field="reorder" sort={sort} direction={direction} onSort={onSort} />
    </div>
    <div className="db-parts-workbench__rows" role="rowgroup">
      {page.items.map((part) => {
        const eligible = isManuallySelectable(part)
        const selected = selectedId === part.id
        const remark = partRemark(part)
        return <div key={part.id} role="row" className={`db-parts-workbench__row${selected ? ' is-selected' : ''}${!eligible ? ' is-ineligible' : ''}`} data-selected-surface={selected ? 'true' : undefined}>
          {manage && <span role="cell" className="db-parts-workbench__check" onClick={(event) => event.stopPropagation()}>{eligible && <input type="checkbox" aria-label={`Select ${part.name} for purchase preparation`} checked={checkedIds.has(part.id)} onClick={(event) => event.stopPropagation()} onChange={(event) => onCheck(part, event.target.checked)} />}</span>}
          <button role="cell" type="button" className="db-parts-workbench__row-select" aria-current={selected ? 'true' : undefined} onClick={() => onSelect(part.id)}>
            <span className="db-parts-workbench__identity"><PartPhoto part={part} logoUrl={logoUrl} companyName={companyName} /><span><strong>{part.name}</strong><small>{part.sku}</small></span></span>
          </button>
          <strong role="cell" data-label="Available" className="is-available">{part.available_packages}</strong>
          <span role="cell" data-label="Bin location" className="is-bin">{part.location ? `Bin ${part.location}` : 'Bin not set'}</span>
          <strong role="cell" data-label="Average cost" className="is-cost">${Number(part.average_unit_cost || 0).toFixed(2)}</strong>
          <span role="cell" data-label="Preferred supplier" className={`is-supplier${!part.preferred_source ? ' is-unassigned' : ''}`}>{part.preferred_source?.supplier_name || 'Unassigned'}</span>
          <span role="cell" data-label="Remarks" className={`db-parts-workbench__remark is-remarks${remark === '—' ? ' is-empty' : ''}`}>{remark !== '—' && <i aria-hidden="true" />}{remark}</span>
        </div>
      })}
    </div>
    <div className="db-parts-workbench__load-more"><span aria-live="polite">Showing {page.items.length} of {page.total}</span>{page.has_more && <button type="button" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? 'Loading 50 more…' : 'Load 50 more'}</button>}</div>
  </div>
}

function Pager({ page, onPage }: { page: Page<unknown>; onPage: (skip: number) => void }) {
  return <div className="db-parts-workbench__pager"><span>{page.total ? `${page.skip + 1}–${Math.min(page.skip + page.items.length, page.total)} of ${page.total}` : '0 results'}</span><div><button type="button" disabled={page.skip === 0} onClick={() => onPage(Math.max(0, page.skip - page.limit))}>Previous</button><button type="button" disabled={!page.has_more} onClick={() => onPage(page.skip + page.limit)}>Next</button></div></div>
}

type AddPartForm = {
  name: string
  sku: string
  description: string
  category: string
  location: string
  stockQuantity: string
  reorderLevel: string
  cost: string
  sellingPrice: string
  unitType: string
  supplierName: string
  supplierContact: string
}

const EMPTY_ADD_PART: AddPartForm = {
  name: '', sku: '', description: '', category: '', location: '', stockQuantity: '0', reorderLevel: '0', cost: '0.00', sellingPrice: '0.00', unitType: 'each', supplierName: '', supplierContact: '',
}

function AddPartDrawer({ isOpen, onClose, onCreated }: { isOpen: boolean; onClose: () => void; onCreated: (partName: string) => Promise<void> }) {
  const [form, setForm] = useState<AddPartForm>(EMPTY_ADD_PART)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const update = (field: keyof AddPartForm, value: string) => { setForm((current) => ({ ...current, [field]: value })); setFormError(null) }
  const close = () => { if (saving) return; setForm(EMPTY_ADD_PART); setFormError(null); onClose() }
  const submit = async () => {
    if (saving) return
    const name = form.name.trim()
    const sku = form.sku.trim()
    const wholeNumberFields: Array<[string, string]> = [['On-hand quantity', form.stockQuantity], ['Reorder level', form.reorderLevel]]
    if (!name) { setFormError('Part name is required.'); return }
    if (!sku) { setFormError('SKU is required.'); return }
    for (const [label, raw] of wholeNumberFields) {
      if (!/^\d+$/.test(raw.trim())) { setFormError(`${label} must be a whole number of zero or more.`); return }
    }
    const cost = Number(form.cost)
    const sellingPrice = Number(form.sellingPrice)
    if (!Number.isFinite(cost) || cost < 0) { setFormError('Cost must be zero or more.'); return }
    if (!Number.isFinite(sellingPrice) || sellingPrice < 0) { setFormError('Selling price must be zero or more.'); return }
    setSaving(true)
    setFormError(null)
    try {
      await api.post('/inventory', {
        name,
        sku,
        description: form.description.trim() || undefined,
        category: form.category.trim() || undefined,
        location: form.location.trim() || undefined,
        stock_quantity: Number(form.stockQuantity),
        reorder_level: Number(form.reorderLevel),
        cost,
        selling_price: sellingPrice,
        unit_type: form.unitType.trim() || 'each',
        supplier_name: form.supplierName.trim() || undefined,
        supplier_contact: form.supplierContact.trim() || undefined,
      })
      setForm(EMPTY_ADD_PART)
      await onCreated(name)
    } catch (cause) {
      setFormError(errorMessage(cause))
    } finally {
      setSaving(false)
    }
  }
  return <SlidePanelForm isOpen={isOpen} onClose={close} category="Parts & inventory" title="Add Part" onSubmit={submit} submitLabel="Add Part" isSubmitting={saving} ariaLabel="Add part">
    <div className="db-parts-workbench__add-form">
      <label>Part name <span aria-hidden="true">*</span><input autoFocus required disabled={saving} value={form.name} onChange={(event) => update('name', event.target.value)} placeholder="Brake pads – rear" /></label>
      <label>SKU <span aria-hidden="true">*</span><input required disabled={saving} value={form.sku} onChange={(event) => update('sku', event.target.value)} placeholder="BRA-HEA-DUT-PAD-001" /></label>
      <label className="is-wide">Description<textarea disabled={saving} rows={3} value={form.description} onChange={(event) => update('description', event.target.value)} placeholder="Optional catalog description" /></label>
      <label>Category<input disabled={saving} value={form.category} onChange={(event) => update('category', event.target.value)} placeholder="Brakes" /></label>
      <label>Bin location<input disabled={saving} value={form.location} onChange={(event) => update('location', event.target.value)} placeholder="A-12" /></label>
      <label>On-hand quantity<input disabled={saving} type="number" min={0} step={1} value={form.stockQuantity} onChange={(event) => update('stockQuantity', event.target.value)} /></label>
      <label>Reorder level<input disabled={saving} type="number" min={0} step={1} value={form.reorderLevel} onChange={(event) => update('reorderLevel', event.target.value)} /></label>
      <label>Cost per unit<input disabled={saving} type="number" min={0} step="0.01" inputMode="decimal" value={form.cost} onChange={(event) => update('cost', event.target.value)} /></label>
      <label>Selling price<input disabled={saving} type="number" min={0} step="0.01" inputMode="decimal" value={form.sellingPrice} onChange={(event) => update('sellingPrice', event.target.value)} /></label>
      <label>Unit<input disabled={saving} value={form.unitType} onChange={(event) => update('unitType', event.target.value)} placeholder="each" /></label>
      <label>Supplier name<input disabled={saving} value={form.supplierName} onChange={(event) => update('supplierName', event.target.value)} placeholder="Optional" /></label>
      <label className="is-wide">Supplier contact<input disabled={saving} value={form.supplierContact} onChange={(event) => update('supplierContact', event.target.value)} placeholder="Optional contact or terms note" /></label>
      {formError && <p className="is-wide" role="alert">{formError}</p>}
    </div>
  </SlidePanelForm>
}

function PartInspector({ part, loading, failed, manage, logoUrl, companyName, onBack, onRetry, onAdjust, onPrepare, onPurchasing, onOpenPurchaseOrder, onOpenRepair }: { part?: PartDetail; loading: boolean; failed: boolean; manage: boolean; logoUrl: string | null; companyName: string | null; onBack: () => void; onRetry: () => void; onAdjust: (part: PartDetail, patch: Record<string, unknown>) => Promise<void>; onPrepare: (part: PartDetail) => void; onPurchasing: () => void; onOpenPurchaseOrder: (id: string) => void; onOpenRepair: (id: string) => void }) {
  const [inspectorView, setInspectorView] = useState<InspectorView>('overview')
  const [edit, setEdit] = useState<'available' | 'reorder' | null>(null)
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [editFocusMode, setEditFocusMode] = useState<'pointer' | 'keyboard'>('pointer')
  const availableTrigger = useRef<HTMLButtonElement>(null)
  const availableStockTrigger = useRef<HTMLButtonElement>(null)
  const reorderTrigger = useRef<HTMLButtonElement>(null)
  const inspectorTabs = useRef<Array<HTMLButtonElement | null>>([])
  const editOrigin = useRef<'available-shortcut' | 'available-stock' | 'reorder' | null>(null)
  const restore = useRef<'available-shortcut' | 'available-stock' | 'reorder' | null>(null)
  const supplierId = part?.preferred_source?.supplier_id || null
  const supplierPurchasingQuery = useQuery<SupplierPurchasing>({
    queryKey: ['parts-operations', 'supplier-purchasing', supplierId],
    queryFn: async () => (await api.get(`/parts-operations/suppliers/${supplierId}/purchasing`)).data,
    enabled: Boolean(supplierId),
    retry: false,
  })
  useEffect(() => { setInspectorView('overview'); setEdit(null); setEditFocusMode('pointer'); setLocalError(null); setReason(''); editOrigin.current = null; restore.current = null }, [part?.id])
  useEffect(() => {
    if (edit || !restore.current) return
    const target = restore.current === 'available-shortcut' ? availableTrigger : restore.current === 'available-stock' ? availableStockTrigger : reorderTrigger
    restore.current = null
    const frame = window.requestAnimationFrame(() => target.current?.focus())
    return () => window.cancelAnimationFrame(frame)
  }, [edit])
  const open = (next: 'available' | 'reorder', origin: 'available-shortcut' | 'available-stock' | 'reorder', event: ReactMouseEvent<HTMLButtonElement>) => { if (!part) return; editOrigin.current = origin; setEditFocusMode(event.detail === 0 ? 'keyboard' : 'pointer'); setInspectorView('stock'); setValue(String(next === 'available' ? part.available_packages : part.reorder_level)); setReason(''); setLocalError(null); setEdit(next) }
  const close = () => { restore.current = editOrigin.current; editOrigin.current = null; setEdit(null); setLocalError(null) }
  const selectInspectorView = (next: InspectorView, focus = false) => {
    setInspectorView(next)
    setEdit(null)
    setLocalError(null)
    if (focus) window.requestAnimationFrame(() => inspectorTabs.current[INSPECTOR_VIEWS.findIndex((view) => view.id === next)]?.focus())
  }
  const handleInspectorKeys = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const currentIndex = INSPECTOR_VIEWS.findIndex((view) => view.id === inspectorView)
    let nextIndex = currentIndex
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % INSPECTOR_VIEWS.length
    else if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + INSPECTOR_VIEWS.length) % INSPECTOR_VIEWS.length
    else if (event.key === 'Home') nextIndex = 0
    else if (event.key === 'End') nextIndex = INSPECTOR_VIEWS.length - 1
    else return
    event.preventDefault()
    selectInspectorView(INSPECTOR_VIEWS[nextIndex].id, true)
  }
  const save = async () => {
    if (!part || !edit || saving) return
    if (!/^\d+$/.test(value.trim())) { setLocalError('Enter a whole number of zero or more.'); return }
    if (edit === 'available' && Number(value) !== part.available_packages && !reason.trim()) { setLocalError('Explain why the on-hand quantity is changing.'); return }
    setSaving(true); setLocalError(null)
    try {
      await onAdjust(part, edit === 'available' ? { stock_quantity: Number(value), stock_adjustment_reason: reason.trim() } : { reorder_level: Number(value) })
      close()
    } catch { /* Parent keeps the exact server recovery message. */ } finally { setSaving(false) }
  }
  if (loading) return <aside className="db-parts-workbench__inspector" role="status">Loading part details…</aside>
  if (failed) return <aside className="db-parts-workbench__inspector" role="alert">Part details could not be loaded.<button type="button" onClick={onRetry}>Retry</button></aside>
  if (!part) return <aside className="db-parts-workbench__inspector"><p>Select a part to see stock, supplier, repair, and purchase history.</p></aside>
  const stockState = part.is_archived ? 'Archived' : part.available_packages < part.needed_for_open_repairs ? 'Short for open repairs' : part.available_packages <= part.reorder_level ? 'Needs reorder' : 'In stock'
  const stockStateClass = part.is_archived ? 'is-archived' : part.available_packages < part.needed_for_open_repairs ? 'is-danger' : part.available_packages <= part.reorder_level ? 'is-warning' : ''
  const supplierPurchasing = supplierPurchasingQuery.data
  const alternateSource = part.supplier_sources.find((source) => source.is_active && !source.is_preferred)
  const lastReceipt = part.recent_receipts[0]
  const supplierLeadTimeDays = part.preferred_source?.lead_time_days ?? supplierPurchasing?.default_lead_time_days ?? null
  const onTimeRate = supplierPurchasing?.timed_order_count && supplierPurchasing.on_time_rate != null
    ? Number(supplierPurchasing.on_time_rate)
    : null
  const onTimeValue = onTimeRate != null && Number.isFinite(onTimeRate)
    ? `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(onTimeRate)}%`
    : null
  const onTimeAccessibleLabel = supplierPurchasingQuery.isLoading
    ? 'Loading delivery reliability'
    : onTimeValue
      ? `${onTimeValue} on-time delivery reliability`
      : 'Not enough delivery history'
  const remark = partRemark(part)
  const renderEditableStockFact = (
    kind: 'available' | 'reorder',
    label: string,
    currentValue: number,
    triggerRef: typeof availableStockTrigger,
    origin: 'available-stock' | 'reorder',
  ) => {
    const isEditing = edit === kind
    const editLabel = kind === 'available' ? 'Edit available quantity' : 'Edit reorder point'
    const fieldLabel = kind === 'available' ? 'On-hand quantity' : 'Reorder at'
    const tooltipId = `part-${part.id}-${kind}-edit-tooltip`
    const cancelLabel = kind === 'available' ? 'Cancel available quantity edit' : 'Cancel reorder point edit'
    const cancelTooltipId = `part-${part.id}-${kind}-cancel-tooltip`

    return <div key={kind} className={`db-parts-workbench__fact${isEditing ? ' is-editing' : ''}`}>
      <dt>{label}</dt>
      <dd className="db-parts-workbench__fact-value">
        {isEditing
          ? <form
              className="db-parts-workbench__edit db-parts-workbench__edit--inline"
              aria-label={editLabel}
              data-focus-mode={editFocusMode}
              onPointerDownCapture={() => setEditFocusMode('pointer')}
              onKeyDownCapture={(event) => {
                setEditFocusMode('keyboard')
                if (event.key === 'Escape' && !saving) {
                  event.preventDefault()
                  event.stopPropagation()
                  close()
                }
              }}
              onSubmit={(event) => { event.preventDefault(); void save() }}
            >
              <button
                className="db-parts-workbench__edit-cancel"
                type="button"
                disabled={saving}
                aria-label={cancelLabel}
                aria-describedby={cancelTooltipId}
                onClick={close}
              >
                <X aria-hidden="true" />
                <span id={cancelTooltipId} className="db-parts-workbench__fact-tooltip" role="tooltip">{cancelLabel}</span>
              </button>
              <div className="db-parts-workbench__edit-quantity">
                <QuantityStepper
                  autoFocus
                  disabled={saving}
                  value={Number(value)}
                  min={0}
                  step={1}
                  unitLabel="units"
                  ariaLabel={fieldLabel}
                  align="start"
                  size="lg"
                  className="db-parts-workbench__quantity-stepper"
                  onChange={(next) => { setValue(String(next)); setLocalError(null) }}
                />
              </div>
              {kind === 'available' && <label className="db-parts-workbench__edit-reason">Adjustment reason<textarea disabled={saving} rows={3} value={reason} onChange={(event) => { setReason(event.target.value); setLocalError(null) }} placeholder="Cycle count, damage, return to shelf…" /></label>}
              {localError && <p role="alert">{localError}</p>}
              <button className="db-parts-workbench__edit-save" type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
            </form>
          : <>
              <span>{currentValue}</span>
              {manage && !part.is_archived && !edit && <button
                ref={triggerRef}
                className="db-parts-workbench__fact-edit"
                type="button"
                aria-label={editLabel}
                aria-describedby={tooltipId}
                onClick={(event) => open(kind, origin, event)}
              ><Pencil aria-hidden="true" /><span id={tooltipId} className="db-parts-workbench__fact-tooltip" role="tooltip">{editLabel}</span></button>}
            </>}
      </dd>
    </div>
  }
  const availableStockFact = renderEditableStockFact('available', 'Available', part.available_packages, availableStockTrigger, 'available-stock')
  const reorderStockFact = renderEditableStockFact('reorder', 'Reorder at', part.reorder_level, reorderTrigger, 'reorder')
  const neededStockFact = <div key="needed"><dt>Needed for open repairs</dt><dd>{part.needed_for_open_repairs}</dd></div>
  const incomingStockFact = <div key="incoming"><dt>Incoming</dt><dd>{part.incoming_packages}</dd></div>
  const stockFacts = edit === 'reorder'
    ? [reorderStockFact, availableStockFact, neededStockFact, incomingStockFact]
    : [availableStockFact, neededStockFact, reorderStockFact, incomingStockFact]
  return <aside className="db-parts-workbench__inspector" aria-labelledby="selected-part-name">
    <button className="db-parts-workbench__mobile-back" type="button" onClick={onBack}>Back to parts</button>
    <div className="db-parts-workbench__selected-action" data-selected-surface="true">
      <p className="db-parts-workbench__selected-label">Selected part</p>
      <div className="db-parts-workbench__selected-part">
        <PartPhoto part={part} logoUrl={logoUrl} companyName={companyName} detail />
        <div className="db-parts-workbench__selected-copy"><h2 id="selected-part-name">{part.name}</h2><p className="db-parts-workbench__technical-line">{part.sku} · {part.location ? <><MapPin aria-hidden="true" />Bin {part.location}</> : 'Bin not set'} · {part.unit_type || 'No unit specified'}</p><span className={`db-parts-workbench__stock-state ${stockStateClass}`}>{stockState}</span></div>
      </div>
      <div className="db-parts-workbench__selected-actions">
        {manage && isManuallySelectable(part) && <button className="db-parts-workbench__action-primary" type="button" onClick={() => onPrepare(part)}>Add to purchase list</button>}
        {manage && !part.is_archived && !edit && <button ref={availableTrigger} className="db-parts-workbench__action-secondary" type="button" onClick={(event) => open('available', 'available-shortcut', event)}>Adjust on-hand quantity</button>}
        <button className="db-parts-workbench__action-tertiary" type="button" onClick={onPurchasing}>Open Purchasing<ArrowRight aria-hidden="true" /></button>
      </div>
      {!manage && !part.is_archived && <p className="db-parts-workbench__selected-permission">You can view stock. Owners and admins can make changes.</p>}
    </div>
    {part.is_archived && <p className="db-parts-workbench__archive" role="status">Archived part. History stays available, but stock and purchasing actions are locked.</p>}
    <div className="db-parts-workbench__inspector-tabs" role="tablist" aria-label="Selected part details" onKeyDown={handleInspectorKeys}>
      {INSPECTOR_VIEWS.map((view, index) => <button key={view.id} ref={(node) => { inspectorTabs.current[index] = node }} id={`part-inspector-${view.id}-tab`} type="button" role="tab" aria-selected={inspectorView === view.id} aria-controls={`part-inspector-${view.id}-panel`} tabIndex={inspectorView === view.id ? 0 : -1} onClick={() => selectInspectorView(view.id)}>{view.label}</button>)}
    </div>
    <div className="db-parts-workbench__inspector-panel" id={`part-inspector-${inspectorView}-panel`} role="tabpanel" aria-labelledby={`part-inspector-${inspectorView}-tab`}>
      {inspectorView === 'overview' && <>
        <section className="db-parts-workbench__section"><h3>At a glance</h3><dl className="db-parts-workbench__facts is-overview"><div><dt>Available</dt><dd>{part.available_packages}</dd></div><div><dt>Needed for open repairs</dt><dd>{part.needed_for_open_repairs}</dd></div><div><dt>Reorder at</dt><dd>{part.reorder_level}</dd></div><div><dt>Incoming</dt><dd>{part.incoming_packages}</dd></div><div><dt>Average cost</dt><dd>${Number(part.average_unit_cost || 0).toFixed(2)}</dd></div><div><dt>Remarks</dt><dd>{remark}</dd></div></dl></section>
        <section className="db-parts-workbench__section db-parts-workbench__supplier-section">
          <div className="db-parts-workbench__supplier-section-head">
            <h3>Supplied by</h3>
            {part.preferred_source && manage && !part.is_archived && <button type="button" aria-label="Change preferred supplier" onClick={() => selectInspectorView('ordering', true)}>Change</button>}
          </div>
          {part.preferred_source ? <div className="db-parts-workbench__supplier-relationship">
            <div className="db-parts-workbench__supplier-identity">
              <span aria-hidden="true">{(part.preferred_source.supplier_name || 'S').slice(0, 2).toUpperCase()}</span>
              <div className="db-parts-workbench__supplier-copy">
                <strong className="db-parts-workbench__supplier-name">{part.preferred_source.supplier_name || 'Supplier'}</strong>
                <small className="db-parts-workbench__supplier-meta">
                  {supplierPurchasing?.payment_terms || 'Terms not set'} · {supplierLeadTimeDays == null ? 'Lead time not set' : `Lead ${supplierLeadTimeDays} ${supplierLeadTimeDays === 1 ? 'day' : 'days'}`} · Min {part.preferred_source.minimum_order_quantity} units · Pack size {part.preferred_source.pack_quantity}
                </small>
              </div>
              <p className="db-parts-workbench__supplier-reliability" data-state={supplierPurchasingQuery.isLoading ? 'loading' : onTimeValue ? 'available' : 'unavailable'}>
                <small>On time</small>
                <strong aria-label={onTimeAccessibleLabel}>{supplierPurchasingQuery.isLoading ? '…' : onTimeValue || '—'}</strong>
              </p>
            </div>
            <dl>
              <div><dt>Their part no.</dt><dd>{part.preferred_source.supplier_part_number || 'Not set'}</dd></div>
              <div><dt>Last receipt / purchase</dt><dd>{lastReceipt ? `$${lastReceipt.unit_cost} · ${formatDate(lastReceipt.received_at)}` : 'No receipt or purchase recorded'}</dd></div>
              <div><dt>Alternate source</dt><dd>{alternateSource ? `${alternateSource.supplier_name || 'Supplier'}${alternateSource.last_unit_cost ? ` · $${alternateSource.last_unit_cost}` : ''}` : 'None on file'}</dd></div>
            </dl>
          </div> : <div className="db-parts-workbench__supplier-unlinked"><i aria-hidden="true" /><span><strong>No supplier linked</strong><small>Add this part to the purchase list to keep it visible as blocked, or use Ordering to link a source.</small></span></div>}
        </section>
        <section className="db-parts-workbench__section"><h3>Why this part is needed</h3>{part.repair_sources.length ? part.repair_sources.slice(0, 3).map((source) => <button className="db-parts-workbench__linked-row" type="button" key={source.repair_order_id} onClick={() => onOpenRepair(source.repair_order_id)}><span><strong>{source.order_number}</strong><small>{source.unit_number ? `Unit ${source.unit_number} · ` : ''}{source.vehicle_display || 'Vehicle not set'}</small></span><strong>{source.packages} units needed</strong><ArrowRight aria-hidden="true" /></button>) : <p className="db-parts-workbench__muted">No open repair is waiting on this part.</p>}</section>
        <section className="db-parts-workbench__section"><h3>Recent movement</h3>{part.recent_movements.length ? part.recent_movements.slice(0, 3).map((movement) => <div className="db-parts-workbench__movement-row" key={movement.id}><span><strong>{movementLabel(movement.movement_type)}</strong><small>{new Date(movement.occurred_at).toLocaleString()}</small></span><strong>{movement.quantity_delta > 0 ? '+' : ''}{movement.quantity_delta} · {movement.balance_after} available</strong></div>) : <p className="db-parts-workbench__muted">No inventory changes have been recorded for this part.</p>}</section>
      </>}
      {inspectorView === 'stock' && <section className="db-parts-workbench__section"><h3>Stock</h3><dl className={`db-parts-workbench__facts${edit ? ' has-editor' : ''}`}>
        {stockFacts}
      </dl>
      </section>}
      {inspectorView === 'ordering' && <section className="db-parts-workbench__section">
        <div className="db-parts-workbench__section-head"><h3>Ordering</h3><button type="button" onClick={onPurchasing}>Open Purchasing<ArrowRight aria-hidden="true" /></button></div>
        <dl className="db-parts-workbench__facts"><div><dt>Recommended order</dt><dd>{part.recommended_order_packages}</dd></div><div><dt>Average unit cost</dt><dd>${part.average_unit_cost}</dd></div></dl>
        <SupplierSources part={part} manage={manage && !part.is_archived} onChanged={onRetry} />
        <div className="db-parts-workbench__purchase-history">
          <h4>Open purchase orders</h4>
          {part.incoming_sources.length ? part.incoming_sources.map((source) => <button className="db-parts-workbench__linked-row" type="button" key={source.purchase_order_id} onClick={() => onOpenPurchaseOrder(source.purchase_order_id)}><span><strong>{source.po_number}</strong><small>{source.expected_at ? `Expected ${formatDate(source.expected_at)}` : 'Delivery date not set'}</small></span><strong>{source.packages} units incoming</strong><ArrowRight aria-hidden="true" /></button>) : <p className="db-parts-workbench__muted">No open purchase order includes this part.</p>}
          <h4>Recent receipts</h4>
          {part.recent_receipts.length ? part.recent_receipts.map((receipt) => <button className="db-parts-workbench__linked-row" type="button" key={receipt.receipt_id} onClick={() => onOpenPurchaseOrder(receipt.purchase_order_id)}><span><strong>{receipt.receipt_number}</strong><small>{receipt.po_number} · Received {formatDate(receipt.received_at)}</small></span><strong>{receipt.quantity} at ${receipt.unit_cost}</strong><ArrowRight aria-hidden="true" /></button>) : <p className="db-parts-workbench__muted">No receiving history has been recorded for this part.</p>}
        </div>
      </section>}
      {inspectorView === 'history' && <>
        <section className="db-parts-workbench__section"><h3>Repair history links</h3>{part.repair_sources.length ? part.repair_sources.map((source) => <button className="db-parts-workbench__linked-row" type="button" key={source.repair_order_id} onClick={() => onOpenRepair(source.repair_order_id)}><span><strong>{source.order_number}</strong><small>{source.unit_number ? `Unit ${source.unit_number} · ` : ''}{source.vehicle_display || 'Vehicle not set'}</small></span><strong>{source.packages} units needed</strong><ArrowRight aria-hidden="true" /></button>) : <p className="db-parts-workbench__muted">No repair has reserved this part.</p>}</section>
        <section className="db-parts-workbench__section"><h3>Recent inventory changes</h3>{part.recent_movements.length ? part.recent_movements.slice(0, 6).map((movement) => <div className="db-parts-workbench__movement-row" key={movement.id}><span><strong>{movementLabel(movement.movement_type)}</strong><small>{new Date(movement.occurred_at).toLocaleString()}</small></span><strong>{movement.quantity_delta > 0 ? '+' : ''}{movement.quantity_delta} · {movement.balance_after} on hand</strong></div>) : <p className="db-parts-workbench__muted">No inventory changes have been recorded for this part.</p>}</section>
      </>}
    </div>
  </aside>
}

function SupplierSources({ part, manage, onChanged }: { part: PartDetail; manage: boolean; onChanged: () => void }) {
  const queryClient = useQueryClient()
  const addTriggerRef = useRef<HTMLButtonElement>(null)
  const sourceTriggerRefs = useRef(new Map<string, HTMLButtonElement>())
  const restoreTrigger = useRef<'new' | string | null>(null)
  const newSupplierFieldRef = useRef<HTMLSelectElement>(null)
  const supplierPartNumberFieldRef = useRef<HTMLInputElement>(null)
  const [editing, setEditing] = useState<SupplierSource | 'new' | null>(null)
  const [focusMode, setFocusMode] = useState<'pointer' | 'keyboard'>('pointer')
  const [supplierId, setSupplierId] = useState('')
  const [supplierPartNumber, setSupplierPartNumber] = useState('')
  const [minimum, setMinimum] = useState('1')
  const [pack, setPack] = useState('1')
  const [leadTime, setLeadTime] = useState('')
  const [preferred, setPreferred] = useState(false)
  const [saving, setSaving] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const suppliersQuery = useQuery<Page<SupplierOption>>({
    queryKey: ['suppliers', 'source-options'],
    queryFn: async () => {
      const all: SupplierOption[] = []
      let page: Page<SupplierOption>
      let nextSkip = 0
      do {
        page = (await api.get('/suppliers', { params: { paginated: true, skip: nextSkip, limit: 100 } })).data
        all.push(...page.items)
        nextSkip = page.skip + page.limit
      } while (page.has_more && page.items.length > 0)
      return { items: all, total: all.length, skip: 0, limit: all.length, has_more: false }
    },
    enabled: editing === 'new',
    retry: false,
  })

  useEffect(() => {
    if (editing || !restoreTrigger.current) return
    const trigger = restoreTrigger.current
    restoreTrigger.current = null
    const frame = window.requestAnimationFrame(() => {
      const target = trigger === 'new' ? addTriggerRef.current : sourceTriggerRefs.current.get(trigger) || addTriggerRef.current
      target?.focus()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [editing])

  useEffect(() => {
    if (!editing || (editing === 'new' && suppliersQuery.isLoading)) return
    const frame = window.requestAnimationFrame(() => {
      if (editing === 'new') newSupplierFieldRef.current?.focus()
      else supplierPartNumberFieldRef.current?.focus()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [editing, suppliersQuery.isLoading])

  const close = () => {
    setEditing(null)
    setLocalError(null)
    setConfirmDelete(false)
  }
  const open = (source: SupplierSource | 'new', event: ReactMouseEvent<HTMLButtonElement>) => {
    restoreTrigger.current = source === 'new' ? 'new' : source.source_id
    setFocusMode(event.detail === 0 ? 'keyboard' : 'pointer')
    setEditing(source)
    setSupplierId(source === 'new' ? '' : source.supplier_id)
    setSupplierPartNumber(source === 'new' ? '' : source.supplier_part_number || '')
    setMinimum(String(source === 'new' ? 1 : source.minimum_order_quantity))
    setPack(String(source === 'new' ? 1 : source.pack_quantity))
    setLeadTime(source === 'new' || source.lead_time_days == null ? '' : String(source.lead_time_days))
    setPreferred(source === 'new' ? !part.preferred_source : source.is_preferred)
    setLocalError(null)
    setConfirmDelete(false)
  }
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['parts-operations', 'parts'] }),
      queryClient.invalidateQueries({ queryKey: ['parts-operations', 'part', part.id] }),
    ])
    onChanged()
  }
  const save = async () => {
    if (!editing || saving) return
    if (editing !== 'new' && !editing.updated_at) { setLocalError('Refresh this part before changing its supplier source.'); return }
    const minimumValue = Number(minimum)
    const packValue = Number(pack)
    const leadTimeValue = leadTime.trim() ? Number(leadTime) : null
    if (editing === 'new' && !supplierId) { setLocalError('Choose a supplier.'); return }
    if (!Number.isInteger(minimumValue) || minimumValue < 1 || minimumValue > 999) { setLocalError('Minimum order must be a whole number from 1 to 999.'); return }
    if (!Number.isInteger(packValue) || packValue < 1 || packValue > 999) { setLocalError('Pack size must be a whole number from 1 to 999.'); return }
    if (leadTimeValue != null && (!Number.isInteger(leadTimeValue) || leadTimeValue < 0 || leadTimeValue > 365)) { setLocalError('Lead time must be a whole number from 0 to 365 days.'); return }
    setSaving(true)
    setLocalError(null)
    try {
      const payload = {
        supplier_part_number: supplierPartNumber.trim() || null,
        is_preferred: preferred,
        minimum_order_quantity: minimumValue,
        pack_quantity: packValue,
        lead_time_days: leadTimeValue,
        is_active: true,
      }
      if (editing === 'new') {
        await api.post(`/parts-operations/parts/${part.id}/supplier-sources`, { supplier_id: supplierId, ...payload }, { headers: { 'Idempotency-Key': `supplier-source-${crypto.randomUUID()}` } })
      } else {
        await api.patch(`/parts-operations/parts/${part.id}/supplier-sources/${editing.source_id}`, { expected_updated_at: editing.updated_at, ...payload })
      }
      await refresh()
      close()
    } catch (cause) {
      setLocalError(errorMessage(cause))
    } finally {
      setSaving(false)
    }
  }
  const remove = async () => {
    if (!editing || editing === 'new' || saving) return
    if (!editing.updated_at) { setLocalError('Refresh this part before removing its supplier source.'); return }
    setSaving(true)
    setLocalError(null)
    try {
      await api.delete(`/parts-operations/parts/${part.id}/supplier-sources/${editing.source_id}`, { data: { expected_updated_at: editing.updated_at } })
      await refresh()
      close()
    } catch (cause) {
      setLocalError(errorMessage(cause))
    } finally {
      setSaving(false)
    }
  }

  return <div className="db-parts-workbench__supplier-sources">
    <div className="db-parts-workbench__sources-heading">
      <h4>Supplier sources</h4>
      {manage && !editing && <button ref={addTriggerRef} type="button" onClick={(event) => open('new', event)}>Add supplier source</button>}
    </div>
    {part.supplier_sources.length ? <div className="db-parts-workbench__sources-list">{part.supplier_sources.map((source) => {
      const supplierName = source.supplier_name || 'Supplier'
      const content = <>
        <span><strong>{supplierName}{source.is_preferred ? ' · Preferred' : ''}</strong><small>{source.supplier_part_number || 'Supplier part number not set'} · Pack size {source.pack_quantity} · Minimum order {source.minimum_order_quantity} · {source.lead_time_days == null ? 'Lead time not set' : `${source.lead_time_days} day lead time`}</small></span>
        <span className="db-parts-workbench__source-cost"><small>Last received cost</small><strong>{source.last_unit_cost == null ? 'Not recorded' : `$${source.last_unit_cost}`}</strong></span>
      </>
      if (!manage || editing) return <div className="db-parts-workbench__source-row" key={source.source_id}>{content}</div>
      return <button
        key={source.source_id}
        ref={(node) => {
          if (node) sourceTriggerRefs.current.set(source.source_id, node)
          else sourceTriggerRefs.current.delete(source.source_id)
        }}
        className="db-parts-workbench__source-row"
        type="button"
        aria-label={`Edit ${supplierName} supplier source`}
        onClick={(event) => open(source, event)}
      >
        {content}
        <span className="db-parts-workbench__source-action" aria-hidden="true"><span>Edit source</span><Pencil /></span>
      </button>
    })}</div> : <p className="db-parts-workbench__muted">No supplier source is set. Add one here before preparing this part for purchase.</p>}

    {editing && <form
      className="db-parts-workbench__source-editor"
      aria-label={editing === 'new' ? 'Add supplier source' : `Edit ${editing.supplier_name || 'supplier'} supplier source`}
      data-focus-mode={focusMode}
      onPointerDownCapture={() => setFocusMode('pointer')}
      onKeyDownCapture={() => setFocusMode('keyboard')}
      onSubmit={(event) => { event.preventDefault(); void save() }}
    >
      <h4>{editing === 'new' ? 'Add supplier source' : `Edit ${editing.supplier_name || 'supplier source'}`}</h4>
      {editing === 'new' && <label>Supplier<select ref={newSupplierFieldRef} disabled={saving || suppliersQuery.isLoading} value={supplierId} onChange={(event) => setSupplierId(event.target.value)}><option value="">Choose supplier</option>{(suppliersQuery.data?.items || []).filter((supplier) => !part.supplier_sources.some((source) => source.supplier_id === supplier.id)).map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></label>}
      <label>Supplier part number<input ref={supplierPartNumberFieldRef} disabled={saving} value={supplierPartNumber} maxLength={150} onChange={(event) => setSupplierPartNumber(event.target.value)} /></label>
      <div><label>Minimum order<input disabled={saving} type="number" min={1} max={999} step={1} value={minimum} onChange={(event) => setMinimum(event.target.value)} /></label><label>Pack size<input disabled={saving} type="number" min={1} max={999} step={1} value={pack} onChange={(event) => setPack(event.target.value)} /></label><label>Lead time (days)<input disabled={saving} type="number" min={0} max={365} step={1} value={leadTime} onChange={(event) => setLeadTime(event.target.value)} /></label></div>
      <label className="db-parts-workbench__source-check"><input disabled={saving} type="checkbox" checked={preferred} onChange={(event) => setPreferred(event.target.checked)} />Use as preferred source for this part</label>
      {localError && <p role="alert">{localError}</p>}
      <div className="db-parts-workbench__source-actions">
        {editing !== 'new' && (confirmDelete ? <><button type="button" disabled={saving} onClick={() => void remove()}>Confirm remove</button><button type="button" disabled={saving} onClick={() => setConfirmDelete(false)}>Keep source</button></> : <button type="button" disabled={saving} onClick={() => setConfirmDelete(true)}>Remove source</button>)}
        <span />
        <button type="button" disabled={saving} onClick={close}>Cancel</button>
        <button type="submit" disabled={saving || (editing === 'new' && suppliersQuery.isLoading)}>{saving ? 'Saving…' : 'Save source'}</button>
      </div>
    </form>}
  </div>
}

function MovementLedger({ page, loading, failed, onRetry, onOpenRepair, onPage }: { page?: Page<Movement>; loading: boolean; failed: boolean; onRetry: () => void; onOpenRepair: (id: string) => void; onPage: (skip: number) => void }) {
  if (loading) return <div className="db-parts-workbench__state" role="status">Loading inventory history…</div>
  if (failed) return <div className="db-parts-workbench__state" role="alert">Inventory history could not be loaded.<button type="button" onClick={onRetry}>Retry</button></div>
  if (!page?.items.length) return <div className="db-parts-workbench__state"><strong>No inventory changes yet.</strong><span>Receipts, repair reservations, and audited adjustments will appear here.</span></div>
  return <div className="db-parts-workbench__movement-ledger">{page.items.map((movement) => <article key={movement.id}><div><strong>{movement.inventory?.name || 'Inventory change'}</strong><p>{movementLabel(movement.movement_type)} · {movement.balance_after} on hand after change{movement.wac_after ? ` · Average cost $${movement.wac_after}` : ''}</p></div><div>{movement.source?.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(movement.source!.id)}>{movement.source.order_number || 'Open repair'}<ArrowRight aria-hidden="true" /></button> : <span>{movement.source?.receipt_number || movement.source?.return_number || 'Stock record'}</span>}<time>{formatDate(movement.occurred_at)}</time></div></article>)}<Pager page={page} onPage={onPage} /></div>
}
