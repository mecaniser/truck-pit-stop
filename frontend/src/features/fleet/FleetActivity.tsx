import { useEffect, useMemo, useRef } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { AlertTriangle, ClipboardCheck, LogOut } from 'lucide-react'

import api from '@/lib/api'
import { Spinner } from '@/components/ui'

/**
 * What has happened on this fleet board.
 *
 * The board answers "what is happening now" — on road, in the shop, PM due.
 * Nothing answered "what happened", which is why a truck leaving a fleet had
 * nowhere to record why it left. This is that record.
 *
 * Repair orders are deliberately absent: there are roughly two hundred of them
 * against forty of everything else, and including them would bury the
 * incidents, inspections and membership changes that have no other home.
 * Service history stays on the truck.
 */

export type FleetActivityEntry = {
  id: string
  kind: 'inspection' | 'incident' | 'membership'
  occurred_at: string
  vehicle_id?: string | null
  unit_number?: string | null
  vehicle_label?: string | null
  summary: string
  actor?: string | null
  severity?: string | null
}

type ActivityPage = {
  items: FleetActivityEntry[]
  next_before: string | null
  has_more: boolean
}

const KIND_META: Record<FleetActivityEntry['kind'], { label: string; Icon: typeof AlertTriangle }> = {
  inspection: { label: 'Inspection', Icon: ClipboardCheck },
  incident: { label: 'Incident', Icon: AlertTriangle },
  membership: { label: 'Fleet', Icon: LogOut },
}

const PAGE_SIZE = 25

function formatWhen(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function FleetActivity({
  kind,
  vehicleId,
}: {
  kind?: FleetActivityEntry['kind'] | 'all'
  vehicleId?: string | null
}) {
  const params = useMemo(() => {
    const base: Record<string, string | number> = { limit: PAGE_SIZE }
    if (kind && kind !== 'all') base.kind = kind
    if (vehicleId) base.vehicle_id = vehicleId
    return base
  }, [kind, vehicleId])

  const query = useInfiniteQuery<ActivityPage>({
    queryKey: ['fleet-activity', params],
    queryFn: async ({ pageParam, signal }) => {
      const response = await api.get('/fleet/activity', {
        signal,
        params: pageParam ? { ...params, before: pageParam } : params,
      })
      return response.data as ActivityPage
    },
    initialPageParam: undefined as string | undefined,
    // next_before is null once the feed is exhausted, which is what stops the
    // scroll asking for more.
    getNextPageParam: (last) => last.next_before ?? undefined,
  })

  const entries = useMemo(
    () => (query.data?.pages || []).flatMap((page) => page.items),
    [query.data],
  )

  // Load the next page when the end of the list comes into view, rather than on
  // a button: the operator is already scrolling to read, and asking them to
  // stop and click is asking them to leave.
  const sentinel = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = sentinel.current
    if (!node || !query.hasNextPage || query.isFetchingNextPage) return
    const observer = new IntersectionObserver(
      (records) => { if (records.some((r) => r.isIntersecting)) query.fetchNextPage() },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [query.hasNextPage, query.isFetchingNextPage, query.fetchNextPage, query])

  if (query.isLoading) {
    return <div className="fleet-activity__state"><Spinner size="sm" /> Loading activity…</div>
  }
  if (query.isError) {
    return <div className="fleet-activity__state">Activity could not be loaded.</div>
  }
  if (!entries.length) {
    return <div className="fleet-activity__state">Nothing has happened on this board yet.</div>
  }

  return (
    <div className="fleet-activity">
      <ol className="fleet-activity__list">
        {entries.map((entry) => {
          const meta = KIND_META[entry.kind]
          const Icon = meta.Icon
          const truck = entry.unit_number
            ? `Unit ${entry.unit_number}`
            : entry.vehicle_label || 'Truck'
          return (
            <li key={`${entry.kind}-${entry.id}`} className="fleet-activity__row">
              <span className={`fleet-activity__icon fleet-activity__icon--${entry.kind}`} aria-hidden="true">
                <Icon size={14} />
              </span>
              <span className="fleet-activity__when">{formatWhen(entry.occurred_at)}</span>
              <span className="fleet-activity__kind">{meta.label}</span>
              <span className="fleet-activity__truck">{truck}</span>
              <span className="fleet-activity__summary">
                {entry.summary}
                {entry.severity ? <em className="fleet-activity__severity"> · {entry.severity}</em> : null}
              </span>
              <span className="fleet-activity__actor">{entry.actor || ''}</span>
            </li>
          )
        })}
      </ol>
      <div ref={sentinel} className="fleet-activity__sentinel">
        {query.isFetchingNextPage ? <><Spinner size="sm" /> Loading more…</> : null}
      </div>
    </div>
  )
}
