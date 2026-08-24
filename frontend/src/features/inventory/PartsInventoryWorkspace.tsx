/* eslint-disable react-refresh/only-export-components -- Session-scoped purchase preparation is shared with Purchasing. */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Boxes, History, MapPin, Package, Search, ShoppingCart } from 'lucide-react'

import api from '@/lib/api'
import useTenantBranding from '@/hooks/useTenantBranding'
import { useAuthStore } from '@/stores/authStore'

type Page<T> = { items: T[]; total: number; skip: number; limit: number; has_more: boolean }
type Summary = { low_stock_count: number; open_purchase_order_count: number }
type WorkspaceView = 'parts' | 'reorder' | 'movement'
type CatalogView = 'active' | 'archived'
type PartSort = 'catalog' | 'name' | 'available' | 'reorder'

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

export type PurchasePreparationLine = {
  inventoryId: string
  name: string
  sku: string
  sourceId: string
  supplierId: string
  supplierName: string
  supplierPartNumber: string | null
  quantity: number
  unitCost: string
  minimumOrderQuantity: number
  packQuantity: number
}

export const PURCHASE_PREPARATION_KEY = 'dieselbridge:db038:purchase-preparation:v1'

export function readPurchasePreparation(): PurchasePreparationLine[] {
  if (typeof window === 'undefined') return []
  try {
    const value = JSON.parse(window.sessionStorage.getItem(PURCHASE_PREPARATION_KEY) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export function writePurchasePreparation(lines: PurchasePreparationLine[]) {
  window.sessionStorage.setItem(PURCHASE_PREPARATION_KEY, JSON.stringify(lines))
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
  const minimum = Math.max(part.recommended_order_packages, source.minimum_order_quantity)
  return Math.ceil(minimum / source.pack_quantity) * source.pack_quantity
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
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [skip, setSkip] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => { setDebouncedSearch(search.trim()); setSkip(0) }, 250)
    return () => window.clearTimeout(timer)
  }, [search])

  const partParams = useMemo(() => ({
    view: catalogView,
    ...(workspaceView === 'reorder' ? { attention: 'needs_reorder' } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    sort,
    skip,
    limit: 50,
    paginated: true,
  }), [catalogView, debouncedSearch, skip, sort, workspaceView])

  const partsQuery = useQuery<Page<PartRecord>>({
    queryKey: ['parts-operations', 'parts', partParams],
    queryFn: async () => (await api.get('/parts-operations/parts', { params: partParams })).data,
    enabled: workspaceView !== 'movement',
    retry: false,
  })
  const movementQuery = useQuery<Page<Movement>>({
    queryKey: ['parts-operations', 'movement', skip],
    queryFn: async () => (await api.get('/parts-operations/activity', { params: { paginated: true, skip, limit: 50 } })).data,
    enabled: workspaceView === 'movement',
    retry: false,
  })
  const detailQuery = useQuery<PartDetail>({
    queryKey: ['parts-operations', 'part', selectedId],
    queryFn: async () => (await api.get(`/parts-operations/parts/${selectedId}`)).data,
    enabled: workspaceView !== 'movement' && Boolean(selectedId),
    retry: false,
  })
  const parts = useMemo(() => partsQuery.data?.items || [], [partsQuery.data?.items])

  useEffect(() => {
    if (!parts.length) { setSelectedId(null); return }
    if (!selectedId || !parts.some((part) => part.id === selectedId)) setSelectedId(parts[0].id)
  }, [parts, selectedId])

  const selectView = (view: WorkspaceView) => {
    setWorkspaceView(view)
    setSkip(0)
    setMobileDetailOpen(false)
    if (view === 'reorder') setCatalogView('active')
  }

  const addToPreparation = (part: PartRecord) => {
    const source = part.preferred_source
    if (!source) { setError('Choose a preferred supplier source before preparing this part for purchase.'); return }
    const current = readPurchasePreparation().filter((line) => line.inventoryId !== part.id)
    const line: PurchasePreparationLine = {
      inventoryId: part.id,
      name: part.name,
      sku: part.sku,
      sourceId: source.source_id,
      supplierId: source.supplier_id,
      supplierName: source.supplier_name || 'Supplier',
      supplierPartNumber: source.supplier_part_number,
      quantity: roundOrderQuantity(part, source),
      unitCost: source.last_unit_cost || part.average_unit_cost,
      minimumOrderQuantity: source.minimum_order_quantity,
      packQuantity: source.pack_quantity,
    }
    writePurchasePreparation([...current, line])
    setNotice(`${part.name} added to the purchase preparation list.`)
  }

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
      <div><h1 id="parts-workbench-title">Parts & inventory</h1><p>Know what is available, what open repairs still need, and what should be purchased next.</p></div>
      <div className="db-parts-workbench__summary" aria-label="Parts summary">
        <button type="button" onClick={() => selectView('reorder')}><strong>{summary.low_stock_count}</strong><span>Need reorder</span></button>
        <button type="button" onClick={() => navigate('/dashboard/garage/purchasing')}><strong>{summary.open_purchase_order_count}</strong><span>Open purchase orders</span></button>
      </div>
    </header>

    <nav className="db-parts-workbench__views" aria-label="Parts and inventory views">
      <button type="button" aria-current={workspaceView === 'parts' ? 'page' : undefined} onClick={() => selectView('parts')}><Boxes aria-hidden="true" />All parts</button>
      <button type="button" aria-current={workspaceView === 'reorder' ? 'page' : undefined} onClick={() => selectView('reorder')}><ShoppingCart aria-hidden="true" />Needs reorder</button>
      <button type="button" aria-current={workspaceView === 'movement' ? 'page' : undefined} onClick={() => selectView('movement')}><History aria-hidden="true" />Movement</button>
    </nav>

    {notice && <div className="db-parts-workbench__notice" role="status"><span>{notice}</span><button type="button" onClick={() => setNotice(null)}>Dismiss</button></div>}
    {error && <div className="db-parts-workbench__error" role="alert"><span>{error}</span><button type="button" onClick={() => setError(null)}>Dismiss</button></div>}

    {workspaceView === 'movement'
      ? <MovementLedger page={movementQuery.data} loading={movementQuery.isLoading} failed={movementQuery.isError} onRetry={() => void movementQuery.refetch()} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} onPage={setSkip} />
      : <>
        <div className="db-parts-workbench__toolbar">
          <label className="db-parts-workbench__search"><Search aria-hidden="true" /><span className="sr-only">Search parts</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search part, SKU, supplier, source number, or bin" /></label>
          <label><span>Catalog</span><select value={catalogView} onChange={(event) => { setCatalogView(event.target.value as CatalogView); setSkip(0) }} disabled={workspaceView === 'reorder'}><option value="active">Active parts</option><option value="archived">Archived parts</option></select></label>
          <label><span>Sort</span><select value={sort} onChange={(event) => { setSort(event.target.value as PartSort); setSkip(0) }}><option value="catalog">Catalog order</option><option value="name">Name</option><option value="available">Available</option><option value="reorder">Reorder urgency</option></select></label>
        </div>
        <div className={`db-parts-workbench__body${mobileDetailOpen ? ' is-mobile-detail' : ''}`}>
          <PartLedger page={partsQuery.data} loading={partsQuery.isLoading} failed={partsQuery.isError} selectedId={selectedId} logoUrl={branding?.logo_url || null} companyName={branding?.name || null} onSelect={(id) => { setSelectedId(id); setMobileDetailOpen(true) }} onRetry={() => void partsQuery.refetch()} onPage={(next) => { setSkip(next); setMobileDetailOpen(false) }} />
          <PartInspector part={detailQuery.data} loading={detailQuery.isLoading} failed={detailQuery.isError} manage={manage} logoUrl={branding?.logo_url || null} companyName={branding?.name || null} onBack={() => setMobileDetailOpen(false)} onRetry={() => void detailQuery.refetch()} onAdjust={updatePart} onPrepare={addToPreparation} onPurchasing={() => navigate('/dashboard/garage/purchasing')} onOpenPurchaseOrder={(id) => navigate(`/dashboard/garage/purchasing?view=orders&purchase_order=${encodeURIComponent(id)}`)} onOpenRepair={(id) => navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(id)}`)} />
        </div>
      </>}
  </section>
}

function PartLedger({ page, loading, failed, selectedId, logoUrl, companyName, onSelect, onRetry, onPage }: { page?: Page<PartRecord>; loading: boolean; failed: boolean; selectedId: string | null; logoUrl: string | null; companyName: string | null; onSelect: (id: string) => void; onRetry: () => void; onPage: (skip: number) => void }) {
  if (loading) return <div className="db-parts-workbench__state" role="status">Loading parts…</div>
  if (failed) return <div className="db-parts-workbench__state" role="alert">Parts could not be loaded.<button type="button" onClick={onRetry}>Retry</button></div>
  if (!page?.items.length) return <div className="db-parts-workbench__state"><strong>No parts match this view.</strong><span>Change the search or catalog filter to see more.</span></div>
  return <div className="db-parts-workbench__ledger" aria-label={`${page.total} matching parts`}>
    <div className="db-parts-workbench__table-head" aria-hidden="true"><span>Part</span><span>Available</span><span>Open repairs</span><span>Reorder at</span><span>Incoming</span></div>
    <div className="db-parts-workbench__rows">
      {page.items.map((part) => <button key={part.id} type="button" className={selectedId === part.id ? 'is-selected' : ''} aria-current={selectedId === part.id ? 'true' : undefined} onClick={() => onSelect(part.id)}>
        <span className="db-parts-workbench__identity"><PartPhoto part={part} logoUrl={logoUrl} companyName={companyName} /><span><strong>{part.name}</strong><small>{part.sku} · {part.location ? `Bin ${part.location}` : 'Bin not set'}{part.preferred_source?.supplier_name ? ` · ${part.preferred_source.supplier_name}` : ''}</small></span></span>
        <strong data-label="Available">{part.available_packages}</strong>
        <strong data-label="Open repairs">{part.needed_for_open_repairs}</strong>
        <strong data-label="Reorder at">{part.reorder_level}</strong>
        <strong data-label="Incoming">{part.incoming_packages}</strong>
      </button>)}
    </div>
    <Pager page={page} onPage={onPage} />
  </div>
}

function Pager({ page, onPage }: { page: Page<unknown>; onPage: (skip: number) => void }) {
  return <div className="db-parts-workbench__pager"><span>{page.total ? `${page.skip + 1}–${Math.min(page.skip + page.items.length, page.total)} of ${page.total}` : '0 results'}</span><div><button type="button" disabled={page.skip === 0} onClick={() => onPage(Math.max(0, page.skip - page.limit))}>Previous</button><button type="button" disabled={!page.has_more} onClick={() => onPage(page.skip + page.limit)}>Next</button></div></div>
}

function PartInspector({ part, loading, failed, manage, logoUrl, companyName, onBack, onRetry, onAdjust, onPrepare, onPurchasing, onOpenPurchaseOrder, onOpenRepair }: { part?: PartDetail; loading: boolean; failed: boolean; manage: boolean; logoUrl: string | null; companyName: string | null; onBack: () => void; onRetry: () => void; onAdjust: (part: PartDetail, patch: Record<string, unknown>) => Promise<void>; onPrepare: (part: PartDetail) => void; onPurchasing: () => void; onOpenPurchaseOrder: (id: string) => void; onOpenRepair: (id: string) => void }) {
  const [edit, setEdit] = useState<'available' | 'reorder' | null>(null)
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)
  const availableTrigger = useRef<HTMLButtonElement>(null)
  const reorderTrigger = useRef<HTMLButtonElement>(null)
  const restore = useRef<'available' | 'reorder' | null>(null)
  useEffect(() => { setEdit(null); setLocalError(null); setReason('') }, [part?.id])
  useEffect(() => {
    if (edit || !restore.current) return
    const target = restore.current === 'available' ? availableTrigger : reorderTrigger
    restore.current = null
    const frame = window.requestAnimationFrame(() => target.current?.focus())
    return () => window.cancelAnimationFrame(frame)
  }, [edit])
  const open = (next: 'available' | 'reorder') => { if (!part) return; setValue(String(next === 'available' ? part.available_packages : part.reorder_level)); setReason(''); setLocalError(null); setEdit(next) }
  const close = () => { restore.current = edit; setEdit(null); setLocalError(null) }
  const save = async () => {
    if (!part || !edit || saving) return
    if (!/^\d+$/.test(value.trim())) { setLocalError('Enter a whole number of zero or more.'); return }
    if (edit === 'available' && Number(value) !== part.available_packages && !reason.trim()) { setLocalError('Explain why available stock is changing.'); return }
    setSaving(true); setLocalError(null)
    try {
      await onAdjust(part, edit === 'available' ? { stock_quantity: Number(value), stock_adjustment_reason: reason.trim() } : { reorder_level: Number(value) })
      close()
    } catch { /* Parent keeps the exact server recovery message. */ } finally { setSaving(false) }
  }
  if (loading) return <aside className="db-parts-workbench__inspector" role="status">Loading part details…</aside>
  if (failed) return <aside className="db-parts-workbench__inspector" role="alert">Part details could not be loaded.<button type="button" onClick={onRetry}>Retry</button></aside>
  if (!part) return <aside className="db-parts-workbench__inspector"><p>Select a part to see stock, supplier, repair, and purchase history.</p></aside>
  return <aside className="db-parts-workbench__inspector" aria-labelledby="selected-part-name">
    <button className="db-parts-workbench__mobile-back" type="button" onClick={onBack}>Back to parts</button>
    <div className="db-parts-workbench__part-head"><div><h2 id="selected-part-name">{part.name}</h2><p>{part.sku} · {part.location ? <><MapPin aria-hidden="true" />Bin {part.location}</> : 'Bin not set'} · {part.unit_type || 'Unit not set'}</p></div><PartPhoto part={part} logoUrl={logoUrl} companyName={companyName} detail /></div>
    {part.is_archived && <p className="db-parts-workbench__archive" role="status">Archived part. History stays available, but stock and purchasing actions are locked.</p>}
    <section className="db-parts-workbench__section"><h3>Stock</h3><dl className="db-parts-workbench__facts"><div><dt>Available</dt><dd>{part.available_packages}</dd></div><div><dt>Needed for open repairs</dt><dd>{part.needed_for_open_repairs}</dd></div><div><dt>Reorder at</dt><dd>{part.reorder_level}</dd></div><div><dt>Incoming</dt><dd>{part.incoming_packages}</dd></div></dl>
      {manage && !part.is_archived && !edit && <div className="db-parts-workbench__actions"><button ref={availableTrigger} type="button" onClick={() => open('available')}>Adjust available stock</button><button ref={reorderTrigger} type="button" onClick={() => open('reorder')}>Change reorder point</button></div>}
      {!manage && !part.is_archived && <p className="db-parts-workbench__muted">You can view stock. Owners and admins can make changes.</p>}
      {edit && <form className="db-parts-workbench__edit" onSubmit={(event) => { event.preventDefault(); void save() }}><h4>{edit === 'available' ? 'Adjust available stock' : 'Change reorder point'}</h4><label>{edit === 'available' ? 'Available packages' : 'Reorder at'}<input autoFocus disabled={saving} type="number" min={0} step={1} value={value} onChange={(event) => { setValue(event.target.value); setLocalError(null) }} /></label>{edit === 'available' && <label>Adjustment reason<textarea disabled={saving} rows={3} value={reason} onChange={(event) => { setReason(event.target.value); setLocalError(null) }} placeholder="Cycle count, damage, return to shelf…" /></label>}{localError && <p role="alert">{localError}</p>}<div><button type="button" disabled={saving} onClick={close}>Cancel</button><button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save change'}</button></div></form>}
    </section>
    <section className="db-parts-workbench__section">
      <div className="db-parts-workbench__section-head"><h3>Ordering</h3><button type="button" onClick={onPurchasing}>Open Purchasing<ArrowRight aria-hidden="true" /></button></div>
      <dl className="db-parts-workbench__facts"><div><dt>Recommended order</dt><dd>{part.recommended_order_packages}</dd></div><div><dt>Average unit cost</dt><dd>${part.average_unit_cost}</dd></div></dl>
      <SupplierSources part={part} manage={manage && !part.is_archived} onChanged={onRetry} />
      {manage && !part.is_archived && part.recommended_order_packages > 0 && <button className="db-parts-workbench__purchase" type="button" onClick={() => onPrepare(part)} disabled={!part.preferred_source}>{part.preferred_source ? 'Add to purchase list' : 'Supplier source required'}</button>}
      <div className="db-parts-workbench__purchase-history">
        <h4>Open purchase orders</h4>
        {part.incoming_sources.length ? part.incoming_sources.map((source) => <button className="db-parts-workbench__linked-row" type="button" key={source.purchase_order_id} onClick={() => onOpenPurchaseOrder(source.purchase_order_id)}><span><strong>{source.po_number}</strong><small>{source.expected_at ? `Expected ${formatDate(source.expected_at)}` : 'Delivery date not set'}</small></span><strong>{source.packages} incoming</strong><ArrowRight aria-hidden="true" /></button>) : <p className="db-parts-workbench__muted">No open purchase order includes this part.</p>}
        <h4>Recent receipts</h4>
        {part.recent_receipts.length ? part.recent_receipts.map((receipt) => <button className="db-parts-workbench__linked-row" type="button" key={receipt.receipt_id} onClick={() => onOpenPurchaseOrder(receipt.purchase_order_id)}><span><strong>{receipt.receipt_number}</strong><small>{receipt.po_number} · Received {formatDate(receipt.received_at)}</small></span><strong>{receipt.quantity} at ${receipt.unit_cost}</strong><ArrowRight aria-hidden="true" /></button>) : <p className="db-parts-workbench__muted">No receiving history has been recorded for this part.</p>}
      </div>
    </section>
    <section className="db-parts-workbench__section"><h3>Open repair needs</h3>{part.repair_sources.length ? part.repair_sources.map((source) => <button className="db-parts-workbench__linked-row" type="button" key={source.repair_order_id} onClick={() => onOpenRepair(source.repair_order_id)}><span><strong>{source.order_number}</strong><small>{source.unit_number ? `Unit ${source.unit_number} · ` : ''}{source.vehicle_display || 'Vehicle not set'}</small></span><strong>{source.packages} needed</strong><ArrowRight aria-hidden="true" /></button>) : <p className="db-parts-workbench__muted">No open repair is waiting on this part.</p>}</section>
    <section className="db-parts-workbench__section"><h3>Recent inventory changes</h3>{part.recent_movements.length ? part.recent_movements.slice(0, 6).map((movement) => <div className="db-parts-workbench__movement-row" key={movement.id}><span><strong>{movementLabel(movement.movement_type)}</strong><small>{new Date(movement.occurred_at).toLocaleString()}</small></span><strong>{movement.quantity_delta > 0 ? '+' : ''}{movement.quantity_delta} · {movement.balance_after} available</strong></div>) : <p className="db-parts-workbench__muted">No inventory changes have been recorded for this part.</p>}</section>
  </aside>
}

function SupplierSources({ part, manage, onChanged }: { part: PartDetail; manage: boolean; onChanged: () => void }) {
  const queryClient = useQueryClient()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [editing, setEditing] = useState<SupplierSource | 'new' | null>(null)
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

  const close = () => {
    setEditing(null)
    setLocalError(null)
    setConfirmDelete(false)
    window.requestAnimationFrame(() => triggerRef.current?.focus())
  }
  const open = (source: SupplierSource | 'new') => {
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
      {manage && !editing && <button ref={triggerRef} type="button" onClick={() => open('new')}>Add supplier source</button>}
    </div>
    {part.supplier_sources.length ? <div className="db-parts-workbench__sources-list">{part.supplier_sources.map((source) => <button key={source.source_id} type="button" disabled={!manage || Boolean(editing)} onClick={() => open(source)}>
      <span><strong>{source.supplier_name || 'Supplier'}{source.is_preferred ? ' · Preferred' : ''}</strong><small>{source.supplier_part_number || 'Supplier part number not set'} · Pack {source.pack_quantity} · Min {source.minimum_order_quantity} · {source.lead_time_days == null ? 'Lead time not set' : `${source.lead_time_days} day lead time`}</small></span>
      <span><small>Last received cost</small><strong>{source.last_unit_cost == null ? 'Not recorded' : `$${source.last_unit_cost}`}</strong></span>
    </button>)}</div> : <p className="db-parts-workbench__muted">No supplier source is set. Add one here before preparing this part for purchase.</p>}

    {editing && <form className="db-parts-workbench__source-editor" onSubmit={(event) => { event.preventDefault(); void save() }}>
      <h4>{editing === 'new' ? 'Add supplier source' : `Edit ${editing.supplier_name || 'supplier source'}`}</h4>
      {editing === 'new' && <label>Supplier<select autoFocus disabled={saving || suppliersQuery.isLoading} value={supplierId} onChange={(event) => setSupplierId(event.target.value)}><option value="">Choose supplier</option>{(suppliersQuery.data?.items || []).filter((supplier) => !part.supplier_sources.some((source) => source.supplier_id === supplier.id)).map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.name}</option>)}</select></label>}
      <label>Supplier part number<input autoFocus={editing !== 'new'} disabled={saving} value={supplierPartNumber} maxLength={150} onChange={(event) => setSupplierPartNumber(event.target.value)} /></label>
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
  return <div className="db-parts-workbench__movement-ledger">{page.items.map((movement) => <article key={movement.id}><div><strong>{movement.inventory?.name || 'Inventory change'}</strong><p>{movementLabel(movement.movement_type)} · {movement.balance_after} available after change{movement.wac_after ? ` · Average cost $${movement.wac_after}` : ''}</p></div><div>{movement.source?.type === 'repair_order' ? <button type="button" onClick={() => onOpenRepair(movement.source!.id)}>{movement.source.order_number || 'Open repair'}<ArrowRight aria-hidden="true" /></button> : <span>{movement.source?.receipt_number || movement.source?.return_number || 'Stock record'}</span>}<time>{formatDate(movement.occurred_at)}</time></div></article>)}<Pager page={page} onPage={onPage} /></div>
}
