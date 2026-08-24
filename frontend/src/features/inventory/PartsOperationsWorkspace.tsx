import { Children, cloneElement, isValidElement, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowRight, ClipboardList, Package, PackageSearch, RotateCcw, Search } from 'lucide-react'
import api from '@/lib/api'
import useTenantBranding from '@/hooks/useTenantBranding'
import type { InventoryItem } from '@/types'
import { useAuthStore } from '@/stores/authStore'

type OperationsTab = 'demand' | 'inventory' | 'purchase-orders' | 'returns-cores' | 'activity'
type DemandFilter = 'all' | 'repair-shortages' | 'replenishment' | 'unlinked'
type InventoryStockFilter = 'all' | 'needs-reorder' | 'out-of-stock' | 'in-stock'
type InventorySort = 'catalog' | 'low-stock' | 'high-stock' | 'name-asc' | 'name-desc'
type Page<T> = { items: T[]; total: number; skip: number; limit: number; has_more: boolean }
type CompletePage<T> = Page<T> & { loaded_pages: number }

type SupplierSummary = { id: string; name: string; normalized_name: string }
type DemandSource = {
  type: 'repair_order' | 'reorder_level' | 'purchase_order' | 'legacy_on_order'
  packages: number
  repair_order_id?: string
  order_number?: string
  purchase_order_id?: string
  po_number?: string
  linked?: boolean
}
type DemandItem = {
  inventory_id: string; sku: string; name: string; unit_type: string; state: 'open' | 'covered' | 'unlinked'
  stock_quantity: number; reorder_level: number; repair_shortage_packages: number
  shelf_replenishment_packages: number; open_supply_packages: number; recommended_order_packages: number
  preferred_supplier: SupplierSummary | null; fresh_as_of: string; sources: DemandSource[]
}
type PurchaseOrder = {
  id: string; po_number: string; supplier_id: string; supplier: SupplierSummary | null
  status: 'draft' | 'submitted' | 'partially_received' | 'received' | 'cancelled'; version: number
  expected_at: string | null; line_count: number; ordered_quantity: number; received_quantity: number
  remaining_quantity: number; created_at: string
}
type PurchaseOrderDetail = PurchaseOrder & {
  notes: string | null
  lines: Array<{ id: string; inventory_id: string; sku: string; description: string; unit_type: string; unit_cost: string; ordered_quantity: number; received_quantity: number }>
}
type ReturnItem = {
  id: string; return_number: string; supplier_id: string; supplier: SupplierSummary | null; kind: 'stock' | 'core'
  status: 'draft' | 'submitted' | 'shipped' | 'credited' | 'cancelled'; version: number
  line_count: number; total_quantity: number; expected_credit_total: string; reverses_return_id: string | null; created_at: string
}
type ReturnDetail = ReturnItem & { reason: string; notes: string | null; lines: Array<{ id: string; inventory: { id: string; sku: string; name: string } | null; quantity: number; expected_credit: string; actual_credit: string | null; source: { type: string; id: string } }> }
type Core = {
  id: string; inventory_id: string; inventory: { id: string; sku: string; name: string } | null
  supplier_id: string | null; supplier: SupplierSummary | null; quantity: number
  status: 'expected' | 'on_hand' | 'returned' | 'waived'; version: number; unit_core_value: string
  source: { repair_order_id: string; order_number: string } | null; created_at: string
}
type Movement = {
  id: string; inventory: { id: string; sku: string; name: string } | null; movement_type: string; quantity_delta: number
  balance_after: number; wac_after: string | null; source: { type: string; id: string; order_number?: string; return_number?: string; receipt_number?: string } | null
  occurred_at: string
}
type Summary = { low_stock_count: number; open_purchase_order_count: number }
type PartImageBranding = { logoUrl: string | null; name: string | null }
type PartImageStage = 'part' | 'logo' | 'icon'

const tabs: Array<{ id: OperationsTab; label: string; icon: typeof PackageSearch }> = [
  { id: 'demand', label: 'Demand', icon: AlertTriangle },
  { id: 'inventory', label: 'Inventory', icon: PackageSearch },
  { id: 'purchase-orders', label: 'Purchase orders', icon: ClipboardList },
  { id: 'returns-cores', label: 'Returns & cores', icon: RotateCcw },
  { id: 'activity', label: 'Activity', icon: Activity },
]

const demandFilters: Array<{ id: DemandFilter; label: string }> = [
  { id: 'all', label: 'All demand' },
  { id: 'repair-shortages', label: 'Repair shortages' },
  { id: 'replenishment', label: 'Replenishment' },
  { id: 'unlinked', label: 'Unlinked' },
]

const inventoryStockFilters: Array<{ id: InventoryStockFilter; label: string }> = [
  { id: 'all', label: 'All stock' },
  { id: 'needs-reorder', label: 'Needs reorder' },
  { id: 'out-of-stock', label: 'Out of stock' },
  { id: 'in-stock', label: 'In stock' },
]

const inventorySorts: Array<{ id: InventorySort; label: string }> = [
  { id: 'catalog', label: 'Catalog order' },
  { id: 'low-stock', label: 'Low stock first' },
  { id: 'high-stock', label: 'High stock first' },
  { id: 'name-asc', label: 'Name A–Z' },
  { id: 'name-desc', label: 'Name Z–A' },
]

const EMPTY_DEMAND: DemandItem[] = []
const EMPTY_INVENTORY: InventoryItem[] = []
const EMPTY_PURCHASE_ORDERS: PurchaseOrder[] = []
const EMPTY_RETURNS: ReturnItem[] = []
const EMPTY_CORES: Core[] = []
const EMPTY_ACTIVITY: Movement[] = []

const operationKeys = {
  summary: ['parts-operations', 'summary'] as const,
  demand: ['parts-operations', 'demand'] as const,
  inventory: ['parts-operations', 'inventory'] as const,
  purchaseOrders: ['parts-operations', 'purchase-orders'] as const,
  returns: ['parts-operations', 'returns'] as const,
  cores: ['parts-operations', 'cores'] as const,
  activity: ['parts-operations', 'activity'] as const,
}

const COLLECTION_PAGE_LIMIT = 100

function asPage<T>(value: Page<T> | T[]): Page<T> {
  if (!Array.isArray(value)) return value
  return { items: value, total: value.length, skip: 0, limit: value.length, has_more: false }
}

/**
 * The API limits each response to 100 records. A visible operations collection
 * must not quietly become a first-page-only view: retain the server metadata,
 * fetch every advertised page, and present the complete result to local search
 * and triage controls.
 */
async function fetchCompletePage<T>(path: string): Promise<CompletePage<T>> {
  const items: T[] = []
  let skip = 0
  let total = 0
  let limit = COLLECTION_PAGE_LIMIT
  let loadedPages = 0
  let hasMore = true

  while (hasMore) {
    const response = asPage<T>((await api.get(path, { params: { paginated: true, skip, limit: COLLECTION_PAGE_LIMIT } })).data)
    items.push(...response.items)
    total = response.total
    limit = response.limit || COLLECTION_PAGE_LIMIT
    loadedPages += 1
    hasMore = response.has_more && response.items.length > 0
    skip = response.skip + response.items.length
  }

  return { items, total, skip: 0, limit, has_more: false, loaded_pages: loadedPages }
}

function operationKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`
}

function message(error: unknown, fallback = 'The operation could not be completed.') {
  const candidate = error as { response?: { status?: number; data?: { detail?: string } }; message?: string }
  if (candidate.response?.status === 409) return 'This record changed elsewhere. Review the latest details and try again.'
  return candidate.response?.data?.detail || candidate.message || fallback
}

function formatDate(value: string | null) {
  if (!value) return 'Not scheduled'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value))
}

function humanize(value: string) {
  return value.replace(/_/g, ' ')
}

function isMutationRole(role: string | undefined) {
  return role === 'garage_owner' || role === 'garage_admin'
}

function isRetiredEmpty(item: InventoryItem) {
  return Boolean(item.ets_retired_at) && item.stock_quantity <= 0
}

function needsReorder(item: InventoryItem) {
  return item.stock_quantity <= item.reorder_level && !item.is_placeholder && !isRetiredEmpty(item)
}

function inventoryStockLabel(item: InventoryItem) {
  if (item.stock_quantity === 0) return 'Out of stock'
  if (needsReorder(item)) return 'Needs reorder'
  if (item.stock_quantity > item.reorder_level) return 'In stock'
  return 'Catalog only'
}

function matchesInventoryStockFilter(item: InventoryItem, filter: InventoryStockFilter) {
  if (filter === 'needs-reorder') return needsReorder(item)
  if (filter === 'out-of-stock') return item.stock_quantity === 0
  if (filter === 'in-stock') return item.stock_quantity > item.reorder_level
  return true
}

function inventoryStockRank(item: InventoryItem, direction: 'low' | 'high') {
  const label = inventoryStockLabel(item)
  if (direction === 'low') return label === 'Out of stock' ? 0 : label === 'Needs reorder' ? 1 : label === 'In stock' ? 2 : 3
  return label === 'In stock' ? 0 : label === 'Needs reorder' ? 1 : label === 'Out of stock' ? 2 : 3
}

function compareInventory(left: InventoryItem, right: InventoryItem, sort: InventorySort) {
  const byName = left.name.localeCompare(right.name, undefined, { sensitivity: 'base' }) || left.id.localeCompare(right.id)
  if (sort === 'name-asc') return byName
  if (sort === 'name-desc') return -byName || left.id.localeCompare(right.id)
  if (sort === 'low-stock' || sort === 'high-stock') {
    const direction = sort === 'low-stock' ? 'low' : 'high'
    const byStatus = inventoryStockRank(left, direction) - inventoryStockRank(right, direction)
    const byQuantity = direction === 'low' ? left.stock_quantity - right.stock_quantity : right.stock_quantity - left.stock_quantity
    return byStatus || byQuantity || byName
  }
  return 0
}

function reconcileVisibleId<T>(currentId: string | null, items: T[], getId: (item: T) => string) {
  if (currentId && items.some((item) => getId(item) === currentId)) return currentId
  return items.length ? getId(items[0]) : null
}

/**
 * The backend is the enablement authority. A 404 means the deployment or tenant
 * flag is off; a 403 means this otherwise eligible browser must retain its
 * existing catalog instead of receiving a client-side approximation.
 */
export function PartsOperationsGate({ legacy }: { legacy: ReactNode }) {
  const role = useAuthStore((state) => state.user?.role)
  const mayRead = role === 'garage_owner' || role === 'garage_admin' || role === 'receptionist'
  const availability = useQuery<Summary>({
    queryKey: operationKeys.summary,
    queryFn: async () => (await api.get('/parts-operations/summary')).data,
    enabled: mayRead,
    retry: false,
    staleTime: 60_000,
  })

  if (!mayRead) return <>{legacy}</>
  if (availability.isPending) {
    return <div className="rounded-2xl border border-[var(--workspace-border)] bg-[var(--surface-raised)] p-6 text-[var(--text-secondary)]" role="status">Checking Parts Operations…</div>
  }
  if (availability.isError) {
    const status = (availability.error as { response?: { status?: number } } | undefined)?.response?.status
    if (status === 403 || status === 404) return <>{legacy}</>
    return <div className="db-parts-operations__unavailable" role="alert"><span>Parts Operations is temporarily unavailable. The existing inventory catalog remains available after refresh.</span><button type="button" onClick={() => void availability.refetch()}>Retry</button></div>
  }
  return <PartsOperationsWorkspace summary={availability.data} />
}

export default function PartsOperationsWorkspace({ summary }: { summary: Summary }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { data: tenantBranding } = useTenantBranding()
  const role = useAuthStore((state) => state.user?.role)
  const canMutate = isMutationRole(role)
  const partImageBranding: PartImageBranding = {
    logoUrl: tenantBranding?.logo_url || null,
    name: tenantBranding?.name || null,
  }
  const [tab, setTab] = useState<OperationsTab>('demand')
  const [selectedDemandId, setSelectedDemandId] = useState<string | null>(null)
  const [selectedInventoryId, setSelectedInventoryId] = useState<string | null>(null)
  const [selectedPOId, setSelectedPOId] = useState<string | null>(null)
  const [selectedReturnId, setSelectedReturnId] = useState<string | null>(null)
  const [selectedCoreId, setSelectedCoreId] = useState<string | null>(null)
  const [custodyView, setCustodyView] = useState<'returns' | 'cores'>('returns')
  const [demandSearch, setDemandSearch] = useState('')
  const [demandFilter, setDemandFilter] = useState<DemandFilter>('all')
  const [inventorySearch, setInventorySearch] = useState('')
  const [inventoryStockFilter, setInventoryStockFilter] = useState<InventoryStockFilter>('all')
  const [inventorySort, setInventorySort] = useState<InventorySort>('catalog')
  const [selectionNotice, setSelectionNotice] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<string | null>(null)
  const pendingActions = useRef(new Set<string>())
  const mutationKeys = useRef(new Map<string, string>())
  const invalidateOperations = () => {
    void queryClient.invalidateQueries({ queryKey: ['parts-operations'] })
    void queryClient.invalidateQueries({ queryKey: ['inventory'] })
  }
  const call = async <T,>(action: string, fn: (key: string) => Promise<T>, success: string) => {
    if (pendingActions.current.has(action)) return
    pendingActions.current.add(action)
    setPendingAction(action)
    setError(null)
    const key = mutationKeys.current.get(action) || operationKey(action)
    mutationKeys.current.set(action, key)
    try {
      await fn(key)
      invalidateOperations()
      setNotice(success)
      mutationKeys.current.delete(action)
    } catch (cause) {
      setError(message(cause))
    } finally {
      pendingActions.current.delete(action)
      setPendingAction(null)
    }
  }

  const demandQuery = useQuery<CompletePage<DemandItem>>({ queryKey: operationKeys.demand, queryFn: () => fetchCompletePage<DemandItem>('/parts-operations/demand'), retry: false })
  const inventoryQuery = useQuery<CompletePage<InventoryItem>>({ queryKey: operationKeys.inventory, queryFn: () => fetchCompletePage<InventoryItem>('/inventory'), retry: false })
  const poQuery = useQuery<CompletePage<PurchaseOrder>>({ queryKey: operationKeys.purchaseOrders, queryFn: () => fetchCompletePage<PurchaseOrder>('/parts-operations/purchase-orders'), retry: false })
  const returnsQuery = useQuery<CompletePage<ReturnItem>>({ queryKey: operationKeys.returns, queryFn: () => fetchCompletePage<ReturnItem>('/parts-operations/returns'), retry: false })
  const coresQuery = useQuery<CompletePage<Core>>({ queryKey: operationKeys.cores, queryFn: () => fetchCompletePage<Core>('/parts-operations/cores'), retry: false })
  const activityQuery = useQuery<CompletePage<Movement>>({ queryKey: operationKeys.activity, queryFn: () => fetchCompletePage<Movement>('/parts-operations/activity'), retry: false })
  const poDetail = useQuery<PurchaseOrderDetail>({ queryKey: ['parts-operations', 'purchase-order', selectedPOId], queryFn: async () => (await api.get(`/parts-operations/purchase-orders/${selectedPOId}`)).data, enabled: Boolean(selectedPOId), retry: false })
  const returnDetail = useQuery<ReturnDetail>({ queryKey: ['parts-operations', 'return', selectedReturnId], queryFn: async () => (await api.get(`/parts-operations/returns/${selectedReturnId}`)).data, enabled: Boolean(selectedReturnId), retry: false })

  const demand = demandQuery.data?.items ?? EMPTY_DEMAND
  const inventory = inventoryQuery.data?.items ?? EMPTY_INVENTORY
  const purchaseOrders = poQuery.data?.items ?? EMPTY_PURCHASE_ORDERS
  const returns = returnsQuery.data?.items ?? EMPTY_RETURNS
  const cores = coresQuery.data?.items ?? EMPTY_CORES
  const activity = activityQuery.data?.items ?? EMPTY_ACTIVITY
  const filteredDemand = useMemo(() => demand.filter((item) => {
    const matchesSearch = `${item.name} ${item.sku} ${item.preferred_supplier?.name || ''}`.toLocaleLowerCase().includes(demandSearch.trim().toLocaleLowerCase())
    const matchesFilter = demandFilter === 'all'
      || (demandFilter === 'repair-shortages' && item.repair_shortage_packages > 0)
      || (demandFilter === 'replenishment' && item.shelf_replenishment_packages > 0)
      || (demandFilter === 'unlinked' && item.state === 'unlinked')
    return matchesSearch && matchesFilter
  }), [demand, demandFilter, demandSearch])
  const filteredInventory = useMemo(() => {
    const search = inventorySearch.trim().toLocaleLowerCase()
    const visible = inventory.filter((item) => {
      const searchable = `${item.name} ${item.sku} ${item.supplier_name || ''} ${item.location || ''}`.toLocaleLowerCase()
      return searchable.includes(search) && matchesInventoryStockFilter(item, inventoryStockFilter)
    })
    return inventorySort === 'catalog' ? visible : [...visible].sort((left, right) => compareInventory(left, right, inventorySort))
  }, [inventory, inventorySearch, inventorySort, inventoryStockFilter])
  const selectedDemand = filteredDemand.find((item) => item.inventory_id === selectedDemandId) || null
  const selectedInventory = filteredInventory.find((item) => item.id === selectedInventoryId) || null
  const selectedCore = cores.find((item) => item.id === selectedCoreId) || null
  const isLoading = demandQuery.isLoading || inventoryQuery.isLoading || poQuery.isLoading || returnsQuery.isLoading || coresQuery.isLoading || activityQuery.isLoading

  const announce = (message: string) => setSelectionNotice(message)
  const demandAnnouncement = (item: DemandItem) => `${item.name} selected. ${item.recommended_order_packages} packages recommended.`
  const inventoryAnnouncement = (item: InventoryItem) => `${item.name} selected. ${item.stock_quantity} on hand. ${inventoryStockLabel(item)}.`
  const purchaseOrderAnnouncement = (item: PurchaseOrder) => `${item.po_number} selected. ${item.remaining_quantity} packages awaiting receipt.`
  const returnAnnouncement = (item: ReturnItem) => `${item.return_number} selected. ${humanize(item.status)}.`
  const coreAnnouncement = (item: Core) => `${item.inventory?.name || 'Core obligation'} selected. ${humanize(item.status)}.`

  const selectTab = (next: OperationsTab) => {
    setTab(next)
    if (next === 'demand') {
      const first = filteredDemand[0] || null
      setSelectedDemandId(first?.inventory_id ?? null)
      setSelectionNotice(first ? demandAnnouncement(first) : '')
    } else if (next === 'inventory') {
      const first = filteredInventory[0] || null
      setSelectedInventoryId(first?.id ?? null)
      setSelectionNotice(first ? inventoryAnnouncement(first) : '')
    } else if (next === 'purchase-orders') {
      const first = purchaseOrders[0] || null
      setSelectedPOId(first?.id ?? null)
      setSelectionNotice(first ? purchaseOrderAnnouncement(first) : '')
    } else if (next === 'returns-cores') {
      const first = returns[0] || null
      setCustodyView('returns')
      setSelectedReturnId(first?.id ?? null)
      setSelectionNotice(first ? returnAnnouncement(first) : '')
    } else {
      setSelectionNotice('')
    }
  }
  const selectCustodyView = (next: 'returns' | 'cores') => {
    setCustodyView(next)
    if (next === 'returns') {
      const first = returns[0] || null
      setSelectedReturnId(first?.id ?? null)
      setSelectionNotice(first ? returnAnnouncement(first) : '')
    } else {
      const first = cores[0] || null
      setSelectedCoreId(first?.id ?? null)
      setSelectionNotice(first ? coreAnnouncement(first) : '')
    }
  }
  const moveTab = (event: KeyboardEvent<HTMLButtonElement>, current: OperationsTab) => {
    const index = tabs.findIndex((item) => item.id === current)
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : index + delta
    if (!delta && event.key !== 'Home' && event.key !== 'End') return
    event.preventDefault()
    const next = tabs[(nextIndex + tabs.length) % tabs.length].id
    document.getElementById(`parts-tab-${next}`)?.focus()
    selectTab(next)
  }

  useLayoutEffect(() => {
    if (tab !== 'demand' || demandQuery.isLoading || demandQuery.isError) return
    const nextId = reconcileVisibleId(selectedDemandId, filteredDemand, (item) => item.inventory_id)
    if (nextId === selectedDemandId) return
    setSelectedDemandId(nextId)
    const next = filteredDemand.find((item) => item.inventory_id === nextId)
    setSelectionNotice(next ? demandAnnouncement(next) : '')
  }, [demandQuery.isError, demandQuery.isLoading, filteredDemand, selectedDemandId, tab])

  useLayoutEffect(() => {
    if (tab !== 'inventory' || inventoryQuery.isLoading || inventoryQuery.isError) return
    const nextId = reconcileVisibleId(selectedInventoryId, filteredInventory, (item) => item.id)
    if (nextId === selectedInventoryId) return
    setSelectedInventoryId(nextId)
    const next = filteredInventory.find((item) => item.id === nextId)
    setSelectionNotice(next ? inventoryAnnouncement(next) : '')
  }, [filteredInventory, inventoryQuery.isError, inventoryQuery.isLoading, selectedInventoryId, tab])

  useLayoutEffect(() => {
    if (tab !== 'purchase-orders' || poQuery.isLoading || poQuery.isError) return
    const nextId = reconcileVisibleId(selectedPOId, purchaseOrders, (item) => item.id)
    if (nextId === selectedPOId) return
    setSelectedPOId(nextId)
    const next = purchaseOrders.find((item) => item.id === nextId)
    setSelectionNotice(next ? purchaseOrderAnnouncement(next) : '')
  }, [poQuery.isError, poQuery.isLoading, purchaseOrders, selectedPOId, tab])

  useLayoutEffect(() => {
    if (tab !== 'returns-cores' || custodyView !== 'returns' || returnsQuery.isLoading || returnsQuery.isError) return
    const nextId = reconcileVisibleId(selectedReturnId, returns, (item) => item.id)
    if (nextId === selectedReturnId) return
    setSelectedReturnId(nextId)
    const next = returns.find((item) => item.id === nextId)
    setSelectionNotice(next ? returnAnnouncement(next) : '')
  }, [custodyView, returns, returnsQuery.isError, returnsQuery.isLoading, selectedReturnId, tab])

  useLayoutEffect(() => {
    if (tab !== 'returns-cores' || custodyView !== 'cores' || coresQuery.isLoading || coresQuery.isError) return
    const nextId = reconcileVisibleId(selectedCoreId, cores, (item) => item.id)
    if (nextId === selectedCoreId) return
    setSelectedCoreId(nextId)
    const next = cores.find((item) => item.id === nextId)
    setSelectionNotice(next ? coreAnnouncement(next) : '')
  }, [cores, coresQuery.isError, coresQuery.isLoading, custodyView, selectedCoreId, tab])

  const updateDemandSearch = (value: string) => setDemandSearch(value)
  const updateDemandFilter = (value: DemandFilter) => setDemandFilter(value)
  const updateInventorySearch = (value: string) => setInventorySearch(value)
  const updateInventoryFilter = (value: InventoryStockFilter) => setInventoryStockFilter(value)
  const updateInventorySort = (value: InventorySort) => setInventorySort(value)
  const resetInventoryView = () => {
    setInventorySearch('')
    setInventoryStockFilter('all')
    setInventorySort('catalog')
  }

  return <section className="db-parts-operations" aria-labelledby="parts-operations-title">
    <div className="db-parts-operations__top">
      <header className="db-parts-operations__header">
        <div>
          <h1 id="parts-operations-title">Supply, stock & custody</h1>
          <p>Review demand, purchasing and receipts, stock activity, or return and core custody in the selected area.</p>
        </div>
        <div className="db-parts-operations__metrics" aria-label="Parts operations summary">
          <Metric label="Low stock" value={summary.low_stock_count} />
          <Metric label="Open purchase orders" value={summary.open_purchase_order_count} />
        </div>
      </header>

      <div className="db-parts-operations__tabs-wrap">
        <div className="db-parts-operations__tabs" role="tablist" aria-label="Parts Operations areas" aria-describedby="parts-tabs-scroll-hint">
        {tabs.map(({ id, label, icon: Icon }) => <button id={`parts-tab-${id}`} key={id} type="button" role="tab" tabIndex={tab === id ? 0 : -1} aria-selected={tab === id} aria-controls={`parts-panel-${id}`} onKeyDown={(event) => moveTab(event, id)} onClick={() => selectTab(id)} className={tab === id ? 'is-selected' : ''}>
          <Icon aria-hidden="true" />{label}
        </button>)}
        </div>
        <p id="parts-tabs-scroll-hint" className="db-parts-operations__tabs-hint">Swipe to see all areas. Arrow keys move the selected area.</p>
      </div>

      {notice && <p className="db-parts-operations__notice" role="status">{notice}</p>}
      {error && <div className="db-parts-operations__error" role="alert"><span>{error}</span><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}
      {isLoading && <p className="db-parts-operations__loading" role="status">Loading current parts operations…</p>}
    </div>

    <div className="db-parts-operations__content">
      {tab === 'demand' && (demandQuery.isError ? <PanelFailure label="Demand could not be loaded." onRetry={() => void demandQuery.refetch()} /> : <section id="parts-panel-demand" className="db-parts-operations__panel" role="tabpanel" aria-label="Demand"><p className="db-parts-operations__panel-context">Review shortages, replenishment, and unlinked demand before creating a draft purchase order.</p><DemandPanel demand={filteredDemand} totalDemand={demandQuery.data?.total ?? demand.length} inventory={inventory} imageBranding={partImageBranding} canMutate={canMutate} selected={selectedDemand} query={demandSearch} filter={demandFilter} pending={pendingAction === `po-create-${selectedDemand?.inventory_id}`} onQuery={updateDemandSearch} onFilter={updateDemandFilter} onSelect={(item) => { setSelectedDemandId(item.inventory_id); announce(demandAnnouncement(item)) }} onCreate={async (body) => call(`po-create-${body.inventoryId}`, (key) => api.post('/parts-operations/purchase-orders', body.payload, { headers: { 'Idempotency-Key': key } }), 'Draft purchase order created.')} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} /></section>)}
      {tab === 'inventory' && (inventoryQuery.isError ? <PanelFailure label="Inventory could not be loaded." onRetry={() => void inventoryQuery.refetch()} /> : <section id="parts-panel-inventory" className="db-parts-operations__panel" role="tabpanel" aria-label="Inventory"><p className="db-parts-operations__panel-context">Review on-hand stock, incoming supply, and recent ledger activity for the selected catalog item.</p><InventoryPanel inventory={filteredInventory} totalInventory={inventoryQuery.data?.total ?? inventory.length} imageBranding={partImageBranding} activity={activity} activityError={activityQuery.isError} onRetryActivity={() => void activityQuery.refetch()} selected={selectedInventory} query={inventorySearch} filter={inventoryStockFilter} sort={inventorySort} onQuery={updateInventorySearch} onFilter={updateInventoryFilter} onSort={updateInventorySort} onReset={resetInventoryView} onSelect={(item) => { setSelectedInventoryId(item.id); announce(inventoryAnnouncement(item)) }} /></section>)}
      {tab === 'purchase-orders' && (poQuery.isError ? <PanelFailure label="Purchase orders could not be loaded." onRetry={() => void poQuery.refetch()} /> : <section id="parts-panel-purchase-orders" className="db-parts-operations__panel" role="tabpanel" aria-label="Purchase orders"><p className="db-parts-operations__panel-context">Review supplier approval and receive packages against the selected purchase order.</p><PurchaseOrdersPanel items={purchaseOrders} selectedId={selectedPOId} detail={poDetail.data} detailError={poDetail.isError} onRetryDetail={() => void poDetail.refetch()} canMutate={canMutate} pendingAction={pendingAction} onSelect={(id) => { setSelectedPOId(id); const selected = purchaseOrders.find((item) => item.id === id); if (selected) announce(purchaseOrderAnnouncement(selected)) }} onOpenDemand={() => selectTab('demand')} onSubmit={(po) => call(`po-submit-${po.id}`, (key) => api.post(`/parts-operations/purchase-orders/${po.id}/submit`, { expected_version: po.version }, { headers: { 'Idempotency-Key': key } }), 'Purchase order submitted.')} onReceive={(po, lines) => call(`po-receipt-${po.id}`, (key) => api.post(`/parts-operations/purchase-orders/${po.id}/receipts`, { expected_version: po.version, received_at: new Date().toISOString(), lines }, { headers: { 'Idempotency-Key': key } }), 'Receipt recorded and inventory ledger updated.')} /></section>)}
      {tab === 'returns-cores' && <section id="parts-panel-returns-cores" className="db-parts-operations__panel" role="tabpanel" aria-label="Returns and cores"><p className="db-parts-operations__panel-context">Choose supplier returns or core custody, then work the selected record.</p><ReturnsCoresPanel view={custodyView} onView={selectCustodyView} returns={returns} returnsError={returnsQuery.isError} onRetryReturns={() => void returnsQuery.refetch()} cores={cores} coresError={coresQuery.isError} onRetryCores={() => void coresQuery.refetch()} selectedReturn={returnDetail.data} selectedReturnId={selectedReturnId} returnDetailError={returnDetail.isError} onRetryReturnDetail={() => void returnDetail.refetch()} selectedCore={selectedCore} canMutate={canMutate} pendingAction={pendingAction} onSelectReturn={(id) => { setSelectedReturnId(id); const selected = returns.find((item) => item.id === id); if (selected) announce(returnAnnouncement(selected)) }} onSelectCore={(id) => { setSelectedCoreId(id); const selected = cores.find((item) => item.id === id); if (selected) announce(coreAnnouncement(selected)) }} onOpenDemand={() => selectTab('demand')} onRecover={(core) => call(`core-recover-${core.id}`, (key) => api.post(`/parts-operations/cores/${core.id}/recover`, { expected_version: core.version }, { headers: { 'Idempotency-Key': key } }), 'Core recovery recorded.')} onCreateCoreReturn={(core) => call(`core-return-${core.id}`, (key) => api.post('/parts-operations/returns', { kind: 'core', supplier_id: core.supplier_id, reason: 'Core return', lines: [{ core_obligation_id: core.id, quantity: core.quantity, expected_credit: '0.00' }] }, { headers: { 'Idempotency-Key': key } }), 'Core return draft created.')} onReturnAction={(row, action) => call(`return-${action}-${row.id}`, (key) => api.post(`/parts-operations/returns/${row.id}/${action}`, { expected_version: row.version, ...(action === 'reverse' ? { reason: 'Return correction' } : {}) }, { headers: { 'Idempotency-Key': key } }), action === 'reverse' ? 'Return reversal recorded.' : `Return ${action}ed.`)} /></section>}
      {tab === 'activity' && (activityQuery.isError ? <PanelFailure label="Stock activity could not be loaded." onRetry={() => void activityQuery.refetch()} /> : <section id="parts-panel-activity" className="db-parts-operations__panel" role="tabpanel" aria-label="Activity"><p className="db-parts-operations__panel-context">Read the immutable stock ledger to understand what changed inventory and when.</p><ActivityPanel movements={activity} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} /></section>)}
    </div>

    <footer className="db-parts-operations__footer"><Link to="/dashboard/garage/suppliers">Manage suppliers</Link><span>Purchase attachments and vendor integrations are not available in this release.</span></footer>
    <p className="sr-only" data-testid="parts-selection-status" role="status" aria-live="polite" aria-atomic="true">{selectionNotice}</p>
  </section>
}

function Metric({ label, value }: { label: string; value: number }) { return <div><strong>{value}</strong><span>{label}</span></div> }

function MasterDetail({ listKey, selectedRowId, listLabel, toolbar, list, detail }: { listKey: string; selectedRowId: string | null; listLabel: string; toolbar?: ReactNode; list: ReactNode; detail: ReactNode }) {
  const [rovingIndex, setRovingIndex] = useState<number | null>(null)
  const rovingContextKey = `${listKey}\u0000${selectedRowId || ''}`
  const [rovingListKey, setRovingListKey] = useState(rovingContextKey)
  const activeRovingIndex = rovingListKey === rovingContextKey ? rovingIndex : null
  const rovedList = Children.map(list, (child, index) => {
    if (!isValidElement<{ 'data-parts-row'?: string; tabIndex?: number }>(child) || !child.props['data-parts-row']) return child
    return cloneElement(child, { tabIndex: activeRovingIndex === null ? child.props.tabIndex : activeRovingIndex === index ? 0 : -1 })
  })
  return <div className="db-parts-operations__split">
    <section className="db-parts-operations__list-pane" tabIndex={0} role="region" aria-label={listLabel}>
      {toolbar}
      <div className="db-parts-operations__list" role="group" aria-label={`${listLabel} rows`} onKeyDown={(event) => moveRovingRowFocus(event, (index) => { setRovingListKey(rovingContextKey); setRovingIndex(index) })}>{rovedList}</div>
    </section>
    <aside className="db-parts-operations__detail" tabIndex={0} role="region" aria-label={`${listLabel} detail`}>{detail}</aside>
  </div>
}

function moveRovingRowFocus(event: KeyboardEvent<HTMLDivElement>, setRovingIndex: (index: number) => void) {
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  const rows = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[data-parts-row]:not(:disabled)'))
  if (!rows.length) return
  const current = event.target instanceof HTMLButtonElement ? rows.indexOf(event.target) : -1
  const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length
  event.preventDefault()
  setRovingIndex(nextIndex)
  rows[nextIndex].focus()
}

function DetailHeader({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="db-parts-operations__detail-header"><h2>{title}</h2>{children}</div>
}

function initialPartImageStage(partSrc: string | null | undefined, logoSrc: string | null | undefined): PartImageStage {
  if (partSrc) return 'part'
  if (logoSrc) return 'logo'
  return 'icon'
}

function PartImage({ partSrc, branding, partName, variant }: { partSrc: string | null | undefined; branding: PartImageBranding; partName: string; variant: 'row' | 'detail' }) {
  const [stage, setStage] = useState<PartImageStage>(() => initialPartImageStage(partSrc, branding.logoUrl))
  const imageSrc = stage === 'part' ? partSrc : stage === 'logo' ? branding.logoUrl : null
  const decorative = variant === 'row'
  const imageAlt = decorative
    ? ''
    : stage === 'part'
      ? `${partName} part photo`
      : `${branding.name || 'Company'} logo placeholder for ${partName}`
  const className = `db-parts-operations__part-image db-parts-operations__part-image--${variant}${stage === 'logo' ? ' is-logo-placeholder' : ''}`
  const fail = () => setStage((current) => {
    if (current === 'part' && branding.logoUrl && branding.logoUrl !== partSrc) return 'logo'
    return 'icon'
  })

  if (!imageSrc || stage === 'icon') {
    return <span
      className={className}
      aria-hidden={decorative ? 'true' : undefined}
      role={decorative ? undefined : 'img'}
      aria-label={decorative ? undefined : `No image available for ${partName}`}
      data-image-source="icon"
    >
      <Package aria-hidden="true" data-testid={variant === 'row' ? 'part-thumbnail-fallback' : 'part-detail-fallback'} />
    </span>
  }

  return <span className={className} aria-hidden={decorative ? 'true' : undefined} data-image-source={stage}>
    <img src={imageSrc} alt={imageAlt} loading={variant === 'row' ? 'lazy' : 'eager'} decoding="async" onError={fail} />
  </span>
}

function SelectedPartHeader({ title, meta, partSrc, branding }: { title: string; meta: string; partSrc: string | null | undefined; branding: PartImageBranding }) {
  return <div className="db-parts-operations__selected-part-header">
    <div><h2>{title}</h2><p>{meta}</p></div>
    <PartImage key={`${title}:${partSrc || ''}:${branding.logoUrl || ''}`} partSrc={partSrc} branding={branding} partName={title} variant="detail" />
  </div>
}

function DemandPanel({ demand, totalDemand, inventory, imageBranding, canMutate, selected, query, filter, pending, onQuery, onFilter, onSelect, onCreate, onOpenRepair }: { demand: DemandItem[]; totalDemand: number; inventory: InventoryItem[]; imageBranding: PartImageBranding; canMutate: boolean; selected: DemandItem | null; query: string; filter: DemandFilter; pending: boolean; onQuery: (value: string) => void; onFilter: (value: DemandFilter) => void; onSelect: (item: DemandItem) => void; onCreate: (payload: { inventoryId: string; payload: unknown }) => Promise<void>; onOpenRepair: (id: string) => void }) {
  const [poNumber, setPoNumber] = useState('')
  const [quantity, setQuantity] = useState('')
  const [unitCost, setUnitCost] = useState('')
  const activeInventory = inventory.find((item) => item.id === selected?.inventory_id)
  const choose = (item: DemandItem) => { onSelect(item); setPoNumber(''); setQuantity(String(item.recommended_order_packages)); setUnitCost(String(inventory.find((entry) => entry.id === item.inventory_id)?.cost || '')) }
  useLayoutEffect(() => {
    setPoNumber('')
    setQuantity(selected ? String(selected.recommended_order_packages) : '')
    setUnitCost(selected ? String(activeInventory?.cost || '') : '')
  }, [activeInventory?.cost, selected])
  const create = async () => {
    if (!selected || !activeInventory || !selected.preferred_supplier) return
    await onCreate({ inventoryId: selected.inventory_id, payload: { po_number: poNumber.trim(), supplier_id: selected.preferred_supplier.id, lines: [{ inventory_id: selected.inventory_id, ordered_quantity: Number(quantity), unit_cost: Number(unitCost) }] } })
  }
  return <MasterDetail listKey={demand.map((item) => item.inventory_id).join('|')} selectedRowId={selected?.inventory_id ?? null}
    listLabel={`Demand results, ${demand.length} shown of ${totalDemand}`}
    toolbar={<div className="db-parts-operations__list-toolbar"><label className="db-parts-operations__search"><Search aria-hidden="true" /><span className="sr-only">Search demand</span><input aria-label="Search demand" type="search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search part, SKU, or supplier" /></label><div className="db-parts-operations__filters" aria-label="Demand triage">{demandFilters.map((item) => <button type="button" aria-pressed={filter === item.id} className={filter === item.id ? 'is-selected' : ''} key={item.id} onClick={() => onFilter(item.id)}>{item.label}</button>)}</div><p>{demand.length === totalDemand ? `${totalDemand} demand items` : `${demand.length} of ${totalDemand} demand items`}</p></div>}
    list={demand.length ? demand.map((item, index) => { const active = selected?.inventory_id === item.inventory_id; const imageUrl = inventory.find((entry) => entry.id === item.inventory_id)?.image_url; return <button data-parts-row={item.inventory_id} type="button" aria-current={active ? 'true' : undefined} tabIndex={active || (!selected && index === 0) ? 0 : -1} className={active ? 'is-active' : ''} key={item.inventory_id} onClick={() => choose(item)}><span className="db-parts-operations__row-identity"><PartImage key={`${item.inventory_id}:${imageUrl || ''}:${imageBranding.logoUrl || ''}`} partSrc={imageUrl} branding={imageBranding} partName={item.name} variant="row" /><span className="db-parts-operations__row-copy"><strong>{item.name}</strong><small>{item.sku} · {item.stock_quantity} on hand · {item.recommended_order_packages} recommended</small></span></span><Status status={item.state} /></button> }) : <Empty label="No demand matches this search and triage view." />}
    detail={selected ? <><SelectedPartHeader title={selected.name} meta={`${selected.sku} · Preferred supplier: ${selected.preferred_supplier?.name || 'Not set'}`} partSrc={activeInventory?.image_url} branding={imageBranding} /><dl className="db-parts-operations__facts"><div><dt>Repair shortage</dt><dd>{selected.repair_shortage_packages} packages</dd></div><div><dt>Shelf replenishment</dt><dd>{selected.shelf_replenishment_packages} packages</dd></div><div><dt>Open supply</dt><dd>{selected.open_supply_packages} packages</dd></div><div><dt>Recommended order</dt><dd>{selected.recommended_order_packages} packages</dd></div></dl><div className="db-parts-operations__sources"><h3>Why this is needed</h3>{selected.sources.map((source, index) => <div key={`${source.type}-${index}`}>{source.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(source.repair_order_id!)}>Repair order {source.order_number}</button> : <span>{humanize(source.type)}</span>}<strong>{source.packages} pkg</strong></div>)}</div>{canMutate && selected.state !== 'unlinked' && selected.recommended_order_packages > 0 && selected.preferred_supplier ? <form className="db-parts-operations__form" onSubmit={(event) => { event.preventDefault(); void create() }}><h3>Create draft purchase order</h3><label>PO number<input disabled={pending} required minLength={1} value={poNumber} onChange={(event) => setPoNumber(event.target.value)} placeholder="PO-000302" /></label><div><label>Packages<input disabled={pending} required min={1} max={999} type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label>Unit cost<input disabled={pending} required min="0.01" step="0.01" type="number" value={unitCost} onChange={(event) => setUnitCost(event.target.value)} /></label></div><button className="db-parts-operations__primary" type="submit" disabled={pending}>{pending ? 'Creating draft PO…' : 'Create draft PO'}</button></form> : <p className="db-parts-operations__hint">{selected.state === 'unlinked' ? 'Promote this placeholder in the legacy catalog before it can be ordered.' : !canMutate ? 'Read-only access: a shop owner or admin can create the purchase order.' : 'Set a preferred supplier in the legacy catalog before creating a PO.'}</p>}</> : <Empty label="Select a demand item to inspect its repair and replenishment sources." />}
  />
}

function InventoryPanel({ inventory, totalInventory, imageBranding, activity, activityError, onRetryActivity, selected, query, filter, sort, onQuery, onFilter, onSort, onReset, onSelect }: { inventory: InventoryItem[]; totalInventory: number; imageBranding: PartImageBranding; activity: Movement[]; activityError: boolean; onRetryActivity: () => void; selected: InventoryItem | null; query: string; filter: InventoryStockFilter; sort: InventorySort; onQuery: (value: string) => void; onFilter: (value: InventoryStockFilter) => void; onSort: (value: InventorySort) => void; onReset: () => void; onSelect: (item: InventoryItem) => void }) {
  const selectedActivity = activity.filter((row) => row.inventory?.id === selected?.id).slice(0, 8)
  const hasActiveView = Boolean(query.trim()) || filter !== 'all' || sort !== 'catalog'
  return <MasterDetail listKey={inventory.map((item) => item.id).join('|')} selectedRowId={selected?.id ?? null}
    listLabel={`Inventory results, ${inventory.length} shown of ${totalInventory}`}
    toolbar={<div className="db-parts-operations__list-toolbar"><label className="db-parts-operations__search"><Search aria-hidden="true" /><span className="sr-only">Search inventory</span><input aria-label="Search inventory" type="search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search part, SKU, supplier, or location" /></label><div className="db-parts-operations__filters" role="group" aria-label="Inventory stock filter">{inventoryStockFilters.map((item) => <button type="button" aria-pressed={filter === item.id} className={filter === item.id ? 'is-selected' : ''} key={item.id} onClick={() => onFilter(item.id)}>{item.label}</button>)}</div><label className="db-parts-operations__sort"><span>Sort inventory</span><select value={sort} onChange={(event) => onSort(event.target.value as InventorySort)}>{inventorySorts.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><p aria-live="polite">{inventory.length === totalInventory ? `${totalInventory} inventory items` : `${inventory.length} of ${totalInventory} inventory items`}</p></div>}
    list={inventory.length ? inventory.map((item, index) => { const active = selected?.id === item.id; return <button data-parts-row={item.id} type="button" aria-current={active ? 'true' : undefined} tabIndex={active || (!selected && index === 0) ? 0 : -1} className={active ? 'is-active' : ''} key={item.id} onClick={() => onSelect(item)}><span className="db-parts-operations__row-identity"><PartImage key={`${item.id}:${item.image_url || ''}:${imageBranding.logoUrl || ''}`} partSrc={item.image_url} branding={imageBranding} partName={item.name} variant="row" /><span className="db-parts-operations__row-copy"><strong>{item.name}</strong><small>{item.sku} · {item.supplier_name || 'No supplier'} · {item.location || 'No location'}</small></span></span><span className="db-parts-operations__stock"><strong>{item.stock_quantity} on hand</strong><small>{inventoryStockLabel(item)}</small></span></button> }) : <Empty label="No inventory items match this view." action={hasActiveView ? <button className="db-parts-operations__inline-action" type="button" onClick={onReset}>Reset inventory view</button> : undefined} />}
    detail={selected ? <><SelectedPartHeader title={selected.name} meta={`${selected.sku} · ${selected.location || 'No location'} · ${selected.unit_type}`} partSrc={selected.image_url} branding={imageBranding} /><dl className="db-parts-operations__facts"><div><dt>On hand</dt><dd>{selected.stock_quantity}</dd></div><div><dt>On order</dt><dd>{selected.on_order_quantity}</dd></div><div><dt>Reorder level</dt><dd>{selected.reorder_level}</dd></div><div><dt>Current WAC</dt><dd>${selected.cost}</dd></div></dl><div className="db-parts-operations__sources"><h3>Recent stock activity</h3>{activityError ? <InlineFailure label="Recent stock activity could not be loaded." onRetry={onRetryActivity} /> : selectedActivity.length ? selectedActivity.map((row) => <div key={row.id}><span>{humanize(row.movement_type)}</span><strong>Balance {row.balance_after}</strong></div>) : <p className="db-parts-operations__hint">No ledger activity is loaded for this item.</p>}</div><p className="db-parts-operations__hint">Catalog fields remain in the existing inventory editor; this operating view reads the same tenant catalog and ledger.</p></> : <Empty label="Select an inventory item to review stock and activity." />}
  />
}

function PurchaseOrdersPanel({ items, selectedId, detail, detailError, onRetryDetail, canMutate, pendingAction, onSelect, onOpenDemand, onSubmit, onReceive }: { items: PurchaseOrder[]; selectedId: string | null; detail: PurchaseOrderDetail | undefined; detailError: boolean; onRetryDetail: () => void; canMutate: boolean; pendingAction: string | null; onSelect: (id: string) => void; onOpenDemand: () => void; onSubmit: (po: PurchaseOrderDetail) => Promise<void>; onReceive: (po: PurchaseOrderDetail, lines: Array<{ purchase_order_line_id: string; quantity: number; unit_cost: number }>) => Promise<void> }) {
  const [receiptQty, setReceiptQty] = useState<Record<string, string>>({})
  const [receiptCost, setReceiptCost] = useState<Record<string, string>>({})
  const receive = async () => { if (!detail) return; const lines = detail.lines.map((line) => ({ purchase_order_line_id: line.id, quantity: Number(receiptQty[line.id] || 0), unit_cost: Number(receiptCost[line.id] || line.unit_cost) })).filter((line) => line.quantity > 0); if (lines.length) await onReceive(detail, lines) }
  return <MasterDetail listKey={items.map((item) => item.id).join('|')} selectedRowId={selectedId}
    listLabel="Purchase orders"
    list={items.length ? items.map((po, index) => { const active = selectedId === po.id; return <button data-parts-row={po.id} type="button" aria-current={active ? 'true' : undefined} tabIndex={active || (!selectedId && index === 0) ? 0 : -1} className={active ? 'is-active' : ''} key={po.id} onClick={() => onSelect(po.id)}><span><strong>{po.po_number}</strong><small>{po.supplier?.name || 'Supplier'} · {po.remaining_quantity} packages awaiting receipt</small></span><Status status={po.status} /></button> }) : <Empty label="No purchase orders are awaiting work." action={<button className="db-parts-operations__inline-action" type="button" onClick={onOpenDemand}>Review demand</button>} />}
    detail={detailError ? <InlineFailure label="This purchase order could not be loaded." onRetry={onRetryDetail} /> : detail ? <><DetailHeader title={detail.po_number}><p>{detail.supplier?.name || 'Supplier'} · {humanize(detail.status)} · {detail.remaining_quantity} packages awaiting receipt</p></DetailHeader><div className="db-parts-operations__line-list">{detail.lines.map((line) => <div key={line.id}><span><strong>{line.description}</strong><small>{line.sku} · {line.received_quantity}/{line.ordered_quantity} received · ${line.unit_cost}</small></span>{canMutate && ['submitted', 'partially_received'].includes(detail.status) && line.ordered_quantity > line.received_quantity && <span className="db-parts-operations__receipt-inputs"><input disabled={pendingAction === `po-receipt-${detail.id}`} aria-label={`Receive quantity for ${line.sku}`} type="number" min={0} max={line.ordered_quantity - line.received_quantity} value={receiptQty[line.id] || ''} onChange={(event) => setReceiptQty((old) => ({ ...old, [line.id]: event.target.value }))} placeholder="Qty" /><input disabled={pendingAction === `po-receipt-${detail.id}`} aria-label={`Receipt unit cost for ${line.sku}`} type="number" min="0.01" step="0.01" value={receiptCost[line.id] ?? line.unit_cost} onChange={(event) => setReceiptCost((old) => ({ ...old, [line.id]: event.target.value }))} /></span>}</div>)}</div>{canMutate && detail.status === 'draft' && <button disabled={pendingAction === `po-submit-${detail.id}`} className="db-parts-operations__primary" type="button" onClick={() => void onSubmit(detail)}>{pendingAction === `po-submit-${detail.id}` ? 'Submitting…' : 'Submit purchase order'}</button>}{canMutate && ['submitted', 'partially_received'].includes(detail.status) && <button disabled={pendingAction === `po-receipt-${detail.id}`} className="db-parts-operations__primary" type="button" onClick={() => void receive()}>{pendingAction === `po-receipt-${detail.id}` ? 'Recording receipt…' : 'Record receipt'}</button>}{!canMutate && <p className="db-parts-operations__hint">Read-only access. Owners and admins can submit and receive this PO.</p>}</> : selectedId ? <p className="db-parts-operations__hint" role="status">Loading purchase order…</p> : <Empty label="Select a purchase order to view remaining quantities and receive stock." />}
  />
}

function ReturnsCoresPanel({ view, onView, returns, returnsError, onRetryReturns, cores, coresError, onRetryCores, selectedReturn, selectedReturnId, returnDetailError, onRetryReturnDetail, selectedCore, canMutate, pendingAction, onSelectReturn, onSelectCore, onOpenDemand, onRecover, onCreateCoreReturn, onReturnAction }: { view: 'returns' | 'cores'; onView: (view: 'returns' | 'cores') => void; returns: ReturnItem[]; returnsError: boolean; onRetryReturns: () => void; cores: Core[]; coresError: boolean; onRetryCores: () => void; selectedReturn: ReturnDetail | undefined; selectedReturnId: string | null; returnDetailError: boolean; onRetryReturnDetail: () => void; selectedCore: Core | null; canMutate: boolean; pendingAction: string | null; onSelectReturn: (id: string) => void; onSelectCore: (id: string) => void; onOpenDemand: () => void; onRecover: (core: Core) => Promise<void>; onCreateCoreReturn: (core: Core) => Promise<void>; onReturnAction: (row: ReturnDetail, action: 'submit' | 'ship' | 'credit' | 'reverse') => Promise<void> }) {
  const moveView = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const target = event.key === 'Home' || event.key === 'ArrowLeft' ? 'returns' : 'cores'
    onView(target)
    document.getElementById(`parts-${target}-tab`)?.focus()
  }
  const subpanelId = view === 'returns' ? 'parts-returns-panel' : 'parts-cores-panel'
  const subtabId = view === 'returns' ? 'parts-returns-tab' : 'parts-cores-tab'
  const returnAction = selectedReturn ? `return-${selectedReturn.status === 'draft' ? 'submit' : selectedReturn.status === 'submitted' ? 'ship' : selectedReturn.status === 'shipped' ? 'credit' : 'reverse'}-${selectedReturn.id}` : ''
  return <div className="db-parts-operations__subsurface">
    <div className="db-parts-operations__subtabs" role="tablist" aria-label="Return and core custody view">
      <button id="parts-returns-tab" type="button" role="tab" tabIndex={view === 'returns' ? 0 : -1} aria-controls="parts-returns-panel" aria-selected={view === 'returns'} onKeyDown={moveView} onClick={() => onView('returns')}>Returns</button>
      <button id="parts-cores-tab" type="button" role="tab" tabIndex={view === 'cores' ? 0 : -1} aria-controls="parts-cores-panel" aria-selected={view === 'cores'} onKeyDown={moveView} onClick={() => onView('cores')}>Cores</button>
    </div>
    <section id={subpanelId} className="db-parts-operations__subpanel" role="tabpanel" aria-labelledby={subtabId}>
      {view === 'returns'
        ? returnsError ? <PanelFailure label="Vendor returns could not be loaded." onRetry={onRetryReturns} />
          : <MasterDetail listKey={returns.map((item) => item.id).join('|')} selectedRowId={selectedReturnId} listLabel="Vendor returns" list={returns.length ? returns.map((row, index) => { const active = selectedReturnId === row.id; return <button data-parts-row={row.id} type="button" aria-current={active ? 'true' : undefined} tabIndex={active || (!selectedReturnId && index === 0) ? 0 : -1} className={active ? 'is-active' : ''} key={row.id} onClick={() => onSelectReturn(row.id)}><span><strong>{row.return_number}</strong><small>{row.kind} · {row.supplier?.name || 'Supplier'} · {row.total_quantity} packages</small></span><Status status={row.status} /></button> }) : <Empty label="No vendor returns are ready to process." action={<button className="db-parts-operations__inline-action" type="button" onClick={onOpenDemand}>Review demand</button>} />} detail={returnDetailError ? <InlineFailure label="This vendor return could not be loaded." onRetry={onRetryReturnDetail} /> : selectedReturn ? <><DetailHeader title={selectedReturn.return_number}><p>{selectedReturn.supplier?.name || 'Supplier'} · {selectedReturn.reason} · {humanize(selectedReturn.status)}</p></DetailHeader>{selectedReturn.lines.map((line) => <p key={line.id} className="db-parts-operations__compact-row">{line.inventory?.sku || 'Inventory'} · {line.quantity} packages · {humanize(line.source.type)}</p>)}{canMutate && selectedReturn.status === 'draft' && <button disabled={pendingAction === returnAction} className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'submit')}>{pendingAction === returnAction ? 'Submitting…' : 'Submit return'}</button>}{canMutate && selectedReturn.status === 'submitted' && <button disabled={pendingAction === returnAction} className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'ship')}>{pendingAction === returnAction ? 'Marking shipped…' : 'Mark shipped'}</button>}{canMutate && selectedReturn.status === 'shipped' && <button disabled={pendingAction === returnAction} className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'credit')}>{pendingAction === returnAction ? 'Recording credit…' : 'Record vendor credit'}</button>}{canMutate && ['shipped', 'credited'].includes(selectedReturn.status) && <button disabled={pendingAction === returnAction} className="db-parts-operations__secondary" type="button" onClick={() => void onReturnAction(selectedReturn, 'reverse')}>{pendingAction === returnAction ? 'Reversing…' : 'Reverse return'}</button>}</> : selectedReturnId ? <p className="db-parts-operations__hint" role="status">Loading vendor return…</p> : <Empty label="Select a return to inspect its receipt or core origin." />} />
        : coresError ? <PanelFailure label="Core obligations could not be loaded." onRetry={onRetryCores} />
          : <MasterDetail listKey={cores.map((item) => item.id).join('|')} selectedRowId={selectedCore?.id ?? null} listLabel="Core obligations" list={cores.length ? cores.map((row, index) => { const active = selectedCore?.id === row.id; return <button data-parts-row={row.id} type="button" aria-current={active ? 'true' : undefined} tabIndex={active || (!selectedCore && index === 0) ? 0 : -1} className={active ? 'is-active' : ''} key={row.id} onClick={() => onSelectCore(row.id)}><span><strong>{row.inventory?.name || 'Core obligation'}</strong><small>{row.source?.order_number || 'Repair order source'} · {row.quantity} core</small></span><Status status={row.status} /></button> }) : <Empty label="No core obligations require custody action." />} detail={selectedCore ? <><DetailHeader title={selectedCore.inventory?.name || 'Core obligation'}><p>{selectedCore.source?.order_number || 'Repair order source'} · {humanize(selectedCore.status)}</p></DetailHeader>{canMutate && selectedCore.status === 'expected' && <button disabled={pendingAction === `core-recover-${selectedCore.id}`} className="db-parts-operations__primary" type="button" onClick={() => void onRecover(selectedCore)}>{pendingAction === `core-recover-${selectedCore.id}` ? 'Recording recovery…' : 'Record recovered core'}</button>}{canMutate && selectedCore.status === 'on_hand' && selectedCore.supplier_id && <button disabled={pendingAction === `core-return-${selectedCore.id}`} className="db-parts-operations__primary" type="button" onClick={() => void onCreateCoreReturn(selectedCore)}>{pendingAction === `core-return-${selectedCore.id}` ? 'Creating return…' : 'Create core return'}</button>}{!canMutate && <p className="db-parts-operations__hint">Read-only access. Owners and admins manage custody transitions.</p>}</> : <Empty label="Select a core obligation to inspect its repair-order custody." />} />}
    </section>
  </div>
}

function ActivityPanel({ movements, onOpenRepair }: { movements: Movement[]; onOpenRepair: (id: string) => void }) { return <div className="db-parts-operations__activity">{movements.length ? movements.map((row) => <article key={row.id}><div><strong>{row.inventory?.name || 'Inventory movement'}</strong><p>{humanize(row.movement_type)} · balance {row.balance_after} · WAC {row.wac_after ? `$${row.wac_after}` : '—'}</p></div><div>{row.source?.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(row.source!.id)}>{row.source.order_number || 'Open repair order'}<ArrowRight aria-hidden="true" /></button> : <span>{row.source?.receipt_number || row.source?.return_number || 'Opening/manual record'}</span>}<time>{formatDate(row.occurred_at)}</time></div></article>) : <Empty label="No inventory activity yet" />}</div> }

function Status({ status }: { status: string }) { return <span className={`db-parts-operations__status is-${status}`}>{humanize(status)}</span> }
function Empty({ label, action }: { label: string; action?: ReactNode }) { return <div className="db-parts-operations__empty"><p>{label}</p>{action}</div> }
function InlineFailure({ label, onRetry }: { label: string; onRetry: () => void }) { return <div className="db-parts-operations__inline-failure" role="alert"><span>{label}</span><button type="button" onClick={onRetry}>Retry</button></div> }
function PanelFailure({ label, onRetry }: { label: string; onRetry: () => void }) { return <section className="db-parts-operations__panel" role="tabpanel"><div className="db-parts-operations__panel-failure" role="alert"><h2>{label}</h2><p>The rest of the workspace is unchanged. Retry this area when the connection is available.</p><button className="db-parts-operations__secondary" type="button" onClick={onRetry}>Retry</button></div></section> }
