import { useState, type KeyboardEvent, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowRight, ClipboardList, PackageSearch, RotateCcw } from 'lucide-react'
import api from '@/lib/api'
import type { InventoryItem } from '@/types'
import { useAuthStore } from '@/stores/authStore'

type OperationsTab = 'demand' | 'inventory' | 'purchase-orders' | 'returns-cores' | 'activity'
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
  const [selectedPOId, setSelectedPOId] = useState<string | null>(null)
  const [selectedReturnId, setSelectedReturnId] = useState<string | null>(null)
  const [selectedCoreId, setSelectedCoreId] = useState<string | null>(null)
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

  const demand = demandQuery.data || []
  const inventory = inventoryQuery.data || []
  const purchaseOrders = poQuery.data || []
  const returns = returnsQuery.data || []
  const cores = coresQuery.data || []
  const activity = activityQuery.data || []
  const selectedDemand = demand.find((item) => item.inventory_id === selectedDemandId) || null
  const selectedCore = cores.find((item) => item.id === selectedCoreId) || null
  const isLoading = demandQuery.isLoading || inventoryQuery.isLoading || poQuery.isLoading || returnsQuery.isLoading || coresQuery.isLoading || activityQuery.isLoading

  return <section className="db-parts-operations" aria-labelledby="parts-operations-title">
    <header className="db-parts-operations__header">
      <div>
        <p className="db-parts-operations__eyebrow">Parts operations</p>
        <h1 id="parts-operations-title">Supply, stock & custody</h1>
        <p>Repair demand, receiving, returns, and the immutable stock ledger for this shop.</p>
      </div>
      <div className="db-parts-operations__metrics" aria-label="Parts operations summary">
        <Metric label="Low stock" value={summary.low_stock_count} />
        <Metric label="Open purchase orders" value={summary.open_purchase_order_count} />
      </div>
    </header>

    <div className="db-parts-operations__tabs" role="tablist" aria-label="Parts Operations areas">
      {tabs.map(({ id, label, icon: Icon }) => <button id={`parts-tab-${id}`} key={id} type="button" role="tab" aria-selected={tab === id} aria-controls={`parts-panel-${id}`} onKeyDown={(event) => moveTab(event, id)} onClick={() => setTab(id)} className={tab === id ? 'is-selected' : ''}>
        <Icon aria-hidden="true" />{label}
      </button>)}
    </div>

    {notice && <p className="db-parts-operations__notice" role="status">{notice}</p>}
    {error && <div className="db-parts-operations__error" role="alert"><span>{error}</span><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}
    {isLoading && <p className="db-parts-operations__loading" role="status">Loading current parts operations…</p>}

    {tab === 'demand' && <section id="parts-panel-demand" role="tabpanel" aria-label="Demand"><DemandPanel demand={demand} inventory={inventory} canMutate={canMutate} selected={selectedDemand} onSelect={setSelectedDemandId} onCreate={async (payload) => call(() => api.post('/parts-operations/purchase-orders', payload.body, { headers: { 'Idempotency-Key': payload.key } }), 'Draft purchase order created.')} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} /></section>}
    {tab === 'inventory' && <section id="parts-panel-inventory" role="tabpanel" aria-label="Inventory"><InventoryPanel inventory={inventory} activity={activity} /></section>}
    {tab === 'purchase-orders' && <section id="parts-panel-purchase-orders" role="tabpanel" aria-label="Purchase orders"><PurchaseOrdersPanel items={purchaseOrders} detail={poDetail.data} canMutate={canMutate} onSelect={setSelectedPOId} onSubmit={(po) => call(() => api.post(`/parts-operations/purchase-orders/${po.id}/submit`, { expected_version: po.version }, { headers: { 'Idempotency-Key': operationKey('po-submit') } }), 'Purchase order submitted.')} onReceive={(po, lines) => call(() => api.post(`/parts-operations/purchase-orders/${po.id}/receipts`, { expected_version: po.version, received_at: new Date().toISOString(), lines }, { headers: { 'Idempotency-Key': operationKey('po-receipt') } }), 'Receipt recorded and inventory ledger updated.')} /></section>}
    {tab === 'returns-cores' && <section id="parts-panel-returns-cores" role="tabpanel" aria-label="Returns and cores"><ReturnsCoresPanel returns={returns} cores={cores} selectedReturn={returnDetail.data} selectedCore={selectedCore} canMutate={canMutate} onSelectReturn={setSelectedReturnId} onSelectCore={setSelectedCoreId} onRecover={(core) => call(() => api.post(`/parts-operations/cores/${core.id}/recover`, { expected_version: core.version }, { headers: { 'Idempotency-Key': operationKey('core-recover') } }), 'Core recovery recorded.')} onCreateCoreReturn={(core) => call(() => api.post('/parts-operations/returns', { kind: 'core', supplier_id: core.supplier_id, reason: 'Core return', lines: [{ core_obligation_id: core.id, quantity: core.quantity, expected_credit: '0.00' }] }, { headers: { 'Idempotency-Key': operationKey('core-return') } }), 'Core return draft created.')} onReturnAction={(row, action) => call(() => api.post(`/parts-operations/returns/${row.id}/${action}`, { expected_version: row.version, ...(action === 'reverse' ? { reason: 'Return correction' } : {}) }, { headers: { 'Idempotency-Key': operationKey(`return-${action}`) } }), action === 'reverse' ? 'Return reversal recorded.' : `Return ${action}ed.`)} /></section>}
    {tab === 'activity' && <section id="parts-panel-activity" role="tabpanel" aria-label="Activity"><ActivityPanel movements={activity} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} /></section>}

    <footer className="db-parts-operations__footer"><Link to="/dashboard/garage/suppliers">Manage suppliers</Link><span>Purchase attachments and vendor integrations are not available in this release.</span></footer>
  </section>
}

function Metric({ label, value }: { label: string; value: number }) { return <div><strong>{value}</strong><span>{label}</span></div> }

function DemandPanel({ demand, inventory, canMutate, selected, onSelect, onCreate, onOpenRepair }: { demand: DemandItem[]; inventory: InventoryItem[]; canMutate: boolean; selected: DemandItem | null; onSelect: (id: string) => void; onCreate: (payload: { body: unknown; key: string }) => Promise<void>; onOpenRepair: (id: string) => void }) {
  const [poNumber, setPoNumber] = useState('')
  const [quantity, setQuantity] = useState('')
  const [unitCost, setUnitCost] = useState('')
  const activeInventory = inventory.find((item) => item.id === selected?.inventory_id)
  const choose = (item: DemandItem) => { onSelect(item.inventory_id); setPoNumber(''); setQuantity(String(item.recommended_order_packages)); setUnitCost(String(inventory.find((entry) => entry.id === item.inventory_id)?.cost || '')) }
  const create = async () => {
    if (!selected || !activeInventory || !selected.preferred_supplier) return
    await onCreate({ key: operationKey('po-create'), body: { po_number: poNumber.trim(), supplier_id: selected.preferred_supplier.id, lines: [{ inventory_id: selected.inventory_id, ordered_quantity: Number(quantity), unit_cost: Number(unitCost) }] } })
  }
  return <div className="db-parts-operations__split"><div className="db-parts-operations__list">{demand.length ? demand.map((item) => <button type="button" className={selected?.inventory_id === item.inventory_id ? 'is-active' : ''} key={item.inventory_id} onClick={() => choose(item)}><span><strong>{item.name}</strong><small>{item.sku} · {item.stock_quantity} on hand · {item.recommended_order_packages} recommended</small></span><Status status={item.state} /></button>) : <Empty label="No open demand" />}</div><aside className="db-parts-operations__detail">{selected ? <><p className="db-parts-operations__eyebrow">Demand detail</p><h2>{selected.name}</h2><dl className="db-parts-operations__facts"><div><dt>Repair shortage</dt><dd>{selected.repair_shortage_packages} packages</dd></div><div><dt>Shelf replenishment</dt><dd>{selected.shelf_replenishment_packages} packages</dd></div><div><dt>Open supply</dt><dd>{selected.open_supply_packages} packages</dd></div><div><dt>Recommended order</dt><dd>{selected.recommended_order_packages} packages</dd></div></dl><div className="db-parts-operations__sources"><h3>Demand sources</h3>{selected.sources.map((source, index) => <div key={`${source.type}-${index}`}>{source.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(source.repair_order_id!)}>Repair order {source.order_number}</button> : <span>{humanize(source.type)}</span>}<strong>{source.packages} pkg</strong></div>)}</div>{canMutate && selected.state !== 'unlinked' && selected.recommended_order_packages > 0 && selected.preferred_supplier ? <form className="db-parts-operations__form" onSubmit={(event) => { event.preventDefault(); void create() }}><h3>Create draft purchase order</h3><label>PO number<input required minLength={1} value={poNumber} onChange={(event) => setPoNumber(event.target.value)} placeholder="PO-000302" /></label><div><label>Packages<input required min={1} max={999} type="number" value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label>Unit cost<input required min="0.01" step="0.01" type="number" value={unitCost} onChange={(event) => setUnitCost(event.target.value)} /></label></div><button className="db-parts-operations__primary" type="submit">Create draft PO</button></form> : <p className="db-parts-operations__hint">{selected.state === 'unlinked' ? 'Promote this placeholder in the legacy catalog before it can be ordered.' : !canMutate ? 'Read-only access: a shop owner or admin can create the purchase order.' : 'Set a preferred supplier in the legacy catalog before creating a PO.'}</p>}</> : <Empty label="Select a demand item to inspect its repair and replenishment sources." />}</aside></div>
}

function InventoryPanel({ inventory, activity }: { inventory: InventoryItem[]; activity: Movement[] }) { return <div className="db-parts-operations__split"><div className="db-parts-operations__list">{inventory.map((item) => <article key={item.id}><span><strong>{item.name}</strong><small>{item.sku} · {item.location || 'No location'} · {item.unit_type}</small></span><span className="db-parts-operations__number">{item.stock_quantity} on hand</span></article>)}</div><aside className="db-parts-operations__detail"><p className="db-parts-operations__eyebrow">Catalog compatibility</p><h2>Inventory stays canonical</h2><p>SKU, price, location, categories, and photos remain in the existing catalog. This workspace is intentionally read-only for stock and cost fields.</p><h3>Recent catalog movement</h3>{activity.slice(0, 4).map((row) => <p key={row.id} className="db-parts-operations__compact-row">{row.inventory?.sku || 'Inventory'} · {humanize(row.movement_type)} · balance {row.balance_after}</p>)}</aside></div> }

function PurchaseOrdersPanel({ items, detail, canMutate, onSelect, onSubmit, onReceive }: { items: PurchaseOrder[]; detail: PurchaseOrderDetail | undefined; canMutate: boolean; onSelect: (id: string) => void; onSubmit: (po: PurchaseOrderDetail) => Promise<void>; onReceive: (po: PurchaseOrderDetail, lines: Array<{ purchase_order_line_id: string; quantity: number; unit_cost: number }>) => Promise<void> }) {
  const [receiptQty, setReceiptQty] = useState<Record<string, string>>({})
  const [receiptCost, setReceiptCost] = useState<Record<string, string>>({})
  const receive = async () => { if (!detail) return; const lines = detail.lines.map((line) => ({ purchase_order_line_id: line.id, quantity: Number(receiptQty[line.id] || 0), unit_cost: Number(receiptCost[line.id] || line.unit_cost) })).filter((line) => line.quantity > 0); if (lines.length) await onReceive(detail, lines) }
  return <div className="db-parts-operations__split"><div className="db-parts-operations__list">{items.length ? items.map((po) => <button type="button" key={po.id} onClick={() => onSelect(po.id)}><span><strong>{po.po_number}</strong><small>{po.supplier?.name || 'Supplier'} · {po.remaining_quantity} packages remaining</small></span><Status status={po.status} /></button>) : <Empty label="No purchase orders yet" />}</div><aside className="db-parts-operations__detail">{detail ? <><p className="db-parts-operations__eyebrow">Purchase order</p><h2>{detail.po_number}</h2><p>{detail.supplier?.name || 'Supplier'} · {humanize(detail.status)}</p><div className="db-parts-operations__line-list">{detail.lines.map((line) => <div key={line.id}><span><strong>{line.description}</strong><small>{line.sku} · {line.received_quantity}/{line.ordered_quantity} received · ${line.unit_cost}</small></span>{canMutate && ['submitted', 'partially_received'].includes(detail.status) && line.ordered_quantity > line.received_quantity && <span className="db-parts-operations__receipt-inputs"><input aria-label={`Receive quantity for ${line.sku}`} type="number" min={0} max={line.ordered_quantity - line.received_quantity} value={receiptQty[line.id] || ''} onChange={(event) => setReceiptQty((old) => ({ ...old, [line.id]: event.target.value }))} placeholder="Qty" /><input aria-label={`Receipt unit cost for ${line.sku}`} type="number" min="0.01" step="0.01" value={receiptCost[line.id] ?? line.unit_cost} onChange={(event) => setReceiptCost((old) => ({ ...old, [line.id]: event.target.value }))} /></span>}</div>)}</div>{canMutate && detail.status === 'draft' && <button className="db-parts-operations__primary" type="button" onClick={() => void onSubmit(detail)}>Submit purchase order</button>}{canMutate && ['submitted', 'partially_received'].includes(detail.status) && <button className="db-parts-operations__primary" type="button" onClick={() => void receive()}>Record receipt</button>}{!canMutate && <p className="db-parts-operations__hint">Read-only access. Owners and admins can submit and receive this PO.</p>}</> : <Empty label="Select a purchase order to view remaining quantities and receive stock." />}</aside></div>
}

function ReturnsCoresPanel({ returns, cores, selectedReturn, selectedCore, canMutate, onSelectReturn, onSelectCore, onRecover, onCreateCoreReturn, onReturnAction }: { returns: ReturnItem[]; cores: Core[]; selectedReturn: ReturnDetail | undefined; selectedCore: Core | null; canMutate: boolean; onSelectReturn: (id: string) => void; onSelectCore: (id: string) => void; onRecover: (core: Core) => Promise<void>; onCreateCoreReturn: (core: Core) => Promise<void>; onReturnAction: (row: ReturnDetail, action: 'submit' | 'ship' | 'credit' | 'reverse') => Promise<void> }) {
  const [view, setView] = useState<'returns' | 'cores'>('returns')
  return <div><div className="db-parts-operations__subtabs" role="tablist" aria-label="Returns and core custody"><button type="button" role="tab" aria-selected={view === 'returns'} onClick={() => setView('returns')}>Returns</button><button type="button" role="tab" aria-selected={view === 'cores'} onClick={() => setView('cores')}>Cores</button></div>{view === 'returns' ? <div className="db-parts-operations__split"><div className="db-parts-operations__list">{returns.length ? returns.map((row) => <button type="button" key={row.id} onClick={() => onSelectReturn(row.id)}><span><strong>{row.return_number}</strong><small>{row.kind} · {row.supplier?.name || 'Supplier'} · {row.total_quantity} packages</small></span><Status status={row.status} /></button>) : <Empty label="No vendor returns" />}</div><aside className="db-parts-operations__detail">{selectedReturn ? <><p className="db-parts-operations__eyebrow">Origin-linked return</p><h2>{selectedReturn.return_number}</h2><p>{selectedReturn.supplier?.name || 'Supplier'} · {selectedReturn.reason}</p>{selectedReturn.lines.map((line) => <p key={line.id} className="db-parts-operations__compact-row">{line.inventory?.sku || 'Inventory'} · {line.quantity} packages · {humanize(line.source.type)}</p>)}{canMutate && selectedReturn.status === 'draft' && <button className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'submit')}>Submit return</button>}{canMutate && selectedReturn.status === 'submitted' && <button className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'ship')}>Mark shipped</button>}{canMutate && selectedReturn.status === 'shipped' && <button className="db-parts-operations__primary" type="button" onClick={() => void onReturnAction(selectedReturn, 'credit')}>Record vendor credit</button>}{canMutate && ['shipped', 'credited'].includes(selectedReturn.status) && <button className="db-parts-operations__secondary" type="button" onClick={() => void onReturnAction(selectedReturn, 'reverse')}>Reverse return</button>}</> : <Empty label="Select a return to inspect its receipt or core origin." />}</aside></div> : <div className="db-parts-operations__split"><div className="db-parts-operations__list">{cores.length ? cores.map((row) => <button type="button" key={row.id} onClick={() => onSelectCore(row.id)}><span><strong>{row.inventory?.name || 'Core obligation'}</strong><small>{row.source?.order_number || 'Repair order source'} · {row.quantity} core</small></span><Status status={row.status} /></button>) : <Empty label="No core obligations" />}</div><aside className="db-parts-operations__detail">{selectedCore ? <><p className="db-parts-operations__eyebrow">Core custody</p><h2>{selectedCore.inventory?.name || 'Core obligation'}</h2><p>{selectedCore.source?.order_number || 'Repair order source'} · {humanize(selectedCore.status)}</p>{canMutate && selectedCore.status === 'expected' && <button className="db-parts-operations__primary" type="button" onClick={() => void onRecover(selectedCore)}>Record recovered core</button>}{canMutate && selectedCore.status === 'on_hand' && selectedCore.supplier_id && <button className="db-parts-operations__primary" type="button" onClick={() => void onCreateCoreReturn(selectedCore)}>Create core return</button>}{!canMutate && <p className="db-parts-operations__hint">Read-only access. Owners and admins manage custody transitions.</p>}</> : <Empty label="Select a core obligation to inspect its repair-order custody." />}</aside></div>}</div>
}

function ActivityPanel({ movements, onOpenRepair }: { movements: Movement[]; onOpenRepair: (id: string) => void }) { return <div className="db-parts-operations__activity">{movements.length ? movements.map((row) => <article key={row.id}><div><strong>{row.inventory?.name || 'Inventory movement'}</strong><p>{humanize(row.movement_type)} · balance {row.balance_after} · WAC {row.wac_after ? `$${row.wac_after}` : '—'}</p></div><div>{row.source?.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(row.source!.id)}>{row.source.order_number || 'Open repair order'}<ArrowRight aria-hidden="true" /></button> : <span>{row.source?.receipt_number || row.source?.return_number || 'Opening/manual record'}</span>}<time>{formatDate(row.occurred_at)}</time></div></article>) : <Empty label="No inventory activity yet" />}</div> }

function Status({ status }: { status: string }) { return <span className={`db-parts-operations__status is-${status}`}>{humanize(status)}</span> }
function Empty({ label }: { label: string }) { return <p className="db-parts-operations__empty">{label}</p> }
