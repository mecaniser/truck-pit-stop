import type { PartsUsage, RepairOrderHistoryEvent } from '../../types'

const PART_UNIT_LABELS: Record<string, string> = {
  each: 'ea',
  gallon: 'gal',
  quart: 'qt',
  liter: 'L',
}

export function buildPartHistoryEvents(parts: PartsUsage[], historyEvents: RepairOrderHistoryEvent[] = []) {
  const persistedPartIds = new Set(
    historyEvents.map((event) => event.entity_id).filter((entityId): entityId is string => !!entityId),
  )
  const persisted = historyEvents.map((event) => ({
    id: event.id,
    label: event.label,
    at: event.created_at,
    detail: event.detail || undefined,
    actor: event.actor_name || undefined,
    entityId: event.entity_id || undefined,
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
