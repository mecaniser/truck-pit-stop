import type { QueryClient } from '@tanstack/react-query'

export const checklistKeys = {
  template: (tenantId: string, serviceId: string) => ['service-checklist-template', tenantId, serviceId] as const,
  order: (tenantId: string, orderId: string) => ['order-checklist', tenantId, orderId] as const,
}
export const checklistOpenEvent = 'dieselbridge:open-checklist'
export function errorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}
export function isConflict(error: unknown): boolean {
  return (error as { response?: { status?: number } })?.response?.status === 409
}
export async function invalidateOrderChecklist(client: QueryClient, tenantId: string, orderId: string) {
  await Promise.all([
    client.invalidateQueries({ queryKey: checklistKeys.order(tenantId, orderId) }),
    client.invalidateQueries({ queryKey: ['repair-order-detail', orderId] }),
    client.invalidateQueries({ queryKey: ['mechanic-job-detail', orderId] }),
    client.invalidateQueries({ queryKey: ['fleet-ro-detail', orderId] }),
  ])
}
/** Completion remains server-authoritative. Call only from a rejected completion. */
export function openChecklistOnCompletionError(error: unknown, orderId: string): boolean {
  if (!isConflict(error) || !errorDetail(error, '').includes('required checklist tasks')) return false
  window.dispatchEvent(new CustomEvent(checklistOpenEvent, { detail: { orderId } }))
  return true
}
