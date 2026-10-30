import { useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

export type ActivityEvent = {
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

export type ActivityFeedResponse = {
  items: ActivityEvent[]
  next_cursor: string | null
  has_more: boolean
  available_actors: ActivityActor[]
  warnings: string[]
}

export type ActivityFilters = { actor_id?: string; event_type?: string; date_from?: string; date_to?: string }

export function useActivityFeed(filters: ActivityFilters = {}) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const allowed = !!user?.is_active && ['garage_owner', 'garage_admin', 'receptionist'].includes(user.role)
  return useQuery<ActivityFeedResponse>({
    queryKey: ['activity-feed', user?.tenant_id, user?.id, user?.role, epoch,
      filters.actor_id || '', filters.event_type || '', filters.date_from || '', filters.date_to || ''],
    queryFn: async ({ signal }) => (await api.get<ActivityFeedResponse>('/activity', { params: { limit: 20, ...filters }, signal })).data,
    enabled: allowed,
    staleTime: 30_000,
    retry: (count, error) => !(isAxiosError(error) && [401, 403, 429].includes(error.response?.status || 0)) && count < 1,
  })
}

/** The endpoint returns a page, not a total or an unread count. */
export function activityCountLabel(data: ActivityFeedResponse | undefined, isError: boolean): string | null {
  return !data || isError ? null : `${data.items.length}${data.has_more ? '+' : ''}`
}
