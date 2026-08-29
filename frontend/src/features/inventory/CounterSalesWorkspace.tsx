import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Download, Plus, ReceiptText, RotateCcw, Search, ShoppingBag, X } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import QuantityStepper from '@/components/QuantityStepper'
import { useTheme } from '@/contexts/ThemeContext'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { PartRecord } from './PartsInventoryWorkspace'
import {
  COUNTER_SALE_TENDER_LABELS,
  type CounterSale,
  type CounterSaleDraftLine,
  type CounterSaleListItem,
  type CounterSaleReturn,
  type CounterSaleTender,
  type CursorPage,
} from './inventoryLifecycleTypes'

type PartSearchPage = { items: PartRecord[]; total: number; skip: number; limit: number; has_more: boolean }
type CustomerOption = { id: string; name: string; email?: string | null; phone?: string | null }
type SalePart = Pick<PartRecord, 'id' | 'sku' | 'name' | 'unit_type' | 'available_packages' | 'physical_on_hand_packages' | 'held_for_checkout_packages' | 'available_to_sell_packages'> & Partial<Pick<PartRecord, 'is_archived' | 'is_placeholder'>>
type DraftSelection = { part: SalePart; quantity: number; overridePrice: string; overrideReason: string }
type ReturnDraft = { quantity: number; reason: string; disposition: 'restock' | 'damaged' }

const SALE_STATUSES = ['', 'draft', 'completed', 'partially_returned', 'returned', 'cancelled'] as const

function formatMoney(value: string | null | undefined) {
  if (value == null || value === '') return '—'
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(Number(value))
}

function idempotency(family: string) {
  return `${family}-${crypto.randomUUID()}`
}

function safeError(error: unknown, fallback: string) {
  return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || fallback
}

function saleStateLabel(value: string) {
  return value.replace(/_/g, ' ')
}

function canManage(role?: string) {
  return role === 'garage_owner' || role === 'garage_admin'
}

function SaleList({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [cursors, setCursors] = useState<Array<string | null>>([null])
  const cursor = cursors[cursors.length - 1] || null
  const query = useQuery<CursorPage<CounterSaleListItem>>({
    queryKey: ['counter-sales', 'list', search, status, cursor],
    queryFn: async () => (await api.get('/parts-operations/counter-sales', {
      params: { ...(search ? { text: search } : {}), ...(status ? { status } : {}), ...(cursor ? { cursor } : {}), limit: 50 },
    })).data,
    retry: false,
  })

  return <div className="db-counter-sales__list">
    <div className="db-counter-sales__list-head">
      <div><h1>Parts sales</h1><p>Occasional walk-in sales, receipts, and audited returns.</p></div>
      <button type="button" onClick={onNew}><Plus aria-hidden="true" />New counter sale</button>
    </div>
    <form className="db-counter-sales__list-filters" onSubmit={(event) => { event.preventDefault(); setSearch(searchDraft.trim()); setCursors([null]) }}>
      <label><Search aria-hidden="true" /><span className="sr-only">Search parts sales</span><input type="search" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Search sale number or buyer" /></label>
      <select aria-label="Filter sale status" value={status} onChange={(event) => { setStatus(event.target.value); setCursors([null]) }}>
        {SALE_STATUSES.map((value) => <option key={value} value={value}>{value ? saleStateLabel(value) : 'All statuses'}</option>)}
      </select>
      <button type="submit">Search</button>
    </form>
    {query.isPending && <div className="db-counter-sales__state" role="status">Loading parts sales…</div>}
    {query.isError && <div className="db-counter-sales__state" role="alert">Parts sales could not be loaded.<button type="button" onClick={() => void query.refetch()}>Retry</button></div>}
    {!query.isPending && !query.isError && !query.data.items.length && <div className="db-counter-sales__state"><ShoppingBag aria-hidden="true" /><strong>No counter sales match this view.</strong><span>Start a walk-in sale or adjust the filters.</span></div>}
    {!!query.data?.items.length && <div className="db-counter-sales__sale-rows">{query.data.items.map((sale) =>
      <button type="button" key={sale.id} onClick={() => onOpen(sale.id)}>
        <span><strong>{sale.sale_number}</strong><small>{sale.buyer_name || 'Walk-in customer'} · {sale.line_count} {sale.line_count === 1 ? 'line' : 'lines'}</small></span>
        <span><em data-status={sale.status}>{saleStateLabel(sale.status)}</em><strong>{formatMoney(sale.total_amount)}</strong><small>{new Date(sale.completed_at || sale.created_at).toLocaleString()}</small></span>
        <ArrowRight aria-hidden="true" />
      </button>)}</div>}
    {query.data && <div className="db-counter-sales__pager">
      <span aria-live="polite">Showing {query.data.items.length} sales</span>
      <div><button type="button" disabled={cursors.length === 1 || query.isFetching} onClick={() => setCursors((current) => current.slice(0, -1))}>Previous</button><button type="button" disabled={!query.data.next_cursor || query.isFetching} onClick={() => query.data.next_cursor && setCursors((current) => [...current, query.data.next_cursor])}>Next</button></div>
    </div>}
  </div>
}

function DraftSale({ initialPartId, existingSale, onSaved, onCancel }: { initialPartId: string | null; existingSale?: CounterSale; onSaved: (id: string) => void; onCancel: () => void }) {
  const role = useAuthStore((state) => state.user?.role)
  const { appearance } = useTheme()
  const manager = canManage(role)
  const [partSearch, setPartSearch] = useState('')
  const [customerSearch, setCustomerSearch] = useState(existingSale?.buyer_name || '')
  const [customer, setCustomer] = useState<CustomerOption | null>(existingSale?.customer_id ? { id: existingSale.customer_id, name: existingSale.buyer_name || 'Linked customer', email: existingSale.buyer_email, phone: existingSale.buyer_phone } : null)
  const [buyerName, setBuyerName] = useState(existingSale?.buyer_name || '')
  const [buyerEmail, setBuyerEmail] = useState(existingSale?.buyer_email || '')
  const [buyerPhone, setBuyerPhone] = useState(existingSale?.buyer_phone || '')
  const [lines, setLines] = useState<DraftSelection[]>(() => existingSale?.lines.map((line) => ({
    part: {
      id: line.inventory_id,
      sku: line.sku,
      name: line.name,
      unit_type: line.unit_type,
      available_packages: line.available_to_sell,
      physical_on_hand_packages: line.physical_on_hand,
      held_for_checkout_packages: 0,
      available_to_sell_packages: line.available_to_sell,
    },
    quantity: line.quantity,
    overridePrice: line.price_override_reason ? line.charged_unit_price : '',
    overrideReason: line.price_override_reason || '',
  })) || [])
  const [error, setError] = useState<string | null>(null)
  const initialAdded = useRef(false)

  const partsQuery = useQuery<PartSearchPage>({
    queryKey: ['parts-operations', 'sale-part-search', partSearch],
    queryFn: async () => (await api.get('/parts-operations/parts', { params: { view: 'active', search: partSearch.trim(), sort: 'name', direction: 'asc', paginated: true, skip: 0, limit: 20 } })).data,
    enabled: partSearch.trim().length >= 2,
    retry: false,
  })
  const initialPartQuery = useQuery<SalePart>({
    queryKey: ['parts-operations', 'sale-initial-part', initialPartId],
    queryFn: async () => (await api.get(`/parts-operations/parts/${initialPartId}`)).data,
    enabled: Boolean(initialPartId) && !existingSale,
    retry: false,
  })
  const customersQuery = useQuery<CustomerOption[]>({
    queryKey: ['customer-typeahead', customerSearch],
    queryFn: async () => {
      const response = await api.get('/customers/typeahead', { params: { q: customerSearch.trim(), limit: 8 } })
      return Array.isArray(response.data) ? response.data : response.data.items || []
    },
    enabled: customerSearch.trim().length >= 2,
    retry: false,
  })

  useEffect(() => {
    if (!initialPartId || initialAdded.current || !initialPartQuery.data) return
    initialAdded.current = true
    setLines([{ part: initialPartQuery.data, quantity: 1, overridePrice: '', overrideReason: '' }])
  }, [initialPartId, initialPartQuery.data])

  const addPart = (part: PartRecord) => setLines((current) => current.some((line) => line.part.id === part.id) ? current : [...current, { part, quantity: 1, overridePrice: '', overrideReason: '' }])
  const payloadLines = (): CounterSaleDraftLine[] => lines.map((line) => ({
    inventory_id: line.part.id,
    quantity: line.quantity,
    ...(line.overridePrice.trim() ? { charged_unit_price: line.overridePrice.trim(), price_override_reason: line.overrideReason.trim() } : {}),
  }))
  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        ...(existingSale ? { expected_version: existingSale.version } : {}),
        customer_id: customer?.id || null,
        buyer_name: buyerName.trim() || customer?.name || null,
        buyer_email: buyerEmail.trim() || customer?.email || null,
        buyer_phone: buyerPhone.trim() || customer?.phone || null,
        lines: payloadLines(),
      }
      const response = existingSale
        ? await api.patch(`/parts-operations/counter-sales/${existingSale.id}`, payload, { headers: { 'Idempotency-Key': idempotency('counter-sale-update') } })
        : await api.post('/parts-operations/counter-sales', payload, { headers: { 'Idempotency-Key': idempotency('counter-sale-create') } })
      return response.data as CounterSale
    },
    onSuccess: (sale) => onSaved(sale.id),
    onError: (cause) => setError(safeError(cause, existingSale ? 'The draft sale could not be updated.' : 'The draft sale could not be created.')),
  })
  const submit = () => {
    if (!lines.length) { setError('Add at least one part.'); return }
    if (lines.some((line) => line.overridePrice && (!manager || line.overrideReason.trim().length < 3))) {
      setError(manager ? 'Every price override needs a reason of at least 3 characters.' : 'Only an owner or admin can override catalog price.')
      return
    }
    setError(null)
    save.mutate()
  }

  return <div className="db-counter-sales__draft">
    <div className="db-counter-sales__workspace-head"><button type="button" onClick={onCancel}><ArrowLeft aria-hidden="true" />{existingSale ? existingSale.sale_number : 'Parts sales'}</button><div><h1>{existingSale ? 'Edit draft sale' : 'New counter sale'}</h1><p>Choose whole quantities, then record one manual tender at checkout.</p></div></div>
    <div className="db-counter-sales__draft-grid">
      <section>
        <h2>Parts</h2>
        <label className="db-counter-sales__search"><Search aria-hidden="true" /><span className="sr-only">Search catalog parts</span><input autoFocus type="search" value={partSearch} onChange={(event) => setPartSearch(event.target.value)} placeholder="Search part name or SKU" /></label>
        {initialPartQuery.isFetching && <p role="status">Loading selected part…</p>}
        {initialPartQuery.isError && <p role="alert">The selected part could not be loaded. Search for it to continue.</p>}
        {partsQuery.isFetching && <p role="status">Searching catalog…</p>}
        {partsQuery.data && <div className="db-counter-sales__search-results">{partsQuery.data.items.filter((part) => !part.is_archived && !part.is_placeholder).map((part) =>
          <button type="button" key={part.id} onClick={() => addPart(part)}><span><strong>{part.name}</strong><small>{part.sku}</small></span><span>{part.available_packages} on hand<Plus aria-hidden="true" /></span></button>)}</div>}
        <div className="db-counter-sales__draft-lines">{lines.map((line, index) => {
          const maximum = Math.max(1, line.part.available_to_sell_packages ?? line.part.available_packages)
          return <article key={line.part.id}>
            <div><strong>{line.part.name}</strong><small>{line.part.sku} · {line.part.unit_type || 'each'}</small><small>{line.part.physical_on_hand_packages ?? line.part.available_packages} on hand</small></div>
            <QuantityStepper value={line.quantity} min={1} step={1} unitLabel={line.part.unit_type || 'units'} ariaLabel={`Quantity for ${line.part.name}`} size="lg" theme={appearance.mode === 'light' ? 'light' : 'dark'} onChange={(quantity) => setLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, quantity: Math.min(maximum, Math.max(1, quantity)) } : item))} />
            {manager && <details><summary>Manager price override</summary><label>Charged unit price<input inputMode="decimal" value={line.overridePrice} onChange={(event) => setLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, overridePrice: event.target.value } : item))} placeholder="Use catalog price" /></label><label>Reason<input value={line.overrideReason} minLength={3} maxLength={500} onChange={(event) => setLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, overrideReason: event.target.value } : item))} placeholder="Required when price changes" /></label></details>}
            <button type="button" aria-label={`Remove ${line.part.name}`} onClick={() => setLines((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X aria-hidden="true" /></button>
          </article>
        })}</div>
      </section>
      <aside>
        <h2>Buyer</h2>
        <label>Existing customer<input value={customerSearch} onChange={(event) => { setCustomerSearch(event.target.value); setCustomer(null) }} placeholder="Optional customer lookup" /></label>
        {customersQuery.data && !customer && <div className="db-counter-sales__customer-results">{customersQuery.data.map((option) =>
          <button type="button" key={option.id} onClick={() => { setCustomer(option); setCustomerSearch(option.name); setBuyerName(option.name); setBuyerEmail(option.email || ''); setBuyerPhone(option.phone || '') }}><strong>{option.name}</strong><small>{option.email || option.phone || 'Customer record'}</small></button>)}</div>}
        <p>Anonymous walk-ins are valid. These optional details are saved as receipt snapshots.</p>
        <label>Buyer name<input value={buyerName} onChange={(event) => setBuyerName(event.target.value)} /></label>
        <label>Email<input type="email" value={buyerEmail} onChange={(event) => setBuyerEmail(event.target.value)} /></label>
        <label>Phone<input type="tel" value={buyerPhone} onChange={(event) => setBuyerPhone(event.target.value)} /></label>
        {error && <p className="db-counter-sales__error" role="alert">{error}</p>}
        <button className="db-counter-sales__primary" type="button" disabled={save.isPending} onClick={submit}>{save.isPending ? 'Saving draft…' : existingSale ? 'Save draft' : 'Review checkout'}<ArrowRight aria-hidden="true" /></button>
      </aside>
    </div>
  </div>
}

function ReturnPanel({ sale, onClose, onChanged }: { sale: CounterSale; onClose: () => void; onChanged: () => void }) {
  const { appearance } = useTheme()
  const closeRef = useRef<HTMLButtonElement>(null)
  const [lines, setLines] = useState<Record<string, ReturnDraft>>(() => Object.fromEntries(sale.lines.map((line) => [line.id, { quantity: 0, reason: '', disposition: 'restock' as const }])))
  const [manualReference, setManualReference] = useState('')
  const [error, setError] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: async () => (await api.post(`/parts-operations/counter-sales/${sale.id}/returns`, {
      expected_version: sale.version,
      lines: sale.lines.flatMap((line) => {
        const draft = lines[line.id]
        return draft?.quantity ? [{ sale_line_id: line.id, quantity: draft.quantity, reason: draft.reason.trim(), disposition: draft.disposition }] : []
      }),
      manual_refund_reference: manualReference.trim() || null,
    }, { headers: { 'Idempotency-Key': idempotency('counter-sale-return') } })).data as CounterSaleReturn,
    onSuccess: onChanged,
    onError: (cause) => setError(safeError(cause, 'The return could not be recorded.')),
  })

  useEffect(() => {
    closeRef.current?.focus()
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !mutation.isPending) { event.preventDefault(); onClose() } }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [mutation.isPending, onClose])

  const submit = () => {
    const selected = Object.values(lines).filter((line) => line.quantity > 0)
    if (!selected.length) { setError('Choose at least one unit to return.'); return }
    if (selected.some((line) => line.reason.trim().length < 3)) { setError('Every returned line needs a reason of at least 3 characters.'); return }
    setError(null)
    mutation.mutate()
  }

  return <div className="db-counter-sales__return-panel" role="dialog" aria-modal="true" aria-labelledby="return-sale-title">
    <div><h2 id="return-sale-title">Return items from {sale.sale_number}</h2><button ref={closeRef} type="button" aria-label="Close return" onClick={onClose}><X aria-hidden="true" /></button></div>
    <p>Restocked units return to on-hand. Damaged units remain out of inventory. Record any external refund separately.</p>
    {sale.lines.map((line) => {
      const remaining = line.remaining_returnable_quantity
      const draft = lines[line.id]
      return <article key={line.id}>
        <div><strong>{line.name}</strong><small>{remaining} of {line.quantity} returnable</small></div>
        <QuantityStepper value={draft?.quantity || 0} min={0} step={1} unitLabel={line.unit_type || 'units'} ariaLabel={`Return quantity for ${line.name}`} size="lg" theme={appearance.mode === 'light' ? 'light' : 'dark'} onChange={(quantity) => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], quantity: Math.min(remaining, Math.max(0, quantity)) } }))} />
        {!!draft?.quantity && <><label>Reason<textarea minLength={3} maxLength={500} value={draft.reason} onChange={(event) => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], reason: event.target.value } }))} /></label><fieldset><legend>Disposition</legend><label><input type="radio" name={`disposition-${line.id}`} checked={draft.disposition === 'restock'} onChange={() => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], disposition: 'restock' } }))} />Restock</label><label><input type="radio" name={`disposition-${line.id}`} checked={draft.disposition === 'damaged'} onChange={() => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], disposition: 'damaged' } }))} />Damaged</label></fieldset></>}
      </article>
    })}
    <label>Refund or reversal reference<input value={manualReference} onChange={(event) => setManualReference(event.target.value)} placeholder="Optional external reference" /></label>
    {error && <p role="alert">{error}</p>}
    <div className="db-counter-sales__dialog-actions"><button type="button" onClick={onClose}>Cancel</button><button type="button" disabled={mutation.isPending} onClick={submit}>{mutation.isPending ? 'Recording…' : 'Record return'}</button></div>
  </div>
}

function SaleDetail({ saleId, tenders, onBack }: { saleId: string; tenders: CounterSaleTender[]; onBack: () => void }) {
  const role = useAuthStore((state) => state.user?.role)
  const manager = canManage(role)
  const queryClient = useQueryClient()
  const [tender, setTender] = useState<CounterSaleTender>(tenders[0] || 'cash')
  const [manualReference, setManualReference] = useState('')
  const [cancelReason, setCancelReason] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [returnOpen, setReturnOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const returnTriggerRef = useRef<HTMLButtonElement>(null)
  const query = useQuery<CounterSale>({ queryKey: ['counter-sale', saleId], queryFn: async () => (await api.get(`/parts-operations/counter-sales/${saleId}`)).data, retry: false })
  const sale = query.data

  useEffect(() => { if (tenders.length && !tenders.includes(tender)) setTender(tenders[0]) }, [tender, tenders])
  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['counter-sale', saleId] }),
      queryClient.invalidateQueries({ queryKey: ['counter-sales'] }),
      queryClient.invalidateQueries({ queryKey: ['parts-operations', 'parts'] }),
    ])
  }
  const checkout = useMutation({
    mutationFn: async () => (await api.post(`/parts-operations/counter-sales/${saleId}/checkout`, {
      expected_version: sale!.version,
      tender,
      manual_reference: manualReference.trim() || null,
    }, { headers: { 'Idempotency-Key': idempotency('counter-sale-checkout') } })).data as CounterSale,
    onSuccess: async () => { await refresh(); setNotice('Sale completed and on-hand stock updated.'); setError(null) },
    onError: (cause) => setError(safeError(cause, 'Checkout could not be completed.')),
  })
  const cancel = useMutation({
    mutationFn: async () => (await api.post(`/parts-operations/counter-sales/${saleId}/cancel`, {
      expected_version: sale!.version,
      reason: cancelReason.trim(),
    }, { headers: { 'Idempotency-Key': idempotency('counter-sale-cancel') } })).data,
    onSuccess: async () => { await refresh(); setCancelReason(''); setNotice('Draft sale cancelled.'); setError(null) },
    onError: (cause) => setError(safeError(cause, 'The draft could not be cancelled.')),
  })
  const downloadReceipt = async () => {
    try {
      const response = await api.get(`/parts-operations/counter-sales/${saleId}/receipt.pdf`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${sale?.sale_number || 'counter-sale'}-receipt.pdf`
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(safeError(cause, 'Receipt PDF could not be downloaded.'))
    }
  }

  if (query.isPending) return <div className="db-counter-sales__state" role="status">Loading sale…</div>
  if (query.isError || !sale) return <div className="db-counter-sales__state" role="alert">This sale could not be loaded.<button type="button" onClick={() => void query.refetch()}>Retry</button></div>
  if (editing) return <DraftSale existingSale={sale} initialPartId={null} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); void refresh(); setNotice('Draft sale updated.') }} />

  const completed = ['completed', 'partially_returned', 'returned'].includes(sale.status)
  const closeReturn = () => {
    setReturnOpen(false)
    requestAnimationFrame(() => returnTriggerRef.current?.focus())
  }

  return <div className="db-counter-sales__detail">
    <div className="db-counter-sales__workspace-head"><button type="button" onClick={onBack}><ArrowLeft aria-hidden="true" />Parts sales</button><div><h1>{sale.sale_number}</h1><p>{sale.buyer_name || 'Walk-in customer'} · <span data-status={sale.status}>{saleStateLabel(sale.status)}</span></p></div></div>
    {(notice || error) && <div className={error ? 'db-counter-sales__error' : 'db-counter-sales__notice'} role={error ? 'alert' : 'status'}><span>{error || notice}</span><button type="button" onClick={() => { setError(null); setNotice(null) }}>Dismiss</button></div>}
    <div className="db-counter-sales__detail-grid">
      <main>
        <section className="db-counter-sales__lines">
          <div><h2>Sale lines</h2><span><strong>{sale.lines.length}</strong>{sale.allowed_actions.includes('edit_draft') && <button type="button" onClick={() => setEditing(true)}>Edit draft</button>}</span></div>
          {sale.lines.map((line) => <article key={line.id}><div><strong>{line.name}</strong><small>{line.sku} · {line.quantity} {line.unit_type || 'units'} × {formatMoney(line.charged_unit_price)}</small>{line.price_override_reason && <small>Manager override · {line.price_override_reason}</small>}</div><div><strong>{formatMoney(line.total_amount)}</strong><small>{line.physical_on_hand} on hand</small></div></article>)}
        </section>
        {!!sale.payment_attempts.length && <section className="db-counter-sales__attempts"><h2>Tender record</h2>{sale.payment_attempts.map((attempt) => <article key={attempt.id}><span><strong>{COUNTER_SALE_TENDER_LABELS[attempt.tender]}</strong><small>{attempt.reference || 'No external reference'} · {new Date(attempt.created_at).toLocaleString()}</small></span><span><em data-status={attempt.state}>recorded</em><strong>{formatMoney(attempt.amount)}</strong></span></article>)}</section>}
        {!!sale.returns.length && <section className="db-counter-sales__attempts"><h2>Returns</h2>{sale.returns.map((record) => <article key={record.id}><span><strong>{record.lines.reduce((sum, line) => sum + line.quantity, 0)} returned units</strong><small>{record.refund_reference || 'No external refund reference'} · {new Date(record.created_at).toLocaleString()}</small></span><span><em data-status={record.state}>recorded</em><strong>{formatMoney(record.refund_amount)}</strong></span></article>)}</section>}
      </main>
      <aside>
        <section className="db-counter-sales__totals"><h2>Totals</h2><dl aria-live="polite"><div><dt>List subtotal</dt><dd>{formatMoney(sale.list_subtotal)}</dd></div><div><dt>Discount</dt><dd>−{formatMoney(sale.discount_amount)}</dd></div><div><dt>Charged subtotal</dt><dd>{formatMoney(sale.charged_subtotal)}</dd></div><div><dt>Tax</dt><dd>{formatMoney(sale.tax_amount)}</dd></div><div><dt>Total</dt><dd>{formatMoney(sale.total_amount)}</dd></div></dl></section>
        {sale.status === 'draft' && sale.allowed_actions.includes('checkout') && <section className="db-counter-sales__checkout"><h2>Record payment</h2><p>One manual tender settles the sale in full. Stock updates only when this succeeds.</p><label>Tender<select value={tender} onChange={(event) => setTender(event.target.value as CounterSaleTender)}>{tenders.map((value) => <option key={value} value={value}>{COUNTER_SALE_TENDER_LABELS[value]}</option>)}</select></label><label>Reference<input value={manualReference} onChange={(event) => setManualReference(event.target.value)} placeholder={tender === 'cash' ? 'Optional till note' : 'Check, ACH, Zelle, terminal, or fleet reference'} /></label><button className="db-counter-sales__primary" type="button" disabled={checkout.isPending || !tenders.length} onClick={() => checkout.mutate()}>{checkout.isPending ? 'Completing…' : `Complete sale · ${formatMoney(sale.total_amount)}`}</button>{manager && sale.allowed_actions.includes('cancel') && <div className="db-counter-sales__cancel"><label>Cancellation reason<input minLength={3} maxLength={500} value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="Required for the audit trail" /></label><button type="button" disabled={cancel.isPending || cancelReason.trim().length < 3} onClick={() => cancel.mutate()}>{cancel.isPending ? 'Cancelling…' : 'Cancel draft'}</button></div>}</section>}
        {completed && <section className="db-counter-sales__receipt-actions"><h2>Receipt and returns</h2>{sale.allowed_actions.includes('download_receipt') && <button type="button" onClick={() => void downloadReceipt()}><Download aria-hidden="true" />Download receipt</button>}{manager && sale.allowed_actions.includes('create_return') && <button ref={returnTriggerRef} type="button" onClick={() => setReturnOpen(true)}><RotateCcw aria-hidden="true" />Return items</button>}<p>External refunds are handled outside DieselBridge and can be referenced in the audited return.</p></section>}
      </aside>
    </div>
    {returnOpen && <ReturnPanel sale={sale} onClose={closeReturn} onChanged={() => { closeReturn(); void refresh() }} />}
  </div>
}

export default function CounterSalesWorkspace() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const summary = useQuery<{ capabilities?: { counter_sales?: boolean; counter_sale_tenders?: CounterSaleTender[] } }>({
    queryKey: ['parts-operations', 'summary'],
    queryFn: async () => (await api.get('/parts-operations/summary')).data,
    retry: false,
  })
  const saleId = searchParams.get('sale')
  const creating = searchParams.get('new') === '1'
  const initialPartId = searchParams.get('part')

  if (summary.isPending) return <section className="db-counter-sales"><div className="db-counter-sales__state" role="status">Opening Parts sales…</div></section>
  if (summary.isError || !summary.data.capabilities?.counter_sales) return <section className="db-counter-sales"><div className="db-counter-sales__state" role="alert"><ReceiptText aria-hidden="true" /><strong>Parts sales is not available for this shop.</strong><button type="button" onClick={() => navigate('/dashboard/garage/inventory')}>Back to Parts</button></div></section>

  const back = () => setSearchParams({}, { replace: true })
  const tenders = summary.data.capabilities.counter_sale_tenders || []
  return <section className="db-counter-sales db-operating-surface__scroller" aria-label="Parts sales workspace">
    {saleId
      ? <SaleDetail saleId={saleId} tenders={tenders} onBack={back} />
      : creating
        ? <DraftSale initialPartId={initialPartId} onSaved={(id) => setSearchParams({ sale: id }, { replace: true })} onCancel={back} />
        : <SaleList onOpen={(id) => setSearchParams({ sale: id })} onNew={() => setSearchParams({ new: '1' })} />}
  </section>
}
