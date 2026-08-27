import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Elements, PaymentElement, useElements, useStripe } from '@stripe/react-stripe-js'
import type { Stripe } from '@stripe/stripe-js'
import { ArrowLeft, ArrowRight, CheckCircle2, Download, Mail, Plus, ReceiptText, RotateCcw, Search, ShoppingBag, X } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import QuantityStepper from '@/components/QuantityStepper'
import { useTheme } from '@/contexts/ThemeContext'
import api from '@/lib/api'
import { getStripeForAccount } from '@/lib/stripe'
import { useAuthStore } from '@/stores/authStore'
import type { PartRecord } from './PartsInventoryWorkspace'
import { COUNTER_SALE_TENDER_LABELS, MANUAL_TENDERS, type CounterSale, type CounterSaleCheckoutResponse, type CounterSaleDraftLine, type CounterSaleListItem, type CounterSaleProviderCapabilities, type CounterSaleReturn, type CounterSaleTender, type CursorPage } from './inventoryLifecycleTypes'

type PartSearchPage = { items: PartRecord[]; total: number; skip: number; limit: number; has_more: boolean }
type CustomerOption = { id: string; name: string; email?: string | null; phone?: string | null }

const SALE_STATUSES = ['', 'draft', 'awaiting_payment', 'completed', 'partially_returned', 'returned', 'cancelled'] as const

function formatMoney(value: string | null | undefined) {
  if (value == null || value === '') return '—'
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD' }).format(Number(value))
}

function moneyWithoutFee(total: string, fee: string) {
  const parseCents = (value: string) => {
    const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim())
    if (!match) return null
    const cents = BigInt(match[2]) * 100n + BigInt((match[3] || '').padEnd(2, '0'))
    return match[1] ? -cents : cents
  }
  const totalCents = parseCents(total)
  const feeCents = parseCents(fee)
  if (totalCents == null || feeCents == null) return total
  const value = totalCents - feeCents
  const absolute = value < 0n ? -value : value
  return `${value < 0n ? '-' : ''}${absolute / 100n}.${String(absolute % 100n).padStart(2, '0')}`
}

function idempotency(family: string) {
  return `${family}-${crypto.randomUUID()}`
}

function safeError(error: unknown, fallback: string) {
  const response = (error as { response?: { status?: number; data?: { detail?: string; code?: string } } }).response
  return { status: response?.status, code: response?.data?.code, message: response?.data?.detail || fallback }
}

function saleStateLabel(value: string) {
  return value.replace(/_/g, ' ')
}

function canManage(role?: string) {
  return role === 'garage_owner' || role === 'garage_admin'
}

function StripeCheckoutForm({ sale, clientSecret, reconcileUrl, onSettled, onFailure }: { sale: CounterSale; clientSecret: string; reconcileUrl: string; onSettled: () => void; onFailure: (message: string) => void }) {
  const stripe = useStripe()
  const elements = useElements()
  const [submitting, setSubmitting] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!stripe || !elements || submitting) return
    setSubmitting(true)
    const result = await stripe.confirmPayment({ elements, clientSecret, confirmParams: { return_url: window.location.href }, redirect: 'if_required' })
    if (result.error) { onFailure(result.error.message || 'Stripe could not confirm this payment.'); setSubmitting(false); return }
    try {
      const path = reconcileUrl.startsWith('/api/v1') ? reconcileUrl.slice('/api/v1'.length) : reconcileUrl
      await api.post(path, { expected_version: sale.version }, { headers: { 'Idempotency-Key': idempotency('counter-sale-reconcile') } })
    } catch (error) {
      const detail = safeError(error, 'Payment confirmation is pending. Reconcile this sale before retrying.').message
      onFailure(detail); setSubmitting(false); return
    }
    onSettled()
    setSubmitting(false)
  }
  return <form className="db-counter-sales__provider-form" onSubmit={(event) => void submit(event)}><PaymentElement /><button type="submit" disabled={!stripe || submitting}>{submitting ? 'Confirming…' : `Pay ${formatMoney(sale.total_amount)}`}</button></form>
}

function QuickBooksTokenForm({ tokenUrl, disabled, onToken }: { tokenUrl: string; disabled: boolean; onToken: (token: string) => void }) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError(null)
    const form = event.currentTarget
    const values = new FormData(form)
    const [expMonth, expYear] = String(values.get('expiry') || '').split('/').map((value) => value.trim())
    if (!expMonth || !expYear) { setError('Enter expiry as MM / YYYY.'); setBusy(false); return }
    try {
      const response = await fetch(tokenUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify({ card: { number: values.get('number'), cvc: values.get('cvc'), expMonth, expYear, name: values.get('name'), address: { country: 'US', postalCode: values.get('postalCode') } } }) })
      const payload = await response.json().catch(() => null)
      form.reset()
      if (!response.ok || typeof payload?.value !== 'string') throw new Error('QuickBooks could not securely prepare this payment.')
      onToken(payload.value)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'QuickBooks could not securely prepare this payment.') }
    finally { setBusy(false) }
  }
  return <form className="db-counter-sales__provider-form" onSubmit={(event) => void submit(event)}><p>Card data goes directly to Intuit. DieselBridge receives only a one-time token.</p><label>Name on card<input name="name" autoComplete="cc-name" required disabled={disabled || busy} /></label><label>Card number<input name="number" autoComplete="cc-number" inputMode="numeric" required disabled={disabled || busy} /></label><div><label>Expiry<input name="expiry" autoComplete="cc-exp" inputMode="numeric" placeholder="MM / YYYY" required disabled={disabled || busy} /></label><label>Security code<input name="cvc" autoComplete="cc-csc" inputMode="numeric" required disabled={disabled || busy} /></label></div><label>Billing ZIP<input name="postalCode" autoComplete="postal-code" required disabled={disabled || busy} /></label>{error && <p role="alert">{error}</p>}<button type="submit" disabled={disabled || busy}>{busy ? 'Securing…' : 'Secure card for checkout'}</button></form>
}

function SaleList({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const [searchDraft, setSearchDraft] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [cursors, setCursors] = useState<Array<string | null>>([null])
  const cursor = cursors[cursors.length - 1] || null
  const query = useQuery<CursorPage<CounterSaleListItem>>({
    queryKey: ['counter-sales', 'list', search, status, cursor],
    queryFn: async () => (await api.get('/parts-operations/counter-sales', { params: { ...(search ? { text: search } : {}), ...(status ? { status } : {}), ...(cursor ? { cursor } : {}), limit: 50 } })).data,
    retry: false,
  })
  return <div className="db-counter-sales__list">
    <div className="db-counter-sales__list-head"><div><h1>Parts sales</h1><p>Counter-sale history, payment recovery, receipts, and returns.</p></div><button type="button" onClick={onNew}><Plus aria-hidden="true" />New counter sale</button></div>
    <form className="db-counter-sales__list-filters" onSubmit={(event) => { event.preventDefault(); setSearch(searchDraft.trim()); setCursors([null]) }}><label><Search aria-hidden="true" /><span className="sr-only">Search parts sales</span><input type="search" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Search sale number or buyer" /></label><select aria-label="Filter sale status" value={status} onChange={(event) => { setStatus(event.target.value); setCursors([null]) }}>{SALE_STATUSES.map((value) => <option key={value} value={value}>{value ? saleStateLabel(value) : 'All statuses'}</option>)}</select><button type="submit">Search</button></form>
    {query.isPending && <div className="db-counter-sales__state" role="status">Loading parts sales…</div>}
    {query.isError && <div className="db-counter-sales__state" role="alert">Parts sales could not be loaded.<button type="button" onClick={() => void query.refetch()}>Retry</button></div>}
    {!query.isPending && !query.isError && !query.data.items.length && <div className="db-counter-sales__state"><ShoppingBag aria-hidden="true" /><strong>No counter sales match this view.</strong><span>Start a sale or adjust the filters.</span></div>}
    {!!query.data?.items.length && <div className="db-counter-sales__sale-rows">{query.data.items.map((sale) => <button type="button" key={sale.id} onClick={() => onOpen(sale.id)}><span><strong>{sale.sale_number}</strong><small>{sale.buyer_name || 'Walk-in customer'} · {sale.line_count} {sale.line_count === 1 ? 'line' : 'lines'}</small></span><span><em data-status={sale.status}>{saleStateLabel(sale.status)}</em><strong>{formatMoney(sale.total_amount)}</strong><small>{new Date(sale.completed_at || sale.created_at).toLocaleString()}</small></span><ArrowRight aria-hidden="true" /></button>)}</div>}
    {query.data && <div className="db-counter-sales__pager"><span aria-live="polite">Showing {query.data.items.length} sales</span><div><button type="button" disabled={cursors.length === 1 || query.isFetching} onClick={() => setCursors((current) => current.slice(0, -1))}>Previous</button><button type="button" disabled={!query.data.next_cursor || query.isFetching} onClick={() => query.data.next_cursor && setCursors((current) => [...current, query.data.next_cursor])}>Next</button></div></div>}
  </div>
}

type SalePart = Pick<PartRecord, 'id' | 'sku' | 'name' | 'unit_type' | 'available_packages' | 'physical_on_hand_packages' | 'held_for_checkout_packages' | 'available_to_sell_packages'> & Partial<Pick<PartRecord, 'is_archived' | 'is_placeholder'>>
type DraftSelection = { part: SalePart; quantity: number; overridePrice: string; overrideReason: string }

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
      held_for_checkout_packages: line.held_for_checkout,
      available_to_sell_packages: line.available_to_sell,
    },
    quantity: line.quantity,
    overridePrice: line.price_override_reason ? line.charged_unit_price : '',
    overrideReason: line.price_override_reason || '',
  })) || [])
  const [error, setError] = useState<string | null>(null)
  const initialAdded = useRef(false)
  const partsQuery = useQuery<PartSearchPage>({ queryKey: ['parts-operations', 'sale-part-search', partSearch], queryFn: async () => (await api.get('/parts-operations/parts', { params: { view: 'active', search: partSearch.trim(), sort: 'name', direction: 'asc', paginated: true, skip: 0, limit: 20 } })).data, enabled: partSearch.trim().length >= 2, retry: false })
  const initialPartQuery = useQuery<SalePart>({ queryKey: ['parts-operations', 'sale-initial-part', initialPartId], queryFn: async () => (await api.get(`/parts-operations/parts/${initialPartId}`)).data, enabled: Boolean(initialPartId) && !existingSale, retry: false })
  const customersQuery = useQuery<CustomerOption[]>({ queryKey: ['customer-typeahead', customerSearch], queryFn: async () => { const response = await api.get('/customers/typeahead', { params: { q: customerSearch.trim(), limit: 8 } }); return Array.isArray(response.data) ? response.data : response.data.items || [] }, enabled: customerSearch.trim().length >= 2, retry: false })
  useEffect(() => {
    if (!initialPartId || initialAdded.current || !initialPartQuery.data) return
    initialAdded.current = true
    setLines([{ part: initialPartQuery.data, quantity: 1, overridePrice: '', overrideReason: '' }])
  }, [initialPartId, initialPartQuery.data])
  const addPart = (part: PartRecord) => setLines((current) => current.some((line) => line.part.id === part.id) ? current : [...current, { part, quantity: 1, overridePrice: '', overrideReason: '' }])
  const payloadLines = (): CounterSaleDraftLine[] => lines.map((line) => ({ inventory_id: line.part.id, quantity: line.quantity, ...(line.overridePrice.trim() ? { charged_unit_price: line.overridePrice.trim(), price_override_reason: line.overrideReason.trim() } : {}) }))
  const save = useMutation({ mutationFn: async () => {
    const payload = { ...(existingSale ? { expected_version: existingSale.version } : {}), customer_id: customer?.id || null, buyer_name: buyerName.trim() || customer?.name || null, buyer_email: buyerEmail.trim() || customer?.email || null, buyer_phone: buyerPhone.trim() || customer?.phone || null, lines: payloadLines() }
    const response = existingSale
      ? await api.patch(`/parts-operations/counter-sales/${existingSale.id}`, payload, { headers: { 'Idempotency-Key': idempotency('counter-sale-update') } })
      : await api.post('/parts-operations/counter-sales', payload, { headers: { 'Idempotency-Key': idempotency('counter-sale-create') } })
    return response.data as CounterSale
  }, onSuccess: (sale) => onSaved(sale.id), onError: (cause) => setError(safeError(cause, existingSale ? 'The draft sale could not be updated.' : 'The draft sale could not be created.').message) })
  const validate = () => {
    if (!lines.length) { setError('Add at least one part.'); return false }
    const invalidOverride = lines.find((line) => line.overridePrice && (!manager || line.overrideReason.trim().length < 3))
    if (invalidOverride) { setError(manager ? 'Every price override needs a reason of at least 3 characters.' : 'Only an owner or admin can override catalog price.'); return false }
    return true
  }
  return <div className="db-counter-sales__draft">
    <div className="db-counter-sales__workspace-head"><button type="button" onClick={onCancel}><ArrowLeft aria-hidden="true" />{existingSale ? existingSale.sale_number : 'Parts sales'}</button><div><h1>{existingSale ? 'Edit draft sale' : 'New counter sale'}</h1><p>Build the draft first. Stock is held only when checkout starts.</p></div></div>
    <div className="db-counter-sales__draft-grid"><section><h2>Parts</h2><label className="db-counter-sales__search"><Search aria-hidden="true" /><span className="sr-only">Search catalog parts</span><input autoFocus type="search" value={partSearch} onChange={(event) => setPartSearch(event.target.value)} placeholder="Search part name or SKU" /></label>{initialPartQuery.isFetching && <p role="status">Loading selected part…</p>}{initialPartQuery.isError && <p role="alert">The selected part could not be loaded. Search for it to continue.</p>}{partsQuery.isFetching && <p role="status">Searching catalog…</p>}{partsQuery.data && <div className="db-counter-sales__search-results">{partsQuery.data.items.filter((part) => !part.is_archived && !part.is_placeholder).map((part) => <button type="button" key={part.id} onClick={() => addPart(part)}><span><strong>{part.name}</strong><small>{part.sku}</small></span><span>{part.available_to_sell_packages ?? part.available_packages} available<Plus aria-hidden="true" /></span></button>)}</div>}
      <div className="db-counter-sales__draft-lines">{lines.map((line, index) => { const maximum = Math.max(1, line.part.available_to_sell_packages ?? line.part.available_packages); return <article key={line.part.id}><div><strong>{line.part.name}</strong><small>{line.part.sku} · {line.part.unit_type || 'each'}</small><small>{line.part.physical_on_hand_packages ?? line.part.available_packages} physical · {line.part.held_for_checkout_packages ?? 0} held · {line.part.available_to_sell_packages ?? line.part.available_packages} available to sell</small></div><QuantityStepper value={line.quantity} min={1} step={1} unitLabel={line.part.unit_type || 'units'} ariaLabel={`Quantity for ${line.part.name}`} size="lg" theme={appearance.mode === 'light' ? 'light' : 'dark'} onChange={(quantity) => setLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, quantity: Math.min(maximum, Math.max(1, quantity)) } : item))} />{manager && <details><summary>Manager price override</summary><label>Charged unit price<input inputMode="decimal" value={line.overridePrice} onChange={(event) => setLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, overridePrice: event.target.value } : item))} placeholder="Use catalog price" /></label><label>Reason<input value={line.overrideReason} minLength={3} maxLength={500} onChange={(event) => setLines((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, overrideReason: event.target.value } : item))} placeholder="Required when price changes" /></label></details>}<button type="button" aria-label={`Remove ${line.part.name}`} onClick={() => setLines((current) => current.filter((_, itemIndex) => itemIndex !== index))}><X aria-hidden="true" /></button></article>})}</div></section>
      <aside><h2>Buyer</h2><label>Existing customer<input value={customerSearch} onChange={(event) => { setCustomerSearch(event.target.value); setCustomer(null) }} placeholder="Optional customer lookup" /></label>{customersQuery.data && !customer && <div className="db-counter-sales__customer-results">{customersQuery.data.map((option) => <button type="button" key={option.id} onClick={() => { setCustomer(option); setCustomerSearch(option.name); setBuyerName(option.name); setBuyerEmail(option.email || ''); setBuyerPhone(option.phone || '') }}><strong>{option.name}</strong><small>{option.email || option.phone || 'Customer record'}</small></button>)}</div>}<p>Anonymous walk-ins are valid. Buyer details are optional receipt snapshots.</p><label>Buyer name<input value={buyerName} onChange={(event) => setBuyerName(event.target.value)} /></label><label>Email<input type="email" value={buyerEmail} onChange={(event) => setBuyerEmail(event.target.value)} /></label><label>Phone<input type="tel" value={buyerPhone} onChange={(event) => setBuyerPhone(event.target.value)} /></label>{error && <p className="db-counter-sales__error" role="alert">{error}</p>}<button className="db-counter-sales__primary" type="button" disabled={save.isPending} onClick={() => validate() && save.mutate()}>{save.isPending ? 'Saving draft…' : existingSale ? 'Save draft' : 'Review checkout'}<ArrowRight aria-hidden="true" /></button></aside></div>
  </div>
}

type ReturnDraft = { quantity: number; reason: string; disposition: 'restock' | 'damaged' }

function ReturnPanel({ sale, onClose, onChanged }: { sale: CounterSale; onClose: () => void; onChanged: () => void }) {
  const { appearance } = useTheme()
  const closeRef = useRef<HTMLButtonElement>(null)
  const [lines, setLines] = useState<Record<string, ReturnDraft>>(() => Object.fromEntries(sale.lines.map((line) => [line.id, { quantity: 0, reason: '', disposition: 'restock' as const }])))
  const [manualReference, setManualReference] = useState('')
  const [error, setError] = useState<string | null>(null)
  const mutation = useMutation({ mutationFn: async () => (await api.post(`/parts-operations/counter-sales/${sale.id}/returns`, { expected_version: sale.version, lines: sale.lines.flatMap((line) => { const draft = lines[line.id]; return draft?.quantity ? [{ sale_line_id: line.id, quantity: draft.quantity, reason: draft.reason.trim(), disposition: draft.disposition }] : [] }), manual_refund_reference: manualReference.trim() || null }, { headers: { 'Idempotency-Key': idempotency('counter-sale-return') } })).data as CounterSaleReturn, onSuccess: () => onChanged(), onError: (cause) => setError(safeError(cause, 'The return could not be submitted.').message) })
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
    mutation.mutate()
  }
  return <div className="db-counter-sales__return-panel" role="dialog" aria-modal="true" aria-labelledby="return-sale-title"><div><h2 id="return-sale-title">Return items from {sale.sale_number}</h2><button ref={closeRef} type="button" aria-label="Close return" onClick={onClose}><X aria-hidden="true" /></button></div><p>Choose remaining quantities. Restocked units return to on-hand only after refund confirmation; damaged units never do.</p>{sale.lines.map((line) => { const remaining = line.remaining_returnable_quantity ?? Math.max(0, line.quantity - (line.returned_quantity || 0)); const draft = lines[line.id]; return <article key={line.id}><div><strong>{line.name}</strong><small>{remaining} of {line.quantity} returnable</small></div><QuantityStepper value={draft?.quantity || 0} min={0} step={1} unitLabel={line.unit_type || 'units'} ariaLabel={`Return quantity for ${line.name}`} size="lg" theme={appearance.mode === 'light' ? 'light' : 'dark'} onChange={(quantity) => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], quantity: Math.min(remaining, Math.max(0, quantity)) } }))} />{!!draft?.quantity && <><label>Reason<textarea minLength={3} maxLength={500} value={draft.reason} onChange={(event) => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], reason: event.target.value } }))} /></label><fieldset><legend>Disposition</legend><label><input type="radio" name={`disposition-${line.id}`} checked={draft.disposition === 'restock'} onChange={() => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], disposition: 'restock' } }))} />Restock</label><label><input type="radio" name={`disposition-${line.id}`} checked={draft.disposition === 'damaged'} onChange={() => setLines((current) => ({ ...current, [line.id]: { ...current[line.id], disposition: 'damaged' } }))} />Damaged</label></fieldset></>}</article>})}<label>Manual refund reference<input value={manualReference} onChange={(event) => setManualReference(event.target.value)} placeholder="Required by the original manual tender when applicable" /></label>{error && <p role="alert">{error}</p>}<div className="db-counter-sales__dialog-actions"><button type="button" onClick={onClose}>Cancel</button><button type="button" disabled={mutation.isPending} onClick={submit}>{mutation.isPending ? 'Submitting…' : 'Submit return and refund'}</button></div></div>
}

function SaleDetail({ saleId, tenders, providers, onBack }: { saleId: string; tenders: CounterSaleTender[]; providers: CounterSaleProviderCapabilities; onBack: () => void }) {
  const role = useAuthStore((state) => state.user?.role)
  const { accentColors, appearance } = useTheme()
  const manager = canManage(role)
  const queryClient = useQueryClient()
  const [tender, setTender] = useState<CounterSaleTender>(tenders[0] || 'cash')
  const [manualReference, setManualReference] = useState('')
  const [receiptEmail, setReceiptEmail] = useState('')
  const [cancelReason, setCancelReason] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stripeConfig, setStripeConfig] = useState<{ stripe: Stripe | null; clientSecret: string; reconcileUrl: string } | null>(null)
  const [returnOpen, setReturnOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const returnTriggerRef = useRef<HTMLButtonElement>(null)
  const query = useQuery<CounterSale>({ queryKey: ['counter-sale', saleId], queryFn: async () => (await api.get(`/parts-operations/counter-sales/${saleId}`)).data, retry: false })
  const sale = query.data
  useEffect(() => { if (sale?.buyer_email && !receiptEmail) setReceiptEmail(sale.buyer_email) }, [receiptEmail, sale?.buyer_email])
  useEffect(() => { if (tenders.length && !tenders.includes(tender)) setTender(tenders[0]) }, [tender, tenders])
  const refresh = async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['counter-sale', saleId] }), queryClient.invalidateQueries({ queryKey: ['counter-sales'] }), queryClient.invalidateQueries({ queryKey: ['parts-operations', 'parts'] })]) }
  const checkout = useMutation({ mutationFn: async (paymentToken?: string) => (await api.post(`/parts-operations/counter-sales/${saleId}/checkout`, { expected_version: sale!.version, tender, payment_token: paymentToken || null, manual_reference: manualReference.trim() || null, receipt_email: receiptEmail.trim() || null }, { headers: { 'Idempotency-Key': idempotency('counter-sale-checkout') } })).data as CounterSaleCheckoutResponse, onSuccess: async (result) => { await refresh(); if (result.payment.client_secret) { const stripe = await getStripeForAccount(result.payment.stripe_account_id); setStripeConfig({ stripe, clientSecret: result.payment.client_secret, reconcileUrl: result.payment.reconcile_url }); setNotice('Stock is held while Stripe confirms this payment.'); return } setNotice(result.sale.status === 'completed' ? 'Sale completed and stock posted.' : 'Payment is pending. Use reconciliation before retrying.'); }, onError: async (cause) => { const failure = safeError(cause, 'Checkout could not be completed.'); if (failure.status === 402) await refresh(); setError(failure.status === 503 ? `${failure.message} Stock remains held. Reconcile this attempt; do not submit another charge.` : failure.message) } })
  const cancel = useMutation({ mutationFn: async () => (await api.post(`/parts-operations/counter-sales/${saleId}/cancel`, { expected_version: sale!.version, reason: cancelReason.trim() }, { headers: { 'Idempotency-Key': idempotency('counter-sale-cancel') } })).data, onSuccess: async () => { await refresh(); setCancelReason(''); setNotice('Draft sale cancelled.') }, onError: (cause) => setError(safeError(cause, 'The draft could not be cancelled.').message) })
  const latestAttempt = sale?.payment_attempts[sale.payment_attempts.length - 1] || null
  const reconcile = useMutation({ mutationFn: async () => (await api.post(`/parts-operations/counter-sales/${saleId}/payment-attempts/${latestAttempt!.id}/reconcile`, { expected_version: sale!.version }, { headers: { 'Idempotency-Key': idempotency('counter-sale-reconcile') } })).data, onSuccess: async () => { await refresh(); setNotice('Provider state reconciled.') }, onError: (cause) => setError(safeError(cause, 'Provider reconciliation is still pending.').message) })
  const emailReceipt = useMutation({ mutationFn: async () => (await api.post(`/parts-operations/counter-sales/${saleId}/receipt/email`, { email: receiptEmail.trim() || sale?.buyer_email || null }, { headers: { 'Idempotency-Key': idempotency('counter-sale-receipt') } })).data, onSuccess: () => setNotice('Receipt email queued.'), onError: (cause) => setError(safeError(cause, 'Receipt email could not be queued.').message) })
  const retryRefund = useMutation({ mutationFn: async (returnId: string) => (await api.post(`/parts-operations/counter-sales/${saleId}/returns/${returnId}/retry-refund`, { expected_version: sale!.version }, { headers: { 'Idempotency-Key': idempotency('counter-sale-refund-retry') } })).data, onSuccess: async () => { await refresh(); setNotice('Refund retry submitted.') }, onError: (cause) => setError(safeError(cause, 'Refund retry could not be submitted.').message) })
  const downloadReceipt = async () => { try { const response = await api.get(`/parts-operations/counter-sales/${saleId}/receipt.pdf`, { responseType: 'blob' }); const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' })); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${sale?.sale_number || 'counter-sale'}-receipt.pdf`; anchor.click(); URL.revokeObjectURL(url) } catch (cause) { setError(safeError(cause, 'Receipt PDF could not be downloaded.').message) } }
  if (query.isPending) return <div className="db-counter-sales__state" role="status">Loading sale…</div>
  if (query.isError || !sale) return <div className="db-counter-sales__state" role="alert">This sale could not be loaded.<button type="button" onClick={() => void query.refetch()}>Retry</button></div>
  if (editing) return <DraftSale existingSale={sale} initialPartId={null} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); void refresh(); setNotice('Draft sale updated.') }} />
  const providerPending = sale.status === 'awaiting_payment' || latestAttempt?.state === 'pending' || latestAttempt?.state === 'compensating_refund_pending'
  const completed = ['completed', 'partially_returned', 'returned'].includes(sale.status)
  const manualTenderPreview = sale.status === 'draft' && MANUAL_TENDERS.includes(tender)
  const previewServiceFee = manualTenderPreview ? '0.00' : sale.service_fee_amount
  const previewTotal = manualTenderPreview ? moneyWithoutFee(sale.total_amount, sale.service_fee_amount) : sale.total_amount
  const previewLineTotal = (total: string, fee: string) => manualTenderPreview ? moneyWithoutFee(total, fee) : total
  const closeReturn = () => {
    setReturnOpen(false)
    requestAnimationFrame(() => returnTriggerRef.current?.focus())
  }
  return <div className="db-counter-sales__detail">
    <div className="db-counter-sales__workspace-head"><button type="button" onClick={onBack}><ArrowLeft aria-hidden="true" />Parts sales</button><div><h1>{sale.sale_number}</h1><p>{sale.buyer_name || 'Walk-in customer'} · <span data-status={sale.status}>{saleStateLabel(sale.status)}</span></p></div></div>
    {(notice || error) && <div className={error ? 'db-counter-sales__error' : 'db-counter-sales__notice'} role={error ? 'alert' : 'status'}><span>{error || notice}</span><button type="button" onClick={() => { setError(null); setNotice(null) }}>Dismiss</button></div>}
    <div className="db-counter-sales__detail-grid"><main><section className="db-counter-sales__lines"><div><h2>Sale lines</h2><span><strong>{sale.lines.length}</strong>{sale.allowed_actions.includes('edit_draft') && <button type="button" onClick={() => setEditing(true)}>Edit draft</button>}</span></div>{sale.lines.map((line) => <article key={line.id}><div><strong>{line.name}</strong><small>{line.sku} · {line.quantity} {line.unit_type || 'units'} × {formatMoney(line.charged_unit_price)}</small>{line.price_override_reason && <small>Manager override · {line.price_override_reason}</small>}</div><div><strong>{formatMoney(previewLineTotal(line.total_amount, line.fee_amount))}</strong><small>{line.physical_on_hand} physical · {line.held_for_checkout} held · {line.available_to_sell} available</small></div></article>)}</section>
      {sale.payment_attempts.length > 0 && <section className="db-counter-sales__attempts"><h2>Payment activity</h2>{sale.payment_attempts.map((attempt) => <article key={attempt.id}><span><strong>{COUNTER_SALE_TENDER_LABELS[attempt.tender]}</strong><small>{new Date(attempt.created_at).toLocaleString()}</small></span><span><em data-status={attempt.state}>{saleStateLabel(attempt.state)}</em><strong>{formatMoney(attempt.amount)}</strong></span></article>)}</section>}
      {!!sale.returns?.length && <section className="db-counter-sales__attempts"><h2>Returns and refunds</h2>{sale.returns.map((record) => <article key={record.id}><span><strong>{record.lines.reduce((sum, line) => sum + line.quantity, 0)} returned units</strong><small>{new Date(record.created_at).toLocaleString()}</small></span><span><em data-status={record.state}>{saleStateLabel(record.state)}</em><strong>{formatMoney(record.refund_amount)}</strong>{manager && record.state === 'refund_failed' && <button type="button" disabled={retryRefund.isPending} onClick={() => retryRefund.mutate(record.id)}>Retry refund</button>}</span></article>)}</section>}</main>
      <aside><section className="db-counter-sales__totals"><h2>Totals</h2><dl aria-live="polite"><div><dt>List subtotal</dt><dd>{formatMoney(sale.list_subtotal)}</dd></div><div><dt>Discount</dt><dd>−{formatMoney(sale.discount_amount)}</dd></div><div><dt>Charged subtotal</dt><dd>{formatMoney(sale.charged_subtotal)}</dd></div><div><dt>Tax</dt><dd>{formatMoney(sale.tax_amount)}</dd></div><div><dt>Service fee</dt><dd>{formatMoney(previewServiceFee)}</dd></div><div><dt>Total</dt><dd>{formatMoney(previewTotal)}</dd></div></dl></section>
      {sale.status === 'draft' && sale.allowed_actions.includes('checkout') && <section className="db-counter-sales__checkout"><h2>Checkout</h2>{!tenders.length ? <p role="status">No tender is currently available. An owner can configure a payment rail in shop settings.</p> : <><label>Tender<select value={tender} onChange={(event) => { setTender(event.target.value as CounterSaleTender); setStripeConfig(null); setError(null) }}>{tenders.map((value) => <option key={value} value={value}>{COUNTER_SALE_TENDER_LABELS[value]}</option>)}</select></label><label>Receipt email<input type="email" value={receiptEmail} onChange={(event) => setReceiptEmail(event.target.value)} placeholder="Optional" /></label>{MANUAL_TENDERS.includes(tender) && <label>Reference<input value={manualReference} onChange={(event) => setManualReference(event.target.value)} placeholder={tender === 'cash' ? 'Optional till note' : 'Check, ACH, Zelle, terminal, or fleet reference'} /></label>}{tender === 'quickbooks_payments' && providers.quickbooks_payments.available && providers.quickbooks_payments.token_url ? <QuickBooksTokenForm tokenUrl={providers.quickbooks_payments.token_url} disabled={checkout.isPending} onToken={(token) => checkout.mutate(token)} /> : <button className="db-counter-sales__primary" type="button" disabled={checkout.isPending || !tenders.includes(tender)} onClick={() => checkout.mutate(undefined)}>{checkout.isPending ? 'Starting checkout…' : `Checkout ${formatMoney(previewTotal)}`}</button>}</>}{manager && sale.allowed_actions.includes('cancel') && <div className="db-counter-sales__cancel"><label>Cancellation reason<input minLength={3} maxLength={500} value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="Required for the audit trail" /></label><button type="button" disabled={cancel.isPending || cancelReason.trim().length < 3} onClick={() => cancel.mutate()}>{cancel.isPending ? 'Cancelling…' : 'Cancel draft'}</button></div>}</section>}
      {stripeConfig && <Elements stripe={stripeConfig.stripe} options={{ clientSecret: stripeConfig.clientSecret, appearance: { theme: appearance.mode === 'light' ? 'stripe' : 'night', variables: { colorPrimary: accentColors[500], borderRadius: '10px' } } }}><StripeCheckoutForm sale={sale} clientSecret={stripeConfig.clientSecret} reconcileUrl={stripeConfig.reconcileUrl} onFailure={setError} onSettled={() => { setStripeConfig(null); void refresh() }} /></Elements>}
      {providerPending && <section className="db-counter-sales__recovery"><h2>Payment pending</h2><p>Stock remains held. The existing attempt must converge before any new charge.</p>{sale.allowed_actions.includes('reconcile_payment') ? <button type="button" disabled={!latestAttempt || reconcile.isPending} onClick={() => reconcile.mutate()}><RotateCcw aria-hidden="true" />{reconcile.isPending ? 'Reconciling…' : 'Reconcile payment'}</button> : <p role="status">Waiting for provider confirmation. Refresh this sale before taking another action.</p>}</section>}
      {completed && <section className="db-counter-sales__receipt-actions"><h2>Receipt and returns</h2>{sale.allowed_actions.includes('download_receipt') && <button type="button" onClick={() => void downloadReceipt()}><Download aria-hidden="true" />Download receipt</button>}<label>Receipt email<input type="email" value={receiptEmail} onChange={(event) => setReceiptEmail(event.target.value)} /></label>{sale.allowed_actions.includes('email_receipt') && <button type="button" disabled={emailReceipt.isPending} onClick={() => emailReceipt.mutate()}><Mail aria-hidden="true" />{emailReceipt.isPending ? 'Queuing…' : 'Email receipt'}</button>}{manager && sale.allowed_actions.includes('create_return') && <button ref={returnTriggerRef} type="button" onClick={() => setReturnOpen(true)}><RotateCcw aria-hidden="true" />Return items</button>}<p><CheckCircle2 aria-hidden="true" />Accounting sync: {sale.accounting_sync_status ? saleStateLabel(sale.accounting_sync_status) : 'queued'}</p></section>}</aside></div>
    {returnOpen && <ReturnPanel sale={sale} onClose={closeReturn} onChanged={() => { closeReturn(); void refresh() }} />}
  </div>
}

export default function CounterSalesWorkspace() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [summaryTenders, setSummaryTenders] = useState<CounterSaleTender[]>([])
  const summary = useQuery<{ capabilities?: { counter_sales?: boolean; counter_sale_tenders?: CounterSaleTender[]; counter_sale_providers?: CounterSaleProviderCapabilities } }>({ queryKey: ['parts-operations', 'summary'], queryFn: async () => (await api.get('/parts-operations/summary')).data, retry: false })
  useEffect(() => { if (summary.data?.capabilities?.counter_sale_tenders) setSummaryTenders(summary.data.capabilities.counter_sale_tenders) }, [summary.data?.capabilities?.counter_sale_tenders])
  const saleId = searchParams.get('sale')
  const creating = searchParams.get('new') === '1'
  const initialPartId = searchParams.get('part')
  if (summary.isPending) return <section className="db-counter-sales"><div className="db-counter-sales__state" role="status">Opening Parts sales…</div></section>
  if (summary.isError || !summary.data.capabilities?.counter_sales) return <section className="db-counter-sales"><div className="db-counter-sales__state" role="alert"><ReceiptText aria-hidden="true" /><strong>Parts sales is not available for this shop.</strong><button type="button" onClick={() => navigate('/dashboard/garage/inventory')}>Back to Parts</button></div></section>
  const back = () => setSearchParams({}, { replace: true })
  return <section className="db-counter-sales" aria-label="Parts sales workspace">
    {saleId ? <SaleDetail saleId={saleId} tenders={summaryTenders} providers={summary.data.capabilities.counter_sale_providers || { stripe: { available: false, stripe_account_id: null }, quickbooks_payments: { available: false, token_url: null } }} onBack={back} /> : creating ? <DraftSale initialPartId={initialPartId} onSaved={(id) => setSearchParams({ sale: id }, { replace: true })} onCancel={back} /> : <SaleList onOpen={(id) => setSearchParams({ sale: id })} onNew={() => setSearchParams({ new: '1' })} />}
  </section>
}
