import { ControlButton } from '@/components/ui/Controls'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Popover, PopoverButton, PopoverGroup, PopoverPanel } from '@headlessui/react'
import DatePicker from '@/components/DatePicker'
import { Spinner } from '@/components/ui'
import { useNavigate } from 'react-router-dom'
import { formatDistanceToNow, isToday, isYesterday, format } from 'date-fns'
import {
  FileText, FilePlus, CheckCircle2, CreditCard, OctagonX, Trash2, ClipboardList, CircleAlert, SlidersHorizontal, X, ChevronRight, History, RefreshCw,
} from 'lucide-react'
import api from '@/lib/api'
import { getAuthenticatedSessionIdentity, useAuthStore } from '@/stores/authStore'
import { useActivityFeed, type ActivityEvent, type ActivityFeedResponse } from './activityFeedQuery'
import ShopWorkSelect from './ShopWorkSelect'
import './shopWorkPolish.css'

type ApiErrorLike = {
  response?: {
    status?: number
  }
}

const EVENT_ICON: Record<string, typeof FileText> = {
  ro_created: ClipboardList,
  ro_cancelled: OctagonX,
  ro_deleted: Trash2,
  ro_completed: CheckCircle2,
  quote_sent: FileText,
  invoice_created: FilePlus,
  invoice_paid: CreditCard,
  payment_recorded: CreditCard,
}

const EVENT_TYPE_OPTIONS = [
  { value: 'ro_created', label: 'Order created' },
  { value: 'ro_cancelled', label: 'Order cancelled' },
  { value: 'ro_deleted', label: 'Order deleted' },
  { value: 'ro_completed', label: 'Work completed' },
  { value: 'quote_sent', label: 'Quote sent' },
  { value: 'invoice_created', label: 'Invoice created' },
  { value: 'invoice_paid', label: 'Invoice paid' },
  { value: 'payment_recorded', label: 'Payment recorded' },
]

const dayLabel = (d: Date): string => {
  if (isToday(d)) return 'Today'
  if (isYesterday(d)) return 'Yesterday'
  return format(d, 'MMM d, yyyy')
}

function groupByDay(items: ActivityEvent[]) {
  const days = new Map<string, { dateKey: string; label: string; events: ActivityEvent[] }>()
  for (const event of items) {
    const date = new Date(event.occurred_at)
    const dateKey = format(date, 'yyyy-MM-dd')
    if (!days.has(dateKey)) days.set(dateKey, { dateKey, label: dayLabel(date), events: [] })
    days.get(dateKey)!.events.push(event)
  }
  return Array.from(days.values())
}

export default function RecentActivityFeed({ className }: { className?: string }) {
  const identity = useAuthStore(getAuthenticatedSessionIdentity)
  return <ScopedRecentActivityFeed key={identity ?? 'inactive-session'} className={className} />
}

function ScopedRecentActivityFeed({ className }: { className?: string }) {
  const navigate = useNavigate()
  const [olderItems, setOlderItems] = useState<ActivityEvent[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState(false)
  const olderRequest = useRef<AbortController | null>(null)

  const [actorFilter, setActorFilter] = useState('')
  const [eventTypeFilter, setEventTypeFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const filterParams = {
    actor_id: actorFilter || undefined,
    event_type: eventTypeFilter || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  }

  const { data, isLoading, isError, error, refetch, isFetching } = useActivityFeed(filterParams)

  // Reset before paint; a previous filter/session must never contribute events.
  useLayoutEffect(() => {
    olderRequest.current?.abort()
    olderRequest.current = null
    setOlderItems([])
    setLoadMoreError(false)
    setLoadingMore(false)
    setCursor(data?.next_cursor ?? null)
    setHasMore(data?.has_more ?? false)
    return () => {
      olderRequest.current?.abort()
      olderRequest.current = null
    }
  }, [data, actorFilter, eventTypeFilter, dateFrom, dateTo])

  const loadMore = async () => {
    if (!cursor || olderRequest.current) return
    const request = new AbortController()
    olderRequest.current = request
    try {
      setLoadingMore(true)
      setLoadMoreError(false)
      const { data: page } = await api.get<ActivityFeedResponse>('/activity', {
        params: { limit: 20, cursor, ...filterParams },
        signal: request.signal,
      })
      if (request.signal.aborted || olderRequest.current !== request) return
      setOlderItems((prev) => [...prev, ...page.items])
      setCursor(page.next_cursor)
      setHasMore(page.has_more)
    } catch {
      if (!request.signal.aborted && olderRequest.current === request) setLoadMoreError(true)
    } finally {
      if (olderRequest.current === request) {
        olderRequest.current = null
        setLoadingMore(false)
      }
    }
  }

  const showLess = () => {
    olderRequest.current?.abort()
    olderRequest.current = null
    setLoadingMore(false)
    setOlderItems([])
    setLoadMoreError(false)
    setCursor(data?.next_cursor ?? null)
    setHasMore(data?.has_more ?? false)
  }

  const isForbidden = isError && (error as ApiErrorLike)?.response?.status === 403

  const items = useMemo(() => [...(data?.items || []), ...olderItems], [data, olderItems])
  const dayGroups = useMemo(() => groupByDay(items), [items])
  const hasActiveFilters = !!(actorFilter || eventTypeFilter || dateFrom || dateTo)

  const clearFilters = () => { setActorFilter(''); setEventTypeFilter(''); setDateFrom(''); setDateTo('') }
  const filterCount = [actorFilter, eventTypeFilter, dateFrom, dateTo].filter(Boolean).length
  const filterDescription = [
    actorFilter && (data?.available_actors.find(actor => actor.id === actorFilter)?.name || 'Selected staff'),
    eventTypeFilter && EVENT_TYPE_OPTIONS.find(type => type.value === eventTypeFilter)?.label,
    dateFrom && `From ${dateFrom}`, dateTo && `To ${dateTo}`,
  ].filter(Boolean).join(' · ')

  return (
    <section className={`db-work-activity ${className || ''}`} aria-label="Shop activity" aria-busy={isFetching}>
      <header className="db-work-activity__header">
        <div><h2>Recent activity</h2>{hasActiveFilters && <p>{filterDescription}</p>}</div>
        <PopoverGroup className="db-work-activity__controls">
          {!!data?.warnings.length && <Popover className="db-work-popover">
            {({ close }) => <>
              <PopoverButton data-db-control="action" className="db-work-control db-work-control--warning"><CircleAlert aria-hidden="true" />Activity incomplete</PopoverButton>
              <PopoverPanel focus className="db-work-popover__panel" role="dialog" aria-label="Activity coverage">
                <div className="db-work-popover__heading"><strong>Activity coverage</strong><ControlButton controlKind="icon" type="button" className="db-work-icon-button" aria-label="Close activity coverage" onClick={() => close()}><X aria-hidden="true" /></ControlButton></div>
                {data.warnings.map(warning => <p key={warning}>{warning}</p>)}
              </PopoverPanel>
            </>}
          </Popover>}
          <Popover className="db-work-popover">
            {({ close }) => <>
              <PopoverButton data-db-control="action" className="db-work-control" aria-label={filterCount ? `Activity filters, ${filterCount} applied` : 'Activity filters'}><SlidersHorizontal aria-hidden="true" />Filters{filterCount > 0 && <span>{filterCount}</span>}</PopoverButton>
              <PopoverPanel className="db-work-popover__panel" role="dialog" aria-label="Activity filters">
                <div className="db-work-popover__heading"><strong>Filter activity</strong><ControlButton controlKind="icon" type="button" className="db-work-icon-button" aria-label="Close activity filters" onClick={() => close()}><X aria-hidden="true" /></ControlButton></div>
                <div className="db-work-activity__filters">
                  <div><span>Staff</span><ShopWorkSelect label="Activity staff" value={actorFilter} onChange={setActorFilter} options={[
                    { value: '', label: 'All staff' }, ...(data?.available_actors || []).map(actor => ({ value: actor.id, label: actor.name })),
                  ]} /></div>
                  <div><span>Activity</span><ShopWorkSelect label="Activity type" value={eventTypeFilter} onChange={setEventTypeFilter} options={[
                    { value: '', label: 'All activity' }, ...EVENT_TYPE_OPTIONS,
                  ]} /></div>
                  <DatePicker label="From date" value={dateFrom} onChange={setDateFrom} max={dateTo || undefined} showDayDetails={false} />
                  <DatePicker label="To date" value={dateTo} onChange={setDateTo} min={dateFrom || undefined} showDayDetails={false} />
                  {hasActiveFilters && <ControlButton type="button" className="db-work-control" onClick={() => { clearFilters(); close() }}><X aria-hidden="true" />Clear filters</ControlButton>}
                </div>
              </PopoverPanel>
            </>}
          </Popover>
        </PopoverGroup>
      </header>
      {isError ? <div className="db-work-state" role="alert"><CircleAlert aria-hidden="true" /><div><strong>{isForbidden ? 'Activity is unavailable for this account' : 'Activity could not be loaded'}</strong><p>{isForbidden ? 'Your available work remains in the other Shop Work views.' : 'Try again to check recent changes.'}</p>{!isForbidden && <ControlButton type="button" className="db-work-control" onClick={() => { void refetch() }} disabled={isFetching}><RefreshCw aria-hidden="true" />Retry activity</ControlButton>}</div></div>
        : isLoading ? <div className="db-work-state" role="status"><span aria-hidden="true"><Spinner size="sm" /></span><strong>Loading activity…</strong></div>
          : dayGroups.length === 0 ? <div className="db-work-state" role="status"><History aria-hidden="true" /><div><strong>{hasActiveFilters ? 'No activity matches these filters' : 'No recent activity'}</strong><p>{hasActiveFilters ? 'Change the filters to check another staff member or date.' : 'Repair, quote, invoice, and payment updates will appear here.'}</p></div></div>
            : <>
              <div className="db-work-activity__days">{dayGroups.map(day => <section key={day.dateKey} aria-label={day.label}>
                <h3>{day.label}</h3>
                <ol>{day.events.map(event => {
                  const Icon = EVENT_ICON[event.event_type] || ClipboardList
                  return <li key={event.id}><ControlButton controlKind="content" type="button" className="db-work-activity__event" disabled={!event.order_id} onClick={() => event.order_id && navigate(`/dashboard/repair-orders?selected=${encodeURIComponent(event.order_id)}`)}>
                    <Icon className="db-work-activity__event-icon" aria-hidden="true" data-outcome={['invoice_paid', 'payment_recorded', 'ro_completed'].includes(event.event_type) ? 'complete' : ['ro_cancelled', 'ro_deleted'].includes(event.event_type) ? 'removed' : undefined} />
                    <span className="db-work-activity__identity"><strong>{event.label}</strong><span>{[event.order_number, event.actor_name || 'System'].filter(Boolean).join(' · ')}</span></span>
                    <time dateTime={event.occurred_at} title={format(new Date(event.occurred_at), 'MMM d, yyyy h:mm a')}>{formatDistanceToNow(new Date(event.occurred_at), { addSuffix: true })}</time>
                    {event.order_id && <ChevronRight className="db-work-activity__open" aria-hidden="true" />}
                  </ControlButton></li>
                })}</ol>
              </section>)}</div>
              {(hasMore || olderItems.length > 0) && <footer className="db-work-activity__footer">
                {loadMoreError && <p role="alert">Older activity could not be loaded. The events above are still available.</p>}
                {hasMore && <ControlButton type="button" className="db-work-control" disabled={loadingMore} onClick={() => { void loadMore() }}>{loadingMore ? 'Loading…' : loadMoreError ? 'Retry older activity' : 'Load older activity'}</ControlButton>}
                {olderItems.length > 0 && <ControlButton type="button" className="db-work-control" onClick={showLess}>Show recent only</ControlButton>}
              </footer>}
            </>}
    </section>
  )
}
