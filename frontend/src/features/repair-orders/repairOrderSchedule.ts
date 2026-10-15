import { z } from 'zod'

export type OrderScheduleSummary = {
  scheduled_start_at?: string | null
  promised_finish_at?: string | null
  schedule_timezone?: string | null
  is_overdue?: boolean
}

export const scheduleSchema = z.object({
  id: z.string(), timezone: z.string(),
  scheduled_start_at: z.string().nullable(), promised_finish_at: z.string().nullable(),
  scheduled_start_local: z.string().nullable(), promised_finish_local: z.string().nullable(),
  scheduled_start_fold: z.union([z.literal(0), z.literal(1)]).nullable(),
  promised_finish_fold: z.union([z.literal(0), z.literal(1)]).nullable(),
  updated_at: z.string(), is_overdue: z.boolean(), can_edit: z.boolean(),
})
export type OrderSchedule = z.infer<typeof scheduleSchema>
export type ScheduleField = 'scheduled_start_local' | 'promised_finish_local'
export type ScheduleChoice = { fold: 0 | 1; utc_offset: string; utc?: string }
export const scheduleLabels: Record<ScheduleField, string> = { scheduled_start_local: 'Start', promised_finish_local: 'Promised finish' }

/** Never substitute the browser zone for the shop zone. */
export function formatScheduleDate(value?: string | null, timezone?: string | null): string | null {
  if (!value || !timezone) return null
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: timezone, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }).format(new Date(value))
  } catch { return null }
}
export function scheduleDeadline(order: OrderScheduleSummary): string | null {
  const date = formatScheduleDate(order.promised_finish_at, order.schedule_timezone)
  return date ? `${order.is_overdue ? 'Overdue' : 'Due'} · ${date}` : null
}
export function overdueSearchParams(current: URLSearchParams, enabled: boolean): URLSearchParams {
  const next = new URLSearchParams(current)
  if (enabled) { next.set('overdue', 'true'); next.delete('queue') }
  else next.delete('overdue')
  return next
}

export function scheduleRefreshInterval(rows: OrderScheduleSummary[], overdueFilter = false): number | false {
  return overdueFilter || rows.some(row => !!row.promised_finish_at) ? 60_000 : false
}
