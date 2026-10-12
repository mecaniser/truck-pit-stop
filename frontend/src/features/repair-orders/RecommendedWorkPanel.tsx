import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowUpRight, ChevronLeft, ChevronRight, RotateCcw } from 'lucide-react'
import { format } from 'date-fns'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'
import type { RecommendedServicePriority, RepairOrderStatus } from '@/types'

const RECOMMENDED_WORK_QUERY_KEY = ['recommended-work'] as const
const PAGE_SIZE = 25

interface RecommendedWorkItem {
  id: string
  description: string
  priority: RecommendedServicePriority
  created_at: string
  vehicle: { id: string; unit_number: string | null; year: number | null; make: string | null; model: string | null }
  source_order: { id: string; order_number: string; status: RepairOrderStatus; created_at: string }
}

interface RecommendedWorkPage {
  items: RecommendedWorkItem[]
  total: number
  skip: number
  limit: number
}

interface Props {
  vehicleId: string
  customerId?: string
  contextOrderId?: string
}

const priorities = {
  urgent: 'bg-red-50 text-red-700',
  soon: 'bg-amber-50 text-amber-800',
  monitor: 'bg-blue-50 text-blue-700',
}

/** Staff-only even when a cached page exists from a previous session/role. */
export default function RecommendedWorkPanel(props: Props) {
  const user = useAuthStore((state) => state.user)
  if (!user?.tenant_id || !['garage_owner', 'garage_admin', 'receptionist'].includes(user.role) || !props.vehicleId) return null
  return <RecommendedWorkContext
    key={[user.id, user.tenant_id, props.vehicleId, props.customerId, props.contextOrderId].join(':')}
    {...props}
    tenantId={user.tenant_id}
  />
}

function RecommendedWorkContext({ tenantId, vehicleId, customerId, contextOrderId }: Props & { tenantId: string }) {
  const [skip, setSkip] = useState(0)
  const query = useQuery({
    queryKey: [...RECOMMENDED_WORK_QUERY_KEY, tenantId, vehicleId, customerId ?? null, contextOrderId ?? null, skip, PAGE_SIZE],
    queryFn: async ({ signal }) => {
      const response = await api.get<RecommendedWorkPage>('/repair-orders/recommended-work', {
        params: { vehicle_id: vehicleId, customer_id: customerId, context_order_id: contextOrderId, skip, limit: PAGE_SIZE },
        signal,
      })
      return response.data
    },
    refetchOnMount: 'always',
  })
  const page = query.data
  return (
    <section className="w-full min-w-0 rounded-xl border border-gray-200 bg-white p-3" aria-label="Open recommendations for this truck">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900">Open recommendations for this truck</h3>
        <button type="button" onClick={() => { void query.refetch() }} disabled={query.isFetching}
          className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          aria-label="Refresh recommendations">
          <RotateCcw className="h-3.5 w-3.5" /> Refresh
        </button>
      </div>
      <p className="mt-1 text-xs text-gray-500">Unresolved work recorded on other orders.</p>
      <div role="status" aria-live="polite">
        {query.isPending && <p className="py-3 text-sm text-gray-500">Loading recommendations…</p>}
        {query.isFetching && !query.isPending && <p className="pt-2 text-xs text-gray-500">Refreshing recommendations…</p>}
      </div>
      {query.isError && <div role="alert" className="mt-3 text-sm text-red-700">
        {page ? 'Could not refresh recommendations. Showing the last loaded page.' : 'Could not load recommendations.'}
        <button type="button" className="ml-2 whitespace-nowrap underline" onClick={() => { void query.refetch() }}>Retry</button>
      </div>}
      {page && !query.isError && page.total === 0 && <p className="py-3 text-sm text-gray-500">No open recommendations on other orders.</p>}
      {!!page?.items.length && <ul className="mt-3 divide-y divide-gray-100">
        {page.items.map((item) => <li key={item.id} className="flex flex-wrap items-start justify-between gap-2 py-3 first:pt-0">
          <div className="min-w-0 flex-1 basis-48">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
              <span className={`rounded px-1.5 py-0.5 font-medium capitalize ${priorities[item.priority]}`}>{item.priority}</span>
              <time dateTime={item.created_at} className="text-gray-500">Recorded {format(new Date(item.created_at), 'MMM d, yyyy')}</time>
            </div>
            <p className="break-words text-sm text-gray-900">{item.description}</p>
          </div>
          <Link to={`/dashboard/repair-orders?selected=${item.source_order.id}`}
            aria-label={`Open source order ${item.source_order.order_number}`}
            className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-gray-200 px-2 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50">
            {item.source_order.order_number}<ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </li>)}
      </ul>}
      {(skip > 0 || (page && page.total > PAGE_SIZE)) && <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3">
        <span className="text-xs text-gray-500">
          {page ? `${page.items.length ? skip + 1 : 0}–${Math.min(skip + page.items.length, page.total)} of ${page.total}` : `Page ${Math.floor(skip / PAGE_SIZE) + 1}`}
        </span>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))} disabled={skip === 0}
            className="inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-1 text-xs disabled:opacity-40">
            <ChevronLeft className="h-3.5 w-3.5" /> Previous
          </button>
          <button type="button" onClick={() => setSkip(skip + PAGE_SIZE)} disabled={!page || skip + PAGE_SIZE >= page.total || query.isFetching}
            className="inline-flex items-center gap-1 whitespace-nowrap rounded-md border px-2 py-1 text-xs disabled:opacity-40">
            Next <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>}
    </section>
  )
}
