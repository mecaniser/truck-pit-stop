import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow, isToday, isYesterday, format } from 'date-fns'
import {
  FileText, FilePlus, CheckCircle2, CreditCard, OctagonX, Trash2, ClipboardList, Loader2, AlertTriangle,
} from 'lucide-react'
import api from '@/lib/api'

type ActivityEvent = {
  id: string
  event_type: string
  label: string
  occurred_at: string
  actor_name?: string | null
  actor_id?: string | null
  order_number?: string | null
  order_id?: string | null
  detail?: string | null
}

type ActivityActor = {
  id: string
  name: string
}

type ActivityFeedResponse = {
  items: ActivityEvent[]
  next_cursor: string | null
  has_more: boolean
  available_actors: ActivityActor[]
  warnings: string[]
}

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

export default function RecentActivityFeed() {
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

  const { data, isLoading, isError, error } = useQuery<ActivityFeedResponse>({
    queryKey: ['activity-feed', actorFilter, eventTypeFilter, dateFrom, dateTo],
    queryFn: async () => {
      const { data } = await api.get<ActivityFeedResponse>('/activity', {
        params: { limit: 20, ...filterParams },
      })
      return data
    },
  })

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

  const isForbidden = isError && (error as ApiErrorLike)?.response?.status === 403

  const items = useMemo(() => [...(data?.items || []), ...olderItems], [data, olderItems])
  const dayGroups = useMemo(() => groupByDayAndActor(items), [items])
  const hasActiveFilters = !!(actorFilter || eventTypeFilter || dateFrom || dateTo)

  if (isForbidden) return null
  if (!isLoading && items.length === 0 && !hasMore && !hasActiveFilters) return null

  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Recent Activity</h2>
      </div>

      {data && data.warnings.length > 0 && (
        <div className="mb-4 space-y-2">
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

      <div className="flex flex-wrap gap-2 mb-4">
        <select
          value={actorFilter}
          onChange={(e) => setActorFilter(e.target.value)}
          className="bg-gray-700/50 border border-gray-600/50 rounded-lg px-3 py-1.5 text-sm text-gray-200"
        >
          <option value="">All staff</option>
          {(data?.available_actors || []).map((actor) => (
            <option key={actor.id} value={actor.id}>{actor.name}</option>
          ))}
        </select>
        <select
          value={eventTypeFilter}
          onChange={(e) => setEventTypeFilter(e.target.value)}
          className="bg-gray-700/50 border border-gray-600/50 rounded-lg px-3 py-1.5 text-sm text-gray-200"
        >
          <option value="">All activity</option>
          {EVENT_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="bg-gray-700/50 border border-gray-600/50 rounded-lg px-3 py-1.5 text-sm text-gray-200"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="bg-gray-700/50 border border-gray-600/50 rounded-lg px-3 py-1.5 text-sm text-gray-200"
        />
        {hasActiveFilters && (
          <button
            type="button"
            onClick={() => { setActorFilter(''); setEventTypeFilter(''); setDateFrom(''); setDateTo('') }}
            className="text-sm text-gray-400 hover:text-white px-2"
          >
            Clear
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-8 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin" />
        </div>
      ) : dayGroups.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-8">No activity matches these filters.</p>
      ) : (
        <div className="space-y-5">
          {dayGroups.map((day) => (
            <div key={day.dateKey}>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">{day.label}</h3>
              <div className="space-y-3">
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
                          <button
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
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {hasMore && (
            <button
              type="button"
              disabled={loadingMore}
              onClick={loadMore}
              className="w-full mt-2 py-2 text-sm text-gray-400 hover:text-white transition-colors disabled:opacity-50"
            >
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
