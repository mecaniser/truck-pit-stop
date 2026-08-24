import { useMemo, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowRight, ClipboardList, PackageSearch, RotateCcw, Search } from 'lucide-react'
import api from '@/lib/api'
import type { InventoryItem } from '@/types'
import { useAuthStore } from '@/stores/authStore'

type OperationsTab = 'demand' | 'inventory' | 'purchase-orders' | 'returns-cores' | 'activity'
type DemandFilter = 'all' | 'repair-shortages' | 'replenishment' | 'unlinked'
type Page<T> = { items: T[]; total: number; skip: number; limit: number; has_more: boolean }

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

const tabs: Array<{ id: OperationsTab; label: string; icon: typeof PackageSearch }> = [
  { id: 'demand', label: 'Demand', icon: AlertTriangle },
  { id: 'inventory', label: 'Inventory', icon: PackageSearch },
  { id: 'purchase-orders', label: 'Purchase orders', icon: ClipboardList },
  { id: 'returns-cores', label: 'Returns & cores', icon: RotateCcw },
  { id: 'activity', label: 'Activity', icon: Activity },
]

const workflowSteps: Array<{ label: string; detail: string; tab: OperationsTab }> = [
  { label: 'Demand', detail: 'What must be bought and why.', tab: 'demand' },
  { label: 'Purchase order', detail: 'Source and approve the order.', tab: 'purchase-orders' },
  { label: 'Receive', detail: 'Post received packages to stock.', tab: 'purchase-orders' },
  { label: 'Stock activity', detail: 'Review the immutable stock ledger.', tab: 'activity' },
  { label: 'Return & core', detail: 'Close supplier returns and core custody.', tab: 'returns-cores' },
]

const demandFilters: Array<{ id: DemandFilter; label: string }> = [
  { id: 'all', label: 'All demand' },
  { id: 'repair-shortages', label: 'Repair shortages' },
  { id: 'replenishment', label: 'Replenishment' },
  { id: 'unlinked', label: 'Unlinked' },
]

const EMPTY_DEMAND: DemandItem[] = []
const EMPTY_INVENTORY: InventoryItem[] = []

const operationKeys = {
  summary: ['parts-operations', 'summary'] as const,
  demand: ['parts-operations', 'demand'] as const,
  inventory: ['parts-operations', 'inventory'] as const,
  purchaseOrders: ['parts-operations', 'purchase-orders'] as const,
  returns: ['parts-operations', 'returns'] as const,
  cores: ['parts-operations', 'cores'] as const,
  activity: ['parts-operations', 'activity'] as const,
}

function page<T>(value: Page<T> | T[]): T[] {
  return Array.isArray(value) ? value : value.items
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
    return <div className="db-parts-operations__unavailable" role="alert">Parts Operations is temporarily unavailable. The existing inventory catalog remains available after refresh.</div>
  }
  return <PartsOperationsWorkspace summary={availability.data} />
}

export default function PartsOperationsWorkspace({ summary }: { summary: Summary }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const role = useAuthStore((state) => state.user?.role)
  const canMutate = isMutationRole(role)
  const [tab, setTab] = useState<OperationsTab>('demand')
  const [selectedDemandId, setSelectedDemandId] = useState<string | null>(null)
  const [selectedInventoryId, setSelectedInventoryId] = useState<string | null>(null)
  const [selectedPOId, setSelectedPOId] = useState<string | null>(null)
  const [selectedReturnId, setSelectedReturnId] = useState<string | null>(null)
  const [selectedCoreId, setSelectedCoreId] = useState<string | null>(null)
  const [demandSearch, setDemandSearch] = useState('')
  const [demandFilter, setDemandFilter] = useState<DemandFilter>('all')
  const [inventorySearch, setInventorySearch] = useState('')
  const [selectionNotice, setSelectionNotice] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const moveTab = (event: KeyboardEvent<HTMLButtonElement>, current: OperationsTab) => {
    const index = tabs.findIndex((item) => item.id === current)
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : index + delta
    if (!delta && event.key !== 'Home' && event.key !== 'End') return
    event.preventDefault()
    const next = tabs[(nextIndex + tabs.length) % tabs.length].id
    document.getElementById(`parts-tab-${next}`)?.focus()
    setTab(next)
  }

  const invalidateOperations = () => {
    void queryClient.invalidateQueries({ queryKey: ['parts-operations'] })
    void queryClient.invalidateQueries({ queryKey: ['inventory'] })
  }
  const call = async <T,>(fn: () => Promise<T>, success: string) => {
    setError(null)
    try {
      await fn()
      invalidateOperations()
      setNotice(success)
    } catch (cause) {
      setError(message(cause))
    }
  }

  const demandQuery = useQuery<DemandItem[]>({ queryKey: operationKeys.demand, queryFn: async () => page((await api.get('/parts-operations/demand', { params: { paginated: true, limit: 100 } })).data) })
  const inventoryQuery = useQuery<InventoryItem[]>({ queryKey: operationKeys.inventory, queryFn: async () => page((await api.get('/inventory', { params: { paginated: true, limit: 100 } })).data) })
  const poQuery = useQuery<PurchaseOrder[]>({ queryKey: operationKeys.purchaseOrders, queryFn: async () => page((await api.get('/parts-operations/purchase-orders', { params: { paginated: true, limit: 100 } })).data) })
  const returnsQuery = useQuery<ReturnItem[]>({ queryKey: operationKeys.returns, queryFn: async () => page((await api.get('/parts-operations/returns', { params: { paginated: true, limit: 100 } })).data) })
  const coresQuery = useQuery<Core[]>({ queryKey: operationKeys.cores, queryFn: async () => page((await api.get('/parts-operations/cores', { params: { paginated: true, limit: 100 } })).data) })
  const activityQuery = useQuery<Movement[]>({ queryKey: operationKeys.activity, queryFn: async () => page((await api.get('/parts-operations/activity', { params: { paginated: true, limit: 100 } })).data) })
  const poDetail = useQuery<PurchaseOrderDetail>({ queryKey: ['parts-operations', 'purchase-order', selectedPOId], queryFn: async () => (await api.get(`/parts-operations/purchase-orders/${selectedPOId}`)).data, enabled: Boolean(selectedPOId) })
  const returnDetail = useQuery<ReturnDetail>({ queryKey: ['parts-operations', 'return', selectedReturnId], queryFn: async () => (await api.get(`/parts-operations/returns/${selectedReturnId}`)).data, enabled: Boolean(selectedReturnId) })

  const demand = demandQuery.data ?? EMPTY_DEMAND
  const inventory = inventoryQuery.data ?? EMPTY_INVENTORY
  const purchaseOrders = poQuery.data || []
  const returns = returnsQuery.data || []
  const cores = coresQuery.data || []
  const activity = activityQuery.data || []
  const filteredDemand = useMemo(() => demand.filter((item) => {
    const matchesSearch = `${item.name} ${item.sku} ${item.preferred_supplier?.name || ''}`.toLocaleLowerCase().includes(demandSearch.trim().toLocaleLowerCase())
    const matchesFilter = demandFilter === 'all'
      || (demandFilter === 'repair-shortages' && item.repair_shortage_packages > 0)
      || (demandFilter === 'replenishment' && item.shelf_replenishment_packages > 0)
      || (demandFilter === 'unlinked' && item.state === 'unlinked')
    return matchesSearch && matchesFilter
  }), [demand, demandFilter, demandSearch])
  const filteredInventory = useMemo(() => inventory.filter((item) => `${item.name} ${item.sku} ${item.location || ''}`.toLocaleLowerCase().includes(inventorySearch.trim().toLocaleLowerCase())), [inventory, inventorySearch])
  const selectedDemand = filteredDemand.find((item) => item.inventory_id === selectedDemandId) || filteredDemand[0] || null
  const selectedInventory = filteredInventory.find((item) => item.id === selectedInventoryId) || filteredInventory[0] || null
  const selectedCore = cores.find((item) => item.id === selectedCoreId) || null
  const isLoading = demandQuery.isLoading || inventoryQuery.isLoading || poQuery.isLoading || returnsQuery.isLoading || coresQuery.isLoading || activityQuery.isLoading

  const selectTab = (next: OperationsTab) => setTab(next)
  const announce = (message: string) => setSelectionNotice(message)

  return <section className="db-parts-operations" aria-labelledby="parts-operations-title">
    <div className="db-parts-operations__top">
      <header className="db-parts-operations__header">
        <div>
          <h1 id="parts-operations-title">Supply, stock & custody</h1>
          <p>Resolve repair demand, purchase and receive stock, then close the return or core trail.</p>
        </div>
        <div className="db-parts-operations__metrics" aria-label="Parts operations summary">
          <Metric label="Low stock" value={summary.low_stock_count} />
          <Metric label="Open purchase orders" value={summary.open_purchase_order_count} />
        </div>
      </header>

      <ol className="db-parts-operations__workflow" aria-label="Parts operations workflow">
        {workflowSteps.map((step, index) => <li key={step.label} className={tab === step.tab ? 'is-current' : ''}>
          <button type="button" onClick={() => selectTab(step.tab)} aria-label={`${step.label}: ${step.detail}`}>
            <span aria-hidden="true">{index + 1}</span><strong>{step.label}</strong><small>{step.detail}</small>
          </button>
        </li>)}
      </ol>

      <div className="db-parts-operations__tabs" role="tablist" aria-label="Parts Operations areas">
        {tabs.map(({ id, label, icon: Icon }) => <button id={`parts-tab-${id}`} key={id} type="button" role="tab" aria-selected={tab === id} aria-controls={`parts-panel-${id}`} onKeyDown={(event) => moveTab(event, id)} onClick={() => selectTab(id)} className={tab === id ? 'is-selected' : ''}>
          <Icon aria-hidden="true" />{label}
        </button>)}
      </div>

      {notice && <p className="db-parts-operations__notice" role="status">{notice}</p>}
      {error && <div className="db-parts-operations__error" role="alert"><span>{error}</span><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}
      {isLoading && <p className="db-parts-operations__loading" role="status">Loading current parts operations…</p>}
    </div>

    <div className="db-parts-operations__content">
      {tab === 'demand' && <section id="parts-panel-demand" className="db-parts-operations__panel" role="tabpanel" aria-label="Demand"><DemandPanel demand={filteredDemand} totalDemand={demand.length} inventory={inventory} canMutate={canMutate} selected={selectedDemand} query={demandSearch} filter={demandFilter} onQuery={setDemandSearch} onFilter={setDemandFilter} onSelect={(item) => { setSelectedDemandId(item.inventory_id); announce(`${item.name} selected. ${item.recommended_order_packages} packages recommended.`) }} onCreate={async (payload) => call(() => api.post('/parts-operations/purchase-orders', payload.body, { headers: { 'Idempotency-Key': payload.key } }), 'Draft purchase order created.')} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} /></section>}
      {tab === 'inventory' && <section id="parts-panel-inventory" className="db-parts-operations__panel" role="tabpanel" aria-label="Inventory"><InventoryPanel inventory={filteredInventory} totalInventory={inventory.length} activity={activity} selected={selectedInventory} query={inventorySearch} onQuery={setInventorySearch} onSelect={(item) => { setSelectedInventoryId(item.id); announce(`${item.name} selected. ${item.stock_quantity} on hand.`) }} /></section>}
      {tab === 'purchase-orders' && <section id="parts-panel-purchase-orders" className="db-parts-operations__panel" role="tabpanel" aria-label="Purchase orders"><PurchaseOrdersPanel items={purchaseOrders} detail={poDetail.data} canMutate={canMutate} onSelect={(id) => { setSelectedPOId(id); const selected = purchaseOrders.find((item) => item.id === id); if (selected) announce(`${selected.po_number} selected. ${selected.remaining_quantity} packages awaiting receipt.`) }} onOpenDemand={() => selectTab('demand')} onSubmit={(po) => call(() => api.post(`/parts-operations/purchase-orders/${po.id}/submit`, { expected_version: po.version }, { headers: { 'Idempotency-Key': operationKey('po-submit') } }), 'Purchase order submitted.')} onReceive={(po, lines) => call(() => api.post(`/parts-operations/purchase-orders/${po.id}/receipts`, { expected_version: po.version, received_at: new Date().toISOString(), lines }, { headers: { 'Idempotency-Key': operationKey('po-receipt') } }), 'Receipt recorded and inventory ledger updated.')} /></section>}
      {tab === 'returns-cores' && <section id="parts-panel-returns-cores" className="db-parts-operations__panel" role="tabpanel" aria-label="Returns and cores"><ReturnsCoresPanel returns={returns} cores={cores} selectedReturn={returnDetail.data} selectedCore={selectedCore} canMutate={canMutate} onSelectReturn={(id) => { setSelectedReturnId(id); const selected = returns.find((item) => item.id === id); if (selected) announce(`${selected.return_number} selected. ${humanize(selected.status)}.`) }} onSelectCore={(id) => { setSelectedCoreId(id); const selected = cores.find((item) => item.id === id); if (selected) announce(`${selected.inventory?.name || 'Core obligation'} selected. ${humanize(selected.status)}.`) }} onOpenDemand={() => selectTab('demand')} onRecover={(core) => call(() => api.post(`/parts-operations/cores/${core.id}/recover`, { expected_version: core.version }, { headers: { 'Idempotency-Key': operationKey('core-recover') } }), 'Core recovery recorded.')} onCreateCoreReturn={(core) => call(() => api.post('/parts-operations/returns', { kind: 'core', supplier_id: core.supplier_id, reason: 'Core return', lines: [{ core_obligation_id: core.id, quantity: core.quantity, expected_credit: '0.00' }] }, { headers: { 'Idempotency-Key': operationKey('core-return') } }), 'Core return draft created.')} onReturnAction={(row, action) => call(() => api.post(`/parts-operations/returns/${row.id}/${action}`, { expected_version: row.version, ...(action === 'reverse' ? { reason: 'Return correction' } : {}) }, { headers: { 'Idempotency-Key': operationKey(`return-${action}`) } }), action === 'reverse' ? 'Return reversal recorded.' : `Return ${action}ed.`)} /></section>}
      {tab === 'activity' && <section id="parts-panel-activity" className="db-parts-operations__panel" role="tabpanel" aria-label="Activity"><ActivityPanel movements={activity} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} /></section>}
    </div>

    <footer className="db-parts-operations__footer"><Link to="/dashboard/garage/suppliers">Manage suppliers</Link><span>Purchase attachments and vendor integrations are not available in this release.</span></footer>
    <p className="sr-only" data-testid="parts-selection-status" role="status" aria-live="polite" aria-atomic="true">{selectionNotice}</p>
  </section>
}

function Metric({ label, value }: { label: string; value: number }) { return <div><strong>{value}</strong><span>{label}</span></div> }

function MasterDetail({ listLabel, toolbar, list, detail }: { listLabel: string; toolbar?: ReactNode; list: ReactNode; detail: ReactNode }) {
  return <div className="db-parts-operations__split">
    <section className="db-parts-operations__list-pane" tabIndex={0} role="region" aria-label={listLabel}>
      {toolbar}
      <div className="db-parts-operations__list">{list}</div>
    </section>
    <aside className="db-parts-operations__detail" tabIndex={0} role="region" aria-label={`${listLabel} detail`}>{detail}</aside>
  </div>
}

function DetailHeader({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="db-parts-operations__detail-header"><h2>{title}</h2>{children}</div>
}

function DemandPanel({ demand, totalDemand, inventory, canMutate, selected, query, filter, onQuery, onFilter, onSelect, onCreate, onOpenRepair }: { demand: DemandItem[]; totalDemand: number; inventory: InventoryItem[]; canMutate: boolean; selected: DemandItem | null; query: string; filter: DemandFilter; onQuery: (value: string) => void; onFilter: (value: DemandFilter) => void; onSelect: (item: DemandItem) => void; onCreate: (payload: { body: unknown; key: string }) => Promise<void>; onOpenRepair: (id: string) => void }) {
  const [poNumber, setPoNumber] = useState('')
  const [quantity, setQuantity] = useState('')
  const [unitCost, setUnitCost] = useState('')
  const activeInventory = inventory.find((item) => item.id === selected?.inventory_id)
  const choose = (item: DemandItem) => { onSelect(item); setPoNumber(''); setQuantity(String(item.recommended_order_packages)); setUnitCost(String(inventory.find((entry) => entry.id === item.inventory_id)?.cost || '')) }
  const create = async () => {
    if (!selected || !activeInventory || !selected.preferred_supplier) return
    await onCreate({ key: operationKey('po-create'), body: { po_number: poNumber.trim(), supplier_id: selected.preferred_supplier.id, lines: [{ inventory_id: selected.inventory_id, ordered_quantity: Number(quantity), unit_cost: Number(unitCost) }] } })
  }
  return <MasterDetail
    listLabel={`Demand results, ${demand.length} shown of ${totalDemand}`}
    toolbar={<div className="db-parts-operations__list-toolbar"><label className="db-parts-operations__search"><Search aria-hidden="true" /><span className="sr-only">Search demand</span><input aria-label="Search demand" type="search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search part, SKU, or supplier" /></label><div className="db-parts-operations__filters" aria-label="Demand triage">{demandFilters.map((item) => <button type="button" aria-pressed={filter === item.id} className={filter === item.id ? 'is-selected' : ''} key={item.id} onClick={() => onFilter(item.id)}>{item.label}</button>)}</div><p>{demand.length === totalDemand ? `${totalDemand} demand items` : `${demand.length} of ${totalDemand} demand items`}</p></div>}
    list={demand.length ? demand.map((item) => <button type="button" aria-current={selected?.inventory_id === item.inventory_id ? 'true' : undefined} className={selected?.inventory_id === item.inventory_id ? 'is-active' : ''} key={item.inventory_id} onClick={() => choose(item)}><span><strong>{item.name}</strong><small>{item.sku} · {item.stock_quantity} on hand · {item.recommended_order_packages} recommended</small></span><Status status={item.state} /></button>) : <Empty label="No demand matches this search and triage view." />}
    detail={selected ? <><DetailHeader title={selected.name}><p>{selected.sku} · Preferred supplier: {selected.preferred_supplier?.name || 'Not set'}</p></DetailHeader><dl className="db-parts-operations__facts"><div><dt>Repair shortage</dt><dd>{selected.repair_shortage_packages} packages</dd></div><div><dt>Shelf replenishment</dt><dd>{selected.shelf_replenishment_packages} packages</dd></div><div><dt>Open supply</dt><dd>{selected.open_supply_packages} packages</dd></div><div><dt>Recommended order</dt><dd>{selected.recommended_order_packages} packages</dd></div></dl><div className="db-parts-operations__sources"><h3>Why this is needed</h3>{selected.sources.map((source, index) => <div key={`${source.type}-${index}`}>{source.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(source.repair_order_id!)}>Repair order {source.order_number}</button> : <span>{humanize(source.type)}</span>}<strong>{source.packages} pkg</strong></div>)}</div>{canMutate && selected.state !== 'unlinked' && selected.recommended_order_packages > 0 && selected.preferred_supplier ? <form className="db-parts-operations__form" onSubmit={(event) => { event.preventDefault(); void create() }}><h3>Create draft purchase order</h3><label>PO number<input required minLength={1} value={poNumber} onChange={(event) => setPoNumber(event.target.value)} placeholder="PO-000302" /></label><div><label>Packages<input required min={1} max={999} type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label>Unit cost<input required min="0.01" step="0.01" type="number" value={unitCost} onChange={(event) => setUnitCost(event.target.value)} /></label></div><button className="db-parts-operations__primary" type="submit">Create draft PO</button></form> : <p className="db-parts-operations__hint">{selected.state === 'unlinked' ? 'Promote this placeholder in the legacy catalog before it can be ordered.' : !canMutate ? 'Read-only access: a shop owner or admin can create the purchase order.' : 'Set a preferred supplier in the legacy catalog before creating a PO.'}</p>}</> : <Empty label="Select a demand item to inspect its repair and replenishment sources." />}
  />
}

function InventoryPanel({ inventory, totalInventory, activity, selected, query, onQuery, onSelect }: { inventory: InventoryItem[]; totalInventory: number; activity: Movement[]; selected: InventoryItem | null; query: string; onQuery: (value: string) => void; onSelect: (item: InventoryItem) => void }) {
  const selectedActivity = activity.filter((row) => row.inventory?.id === selected?.id).slice(0, 8)
  return <MasterDetail
    listLabel={`Inventory results, ${inventory.length} shown of ${totalInventory}`}
    toolbar={<div className="db-parts-operations__list-toolbar"><label className="db-parts-operations__search"><Search aria-hidden="true" /><span className="sr-only">Search inventory</span><input aria-label="Search inventory" type="search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Search part, SKU, or location" /></label><p>{inventory.length === totalInventory ? `${totalInventory} inventory items` : `${inventory.length} of ${totalInventory} inventory items`}</p></div>}
    list={inventory.length ? inventory.map((item) => <button type="button" aria-current={selected?.id === item.id ? 'true' : undefined} className={selected?.id === item.id ? 'is-active' : ''} key={item.id} onClick={() => onSelect(item)}><span><strong>{item.name}</strong><small>{item.sku} · {item.location || 'No location'} · {item.unit_type}</small></span><span className="db-parts-operations__number">{item.stock_quantity} on hand</span></button>) : <Empty label="No inventory items match this search." />}
    detail={selected ? <><DetailHeader title={selected.name}><p>{selected.sku} · {selected.location || 'No location'} · {selected.unit_type}</p></DetailHeader><dl className="db-parts-operations__facts"><div><dt>On hand</dt><dd>{selected.stock_quantity}</dd></div><div><dt>On order</dt><dd>{selected.on_order_quantity}</dd></div><div><dt>Reorder level</dt><dd>{selected.reorder_level}</dd></div><div><dt>Current WAC</dt><dd>${selected.cost}</dd></div></dl><div className="db-parts-operations__sources"><h3>Recent stock activity</h3>{selectedActivity.length ? selectedActivity.map((row) => <div key={row.id}><span>{humanize(row.movement_type)}</span><strong>Balance {row.balance_after}</strong></div>) : <p className="db-parts-operations__hint">No ledger activity is loaded for this item.</p>}</div><p className="db-parts-operations__hint">Catalog fields remain in the existing inventory editor; this operating view reads the same tenant catalog and ledger.</p></> : <Empty label="Select an inventory item to review stock and activity." />}
  />
}

function PurchaseOrdersPanel({ items, detail, canMutate, onSelect, onOpenDemand, onSubmit, onReceive }: { items: PurchaseOrder[]; detail: PurchaseOrderDetail | undefined; canMutate: boolean; onSelect: (id: string) => void; onOpenDemand: () => void; onSubmit: (po: PurchaseOrderDetail) => Promise<void>; onReceive: (po: PurchaseOrderDetail, lines: Array<{ purchase_order_line_id: string; quantity: number; unit_cost: number }>) => Promise<void> }) {
  const [receiptQty, setReceiptQty] = useState<Record<string, string>>({})
  const [receiptCost, setReceiptCost] = useState<Record<string, string>>({})
  const receive = async () => { if (!detail) return; const lines = detail.lines.map((line) => ({ purchase_order_line_id: line.id, quantity: Number(receiptQty[line.id] || 0), unit_cost: Number(receiptCost[line.id] || line.unit_cost) })).filter((line) => line.quantity > 0); if (lines.length) await onReceive(detail, lines) }
  return <MasterDetail
    listLabel="Purchase orders"
    list={items.length ? items.map((po) => <button type="button" aria-current={detail?.id === po.id ? 'true' : undefined} className={detail?.id === po.id ? 'is-active' : ''} key={po.id} onClick={() => onSelect(po.id)}><span><strong>{po.po_number}</strong><small>{po.supplier?.name || 'Supplier'} · {po.remaining_quantity} packages awaiting receipt</small></span><Status status={po.status} /></button>) : <Empty label="No purchase orders are awaiting work." action={<button className="db-parts-operations__inline-action" type="button" onClick={onOpenDemand}>Review demand</button>} />}
    detail={detail ? <><DetailHeader title={detail.po_number}><p>{detail.supplier?.name || 'Supplier'} · {humanize(detail.status)} · {detail.remaining_quantity} packages awaiting receipt</p></DetailHeader><div className="db-parts-operations__line-list">{detail.lines.map((line) => <div key={line.id}><span><strong>{line.description}</strong><small>{line.sku} · {line.received_quantity}/{line.ordered_quantity} received · ${line.unit_cost}</small></span>{canMutate && ['submitted', 'partially_received'].includes(detail.status) && line.ordered_quantity > line.received_quantity && <span className="db-parts-operations__receipt-inputs"><input aria-label={`Receive quantity for ${line.sku}`} type="number" min={0} max={line.ordered_quantity - line.received_quantity} value={receiptQty[line.id] || ''} onChange={(event) => setReceiptQty((old) => ({ ...old, [line.id]: event.target.value }))} placeholder="Qty" /><input aria-label={`Receipt unit cost for ${line.sku}`} type="number" min="0.01" step="0.01" value={receiptCost[line.id] ?? line.unit_cost} onChange={(event) => setReceiptCost((old) => ({ ...old, [line.id]: event.target.value }))} /></span>}</div>)}</div>{canMutate && detail.status === 'draft' && <button className="db-parts-operations__primary" type="button" onClick={() => void onSubmit(detail)}>Submit purchase order</button>}{canMutate && ['submitted', 'partially_received'].includes(detail.status) && <button className="db-parts-operations__primary" type="button" onClick={() => void receive()}>Record receipt</button>}{!canMutate && <p className="db-parts-operations__hint">Read-only access. Owners and admins can submit and receive this PO.</p>}</> : <Empty label="Select a purchase order to view remaining quantities and receive stock." />}
  />
}

function ReturnsCoresPanel({ returns, cores, selectedReturn, selectedCore, canMutate, onSelectReturn, onSelectCore, onOpenDemand, onRecover, onCreateCoreReturn, onReturnAction }: { returns: ReturnItem[]; cores: Core[]; selectedReturn: ReturnDetail | undefined; selectedCore: Core | null; canMutate: boolean; onSelectReturn: (id: string) => void; onSelectCore: (id: string) => void; onOpenDemand: () => void; onRecover: (core: Core) => Promise<void>; onCreateCoreReturn: (core: Core) => Promise<void>; onReturnAction: (row: ReturnDetail, action: 'submit' | 'ship' | 'credit' | 'reverse') => Promise<void> }) {
  const [view, setView] = useState<'returns' | 'cores'>('returns')
  const moveView = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const target = event.key === 'Home' || event.key === 'ArrowLeft' ? 'returns' : 'cores'
    setView(target)
    document.getElementById(`parts-${target}-tab`)?.focus()
  }
  return <div className="db-parts-operations__subsurface"><div className="db-parts-operations__subtabs" role="tablist" aria-label="Returns and core custody"><button id="parts-returns-tab" type="button" role="tab" aria-selected={view === 'returns'} onKeyDown={moveView} onClick={() => setView('returns')}>Returns</button><button id="parts-cores-tab" type="button" role="tab" aria-selected={view === 'cores'} onKeyDown={moveView} onClick={() => setView('cores')}>Cores</button></div>{view === 'returns' ? <MasterDetail listLabel="Vendor returns" list={returns.length ? returns.map((row) => <button type="button" aria-current={selectedReturn?.id === row.id ? 'true' : undefined} className={selectedReturn?.id === row.id ? 'is-active' : ''} key={row.id} onClick={() => onSelectReturn(row.id)}><span><strong>{row.return_number}</strong><small>{row.kind} · {row.supplier?.name || 'Supplier'} · {row.total_quantity} packages</small></span><Status status={row.status} /></button>) : <Empty label="No vendor returns are ready to process." action={<button className="db-parts-operations__inline-action" type="button" onClick={onOpenDemand}>Review demand</button>} />} detail={selectedReturn ? <><DetailHeader title={selectedReturn.return_number}><p>{selectedReturn.supplier?.name || 'Supplier'} · {selectedReturn.reason} · {humanize(selectedReturn.status)}</p></DetailHeader>{selectedReturn.lines.map((line) => <p key={line.id} className="db-parts-operations__compact-row">{line.inventory?.sku || 'Inventory'} · {line.quantity} packages · {humanize(line.source.type)}</p>)}{canMutate && selectedReturn.status === 'draft' && <button className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'submit')}>Submit return</button>}{canMutate && selectedReturn.status === 'submitted' && <button className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'ship')}>Mark shipped</button>}{canMutate && selectedReturn.status === 'shipped' && <button className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'credit')}>Record vendor credit</button>}{canMutate && ['shipped', 'credited'].includes(selectedReturn.status) && <button className="db-parts-operations__secondary" type="button" onClick={() => void onReturnAction(selectedReturn, 'reverse')}>Reverse return</button>}</> : <Empty label="Select a return to inspect its receipt or core origin." />} /> : <MasterDetail listLabel="Core obligations" list={cores.length ? cores.map((row) => <button type="button" aria-current={selectedCore?.id === row.id ? 'true' : undefined} className={selectedCore?.id === row.id ? 'is-active' : ''} key={row.id} onClick={() => onSelectCore(row.id)}><span><strong>{row.inventory?.name || 'Core obligation'}</strong><small>{row.source?.order_number || 'Repair order source'} · {row.quantity} core</small></span><Status status={row.status} /></button>) : <Empty label="No core obligations require custody action." />} detail={selectedCore ? <><DetailHeader title={selectedCore.inventory?.name || 'Core obligation'}><p>{selectedCore.source?.order_number || 'Repair order source'} · {humanize(selectedCore.status)}</p></DetailHeader>{canMutate && selectedCore.status === 'expected' && <button className="db-parts-operations__primary" type="button" onClick={() => void onRecover(selectedCore)}>Record recovered core</button>}{canMutate && selectedCore.status === 'on_hand' && selectedCore.supplier_id && <button className="db-parts-operations__primary" type="button" onClick={() => void onCreateCoreReturn(selectedCore)}>Create core return</button>}{!canMutate && <p className="db-parts-operations__hint">Read-only access. Owners and admins manage custody transitions.</p>}</> : <Empty label="Select a core obligation to inspect its repair-order custody." />} />}</div>
}

function ActivityPanel({ movements, onOpenRepair }: { movements: Movement[]; onOpenRepair: (id: string) => void }) { return <div className="db-parts-operations__activity">{movements.length ? movements.map((row) => <article key={row.id}><div><strong>{row.inventory?.name || 'Inventory movement'}</strong><p>{humanize(row.movement_type)} · balance {row.balance_after} · WAC {row.wac_after ? `$${row.wac_after}` : '—'}</p></div><div>{row.source?.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(row.source!.id)}>{row.source.order_number || 'Open repair order'}<ArrowRight aria-hidden="true" /></button> : <span>{row.source?.receipt_number || row.source?.return_number || 'Opening/manual record'}</span>}<time>{formatDate(row.occurred_at)}</time></div></article>) : <Empty label="No inventory activity yet" />}</div> }

function Status({ status }: { status: string }) { return <span className={`db-parts-operations__status is-${status}`}>{humanize(status)}</span> }
function Empty({ label, action }: { label: string; action?: ReactNode }) { return <div className="db-parts-operations__empty"><p>{label}</p>{action}</div> }
