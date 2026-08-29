import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, ChevronDown, Download, ExternalLink, Search, SlidersHorizontal } from 'lucide-react'
import { Link } from 'react-router-dom'

import api from '@/lib/api'
import type { ActivityCategory, ActivityEvent, CursorPage, LifecycleSummary } from './inventoryLifecycleTypes'

const CATEGORIES: Array<{ value: '' | ActivityCategory; label: string }> = [
  { value: '', label: 'All categories' },
  { value: 'catalog', label: 'Catalog' },
  { value: 'stock', label: 'Stock' },
  { value: 'repairs', label: 'Repairs' },
  { value: 'purchasing', label: 'Purchasing' },
  { value: 'returns', label: 'Returns' },
  { value: 'sales', label: 'Sales' },
]

const CATEGORY_LABELS: Record<ActivityCategory, string> = Object.fromEntries(
  CATEGORIES.filter((category): category is { value: ActivityCategory; label: string } => Boolean(category.value))
    .map((category) => [category.value, category.label]),
) as Record<ActivityCategory, string>

const EVENT_LABELS: Record<string, string> = {
  'part.baseline': 'Imported starting inventory',
  'part.created': 'Part added',
  'part.identity_changed': 'Part details changed',
  'part.category_changed': 'Category changed',
  'part.location_changed': 'Bin location changed',
  'part.unit_changed': 'Unit changed',
  'part.photo_changed': 'Part photo changed',
  'part.reorder_level_changed': 'Reorder point changed',
  'part.cost_changed': 'Unit cost changed',
  'part.selling_price_changed': 'Selling price changed',
  'supplier_source.created': 'Supplier source added',
  'supplier_source.updated': 'Supplier source changed',
  'supplier_source.preferred_changed': 'Preferred supplier changed',
  'supplier_source.removed': 'Supplier source removed',
  'stock.adjusted': 'Stock adjusted',
  'stock.received': 'Stock received',
  'stock.repair_reserved': 'Stock reserved for repair',
  'stock.repair_released': 'Repair stock released',
  'stock.counter_sale_completed': 'Part sale completed',
  'stock.counter_sale_returned': 'Sold part returned to stock',
  'repair_usage.added': 'Part added to repair',
  'repair_usage.changed': 'Repair usage changed',
  'repair_usage.removed': 'Part removed from repair',
  'repair_usage.current_snapshot': 'Imported repair usage',
  'purchase_order.created': 'Purchase order created',
  'purchase_order.updated': 'Purchase order changed',
  'purchase_order.submitted': 'Purchase order submitted',
  'purchase_order.cancelled': 'Purchase order cancelled',
  'receipt.recorded': 'Receipt recorded',
  'receipt.current_snapshot': 'Imported receipt',
  'core.status_changed': 'Core status changed',
  'core.current_snapshot': 'Imported core obligation',
  'vendor_return.created': 'Vendor return created',
  'vendor_return.submitted': 'Vendor return submitted',
  'vendor_return.shipped': 'Vendor return shipped',
  'vendor_return.credited': 'Vendor credit recorded',
  'vendor_return.cancelled': 'Vendor return cancelled',
  'vendor_return.reversed': 'Vendor return reversed',
  'vendor_return.current_snapshot': 'Imported vendor return',
  'counter_sale.created': 'Part sale started',
  'counter_sale.updated': 'Part sale changed',
  'counter_sale.completed': 'Part sale completed',
  'counter_sale.cancelled': 'Part sale cancelled',
  'counter_sale.return_completed': 'Part sale return completed',
}

const FIELD_LABELS: Record<string, string> = {
  sku: 'SKU',
  name: 'Part name',
  description: 'Description',
  category: 'Category',
  category_id: 'Category reference',
  location: 'Bin location',
  unit_type: 'Unit',
  image_url: 'Photo',
  reorder_level: 'Reorder point',
  cost: 'Unit cost',
  selling_price: 'Selling price',
  core_charge: 'Core charge',
  supplier_name: 'Supplier',
  supplier_contact: 'Supplier contact',
  is_placeholder: 'Placeholder',
  unit_cost: 'Unit cost',
  unit_price: 'Unit price',
  list_price: 'List price',
  supplier_id: 'Supplier reference',
  supplier_part_number: 'Supplier part number',
  is_preferred: 'Preferred source',
  minimum_order_quantity: 'Minimum order',
  pack_quantity: 'Pack quantity',
  lead_time_days: 'Lead time',
  is_active: 'Active',
  stock_quantity: 'On hand',
  status: 'Status',
  quantity: 'Quantity',
  tender: 'Tender',
  disposition: 'Disposition',
}

const SOURCE_TYPES = [
  { value: '', label: 'All sources' },
  { value: 'inventory_movement', label: 'Inventory movement' },
  { value: 'repair_order', label: 'Repair order' },
  { value: 'purchase_order', label: 'Purchase order' },
  { value: 'purchase_receipt', label: 'Purchase receipt' },
  { value: 'vendor_return', label: 'Vendor return' },
  { value: 'counter_sale', label: 'Recorded part sale' },
]

const SOURCE_LABELS = Object.fromEntries(SOURCE_TYPES.map((source) => [source.value, source.label]))
const MONEY_VALUE_FIELDS = new Set(['cost', 'selling_price', 'core_charge', 'unit_cost', 'unit_price', 'list_price'])

type ActivityFilters = {
  search: string
  category: '' | ActivityCategory
  eventType: string
  actorId: string
  sourceType: string
  sourceId: string
  from: string
  to: string
}

const EMPTY_FILTERS: ActivityFilters = { search: '', category: '', eventType: '', actorId: '', sourceType: '', sourceId: '', from: '', to: '' }

function titleCase(value: string) {
  const words = value.replace(/[._]/g, ' ').replace(/\s+/g, ' ').trim()
  return words ? `${words.charAt(0).toUpperCase()}${words.slice(1)}` : 'Activity recorded'
}

function activityLabel(value: string) {
  return EVENT_LABELS[value] || titleCase(value)
}

function money(value: string | null | undefined) {
  if (value == null) return null
  const numeric = Number(value)
  return Number.isFinite(numeric)
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(numeric)
    : `$${value}`
}

function moneyMetricLabel(event: ActivityEvent) {
  if (event.money?.charged_price != null) return 'Charged price'
  if (event.money?.list_price != null) return 'List price'
  return 'Amount'
}

function fieldLabel(value: string) {
  return FIELD_LABELS[value] || titleCase(value)
}

function formatValue(key: string, value: unknown) {
  if (value == null || value === '') return 'Not set'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (MONEY_VALUE_FIELDS.has(key)) return money(String(value)) || 'Not set'
  if (key === 'lead_time_days') return `${String(value)} days`
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

type ActivityFact = { key: string; label: string; before: string; after: string; baseline: boolean }

function activityFacts(event: ActivityEvent): ActivityFact[] {
  const before = event.before || {}
  const after = event.after || {}
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)]))
  return keys.map((key) => ({
    key,
    label: fieldLabel(key),
    before: formatValue(key, before[key]),
    after: formatValue(key, after[key]),
    baseline: event.origin === 'baseline' || !Object.prototype.hasOwnProperty.call(before, key),
  }))
}

function originLabel(origin: string) {
  if (origin === 'baseline') return 'Baseline import'
  if (origin === 'backfill_snapshot' || origin === 'backfill') return 'Historical snapshot'
  return null
}

function sourceLink(source: ActivityEvent['source']) {
  const label = source?.number || SOURCE_LABELS[source?.type || ''] || (source?.type ? titleCase(source.type) : 'No linked source')
  if (!source?.href) return <span>{label}</span>
  if (/^https?:\/\//.test(source.href)) return <a href={source.href} target="_blank" rel="noreferrer">{source.number || 'Open source'}<ExternalLink aria-hidden="true" /></a>
  return <Link to={source.href}>{label}<ArrowRight aria-hidden="true" /></Link>
}

export function PartLifecycleSummary({ inventoryId }: { inventoryId: string }) {
  const query = useQuery<LifecycleSummary>({
    queryKey: ['parts-operations', 'lifecycle-summary', inventoryId],
    queryFn: async () => (await api.get(`/parts-operations/parts/${inventoryId}/lifecycle-summary`)).data,
    retry: false,
  })
  if (query.isPending) return <div className="db-activity__summary-state" role="status">Loading lifecycle summary…</div>
  if (query.isError) return <div className="db-activity__summary-state" role="alert">Lifecycle summary could not be loaded.<button type="button" onClick={() => void query.refetch()}>Retry</button></div>
  const summary = query.data
  return <section className="db-activity__lifecycle" aria-labelledby={`part-lifecycle-${inventoryId}`}>
    <div className="db-activity__section-heading"><h3 id={`part-lifecycle-${inventoryId}`}>Lifecycle summary</h3><time dateTime={summary.as_of}>As of {new Date(summary.as_of).toLocaleString()}</time></div>
    <dl>
      <div><dt>Repair usage</dt><dd>{summary.repairs.units_used}</dd><small>{summary.repairs.repair_order_count} repair orders</small></div>
      <div><dt>Units received</dt><dd>{summary.purchasing.units_received}</dd><small>{summary.purchasing.receipt_count} receipts</small></div>
      <div><dt>Net units sold</dt><dd>{summary.sales.net_units}</dd><small>{summary.sales.units_returned} returned</small></div>
      <div><dt>Net item revenue</dt><dd>{money(summary.sales.net_item_revenue)}</dd><small>{money(summary.sales.refunds)} refunded</small></div>
    </dl>
  </section>
}

export default function ActivityWorkspace({ inventoryId, compact = false }: { inventoryId?: string; compact?: boolean }) {
  const [draft, setDraft] = useState<ActivityFilters>(EMPTY_FILTERS)
  const [filters, setFilters] = useState<ActivityFilters>(EMPTY_FILTERS)
  const [cursors, setCursors] = useState<Array<string | null>>([null])
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const cursor = cursors[cursors.length - 1] || null
  const params = useMemo(() => ({
    ...(inventoryId ? { inventory_id: inventoryId } : {}),
    ...(filters.category ? { category: filters.category } : {}),
    ...(filters.eventType.trim() ? { event_type: filters.eventType.split(',').map((value) => value.trim()).filter(Boolean) } : {}),
    ...(filters.actorId.trim() ? { actor_id: filters.actorId.trim() } : {}),
    ...(filters.sourceType.trim() ? { source_type: filters.sourceType.trim() } : {}),
    ...(filters.sourceId.trim() ? { source_id: filters.sourceId.trim() } : {}),
    ...(filters.search.trim() ? { search: filters.search.trim() } : {}),
    ...(filters.from ? { from: new Date(filters.from).toISOString() } : {}),
    ...(filters.to ? { to: new Date(filters.to).toISOString() } : {}),
    ...(cursor ? { cursor } : {}),
    limit: compact ? 20 : 50,
  }), [compact, cursor, filters, inventoryId])
  const query = useQuery<CursorPage<ActivityEvent>>({
    queryKey: ['parts-operations', 'activity-events', params],
    queryFn: async () => (await api.get('/parts-operations/activity-events', { params })).data,
    retry: false,
  })
  // <details> has no dismiss-on-outside-click of its own, so the popover stayed
  // open over the ledger. Escape closes it too, matching the other menus.
  const advancedRef = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    const closeIfOutside = (event: Event) => {
      const el = advancedRef.current
      if (!el?.open) return
      if (event.target instanceof Node && el.contains(event.target)) return
      el.open = false
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      const el = advancedRef.current
      if (event.key !== 'Escape' || !el?.open) return
      el.open = false
      el.querySelector('summary')?.focus()
    }
    document.addEventListener('pointerdown', closeIfOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeIfOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [])

  const advancedFilterCount = [draft.eventType, draft.actorId, draft.sourceType, draft.sourceId, draft.from, draft.to].filter((value) => value.trim()).length
  const appliedFilterCount = Object.values(filters).filter((value) => value.trim()).length
  const eventTypeHelpId = `activity-event-type-help-${inventoryId || 'global'}`
  const apply = () => { setFilters(draft); setCursors([null]) }
  const clear = () => { setDraft(EMPTY_FILTERS); setFilters(EMPTY_FILTERS); setCursors([null]) }
  const exportCsv = async () => {
    setExporting(true); setExportError(null)
    try {
      const exportParams = Object.fromEntries(Object.entries(params).filter(([key]) => key !== 'cursor' && key !== 'limit'))
      const response = await api.get('/parts-operations/activity-events/export.csv', { params: exportParams, responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv;charset=utf-8' }))
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = inventoryId ? `part-${inventoryId}-activity.csv` : 'inventory-activity.csv'
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
      setExportError(detail || 'The Activity export could not be prepared. Narrow the filters and try again.')
    } finally { setExporting(false) }
  }
  return <section className={`db-activity${compact ? ' is-compact' : ' db-operating-surface__scroller'}`} aria-labelledby={inventoryId ? `part-activity-${inventoryId}` : 'inventory-activity-title'}>
    <div className="db-activity__heading">
      <div><h2 id={inventoryId ? `part-activity-${inventoryId}` : 'inventory-activity-title'}>{inventoryId ? 'Part activity' : 'Inventory activity'}</h2><p>A searchable record of catalog, stock, repair, purchasing, returns, and recorded part sales.</p></div>
      <button type="button" disabled={exporting} onClick={() => void exportCsv()}><Download aria-hidden="true" />{exporting ? 'Preparing…' : 'Export CSV'}</button>
    </div>
    <form className="db-activity__filters" aria-label="Filter activity" onSubmit={(event) => { event.preventDefault(); apply() }}>
      <div className="db-activity__filter-primary">
        <label className="is-search"><Search aria-hidden="true" /><span className="sr-only">Search Activity</span><input type="search" value={draft.search} minLength={2} maxLength={200} onChange={(event) => setDraft((current) => ({ ...current, search: event.target.value }))} placeholder="Search parts, people, reasons, or sources" /></label>
        <label className="db-activity__category"><span className="sr-only">Category</span><select aria-label="Category" value={draft.category} onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value as ActivityFilters['category'] }))}>{CATEGORIES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        {!compact && <details ref={advancedRef} className="db-activity__advanced">
          <summary><SlidersHorizontal aria-hidden="true" /><span>Advanced</span>{advancedFilterCount > 0 && <strong aria-label={`${advancedFilterCount} advanced filters selected`}>{advancedFilterCount}</strong>}<ChevronDown aria-hidden="true" /></summary>
          <div className="db-activity__advanced-fields">
            <label><span>Event types</span><input aria-label="Event types" aria-describedby={eventTypeHelpId} value={draft.eventType} onChange={(event) => setDraft((current) => ({ ...current, eventType: event.target.value }))} placeholder="Example: stock.adjusted" /><small id={eventTypeHelpId}>Separate multiple event types with commas.</small></label>
            <label><span>Source</span><select value={draft.sourceType} onChange={(event) => setDraft((current) => ({ ...current, sourceType: event.target.value }))}>{SOURCE_TYPES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
            <label><span>Actor reference</span><input value={draft.actorId} onChange={(event) => setDraft((current) => ({ ...current, actorId: event.target.value }))} placeholder="Optional UUID" /></label>
            <label><span>Source reference</span><input value={draft.sourceId} onChange={(event) => setDraft((current) => ({ ...current, sourceId: event.target.value }))} placeholder="Optional UUID" /></label>
            <label><span>From</span><input type="datetime-local" value={draft.from} onChange={(event) => setDraft((current) => ({ ...current, from: event.target.value }))} /></label>
            <label><span>To</span><input type="datetime-local" value={draft.to} onChange={(event) => setDraft((current) => ({ ...current, to: event.target.value }))} /></label>
          </div>
        </details>}
        <div className="db-activity__filter-actions"><button type="button" disabled={!appliedFilterCount && !Object.values(draft).some((value) => value.trim())} onClick={clear}>Reset</button><button type="submit">Apply{appliedFilterCount > 0 ? ` (${appliedFilterCount})` : ''}</button></div>
      </div>
    </form>
    {exportError && <p className="db-activity__error" role="alert">{exportError}</p>}
    {query.isPending && <div className="db-activity__state" role="status">Loading Activity…</div>}
    {query.isError && <div className="db-activity__state" role="alert">Activity could not be loaded.<button type="button" onClick={() => void query.refetch()}>Retry</button></div>}
    {!query.isPending && !query.isError && !query.data.items.length && <div className="db-activity__state"><strong>No events match these filters.</strong><span>Clear or broaden the filters to see more lifecycle history.</span></div>}
    {!!query.data?.items.length && <div className="db-activity__ledger-head"><strong>Recent activity</strong><span>{query.data.items.length} shown</span></div>}
    {!!query.data?.items.length && <div className="db-activity__ledger db-operating-surface__card" role="feed" aria-busy={query.isFetching}>
      {query.data.items.map((event) => { const item = event.part || event.inventory; const facts = activityFacts(event); const visibleFacts = facts.slice(0, 4); const extraFacts = facts.slice(4); const includesOnHandChange = facts.some((fact) => fact.key === 'stock_quantity'); const eventHeadingId = `activity-event-${event.id}`; return <article key={event.id} aria-labelledby={eventHeadingId}>
        <div className="db-activity__event-mark" data-category={event.category} aria-hidden="true" />
        <div className="db-activity__event-copy"><div><span>{CATEGORY_LABELS[event.category]}</span>{originLabel(event.origin) && <em>{originLabel(event.origin)}</em>}</div><h3 id={eventHeadingId}>{activityLabel(event.event_type)}</h3><p>{item ? `${item.sku || 'SKU not set'} · ${item.name || 'Part name not set'}` : 'Inventory lifecycle event'}</p><small>{event.actor?.name || 'System'}{event.reason?.note ? ` · ${event.reason.note}` : ''}</small></div>
        <div className="db-activity__event-values">
          {!!facts.length && <dl className="db-activity__changes">{visibleFacts.map((fact) => <div key={fact.key}><dt>{fact.label}</dt><dd>{fact.baseline ? <strong>{fact.after}</strong> : <><span>{fact.before}</span><ArrowRight aria-label="changed to" /><strong>{fact.after}</strong></>}</dd></div>)}</dl>}
          {!!extraFacts.length && <details className="db-activity__more"><summary>Show {extraFacts.length} more {extraFacts.length === 1 ? 'detail' : 'details'}<ChevronDown aria-hidden="true" /></summary><dl className="db-activity__changes">{extraFacts.map((fact) => <div key={fact.key}><dt>{fact.label}</dt><dd>{fact.baseline ? <strong>{fact.after}</strong> : <><span>{fact.before}</span><ArrowRight aria-label="changed to" /><strong>{fact.after}</strong></>}</dd></div>)}</dl></details>}
          {(event.stock || event.money) && <dl className="db-activity__metrics">{event.stock && <>{!includesOnHandChange && <div><dt>On hand</dt><dd>{event.stock.physical_on_hand ?? event.stock.balance_after ?? '—'}</dd></div>}<div><dt>Held</dt><dd>{event.stock.held_for_checkout ?? 0}</dd></div><div><dt>Available</dt><dd>{event.stock.available_to_sell ?? '—'}</dd></div></>}{event.money && <div><dt>{moneyMetricLabel(event)}</dt><dd>{money(event.money.charged_price) || money(event.money.list_price) || '—'}{event.money.tax ? <small>{money(event.money.tax)} tax</small> : null}</dd></div>}</dl>}
        </div>
        <div className="db-activity__event-source">{sourceLink(event.source)}<time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time></div>
      </article> })}
      <div className="db-activity__pager"><span aria-live="polite">Showing {query.data.items.length} activity records</span><div><button type="button" disabled={cursors.length === 1 || query.isFetching} onClick={() => setCursors((current) => current.slice(0, -1))}><ArrowLeft aria-hidden="true" />Previous</button><button type="button" disabled={!query.data.next_cursor || query.isFetching} onClick={() => query.data.next_cursor && setCursors((current) => [...current, query.data.next_cursor])}>Next<ArrowRight aria-hidden="true" /></button></div></div>
    </div>}
  </section>
}
