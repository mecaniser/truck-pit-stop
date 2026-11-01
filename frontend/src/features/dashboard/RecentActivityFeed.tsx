import { ControlButton } from '@/components/ui/Controls'
import { useEffect, useMemo, useState } from 'react'
import DatePicker from '@/components/DatePicker'
import { Spinner } from '@/components/ui'
import { useNavigate } from 'react-router-dom'
import { formatDistanceToNow, isToday, isYesterday, format } from 'date-fns'
import {
  FileText, FilePlus, CheckCircle2, CreditCard, OctagonX, Trash2, ClipboardList, AlertTriangle,
} from 'lucide-react'
import api from '@/lib/api'
import { useActivityFeed, type ActivityEvent, type ActivityFeedResponse } from './activityFeedQuery'
import ShopWorkSelect from './ShopWorkSelect'

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

const EVENT_COLOR: Record<string, string> = {
  ro_created: 'text-blue-400',
  ro_cancelled: 'text-red-400',
  ro_deleted: 'text-red-400',
  ro_completed: 'text-emerald-400',
  quote_sent: 'text-amber-400',
  invoice_created: 'text-indigo-400',
  invoice_paid: 'text-emerald-400',
  payment_recorded: 'text-emerald-400',
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

type DayGroup = {
  dateKey: string
  label: string
  actorGroups: Array<{ actorName: string | null; events: ActivityEvent[] }>
}

function groupByDayAndActor(items: ActivityEvent[]): DayGroup[] {
  const dayMap = new Map<string, { label: string; events: ActivityEvent[] }>()
  for (const event of items) {
    const d = new Date(event.occurred_at)
    const dateKey = format(d, 'yyyy-MM-dd')
    if (!dayMap.has(dateKey)) {
      dayMap.set(dateKey, { label: dayLabel(d), events: [] })
    }
    dayMap.get(dateKey)!.events.push(event)
  }

  return Array.from(dayMap.entries()).map(([dateKey, { label, events }]) => {
    const actorOrder: string[] = []
    const actorMap = new Map<string, ActivityEvent[]>()
    for (const event of events) {
      const key = event.actor_name || ''
      if (!actorMap.has(key)) {
        actorOrder.push(key)
        actorMap.set(key, [])
      }
      actorMap.get(key)!.push(event)
    }
    return {
      dateKey,
      label,
      actorGroups: actorOrder.map((key) => ({
        actorName: key || null,
        events: actorMap.get(key)!,
      })),
    }
  })
}

export default function RecentActivityFeed({
  className,
}: {
  className?: string
}) {
  const navigate = useNavigate()
  const [olderItems, setOlderItems] = useState<ActivityEvent[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

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

  const { data, isLoading, isError, error } = useActivityFeed(filterParams)

  useEffect(() => {
    setOlderItems([])
    setCursor(data?.next_cursor ?? null)
    setHasMore(data?.has_more ?? false)
  }, [data])

  const loadMore = async () => {
    if (!cursor) return
    try {
      setLoadingMore(true)
      const { data: page } = await api.get<ActivityFeedResponse>('/activity', {
        params: { limit: 20, cursor, ...filterParams },
      })
      setOlderItems((prev) => [...prev, ...page.items])
      setCursor(page.next_cursor)
      setHasMore(page.has_more)
    } finally {
      setLoadingMore(false)
    }
  }

  const showLess = () => {
    setOlderItems([])
    setCursor(data?.next_cursor ?? null)
    setHasMore(data?.has_more ?? false)
  }

  const isForbidden = isError && (error as ApiErrorLike)?.response?.status === 403

  const items = useMemo(() => [...(data?.items || []), ...olderItems], [data, olderItems])
  const dayGroups = useMemo(() => groupByDayAndActor(items), [items])
  const hasActiveFilters = !!(actorFilter || eventTypeFilter || dateFrom || dateTo)

  if (isForbidden) return null

  return (
    <div className={className ?? 'bg-gray-800/50 border border-gray-700/50 rounded-lg p-6'}>
      {data && data.warnings.length > 0 && (
        <div className="mb-4 space-y-2 flex-shrink-0">
          {data.warnings.map((warning) => (
            <div
              key={warning}
              className="flex items-center gap-3 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg"
            >
              <AlertTriangle className="w-4 h-4 text-yellow-400 flex-shrink-0" />
              <p className="text-sm text-yellow-200">{warning}</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-4 flex-shrink-0">
        <ShopWorkSelect label="Activity staff" value={actorFilter} onChange={setActorFilter} options={[
          { value: '', label: 'All staff' }, ...(data?.available_actors || []).map(actor => ({ value: actor.id, label: actor.name })),
        ]} />
        <ShopWorkSelect label="Activity type" value={eventTypeFilter} onChange={setEventTypeFilter} options={[
          { value: '', label: 'All activity' }, ...EVENT_TYPE_OPTIONS,
        ]} />
        <DatePicker compact label="Activity from date" value={dateFrom} onChange={setDateFrom} />
        <DatePicker compact label="Activity to date" value={dateTo} onChange={setDateTo} min={dateFrom || undefined} />
        {hasActiveFilters && (
          <ControlButton
            type="button"
            onClick={() => { setActorFilter(''); setEventTypeFilter(''); setDateFrom(''); setDateTo('') }}
            className="text-sm text-gray-400 hover:text-white px-2"
          >
            Clear
          </ControlButton>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8 text-gray-400">
          <Spinner size="sm" />
        </div>
      ) : dayGroups.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">No activity matches these filters.</p>
      ) : (
        <div className="flex flex-col flex-1 min-h-0">
          <div
            className="grid gap-4 flex-1 min-h-0 items-stretch"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}
          >
            {dayGroups.map((day) => (
              <div key={day.dateKey} className="flex flex-col min-h-0">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2 flex-shrink-0">{day.label}</h3>
                <div className="flex-1 min-h-0 space-y-3 overflow-y-auto scrollbar-dark pr-1">
                  {day.actorGroups.map((actorGroup, idx) => (
                    <div key={`${day.dateKey}-${actorGroup.actorName || 'system'}-${idx}`}>
                      <p className="text-xs text-gray-500 mb-1 px-1">
                        {actorGroup.actorName || 'System'}
                        <span className="text-gray-600"> · {actorGroup.events.length} action{actorGroup.events.length === 1 ? '' : 's'}</span>
                      </p>
                      <div className="space-y-1">
                        {actorGroup.events.map((event) => {
                          const Icon = EVENT_ICON[event.event_type] || ClipboardList
                          const color = EVENT_COLOR[event.event_type] || 'text-gray-400'
                          return (
                            <ControlButton controlKind="content"
                              key={event.id}
                              type="button"
                              disabled={!event.order_id}
                              onClick={() => event.order_id && navigate(`/dashboard/repair-orders?selected=${event.order_id}`)}
                              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left hover:bg-gray-700/30 disabled:hover:bg-transparent disabled:cursor-default transition-colors"
                            >
                              <Icon className={`w-4 h-4 flex-shrink-0 ${color}`} />
                              <div className="min-w-0 flex-1">
                                <p className="text-sm text-gray-200 truncate">
                                  {event.label}
                                  {event.order_number ? <span className="text-gray-400"> · {event.order_number}</span> : null}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {formatDistanceToNow(new Date(event.occurred_at), { addSuffix: true })}
                                </p>
                              </div>
                            </ControlButton>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {(hasMore || olderItems.length > 0) && (
            <div className="flex items-center justify-center gap-3 mt-3 flex-shrink-0">
              {hasMore && (
                <ControlButton
                  type="button"
                  disabled={loadingMore}
                  onClick={loadMore}
                  className=" text-sm text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                >
                  {loadingMore ? 'Loading…' : 'Load more'}
                </ControlButton>
              )}
              {olderItems.length > 0 && (
                <ControlButton
                  type="button"
                  onClick={showLess}
                  className=" text-sm text-gray-400 hover:text-white transition-colors"
                >
                  Show less
                </ControlButton>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
