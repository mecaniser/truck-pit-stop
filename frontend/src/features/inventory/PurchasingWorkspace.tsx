import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ClipboardCheck, PackageCheck, RotateCcw, Store, Truck } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import SuppliersPage from '@/features/suppliers/SuppliersPage'
import PartsOperationsWorkspace from './PartsOperationsWorkspace'
import {
  readPurchasePreparation,
  writePurchasePreparation,
  type PurchasePreparationLine,
} from './PartsInventoryWorkspace'
import './PurchasingWorkspace.css'

type Summary = { low_stock_count: number; open_purchase_order_count: number }
type PurchasingView = 'orders' | 'suppliers' | 'receiving' | 'returns'
type StoredBatchKey = { fingerprint: string; key: string }

const PURCHASE_BATCH_KEY = 'dieselbridge:db038:purchase-batch-key:v1'

const views = [
  { id: 'orders', label: 'Purchase orders', icon: ClipboardCheck },
  { id: 'suppliers', label: 'Suppliers', icon: Store },
  { id: 'receiving', label: 'Receiving', icon: PackageCheck },
  { id: 'returns', label: 'Returns & cores', icon: RotateCcw },
] as const

function purchasingView(value: string | null): PurchasingView {
  return views.some((view) => view.id === value) ? value as PurchasingView : 'orders'
}

function canPurchase(role: string | undefined) {
  return role === 'garage_owner' || role === 'garage_admin'
}

function lineIssue(line: PurchasePreparationLine) {
  const pack = Math.max(1, line.packQuantity)
  const minimum = Math.max(1, line.minimumOrderQuantity)
  if (!Number.isInteger(line.quantity) || line.quantity < minimum) {
    return `Minimum ${minimum}`
  }
  if (line.quantity % pack !== 0) return `Order in packs of ${pack}`
  return null
}

function normalizedQuantity(line: PurchasePreparationLine) {
  const pack = Math.max(1, line.packQuantity)
  const minimum = Math.max(1, line.minimumOrderQuantity)
  return Math.ceil(Math.max(minimum, Math.floor(line.quantity || 0)) / pack) * pack
}

function requestError(error: unknown) {
  const candidate = error as { response?: { status?: number; data?: { detail?: unknown } }; message?: string }
  if (candidate.response?.status === 404) {
    return 'A part or supplier source changed. Refresh Parts & inventory, then prepare the order again.'
  }
  if (candidate.response?.status === 409) return 'This purchase preparation was already used or changed. Review it and try again.'
  const detail = candidate.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => (item as { msg?: string }).msg).filter(Boolean).join(' ')
  return candidate.message || 'The draft purchase orders could not be created.'
}

function batchFingerprint(lines: PurchasePreparationLine[]) {
  return JSON.stringify([...lines]
    .sort((left, right) => left.inventoryId.localeCompare(right.inventoryId))
    .map((line) => [line.inventoryId, line.sourceId, line.supplierId, line.quantity, line.unitCost]))
}

function batchIdempotencyKey(lines: PurchasePreparationLine[]) {
  const fingerprint = batchFingerprint(lines)
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(PURCHASE_BATCH_KEY) || 'null') as StoredBatchKey | null
    if (stored?.fingerprint === fingerprint && stored.key) return stored.key
  } catch { /* Replace malformed session state below. */ }
  const key = `po-batch-${crypto.randomUUID()}`
  window.sessionStorage.setItem(PURCHASE_BATCH_KEY, JSON.stringify({ fingerprint, key } satisfies StoredBatchKey))
  return key
}

export default function PurchasingWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const role = useAuthStore((state) => state.user?.role)
  const mayRead = role === 'garage_owner' || role === 'garage_admin' || role === 'receptionist'
  const view = purchasingView(searchParams.get('view'))
  const linkedPurchaseOrderId = searchParams.get('purchase_order')
  const summaryQuery = useQuery<Summary>({
    queryKey: ['parts-operations', 'summary'],
    queryFn: async () => (await api.get('/parts-operations/summary')).data,
    enabled: mayRead,
    retry: false,
    staleTime: 60_000,
  })
  const [preparationCount, setPreparationCount] = useState(() => readPurchasePreparation().length)

  useEffect(() => {
    const refresh = () => setPreparationCount(readPurchasePreparation().length)
    window.addEventListener('db038:purchase-preparation', refresh)
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener('db038:purchase-preparation', refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])

  if (!mayRead) return <div className="db-purchasing__gate" role="alert">Purchasing is available to shop owners, admins, and reception staff.</div>
  if (summaryQuery.isPending) return <div className="db-purchasing__gate" role="status">Opening Purchasing…</div>
  if (summaryQuery.isError) return <div className="db-purchasing__gate" role="alert"><span>Purchasing is not available for this shop right now.</span><button type="button" onClick={() => void summaryQuery.refetch()}>Retry</button></div>

  const selectView = (next: PurchasingView) => setSearchParams({ view: next }, { replace: true })
  const summary = summaryQuery.data

  return <section className="db-purchasing" aria-labelledby="purchasing-title">
    <header className="db-purchasing__header">
      <div>
        <h1 id="purchasing-title">Purchasing</h1>
        <p>Prepare supplier orders, receive deliveries, and close the loop on returns and cores.</p>
      </div>
      <button type="button" onClick={() => navigate('/dashboard/garage/inventory')}>
        <ArrowLeft aria-hidden="true" />Parts & inventory
      </button>
    </header>

    <nav className="db-purchasing__tabs" aria-label="Purchasing areas">
      {views.map(({ id, label, icon: Icon }) => <button
        key={id}
        type="button"
        aria-current={view === id ? 'page' : undefined}
        onClick={() => selectView(id)}
      >
        <Icon aria-hidden="true" />
        <span>{label}</span>
        {id === 'orders' && preparationCount > 0 ? <strong aria-label={`${preparationCount} parts prepared`}>{preparationCount}</strong> : null}
      </button>)}
    </nav>

    <div className="db-purchasing__content">
      {view === 'orders' && <>
        <PurchasePreparationTray onCreated={() => selectView('orders')} />
        <WorkspaceIntroduction title="Current purchase orders">Review draft orders, submit approved orders, and see what is still expected from each supplier.</WorkspaceIntroduction>
        <PartsOperationsWorkspace key={`purchasing-orders-${linkedPurchaseOrderId || 'default'}`} summary={summary} initialTab="purchase-orders" initialPurchaseOrderId={linkedPurchaseOrderId} visibleTabs={['purchase-orders']} embedded />
      </>}

      {view === 'suppliers' && <>
        <WorkspaceIntroduction title="Suppliers">Keep supplier contacts current. Part numbers, pack sizes, lead times, and preferred sources remain attached to each part.</WorkspaceIntroduction>
        <SuppliersPage />
      </>}

      {view === 'receiving' && <>
        <WorkspaceIntroduction title="Receiving">Open a submitted purchase order, record the delivered quantity and cost, and let inventory update from the receipt.</WorkspaceIntroduction>
        <PartsOperationsWorkspace key="purchasing-receiving" summary={summary} initialTab="purchase-orders" purchaseOrderMode="receiving" visibleTabs={['purchase-orders']} embedded />
      </>}

      {view === 'returns' && <>
        <WorkspaceIntroduction title="Returns & cores">Track parts going back to suppliers and the refundable cores the shop still holds.</WorkspaceIntroduction>
        <PartsOperationsWorkspace key="purchasing-returns" summary={summary} initialTab="returns-cores" visibleTabs={['returns-cores']} embedded />
      </>}
    </div>
  </section>
}

function WorkspaceIntroduction({ title, children }: { title: string; children: string }) {
  return <div className="db-purchasing__introduction">
    <h2>{title}</h2>
    <p>{children}</p>
  </div>
}

function PurchasePreparationTray({ onCreated }: { onCreated: () => void }) {
  const role = useAuthStore((state) => state.user?.role)
  const mayCreate = canPurchase(role)
  const queryClient = useQueryClient()
  const [lines, setLines] = useState<PurchasePreparationLine[]>(readPurchasePreparation)
  const [submitting, setSubmitting] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const refresh = () => setLines(readPurchasePreparation())
    window.addEventListener('db038:purchase-preparation', refresh)
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener('db038:purchase-preparation', refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])

  const groups = useMemo(() => {
    const grouped = new Map<string, { supplierId: string; supplierName: string; lines: PurchasePreparationLine[] }>()
    lines.forEach((line) => {
      const current = grouped.get(line.supplierId) || { supplierId: line.supplierId, supplierName: line.supplierName, lines: [] }
      current.lines.push(line)
      grouped.set(line.supplierId, current)
    })
    return Array.from(grouped.values()).sort((left, right) => left.supplierName.localeCompare(right.supplierName))
  }, [lines])
  const hasInvalidLine = lines.some(lineIssue)

  const commit = (next: PurchasePreparationLine[]) => {
    setLines(next)
    writePurchasePreparation(next)
    setNotice(null)
    setError(null)
  }
  const updateQuantity = (inventoryId: string, quantity: number, normalize = false) => commit(lines.map((line) => {
    if (line.inventoryId !== inventoryId) return line
    const next = { ...line, quantity: Number.isFinite(quantity) ? Math.max(0, Math.floor(quantity)) : 0 }
    return normalize ? { ...next, quantity: normalizedQuantity(next) } : next
  }))
  const removeLine = (inventoryId: string) => commit(lines.filter((line) => line.inventoryId !== inventoryId))

  const createDrafts = async () => {
    if (!mayCreate || !lines.length || hasInvalidLine || submitting) return
    setSubmitting(true)
    setNotice(null)
    setError(null)
    try {
      const response = await api.post('/parts-operations/purchase-orders/batch', {
        groups: groups.map((group) => ({
          supplier_id: group.supplierId,
          lines: group.lines.map((line) => ({
            inventory_id: line.inventoryId,
            source_id: line.sourceId,
            ordered_quantity: line.quantity,
            unit_cost: line.unitCost,
          })),
        })),
        notes: 'Prepared from Parts & inventory',
      }, { headers: { 'Idempotency-Key': batchIdempotencyKey(lines) } })
      const count = Number(response.data?.count || response.data?.purchase_orders?.length || groups.length)
      writePurchasePreparation([])
      window.sessionStorage.removeItem(PURCHASE_BATCH_KEY)
      setLines([])
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'summary'] }),
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'parts'] }),
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'purchase-orders'] }),
        queryClient.invalidateQueries({ queryKey: ['parts-operations', 'purchase-order'] }),
      ])
      setNotice(`${count} draft purchase ${count === 1 ? 'order' : 'orders'} created. Nothing was submitted to a supplier.`)
      onCreated()
    } catch (cause) {
      setError(requestError(cause))
    } finally {
      setSubmitting(false)
    }
  }

  return <section className="db-purchasing__preparation" aria-labelledby="purchase-preparation-title">
    <div className="db-purchasing__preparation-head">
      <div>
        <h2 id="purchase-preparation-title">Ready to prepare</h2>
        <p>Parts added from the reorder list are grouped by supplier. Creating drafts does not send or submit them.</p>
      </div>
      {lines.length > 0 ? <span>{lines.length} {lines.length === 1 ? 'part' : 'parts'} · {groups.length} {groups.length === 1 ? 'supplier' : 'suppliers'}</span> : null}
    </div>

    {notice && <p className="db-purchasing__notice" role="status">{notice}</p>}
    {error && <p className="db-purchasing__error" role="alert">{error}</p>}

    {!lines.length ? <div className="db-purchasing__empty">
      <Truck aria-hidden="true" />
      <span><strong>No parts are waiting to be prepared.</strong><small>Use “Add to purchase list” from a part that needs reorder.</small></span>
    </div> : <div className="db-purchasing__supplier-groups">
      {groups.map((group) => <section key={group.supplierId} className="db-purchasing__supplier-group" aria-labelledby={`supplier-group-${group.supplierId}`}>
        <header>
          <h3 id={`supplier-group-${group.supplierId}`}>{group.supplierName}</h3>
          <span>{group.lines.length} {group.lines.length === 1 ? 'line' : 'lines'} · ${group.lines.reduce((total, line) => total + line.quantity * Number(line.unitCost || 0), 0).toFixed(2)}</span>
        </header>
        <div className="db-purchasing__lines">
          {group.lines.map((line) => {
            const issue = lineIssue(line)
            return <div key={line.inventoryId} className="db-purchasing__line">
              <span className="db-purchasing__line-name">
                <strong>{line.name}</strong>
                <small>{line.sku}{line.supplierPartNumber ? ` · Supplier part ${line.supplierPartNumber}` : ''}</small>
              </span>
              <label>
                <span>Quantity</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={Math.max(1, line.minimumOrderQuantity)}
                  step={Math.max(1, line.packQuantity)}
                  value={line.quantity}
                  aria-invalid={Boolean(issue)}
                  aria-describedby={issue ? `purchase-line-issue-${line.inventoryId}` : undefined}
                  onChange={(event) => updateQuantity(line.inventoryId, Number(event.target.value))}
                  onBlur={() => updateQuantity(line.inventoryId, line.quantity, true)}
                />
                {issue ? <small id={`purchase-line-issue-${line.inventoryId}`} role="alert">{issue}</small> : <small>Pack {Math.max(1, line.packQuantity)} · min {Math.max(1, line.minimumOrderQuantity)}</small>}
              </label>
              <span className="db-purchasing__line-cost"><small>Last unit cost</small><strong>${Number(line.unitCost || 0).toFixed(2)}</strong></span>
              <button type="button" onClick={() => removeLine(line.inventoryId)} aria-label={`Remove ${line.name} from purchase preparation`}>Remove</button>
            </div>
          })}
        </div>
      </section>)}
    </div>}

    {lines.length > 0 && <div className="db-purchasing__preparation-actions">
      {!mayCreate && <p>Read-only access. Owners and admins can create draft purchase orders.</p>}
      {hasInvalidLine && <p>Correct the highlighted quantities before creating drafts.</p>}
      <button type="button" disabled={!mayCreate || hasInvalidLine || submitting} onClick={() => void createDrafts()}>
        {submitting ? 'Creating drafts…' : `Create ${groups.length} draft ${groups.length === 1 ? 'order' : 'orders'}`}
      </button>
    </div>}
  </section>
}
