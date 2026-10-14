import type { PartsUsage, RepairOrderHistoryEvent } from '../../types'
import { staffHoldHistoryDetail } from './staffHold'

const PART_UNIT_LABELS: Record<string, string> = {
  each: 'ea',
  gallon: 'gal',
  quart: 'qt',
  liter: 'L',
}

const OPERATION_EVENTS = new Set([
  'operation_assigned', 'operation_completed', 'operation_reopened', 'operation_scope_removed',
])

export function repairOrderHistoryDetail(event: RepairOrderHistoryEvent): string | undefined {
  if (['work_held', 'work_hold_released'].includes(event.event_type)) {
    return staffHoldHistoryDetail(event.event_type, event.detail)
  }
  if (!OPERATION_EVENTS.has(event.event_type)) return event.detail || undefined
  // Legacy execution events append internal snapshots to the recorded operation
  // description. Keep the historical description, never infer past assignees
  // from today's roster or expose implementation fields as operator copy.
  const detail = event.detail?.trim()
  if (!detail) return undefined
  const boundary = detail.lastIndexOf('; before: technician=')
  if (boundary >= 0) return detail.slice(0, boundary).trim() || undefined
  if (/\b(?:technician|version|completed_by|completed_at)=|; (?:before|after):/.test(detail)) return undefined
  return detail
}

export function buildPartHistoryEvents(parts: PartsUsage[], historyEvents: RepairOrderHistoryEvent[] = []) {
  const persistedPartIds = new Set(
    historyEvents.map((event) => event.entity_id).filter((entityId): entityId is string => !!entityId),
  )
  const persisted = historyEvents.map((event) => ({
    id: event.id,
    label: event.label,
    at: event.created_at,
    detail: repairOrderHistoryDetail(event),
    actor: event.actor_name || undefined,
    ...(event.entity_id ? { entityId: event.entity_id } : {}),
  }))
  const fallback = parts.map((part) => ({
    id: `part-${part.id}`,
    label: part.stock_shortage_override ? 'Part added with stock override' : 'Part added to repair order',
    at: part.created_at,
    detail: `${part.inventory_name} · ${part.quantity} ${PART_UNIT_LABELS[part.unit_type] || part.unit_type}`,
    entityId: part.id,
  }))
  return [
    ...persisted,
    ...fallback.filter((event) => !persistedPartIds.has(event.entityId)),
  ]
}
