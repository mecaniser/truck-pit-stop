import { useEffect } from 'react'
import { useQuery, type QueryClient } from '@tanstack/react-query'
import { z } from 'zod'
import api from '@/lib/api'
import { useAuthStore } from '@/stores/authStore'

const count = z.number().int().nonnegative()
export const operationSchema = z.object({
  labor_id: z.string().min(1), description: z.string(), mechanic_id: z.string().nullable(), mechanic_name: z.string().nullable(),
  status: z.enum(['pending', 'completed']).nullable(), version: count,
  completed_at: z.string().nullable(), completed_by: z.object({ id: z.string().nullable(), name: z.string().nullable() }).nullable(),
  tracked_seconds: z.number().nonnegative().nullable(),
  active_session: z.object({ id: z.string(), mechanic_id: z.string(), mechanic_name: z.string(), started_at: z.string() }).nullable(),
  required_tasks_remaining: count, can_assign: z.boolean(), can_complete: z.boolean(), can_reopen: z.boolean(), can_start_timer: z.boolean(), can_stop_timer: z.boolean(),
})
export const operationPageSchema = z.object({
  items: z.array(operationSchema), summary: z.object({ tracked: count, completed: count, remaining: count, legacy_untracked: count }),
  order_status: z.string(), is_order_lead: z.boolean(),
}).refine(page => page.summary.completed + page.summary.remaining === page.summary.tracked, 'Invalid operation summary')
export type OperationExecution = z.infer<typeof operationSchema>
export type OperationPage = z.infer<typeof operationPageSchema>
export const operationKeys = { order: (tenantId: string, orderId: string) => ['order-operations', tenantId, orderId] as const }
const internalRoles = ['garage_owner', 'garage_admin', 'receptionist', 'mechanic', 'fleet_manager']

export function useOperationExecution(orderId: string, refreshToken?: unknown, enabled = true) {
  const user = useAuthStore(state => state.user)
  const epoch = useAuthStore(state => state.authSessionEpoch)
  const allowed = Boolean(user?.tenant_id && internalRoles.includes(user.role) && enabled && orderId)
  const query = useQuery({
    queryKey: [...operationKeys.order(user?.tenant_id ?? '', orderId), user?.id, user?.role, epoch],
    queryFn: async ({ signal }) => operationPageSchema.parse((await api.get(`/repair-orders/${orderId}/operations`, { signal })).data),
    enabled: allowed,
    staleTime: 0,
    refetchInterval: state => state.state.data?.items.some(item => item.active_session) ? 15000 : false,
  })
  const refetch = query.refetch
  useEffect(() => { if (allowed) void refetch() }, [allowed, refreshToken, refetch])
  return { ...query, allowed }
}

export async function invalidateOperationExecution(client: QueryClient, tenantId: string, orderId: string) {
  await Promise.all([
    operationKeys.order(tenantId, orderId), ['order-checklist', tenantId, orderId],
    ['repair-order-detail', orderId], ['repair-order-workspace', orderId], ['price-build', orderId], ['fleet-ro-detail', orderId],
    ['repair-orders'], ['mechanic-job-detail'], ['mechanic-jobs'], ['mechanic-day-summary'],
    ['mechanic-board-team'], ['mechanic-board-detail'], ['dashboard-action-queue'], ['activity-feed'],
  ].map(queryKey => client.invalidateQueries({ queryKey })))
}
