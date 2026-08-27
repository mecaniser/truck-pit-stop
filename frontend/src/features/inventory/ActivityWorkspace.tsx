import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Download, ExternalLink, Search } from 'lucide-react'
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

function activityLabel(value: string) {
  return value.split('.').map((part) => part.replace(/_/g, ' ')).join(' · ')
}

function money(value: string | null | undefined) {
  return value == null ? null : `$${value}`
}

function compactRecord(record: Record<string, unknown> | null) {
  if (!record || !Object.keys(record).length) return '—'
  return Object.entries(record).slice(0, 3).map(([key, value]) => `${key.replace(/_/g, ' ')}: ${String(value ?? '—')}`).join(' · ')
}

function sourceLink(source: ActivityEvent['source']) {
  if (!source?.href) return <span>{source?.number || source?.type?.replace(/_/g, ' ') || 'No linked source'}</span>
  if (/^https?:\/\//.test(source.href)) return <a href={source.href} target="_blank" rel="noreferrer">{source.number || 'Open source'}<ExternalLink aria-hidden="true" /></a>
  return <Link to={source.href}>{source.number || 'Open source'}<ArrowRight aria-hidden="true" /></Link>
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
  return <section className={`db-activity${compact ? ' is-compact' : ''}`} aria-labelledby={inventoryId ? `part-activity-${inventoryId}` : 'inventory-activity-title'}>
    <div className="db-activity__heading">
      <div><h2 id={inventoryId ? `part-activity-${inventoryId}` : 'inventory-activity-title'}>{inventoryId ? 'Part activity' : 'Inventory activity'}</h2><p>Immutable catalog, stock, repair, purchasing, return, and sale events.</p></div>
      <button type="button" disabled={exporting} onClick={() => void exportCsv()}><Download aria-hidden="true" />{exporting ? 'Preparing…' : 'Export CSV'}</button>
    </div>
    <form className="db-activity__filters" aria-label="Filter activity" onSubmit={(event) => { event.preventDefault(); apply() }}>
      <label className="is-search"><Search aria-hidden="true" /><span className="sr-only">Search Activity</span><input type="search" value={draft.search} minLength={2} maxLength={200} onChange={(event) => setDraft((current) => ({ ...current, search: event.target.value }))} placeholder="Search part, actor, reason, or source" /></label>
      <label><span>Category</span><select value={draft.category} onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value as ActivityFilters['category'] }))}>{CATEGORIES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label><span>Event type</span><input value={draft.eventType} onChange={(event) => setDraft((current) => ({ ...current, eventType: event.target.value }))} placeholder="stock.adjusted" /></label>
      {!compact && <><label><span>Actor ID</span><input value={draft.actorId} onChange={(event) => setDraft((current) => ({ ...current, actorId: event.target.value }))} placeholder="Optional UUID" /></label><label><span>Source type</span><input value={draft.sourceType} onChange={(event) => setDraft((current) => ({ ...current, sourceType: event.target.value }))} placeholder="repair_order" /></label><label><span>Source ID</span><input value={draft.sourceId} onChange={(event) => setDraft((current) => ({ ...current, sourceId: event.target.value }))} placeholder="Optional UUID" /></label><label><span>From</span><input type="datetime-local" value={draft.from} onChange={(event) => setDraft((current) => ({ ...current, from: event.target.value }))} /></label><label><span>To</span><input type="datetime-local" value={draft.to} onChange={(event) => setDraft((current) => ({ ...current, to: event.target.value }))} /></label></>}
      <div className="db-activity__filter-actions"><button type="button" onClick={clear}>Clear</button><button type="submit">Apply filters</button></div>
    </form>
    {exportError && <p className="db-activity__error" role="alert">{exportError}</p>}
    {query.isPending && <div className="db-activity__state" role="status">Loading Activity…</div>}
    {query.isError && <div className="db-activity__state" role="alert">Activity could not be loaded.<button type="button" onClick={() => void query.refetch()}>Retry</button></div>}
    {!query.isPending && !query.isError && !query.data.items.length && <div className="db-activity__state"><strong>No events match these filters.</strong><span>Clear or broaden the filters to see more lifecycle history.</span></div>}
    {!!query.data?.items.length && <div className="db-activity__ledger" role="feed" aria-busy={query.isFetching}>
      {query.data.items.map((event) => { const item = event.part || event.inventory; return <article key={event.id}>
        <div className="db-activity__event-mark" data-category={event.category} aria-hidden="true" />
        <div className="db-activity__event-copy"><div><span>{event.category}</span><strong>{activityLabel(event.event_type)}</strong>{event.origin !== 'live' && <em>{event.origin}</em>}</div><p>{item ? `${item.sku || 'SKU not set'} · ${item.name || 'Part name not set'}` : event.reason?.note || 'Inventory lifecycle event'}</p><small>{event.actor?.name || 'System'}{event.reason?.note ? ` · ${event.reason.note}` : ''}</small></div>
        <dl className="db-activity__event-values"><div><dt>Before</dt><dd>{compactRecord(event.before)}</dd></div><div><dt>After</dt><dd>{compactRecord(event.after)}</dd></div>{event.stock && <div><dt>Stock</dt><dd>{event.stock.physical_on_hand ?? event.stock.balance_after ?? '—'} physical · {event.stock.held_for_checkout ?? 0} held · {event.stock.available_to_sell ?? '—'} available</dd></div>}{event.money && <div><dt>Money</dt><dd>{money(event.money.charged_price) || money(event.money.list_price) || '—'}{event.money.tax ? ` · ${money(event.money.tax)} tax` : ''}</dd></div>}</dl>
        <div className="db-activity__event-source">{sourceLink(event.source)}<time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString()}</time></div>
      </article> })}
      <div className="db-activity__pager"><span aria-live="polite">Showing {query.data.items.length} immutable events</span><div><button type="button" disabled={cursors.length === 1 || query.isFetching} onClick={() => setCursors((current) => current.slice(0, -1))}><ArrowLeft aria-hidden="true" />Previous</button><button type="button" disabled={!query.data.next_cursor || query.isFetching} onClick={() => query.data.next_cursor && setCursors((current) => [...current, query.data.next_cursor])}>Next<ArrowRight aria-hidden="true" /></button></div></div>
    </div>}
  </section>
}
