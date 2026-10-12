import { z } from 'zod'

const linkedOrder = z.object({ id: z.string().uuid(), order_number: z.string(), available: z.boolean() })
export const conversionSchema = z.object({
  id: z.string().uuid(), recommendation_id: z.string().uuid(),
  source_order: linkedOrder, source_description: z.string(),
  target_order: linkedOrder.extend({ status: z.string() }),
  labor_id: z.string().uuid(),
  state: z.enum(['active', 'operation_removed', 'target_cancelled', 'target_deleted', 'superseded']),
  created_at: z.string().datetime({ offset: true }), can_replace: z.boolean(), can_resolve: z.boolean(),
})
export type RecommendationConversion = z.infer<typeof conversionSchema>

/** Keep the Shop Work queue when following either end of a recommendation. */
export function recommendationLink(pathname: string, search: string, orderId: string, focus: { operation?: string; recommendation?: string }) {
  const params = new URLSearchParams(search)
  params.set('selected', orderId)
  for (const key of ['customer', 'operation', 'recommendation']) params.delete(key)
  for (const [key, value] of Object.entries(focus)) if (value) params.set(key, value)
  const route = pathname === '/dashboard' ? pathname : '/dashboard/repair-orders'
  return `${route}?${params.toString()}`
}

export function conversionHours(text: string): number | null {
  const clock = text.trim().match(/^(\d+):([0-5]\d)$/)
  const value = clock ? Number((Number(clock[1]) + Number(clock[2]) / 60).toFixed(2))
    : /^\d+(?:\.\d{1,2})?$/.test(text.trim()) ? Number(text) : NaN
  return Number.isFinite(value) && value >= 0.01 && value <= 999.99 ? value : null
}

/** Server money uses Decimal half-even; calculate in integer hundredths/cents. */
export function conversionTotal(hours: number, rate: number): number {
  const hundredthsOfCents = Math.round(hours * 100) * Math.round(rate * 100)
  const cents = Math.floor(hundredthsOfCents / 100)
  const remainder = hundredthsOfCents % 100
  return (cents + (remainder > 50 || (remainder === 50 && cents % 2 === 1) ? 1 : 0)) / 100
}

export function recommendationErrorMessage(failure: unknown, fallback: string): string {
  const detail = (failure as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message
  return fallback
}

/** Reveal within the workspace, without scrolling outer shells beneath mobile nav. */
export function revealWorkspaceContent(element: HTMLElement) {
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    if (['auto', 'scroll'].includes(getComputedStyle(parent).overflowY) && parent.scrollHeight > parent.clientHeight) {
      parent.scrollTo?.({ top: parent.scrollTop + element.getBoundingClientRect().top - parent.getBoundingClientRect().top - 8 })
      return
    }
  }
}
