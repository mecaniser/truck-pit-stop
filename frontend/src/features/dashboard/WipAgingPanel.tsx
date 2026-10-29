import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react'
import { useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { ChevronDown, ChevronLeft, ChevronRight, Info, Search, SlidersHorizontal } from 'lucide-react'
import api from '@/lib/api'
import { shortDuration } from '@/lib/elapsed'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useAuthStore } from '@/stores/authStore'
import { clockLabel, WIP_CATEGORIES, WIP_LABELS, WIP_REASONS, type WipAgingResponse, type WipFilters } from './wipAging'
import './wipAging.css'

function promiseLabel(value: string, timezone: string | null): string {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return 'Unknown'
  try {
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: timezone || 'UTC', timeZoneName: 'short' }).format(date)
  } catch {
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' }).format(date)
  }
}

export default function WipAgingPanel({ filters, onFiltersChange, onOpenRecord }: {
  filters: WipFilters
  onFiltersChange: (filters: WipFilters) => void
  onOpenRecord: (id: string, lane: 'needs_action' | 'on_floor') => void
}) {
  const user = useAuthStore(state => state.user)
  const authSessionEpoch = useAuthStore(state => state.authSessionEpoch)
  const search = useDebouncedValue(filters.search.trim(), 300)
  const searchPending = search !== filters.search.trim()
  const query = useQuery<WipAgingResponse>({
    queryKey: ['dashboard-wip-aging', user?.tenant_id, user?.id, { ...filters, search }, user?.role, user?.is_active, authSessionEpoch],
    queryFn: async ({ signal }) => (await api.get('/dashboard/wip-aging', { params: { ...filters, search, limit: 50 }, signal })).data,
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    refetchOnMount: 'always',
    retry: (count, error) => !(isAxiosError(error) && [403, 429].includes(error.response?.status || 0)) && count < 1,
  })
  const data = query.data
  const busy = query.isFetching || searchPending
  const update = (next: Partial<WipFilters>) => onFiltersChange({ ...filters, ...next, offset: 0 })
  const count = (value: number | undefined) => value == null || searchPending || query.isError ? '—' : value
  const statusText = isAxiosError(query.error) && query.error.response?.status === 403
    ? 'Active work is unavailable for this account.'
    : isAxiosError(query.error) && query.error.response?.status === 429
      ? 'Too many requests. Wait a moment, then retry.'
      : 'Active work could not be loaded.'
  return (
    <section className="db-wip" aria-label="Active work aging" aria-busy={busy}>
      <div className="db-wip__toolbar">
        <label className="db-shop-work-new__search">
          <span className="sr-only">Search active work</span><Search aria-hidden="true" />
          <input type="search" maxLength={200} value={filters.search} onChange={event => update({ search: event.target.value })} placeholder="Order, customer, truck, or technician" />
        </label>
        <Popover className="db-wip__popover">
          <PopoverButton className="db-wip__filter-trigger"><SlidersHorizontal aria-hidden="true" />Filters{(filters.overdue_only || filters.timing !== 'all' || filters.sort !== 'priority') && <span className="db-wip__filter-dot" aria-label="Filters applied" />}</PopoverButton>
          <PopoverPanel focus className="db-wip__popover-panel" role="dialog" aria-label="Active work filters">
            <div className="db-wip__filters">
              <button type="button" aria-pressed={filters.overdue_only} onClick={() => update({ overdue_only: !filters.overdue_only })}>Promise overdue <span>{count(data?.summary.overdue_jobs)}</span></button>
              <label>Wait timing<span className="db-wip__select"><select value={filters.timing} onChange={event => update({ timing: event.target.value as WipFilters['timing'] })}>
                <option value="all">All timing</option><option value="known">Known</option><option value="unknown">Unknown</option>
              </select><ChevronDown aria-hidden="true" /></span></label>
              <label>Sort<span className="db-wip__select"><select value={filters.sort} onChange={event => update({ sort: event.target.value as WipFilters['sort'] })}>
                <option value="priority">Needs attention first</option><option value="oldest_wait">Longest wait</option><option value="oldest_order">Oldest order</option>
              </select><ChevronDown aria-hidden="true" /></span></label>
            </div>
          </PopoverPanel>
        </Popover>
      </div>
      <div className="db-wip__facets" aria-label="Active work categories">
        <button type="button" aria-pressed={filters.category === 'all'} onClick={() => update({ category: 'all' })}>All active <span>{count(data?.summary.total_jobs)}</span></button>
        {WIP_CATEGORIES.map(category => (
          <button type="button" key={category} aria-pressed={filters.category === category} onClick={() => update({ category })}>
            {WIP_LABELS[category]} <span>{count(data?.summary.category_counts[category])}</span>
          </button>
        ))}
      </div>
      <label className="db-wip__mobile-category"><span className="sr-only">Active work category</span><span className="db-wip__select"><select value={filters.category} onChange={event => update({ category: event.target.value as WipFilters['category'] })}>
        <option value="all">All active · {count(data?.summary.total_jobs)}</option>
        {WIP_CATEGORIES.map(category => <option key={category} value={category}>{WIP_LABELS[category]} · {count(data?.summary.category_counts[category])}</option>)}
      </select><ChevronDown aria-hidden="true" /></span></label>
      <div className="db-wip__result-meta">
        <span role="status">{query.isLoading || searchPending ? 'Loading active work…' : query.isError ? 'Active work unavailable' : `${data?.filtered_total ?? 0} matching jobs${data?.scope === 'assigned' ? ' · assigned to you' : ''}`}</span>
        <div className="db-wip__timing-summary">
          {!query.isError && data && <button type="button" className="db-wip__unknown" aria-pressed={filters.timing === 'unknown'} aria-label={`${data.summary.unknown_wait_jobs} unknown across ${data.filters.search ? 'matching' : 'all'} active jobs; filter unknown wait timing`} onClick={() => update({ timing: filters.timing === 'unknown' ? 'all' : 'unknown' })}>Unknown {data.summary.unknown_wait_jobs}</button>}
          <Popover className="db-wip__popover"><PopoverButton className="db-wip__info" aria-label="About work timing"><Info aria-hidden="true" /></PopoverButton><PopoverPanel focus className="db-wip__popover-panel db-wip__timing-help" role="dialog" aria-label="Work timing explained">
            <strong>Work timing</strong><p>Elapsed time includes nights and weekends. Order age is not time in the shop.</p><p>Unknown means a reliable wait start is missing. Counts cover {data?.filters.search ? 'all jobs matching your search' : 'all active jobs'}, before category and timing filters.</p>
          </PopoverPanel></Popover>
        </div>
      </div>
      {query.isError ? <div className="db-action-ledger__empty" role="alert"><strong>{statusText}</strong><button type="button" onClick={() => query.refetch()} disabled={busy}>Retry active work</button></div>
        : !data || searchPending ? <div className="db-action-ledger__empty">Loading active work…</div>
          : <div className="db-operating-surface__scroller db-wip__scroller">
            <div className="db-wip__rows">
              {data.items.length === 0 ? <div className="db-action-ledger__empty"><strong>{data.summary.total_jobs === 0 ? 'No active jobs in this view' : 'No jobs match these filters'}</strong><span>Completed work and payment follow-up stay in Closeout.</span></div>
                : data.items.map(order => (
                  <button type="button" className="db-wip__row" key={order.id} onClick={() => onOpenRecord(order.id, order.action_lane)} aria-label={`Open ${order.order_number} in Shop Work`} data-overdue={order.is_overdue || undefined}>
                    <span className="db-wip__identity"><strong>{order.customer_name}</strong><span>{[order.vehicle_info, order.vehicle_unit_number ? `Unit ${order.vehicle_unit_number}` : null].filter(Boolean).join(' · ')}</span><small>{order.order_number}</small></span>
                    <span className="db-wip__wait"><strong>{WIP_REASONS[order.reason]}</strong>{order.current_wait.state !== 'not_applicable' && <span>Wait <b>{clockLabel(order.current_wait)}</b></span>}{order.hold_reason && order.reason === 'other_hold' && <small>{order.hold_reason}</small>}</span>
                    <span className="db-wip__evidence"><span>{order.technician_names.length ? order.technician_names.join(', ') : order.assignment === 'unassigned' ? 'Unassigned' : 'Assignment unknown'}</span><span>Order age <b>{clockLabel(order.order_age)}</b></span>{order.promised_finish_at && <span className="db-wip__promise">{order.is_overdue && order.overdue_seconds != null ? `Promise overdue · ${order.overdue_seconds < 60 ? '<1m' : shortDuration(order.overdue_seconds * 1000)}` : `Promised ${promiseLabel(order.promised_finish_at, data.timezone)}`}</span>}</span>
                    <ChevronRight className="db-wip__open" aria-hidden="true" />
                  </button>
                ))}
            </div>
            <div className="db-wip__pagination">
              <span>{data.items.length ? `${data.offset + 1}–${data.offset + data.items.length} of ${data.filtered_total}` : `0 of ${data.filtered_total} jobs`}</span>
              <button type="button" aria-label="Previous active jobs" disabled={busy || data.offset === 0} onClick={() => onFiltersChange({ ...filters, offset: Math.max(0, data.offset - data.limit) })}><ChevronLeft aria-hidden="true" /> Previous</button>
              <button type="button" aria-label="Next active jobs" disabled={busy || !data.has_more} onClick={() => onFiltersChange({ ...filters, offset: data.offset + data.limit })}>Next <ChevronRight aria-hidden="true" /></button>
            </div>
          </div>}
    </section>
  )
}
