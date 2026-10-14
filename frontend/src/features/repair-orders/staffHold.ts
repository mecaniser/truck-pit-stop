import { z } from 'zod'
import type { RepairOrder } from '@/types'
import { holdReasonLabel } from './holdReason'

export type WorkHoldOrder = Pick<RepairOrder, 'id' | 'order_number' | 'status' | 'updated_at' | 'hold_reason' | 'held_at' | 'is_internal' | 'is_fleet_work'>

export function canManageWorkHold(role: string | undefined, order: WorkHoldOrder) {
  return order.status === 'in_progress' && !!order.updated_at && (
    ['garage_owner', 'garage_admin', 'receptionist'].includes(role ?? '')
    || (role === 'fleet_manager' && (order.is_internal || order.is_fleet_work))
  )
}

export const staffHoldResultSchema = z.object({
  id: z.string(), status: z.literal('in_progress'), hold_reason: z.string().nullable(),
  held_at: z.string().nullable(), updated_at: z.string().datetime({ offset: true }),
  stopped_sessions_count: z.number().int().nonnegative(),
})

export function staffHoldHistoryDetail(eventType: string, detail?: string | null) {
  if (!detail) return undefined
  try {
    const payload = JSON.parse(detail)
    const reason = eventType === 'work_hold_released' ? payload.previous?.hold_reason : payload.current?.hold_reason
    return typeof reason === 'string' && reason.trim() ? holdReasonLabel(reason) : undefined
  } catch { return undefined }
}

